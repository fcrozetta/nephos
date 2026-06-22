from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Protocol

import yaml

from nephos_api.catalog import AppManifest
from nephos_api.kubernetes_runtime import ResourceType
from nephos_api.provisioning import BindingProvisioner, BindingProvisioningContext
from nephos_api.repository import DesiredStateRepository
from nephos_api.runtime_errors import RuntimeBlockedError


class RuntimeAdapter(Protocol):
    def ensure_namespace(self, resource_type: ResourceType, slug: str) -> object: ...

    def delete_namespace_if_owned(
        self,
        resource_type: ResourceType,
        slug: str,
    ) -> bool: ...

    def ensure_binding_secret(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
        values: dict[str, str],
    ) -> object: ...

    def delete_binding_secret_if_owned(
        self,
        *,
        app_slug: str,
        service_slug: str,
        alias: str,
        capability: str,
        protocol: str | None = None,
    ) -> bool: ...

    def scale_workloads(
        self,
        resource_type: ResourceType,
        slug: str,
        replicas: int,
    ) -> object: ...

    def ensure_app_ingresses(
        self,
        *,
        app_slug: str,
        routes: list[dict[str, object]],
        domains: list[dict[str, object]],
    ) -> object: ...

    def delete_app_ingresses(
        self,
        *,
        app_slug: str,
        routes: list[dict[str, object]],
    ) -> object: ...


class RuntimeDeployer(Protocol):
    def deploy(self, *, target_type: str, slug: str) -> None: ...

    def uninstall(self, *, target_type: str, slug: str) -> None: ...


class Reconciler:
    def __init__(
        self,
        repository: DesiredStateRepository,
        *,
        runtime: RuntimeAdapter | None = None,
        provisioner: BindingProvisioner | None = None,
        deployer: RuntimeDeployer | None = None,
    ) -> None:
        self._repository = repository
        self._runtime = runtime
        self._provisioner = provisioner
        self._deployer = deployer

    def run_once(self) -> int:
        request = self._repository.claim_next_reconciliation_request()
        if request is None:
            return 0

        try:
            if self._reconcile_desired_lifecycle_request(request):
                return 1
            if self._reconcile_namespace_request(request):
                return 1
            if self._reconcile_namespace_stop_request(request):
                return 1
            if self._reconcile_namespace_remove_request(request):
                return 1
            if self._reconcile_namespace_destroy_request(request):
                return 1
            if self._reconcile_platform_domain_request(request):
                return 1
            if self._reconcile_binding_request(request):
                return 1
        except RuntimeBlockedError as exc:
            self._mark_blocked(request, reason=exc.reason, message=str(exc))
            return 1
        except Exception as exc:
            self._mark_failed(request, message=str(exc))
            return 1

        message = (
            "No runtime handler is implemented for "
            f"{request['target_type']} {request['action']}."
        )
        with self._repository.transaction() as tx:
            tx.update_reconciliation_request_state(
                request_id=str(request["id"]),
                state="blocked",
                error=message,
            )
            tx.upsert_status_snapshot(
                resource_type=str(request["target_type"]),
                resource_id=str(request["target_id"]),
                level="blocked",
                lifecycle=self._status_lifecycle(request),
                reconciliation="blocked",
                reason="runtime_handler_missing",
                message=message,
                evidence=[
                    {
                        "source": "nephos-api",
                        "subject": str(request["id"]),
                        "reason": "runtime_handler_missing",
                        "message": message,
                    }
                ],
                observed_generation=int(request["target_generation"]),
            )
        return 1

    def _reconcile_desired_lifecycle_request(
        self,
        request: dict[str, object],
    ) -> bool:
        target_type = str(request["target_type"])
        action = str(request["action"])
        if (
            self._runtime is None
            or target_type not in {"app_instance", "service_instance"}
            or action != "reconcile"
        ):
            return False

        row = self._target_row(request)
        if row.get("delete_requested_at") is not None:
            return self._reconcile_namespace_destroy_request(
                _request_with_action(request, "destroy")
            )

        lifecycle = str(row["lifecycle"])
        if lifecycle == "running":
            return False
        if lifecycle == "stopped":
            if target_type == "app_instance":
                return self._reconcile_stopped_app_request(request)
            return self._reconcile_namespace_stop_request(
                _request_with_action(request, "stop")
            )
        if lifecycle == "removed":
            if self._deployer is None:
                message = (
                    "No runtime handler is implemented for "
                    f"{target_type} remove."
                )
                self._mark_blocked(
                    request,
                    reason="runtime_handler_missing",
                    message=message,
                )
                return True
            return self._reconcile_namespace_remove_request(
                _request_with_action(request, "remove")
            )
        raise ValueError(f"unsupported lifecycle state {lifecycle}")

    def _target_row(self, request: dict[str, object]) -> dict[str, object]:
        target_type = str(request["target_type"])
        slug = _target_slug(request)
        if target_type == "app_instance":
            row = self._repository.get_app_row(slug)
            if row is None:
                raise RuntimeBlockedError(
                    reason="app_not_found",
                    message="App desired state was not found.",
                )
            return row
        if target_type == "service_instance":
            row = self._repository.get_service_row(slug)
            if row is None:
                raise RuntimeBlockedError(
                    reason="service_not_found",
                    message="Service desired state was not found.",
                )
            return row
        raise ValueError(f"unsupported target type {target_type}")

    def _reconcile_stopped_app_request(self, request: dict[str, object]) -> bool:
        assert self._runtime is not None
        slug = _target_slug(request)
        app_routes = self._app_routes(slug)
        if app_routes:
            app_domains = self._platform_domains_for_ingress()
            if not app_domains:
                raise RuntimeBlockedError(
                    reason="platform_root_domain_missing",
                    message="App routes require a platform root domain.",
                )
            self._runtime.ensure_app_ingresses(
                app_slug=slug,
                routes=app_routes,
                domains=app_domains,
            )
        return self._reconcile_namespace_stop_request(
            _request_with_action(request, "stop")
        )

    def _reconcile_namespace_request(self, request: dict[str, object]) -> bool:
        target_type = str(request["target_type"])
        action = str(request["action"])
        if (
            self._runtime is None
            or target_type not in {"app_instance", "service_instance"}
            or action not in {"install", "start", "reconcile"}
        ):
            return False

        slug = _target_slug(request)
        app_routes: list[dict[str, object]] = []
        app_domains: list[dict[str, object]] = []
        if target_type == "app_instance":
            app_routes = self._app_routes(slug)
            app_domains = self._platform_domains_for_ingress()
            if app_routes and not app_domains:
                raise RuntimeBlockedError(
                    reason="platform_root_domain_missing",
                    message="App routes require a platform root domain.",
                )
        self._runtime.ensure_namespace(_resource_type(target_type), slug)
        reason = "runtime_namespace_ready"
        message = "Kubernetes namespace is present and owned by Nephos."
        if self._deployer is not None:
            self._deployer.deploy(target_type=target_type, slug=slug)
            reason = "runtime_deployed"
            message = "Runtime deployment is present and owned by Nephos."
        dependent_bindings = (
            self._dependent_bindings_for_service(str(request["target_id"]))
            if target_type == "service_instance" and reason == "runtime_deployed"
            else []
        )
        if target_type == "app_instance" and app_routes:
            self._runtime.ensure_app_ingresses(
                app_slug=slug,
                routes=app_routes,
                domains=app_domains,
            )
        with self._repository.transaction() as tx:
            for binding in dependent_bindings:
                tx.create_reconciliation_request_if_not_active(
                    target_type="binding",
                    target_id=str(binding["id"]),
                    target_generation=int(binding["generation"]),
                    action="reconcile",
                    target_snapshot={
                        "id": str(binding["id"]),
                        "alias": str(binding["alias"]),
                    },
                )
            tx.update_reconciliation_request_state(
                request_id=str(request["id"]),
                state="succeeded",
            )
            tx.upsert_status_snapshot(
                resource_type=target_type,
                resource_id=str(request["target_id"]),
                level="healthy",
                lifecycle=self._status_lifecycle(request),
                reconciliation="succeeded",
                reason=reason,
                message=message,
                evidence=[
                    {
                        "source": "nephos-api",
                        "subject": str(request["id"]),
                        "reason": reason,
                        "message": message,
                    }
                ],
                observed_generation=int(request["target_generation"]),
            )
        return True

    def _dependent_bindings_for_service(
        self,
        service_instance_id: str,
    ) -> list[dict[str, object]]:
        bindings: list[dict[str, object]] = []
        for dependent in self._repository.list_dependents_for_service(
            service_instance_id,
        ):
            if (
                dependent["app_lifecycle"] == "removed"
                or dependent["app_delete_requested_at"] is not None
            ):
                continue
            binding = self._repository.get_binding_row(str(dependent["binding_id"]))
            if binding is not None:
                binding["app_lifecycle"] = dependent["app_lifecycle"]
                bindings.append(binding)
        return bindings

    def _reconcile_namespace_stop_request(self, request: dict[str, object]) -> bool:
        target_type = str(request["target_type"])
        action = str(request["action"])
        if (
            self._runtime is None
            or target_type not in {"app_instance", "service_instance"}
            or action != "stop"
        ):
            return False

        slug = _target_slug(request)
        self._runtime.scale_workloads(_resource_type(target_type), slug, 0)
        message = "Runtime workloads are scaled to zero."
        with self._repository.transaction() as tx:
            tx.update_reconciliation_request_state(
                request_id=str(request["id"]),
                state="succeeded",
            )
            tx.upsert_status_snapshot(
                resource_type=target_type,
                resource_id=str(request["target_id"]),
                level="stopped",
                lifecycle=self._status_lifecycle(request),
                reconciliation="succeeded",
                reason="runtime_stopped",
                message=message,
                evidence=[
                    {
                        "source": "nephos-api",
                        "subject": str(request["id"]),
                        "reason": "runtime_stopped",
                        "message": message,
                    }
                ],
                observed_generation=int(request["target_generation"]),
            )
        return True

    def _reconcile_namespace_remove_request(self, request: dict[str, object]) -> bool:
        target_type = str(request["target_type"])
        action = str(request["action"])
        if (
            self._runtime is None
            or self._deployer is None
            or target_type not in {"app_instance", "service_instance"}
            or action != "remove"
        ):
            return False

        slug = _target_slug(request)
        if target_type == "app_instance":
            self._delete_app_ingresses(slug)
        self._deployer.uninstall(target_type=target_type, slug=slug)
        message = "Runtime deployment is removed while desired state is preserved."
        with self._repository.transaction() as tx:
            tx.update_reconciliation_request_state(
                request_id=str(request["id"]),
                state="succeeded",
            )
            tx.upsert_status_snapshot(
                resource_type=target_type,
                resource_id=str(request["target_id"]),
                level="not_applicable",
                lifecycle=self._status_lifecycle(request),
                reconciliation="succeeded",
                reason="runtime_removed",
                message=message,
                evidence=[
                    {
                        "source": "nephos-api",
                        "subject": str(request["id"]),
                        "reason": "runtime_removed",
                        "message": message,
                    }
                ],
                observed_generation=int(request["target_generation"]),
            )
        return True

    def _reconcile_namespace_destroy_request(
        self,
        request: dict[str, object],
    ) -> bool:
        target_type = str(request["target_type"])
        action = str(request["action"])
        if (
            self._runtime is None
            or target_type not in {"app_instance", "service_instance"}
            or action != "destroy"
        ):
            return False

        slug = _target_slug(request)
        if target_type == "app_instance":
            self._delete_app_ingresses(slug)
        service_dependent_bindings: list[dict[str, object]] = []
        if target_type == "service_instance":
            service_dependent_bindings = self._cleanup_service_dependent_bindings(
                service_instance_id=str(request["target_id"]),
            )
        if self._deployer is not None:
            self._deployer.uninstall(target_type=target_type, slug=slug)
        if target_type == "app_instance":
            self._deprovision_app_bindings(
                app_instance_id=str(request["target_id"]),
            )
        self._runtime.delete_namespace_if_owned(_resource_type(target_type), slug)
        message = "Kubernetes namespace teardown completed."
        with self._repository.transaction() as tx:
            for binding in service_dependent_bindings:
                tx.create_reconciliation_request_if_not_active(
                    target_type="app_instance",
                    target_id=str(binding["app_instance_id"]),
                    target_generation=int(str(binding["app_instance_generation"])),
                    action="reconcile",
                    target_snapshot={"slug": str(binding["app_instance_slug"])},
                )
                tx.upsert_status_snapshot(
                    resource_type="app_instance",
                    resource_id=str(binding["app_instance_id"]),
                    level="blocked",
                    lifecycle=str(binding.get("app_lifecycle", "running")),
                    reconciliation="blocked",
                    reason="binding_provider_destroyed",
                    message=(
                        "A bound Service was destroyed; App reconciliation is "
                        "queued to remove stale binding data."
                    ),
                    evidence=[
                        {
                            "source": "nephos-api",
                            "subject": str(request["id"]),
                            "reason": "binding_provider_destroyed",
                            "message": (
                                "Bound Service was destroyed during forced "
                                "Service teardown."
                            ),
                            "bindingAlias": str(binding["alias"]),
                            "serviceSlug": str(binding["service_instance_slug"]),
                        }
                    ],
                    observed_generation=int(str(binding["app_instance_generation"])),
                )
            tx.update_reconciliation_request_state(
                request_id=str(request["id"]),
                state="succeeded",
            )
            tx.upsert_status_snapshot(
                resource_type=target_type,
                resource_id=str(request["target_id"]),
                level="not_applicable",
                lifecycle=self._status_lifecycle(request),
                reconciliation="succeeded",
                reason="runtime_namespace_destroyed",
                message=message,
                evidence=[
                    {
                        "source": "nephos-api",
                        "subject": str(request["id"]),
                        "reason": "runtime_namespace_destroyed",
                        "message": message,
                    }
                ],
                observed_generation=int(request["target_generation"]),
            )
            if target_type == "app_instance":
                tx.delete_app_instance(instance_id=str(request["target_id"]))
            else:
                tx.delete_service_instance(instance_id=str(request["target_id"]))
        return True

    def _app_routes(self, slug: str) -> list[dict[str, object]]:
        row = self._repository.get_app_row(slug)
        if row is None:
            raise RuntimeBlockedError(
                reason="app_not_found",
                message="App desired state was not found.",
            )
        manifest = _app_manifest_from_row(row)
        return [
            {
                "name": route.name,
                "visibility": route.visibility,
                "target": {"port": route.target.port},
            }
            for route in manifest.spec.routes
        ]

    def _platform_domains_for_ingress(self) -> list[dict[str, object]]:
        return [
            {
                "id": domain.id,
                "name": domain.name,
                "domain": domain.domain,
                "default": domain.is_default,
            }
            for domain in self._repository.list_platform_domains()
        ]

    def _delete_app_ingresses(self, slug: str) -> None:
        assert self._runtime is not None
        routes = self._app_routes(slug)
        if not routes:
            return
        self._runtime.delete_app_ingresses(app_slug=slug, routes=routes)

    def _deprovision_app_bindings(self, *, app_instance_id: str) -> None:
        if self._provisioner is None:
            return
        deprovision = getattr(self._provisioner, "deprovision_binding", None)
        if deprovision is None:
            return
        for binding in self._repository.list_bindings_for_app(app_instance_id):
            deprovision(
                BindingProvisioningContext(
                    binding_id=str(binding["id"]),
                    app_slug=str(binding["app_instance_slug"]),
                    service_slug=str(binding["service_instance_slug"]),
                    alias=str(binding["alias"]),
                    capability=str(binding["capability"]),
                    protocol=_optional_str(binding["protocol"]),
                )
            )

    def _cleanup_service_dependent_bindings(
        self,
        *,
        service_instance_id: str,
    ) -> list[dict[str, object]]:
        assert self._runtime is not None
        bindings = self._dependent_bindings_for_service(service_instance_id)
        deprovision = (
            getattr(self._provisioner, "deprovision_binding", None)
            if self._provisioner is not None
            else None
        )
        for binding in bindings:
            context = BindingProvisioningContext(
                binding_id=str(binding["id"]),
                app_slug=str(binding["app_instance_slug"]),
                service_slug=str(binding["service_instance_slug"]),
                alias=str(binding["alias"]),
                capability=str(binding["capability"]),
                protocol=_optional_str(binding["protocol"]),
            )
            if deprovision is not None:
                # Force-destroy tears down the whole Service namespace next. If
                # the Service runtime/admin Secret/pod is already gone,
                # provider cleanup cannot run but App-side binding cleanup and
                # Service teardown must still proceed.
                with suppress(Exception):
                    deprovision(context)
            self._runtime.delete_binding_secret_if_owned(
                app_slug=context.app_slug,
                service_slug=context.service_slug,
                alias=context.alias,
                capability=context.capability,
                protocol=context.protocol,
            )
        return bindings

    def _reconcile_platform_domain_request(self, request: dict[str, object]) -> bool:
        target_type = str(request["target_type"])
        action = str(request["action"])
        if target_type != "platform_domain" or action not in {
            "create",
            "set-default",
            "remove",
            "reconcile",
        }:
            return False

        routed_apps = [
            row
            for row in self._repository.list_app_rows()
            if _app_row_should_reconcile_routes(row)
        ]
        message = (
            "Platform domain desired state is recorded; "
            "App route reconciliation is queued."
        )
        with self._repository.transaction() as tx:
            for app in routed_apps:
                tx.create_reconciliation_request(
                    target_type="app_instance",
                    target_id=str(app["id"]),
                    target_generation=int(app["generation"]),
                    action="reconcile",
                    target_snapshot={"slug": str(app["slug"])},
                )
            tx.update_reconciliation_request_state(
                request_id=str(request["id"]),
                state="succeeded",
            )
            tx.upsert_status_snapshot(
                resource_type="platform_domain",
                resource_id=str(request["target_id"]),
                level="healthy",
                lifecycle=self._status_lifecycle(request),
                reconciliation="succeeded",
                reason="platform_domain_reconciled",
                message=message,
                evidence=[
                    {
                        "source": "nephos-api",
                        "subject": str(request["id"]),
                        "reason": "platform_domain_reconciled",
                        "message": message,
                        "enqueuedAppReconciliations": len(routed_apps),
                    }
                ],
                observed_generation=int(request["target_generation"]),
            )
        return True

    def _reconcile_binding_request(self, request: dict[str, object]) -> bool:
        target_type = str(request["target_type"])
        action = str(request["action"])
        if self._runtime is None or target_type != "binding" or action != "reconcile":
            return False

        binding = self._repository.get_binding_row(str(request["target_id"]))
        if binding is None:
            self._mark_blocked(
                request,
                reason="binding_not_found",
                message="Binding desired state was not found.",
            )
            return True

        app = self._repository.get_app_row(str(binding["app_instance_slug"]))
        if (
            app is None
            or app["lifecycle"] == "removed"
            or app["delete_requested_at"] is not None
        ):
            self._mark_not_applicable(
                request,
                reason="binding_consumer_inactive",
                message="Binding consumer App is not active.",
            )
            return True

        values = _binding_output_values(binding)
        if values is None and self._provisioner is not None:
            values = self._provisioner.provision_binding(
                BindingProvisioningContext(
                    binding_id=str(binding["id"]),
                    app_slug=str(binding["app_instance_slug"]),
                    service_slug=str(binding["service_instance_slug"]),
                    alias=str(binding["alias"]),
                    capability=str(binding["capability"]),
                    protocol=_optional_str(binding["protocol"]),
                )
            )
        if values is None:
            self._mark_blocked(
                request,
                reason="binding_output_unavailable",
                message="Binding output values are not available.",
            )
            return True

        self._runtime.ensure_namespace(
            "app_instance",
            str(binding["app_instance_slug"]),
        )
        self._runtime.ensure_binding_secret(
            app_slug=str(binding["app_instance_slug"]),
            service_slug=str(binding["service_instance_slug"]),
            alias=str(binding["alias"]),
            capability=str(binding["capability"]),
            protocol=_optional_str(binding["protocol"]),
            values=values,
        )
        message = "Binding Secret is present and owned by Nephos."
        with self._repository.transaction() as tx:
            tx.update_binding_output_summary(
                binding_id=str(binding["id"]),
                output_summary=_redacted_binding_output_summary(
                    app_slug=str(binding["app_instance_slug"]),
                    alias=str(binding["alias"]),
                    capability=str(binding["capability"]),
                    protocol=_optional_str(binding["protocol"]),
                    values=values,
                ),
            )
            tx.update_reconciliation_request_state(
                request_id=str(request["id"]),
                state="succeeded",
            )
            tx.upsert_status_snapshot(
                resource_type="binding",
                resource_id=str(request["target_id"]),
                level="healthy",
                lifecycle=self._status_lifecycle(request),
                reconciliation="succeeded",
                reason="binding_secret_ready",
                message=message,
                evidence=[
                    {
                        "source": "nephos-api",
                        "subject": str(request["id"]),
                        "reason": "binding_secret_ready",
                        "message": message,
                    }
                ],
                observed_generation=int(request["target_generation"]),
            )
            tx.create_reconciliation_request(
                target_type="app_instance",
                target_id=str(binding["app_instance_id"]),
                target_generation=int(binding["app_instance_generation"]),
                action="reconcile",
                target_snapshot={"slug": str(binding["app_instance_slug"])},
            )
        return True

    def _mark_failed(self, request: dict[str, object], *, message: str) -> None:
        with self._repository.transaction() as tx:
            tx.update_reconciliation_request_state(
                request_id=str(request["id"]),
                state="failed",
                error=message,
            )
            tx.upsert_status_snapshot(
                resource_type=str(request["target_type"]),
                resource_id=str(request["target_id"]),
                level="degraded",
                lifecycle=self._status_lifecycle(request),
                reconciliation="failed",
                reason="runtime_error",
                message=message,
                evidence=[
                    {
                        "source": "nephos-api",
                        "subject": str(request["id"]),
                        "reason": "runtime_error",
                        "message": message,
                    }
                ],
                observed_generation=int(request["target_generation"]),
            )

    def _mark_not_applicable(
        self,
        request: dict[str, object],
        *,
        reason: str,
        message: str,
    ) -> None:
        with self._repository.transaction() as tx:
            tx.update_reconciliation_request_state(
                request_id=str(request["id"]),
                state="succeeded",
            )
            tx.upsert_status_snapshot(
                resource_type=str(request["target_type"]),
                resource_id=str(request["target_id"]),
                level="not_applicable",
                lifecycle=self._status_lifecycle(request),
                reconciliation="succeeded",
                reason=reason,
                message=message,
                evidence=[
                    {
                        "source": "nephos-api",
                        "subject": str(request["id"]),
                        "reason": reason,
                        "message": message,
                    }
                ],
                observed_generation=int(request["target_generation"]),
            )

    def _mark_blocked(
        self,
        request: dict[str, object],
        *,
        reason: str,
        message: str,
    ) -> None:
        with self._repository.transaction() as tx:
            tx.update_reconciliation_request_state(
                request_id=str(request["id"]),
                state="blocked",
                error=message,
            )
            tx.upsert_status_snapshot(
                resource_type=str(request["target_type"]),
                resource_id=str(request["target_id"]),
                level="blocked",
                lifecycle=self._status_lifecycle(request),
                reconciliation="blocked",
                reason=reason,
                message=message,
                evidence=[
                    {
                        "source": "nephos-api",
                        "subject": str(request["id"]),
                        "reason": reason,
                        "message": message,
                    }
                ],
                observed_generation=int(request["target_generation"]),
            )

    def _status_lifecycle(self, request: dict[str, object]) -> str | None:
        target_type = str(request["target_type"])
        if target_type not in {"app_instance", "service_instance"}:
            return None
        try:
            slug = _target_slug(request)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if target_type == "app_instance":
            row = self._repository.get_app_row(slug)
        else:
            row = self._repository.get_service_row(slug)
        if row is None:
            return None
        return str(row["lifecycle"])


def _target_slug(request: dict[str, object]) -> str:
    snapshot = json.loads(str(request["target_snapshot_json"]))
    slug = snapshot.get("slug")
    if not isinstance(slug, str):
        raise ValueError("reconciliation target snapshot is missing slug")
    return slug


def _request_with_action(
    request: dict[str, object],
    action: str,
) -> dict[str, object]:
    return {**request, "action": action}


def _app_manifest_from_row(row: dict[str, object]) -> AppManifest:
    raw = yaml.safe_load(Path(str(row["catalog_source_path"])).read_text())
    return AppManifest.model_validate(raw)


def _app_row_should_reconcile_routes(row: dict[str, object]) -> bool:
    if row.get("lifecycle") == "removed" or row.get("delete_requested_at") is not None:
        return False
    return bool(_app_manifest_from_row(row).spec.routes)


def _resource_type(value: str) -> ResourceType:
    if value == "app_instance":
        return "app_instance"
    if value == "service_instance":
        return "service_instance"
    raise ValueError(f"unsupported namespace resource type {value}")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _binding_output_values(row: dict[str, object]) -> dict[str, str] | None:
    output_summary_json = row.get("output_summary_json")
    if not isinstance(output_summary_json, str):
        return None
    output_summary = json.loads(output_summary_json)
    values = output_summary.get("values")
    if not isinstance(values, dict):
        return None
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in values.items()
    ):
        return None
    return values


def _redacted_binding_output_summary(
    *,
    app_slug: str,
    alias: str,
    capability: str,
    protocol: str | None,
    values: dict[str, str],
) -> dict[str, object]:
    summary: dict[str, object] = {
        "target": "app-secret",
        "secretName": f"nephos-bind-{alias}",
        "namespace": f"app-{app_slug}",
        "keys": sorted(values),
        "redacted": True,
    }
    if protocol is not None:
        summary["capability"] = capability
        summary["protocol"] = protocol
    return summary
