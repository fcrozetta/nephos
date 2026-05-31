from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from nephos_api.config import Settings
from nephos_api.db import connect
from nephos_api.domain import utc_now
from nephos_api.repositories import ReconciliationRepository, _status_snapshot
from nephos_api.runtime import RuntimeHandler, RuntimeResult

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class HandlerOutcome:
    state: str
    status: dict[str, Any]
    error: str | None = None


@dataclass(frozen=True)
class ReconcileRunResult:
    processed: int
    request: dict[str, Any] | None = None
    final_state: str | None = None


@dataclass(frozen=True)
class ReconcileDrainResult:
    processed: int
    states: dict[str, int] = field(default_factory=dict)
    requests: tuple[dict[str, Any], ...] = ()


class Reconciler:
    """Serialized reconciler over persisted SQLite reconciliation requests.

    Shell mode keeps runtime-facing targets blocked without mutating Kubernetes.
    Helm mode delegates App, Service, and Binding requests to the opt-in runtime
    handler while preserving the durable queue/status boundary.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        runtime_handler: RuntimeHandler | None = None,
    ) -> None:
        self.settings = settings
        self.repository = ReconciliationRepository(settings)
        self.runtime_handler = runtime_handler

    def run_once(self) -> ReconcileRunResult:
        request = self.repository.claim_next_pending()
        if request is None:
            return ReconcileRunResult(processed=0)

        try:
            outcome = self._handle_request(request)
        except Exception as exc:  # pragma: no cover - defensive safety path
            LOGGER.exception("reconciliation request failed: %s", request["id"])
            outcome = self._failed_outcome(request, str(exc))

        finished = self.repository.finish_request(
            request_id=request["id"],
            state=outcome.state,
            error=outcome.error,
            status=outcome.status,
        )
        return ReconcileRunResult(processed=1, request=finished, final_state=finished["state"])

    def drain(self, *, limit: int | None = None) -> ReconcileDrainResult:
        processed = 0
        states: dict[str, int] = {}
        requests: list[dict[str, Any]] = []
        while limit is None or processed < limit:
            result = self.run_once()
            if not result.processed:
                break
            processed += 1
            if result.request is not None:
                requests.append(result.request)
                state = result.request["state"]
                states[state] = states.get(state, 0) + 1
        return ReconcileDrainResult(processed=processed, states=states, requests=tuple(requests))

    def _handle_request(self, request: dict[str, Any]) -> HandlerOutcome:
        target_type = request["targetType"]
        if target_type == "platform_domain":
            return self._handle_platform_domain(request)
        if target_type == "service_instance":
            return self._handle_service_instance(request)
        if target_type == "app_instance":
            return self._handle_app_instance(request)
        if target_type == "binding":
            return self._handle_binding(request)
        return self._failed_outcome(
            request,
            f"unsupported reconciliation target type: {target_type}",
        )

    def _handle_platform_domain(self, request: dict[str, Any]) -> HandlerOutcome:
        resource = self._read_platform_domain(request["targetId"])
        snapshot = request.get("targetSnapshot") or {}
        action = request["action"]
        if resource is None and action != "platform_domain.remove":
            return self._target_missing_outcome(request)

        reason = "desired_state_reconciled"
        message = "Platform domain desired state was reconciled."
        if action == "platform_domain.remove":
            reason = "desired_state_removed"
            message = "Platform domain desired state was removed."

        evidence = self._evidence(
            subject=self._subject(request),
            reason=reason,
            message=(
                f"{message} No Kubernetes or DNS mutation is required by the current "
                "reconciler shell."
            ),
            data={
                "action": action,
                "domain": (resource or snapshot).get("domain"),
                "name": (resource or snapshot).get("name"),
            },
        )
        status = self._status(
            request,
            level="healthy" if action != "platform_domain.remove" else "not_applicable",
            lifecycle="not_applicable",
            reconciliation="succeeded",
            reason=reason,
            message=message,
            evidence=[evidence],
        )
        return HandlerOutcome(state="succeeded", status=status)

    def _handle_service_instance(self, request: dict[str, Any]) -> HandlerOutcome:
        if self._helm_runtime_enabled():
            return self._handle_with_runtime(request)
        resource = self._read_service_instance(request["targetId"])
        if resource is None:
            return self._target_missing_outcome(request)
        return self._runtime_handler_missing_outcome(
            request,
            lifecycle=resource["lifecycle"],
            message=(
                "Service desired state is recorded, but the Helm/Kubernetes Service runtime "
                "handler is not implemented in this reconciler shell."
            ),
        )

    def _handle_app_instance(self, request: dict[str, Any]) -> HandlerOutcome:
        if self._helm_runtime_enabled():
            return self._handle_with_runtime(request)
        resource = self._read_app_instance(request["targetId"])
        if resource is None:
            return self._target_missing_outcome(request)

        routes = request.get("targetSnapshot", {}).get("routes") or []
        if routes and not self._has_platform_domain():
            route_names = [route.get("name") for route in routes if route.get("name")]
            evidence = self._evidence(
                subject=self._subject(request),
                reason="platform_root_domain_missing",
                message="App route reconciliation requires at least one configured root domain.",
                data={"routes": route_names},
            )
            status = self._status(
                request,
                level="blocked",
                lifecycle=resource["lifecycle"],
                reconciliation="blocked",
                reason="platform_root_domain_missing",
                message=(
                    "App has route intent, but no platform root domain is configured yet. "
                    "Add a platform domain, then create a new reconciliation request."
                ),
                evidence=[evidence],
            )
            return HandlerOutcome(state="blocked", status=status)

        return self._runtime_handler_missing_outcome(
            request,
            lifecycle=resource["lifecycle"],
            message=(
                "App desired state is recorded, but the Helm/Kubernetes App runtime handler "
                "is not implemented in this reconciler shell."
            ),
        )

    def _handle_binding(self, request: dict[str, Any]) -> HandlerOutcome:
        if self._helm_runtime_enabled():
            return self._handle_with_runtime(request)
        resource = self._read_binding(request["targetId"])
        if resource is None:
            return self._target_missing_outcome(request)
        return self._runtime_handler_missing_outcome(
            request,
            lifecycle="not_applicable",
            message=(
                "Binding desired state is recorded, but Service provisioning and App Secret "
                "materialization are not implemented in this reconciler shell."
            ),
        )

    def _helm_runtime_enabled(self) -> bool:
        return self.settings.runtime_mode == "helm"

    def _handle_with_runtime(self, request: dict[str, Any]) -> HandlerOutcome:
        handler = self.runtime_handler or RuntimeHandler(self.settings)
        result = handler.handle(request)
        return self._runtime_result_outcome(request, result)

    def _runtime_result_outcome(
        self,
        request: dict[str, Any],
        result: RuntimeResult,
    ) -> HandlerOutcome:
        status = self._status(
            request,
            level=result.level,
            lifecycle=result.lifecycle,
            reconciliation=result.state,
            reason=result.reason,
            message=result.message,
            evidence=result.evidence,
        )
        return HandlerOutcome(state=result.state, status=status, error=result.error)

    def _runtime_handler_missing_outcome(
        self,
        request: dict[str, Any],
        *,
        lifecycle: str,
        message: str,
    ) -> HandlerOutcome:
        evidence = self._evidence(
            subject=self._subject(request),
            reason="runtime_handler_not_implemented",
            message=message,
            data={"action": request["action"]},
        )
        status = self._status(
            request,
            level="blocked",
            lifecycle=lifecycle,
            reconciliation="blocked",
            reason="runtime_handler_not_implemented",
            message=message,
            evidence=[evidence],
        )
        return HandlerOutcome(state="blocked", status=status)

    def _target_missing_outcome(self, request: dict[str, Any]) -> HandlerOutcome:
        message = "Reconciliation target desired-state row was not found."
        evidence = self._evidence(
            subject=self._subject(request),
            reason="target_not_found",
            message=message,
            data={"action": request["action"]},
        )
        status = self._status(
            request,
            level="degraded",
            lifecycle="not_applicable",
            reconciliation="failed",
            reason="target_not_found",
            message=message,
            evidence=[evidence],
        )
        return HandlerOutcome(state="failed", status=status, error=message)

    def _failed_outcome(self, request: dict[str, Any], error: str) -> HandlerOutcome:
        message = "Reconciliation handler failed."
        evidence = self._evidence(
            subject=self._subject(request),
            reason="handler_failed",
            message=message,
            data={"error": error, "action": request.get("action")},
        )
        status = self._status(
            request,
            level="degraded",
            lifecycle="not_applicable",
            reconciliation="failed",
            reason="handler_failed",
            message=message,
            evidence=[evidence],
        )
        return HandlerOutcome(state="failed", status=status, error=error)

    def _status(
        self,
        request: dict[str, Any],
        *,
        level: str,
        lifecycle: str,
        reconciliation: str,
        reason: str,
        message: str,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return _status_snapshot(
            resource_type=request["targetType"],
            resource_id=request["targetId"],
            level=level,
            lifecycle=lifecycle,
            reconciliation=reconciliation,
            reason=reason,
            message=message,
            observed_generation=request.get("targetGeneration"),
            evidence=evidence,
        )

    def _evidence(
        self,
        *,
        subject: str,
        reason: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "source": "nephos.reconciler",
            "subject": subject,
            "reason": reason,
            "message": message,
            "observedAt": utc_now(),
        }
        if data is not None:
            evidence["data"] = data
        return evidence

    def _subject(self, request: dict[str, Any]) -> str:
        return f"{request['targetType']}:{request['targetId']}"

    def _has_platform_domain(self) -> bool:
        with connect(self.settings.db_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM platform_domains").fetchone()[0]
            return bool(count)

    def _read_app_instance(self, resource_id: str) -> dict[str, Any] | None:
        with connect(self.settings.db_path) as connection:
            row = connection.execute(
                "SELECT id, slug, lifecycle, generation FROM app_instances WHERE id = ?",
                (resource_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def _read_service_instance(self, resource_id: str) -> dict[str, Any] | None:
        with connect(self.settings.db_path) as connection:
            row = connection.execute(
                "SELECT id, slug, lifecycle, generation FROM service_instances WHERE id = ?",
                (resource_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def _read_binding(self, resource_id: str) -> dict[str, Any] | None:
        with connect(self.settings.db_path) as connection:
            row = connection.execute(
                "SELECT id, alias, capability, generation FROM bindings WHERE id = ?",
                (resource_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def _read_platform_domain(self, resource_id: str) -> dict[str, Any] | None:
        with connect(self.settings.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, name, domain, is_default, generation
                FROM platform_domains
                WHERE id = ?
                """,
                (resource_id,),
            ).fetchone()
            return dict(row) if row is not None else None


class BackgroundReconciler:
    def __init__(self, settings: Settings, *, poll_interval_seconds: float = 1.0) -> None:
        self.settings = settings
        self.poll_interval_seconds = poll_interval_seconds
        self.reconciler = Reconciler(settings)
        self._stop_event: asyncio.Event | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="nephos-reconciler")

    async def stop(self) -> None:
        if self._task is None or self._stop_event is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None
        self._stop_event = None

    async def _run(self) -> None:
        if self._stop_event is None:
            raise RuntimeError("background reconciler started without a stop event")
        while not self._stop_event.is_set():
            try:
                result = await asyncio.to_thread(self.reconciler.run_once)
            except Exception:  # pragma: no cover - defensive worker loop safety
                LOGGER.exception("background reconciler loop failed")
                result = ReconcileRunResult(processed=0)
            if result.processed:
                await asyncio.sleep(0)
                continue
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                continue
