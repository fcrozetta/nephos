import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nephos_api.providers.pulumi import (
    _ensure_pulumi_cli,
    _ensure_pulumi_local_backend_passphrase,
    _pulumi_workspace_env_vars,
)
from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.runtime_errors import RuntimeBlockedError


class ZitadelProvisioningClient(Protocol):
    def ensure_oidc_client(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]: ...

    def ensure_service_account(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]: ...

    def delete_oidc_client(self, context: BindingProvisioningContext) -> None: ...

    def delete_service_account(self, context: BindingProvisioningContext) -> None: ...


@dataclass(frozen=True)
class PulumiZitadelProvisionerConfig:
    work_dir: Path
    state_dir: Path
    issuer_url: str
    domain: str
    port: int
    insecure: bool
    jwt_profile_json: str
    project_name: str = "nephos-zitadel"


@dataclass(frozen=True)
class ZitadelOidcBindingSpec:
    project_name: str
    stack_name: str
    work_dir: Path
    state_dir: Path
    issuer_url: str
    domain: str
    port: int
    insecure: bool
    jwt_profile_json: str
    app_slug: str
    alias: str
    redirect_uris: tuple[str, ...]
    post_logout_redirect_uris: tuple[str, ...]

    @property
    def backend_url(self) -> str:
        return f"file://{self.state_dir}"


@dataclass(frozen=True)
class ZitadelServiceAccountBindingSpec:
    project_name: str
    stack_name: str
    work_dir: Path
    state_dir: Path
    issuer_url: str
    domain: str
    port: int
    insecure: bool
    jwt_profile_json: str
    app_slug: str
    alias: str

    @property
    def backend_url(self) -> str:
        return f"file://{self.state_dir}"


class ZitadelPulumiRunner(Protocol):
    def up_oidc(self, spec: ZitadelOidcBindingSpec) -> dict[str, str]: ...

    def up_service_account(
        self,
        spec: ZitadelServiceAccountBindingSpec,
    ) -> dict[str, str]: ...

    def destroy_oidc(self, spec: ZitadelOidcBindingSpec) -> None: ...

    def destroy_service_account(
        self,
        spec: ZitadelServiceAccountBindingSpec,
    ) -> None: ...


class PulumiZitadelProvisioningClient:
    def __init__(
        self,
        *,
        config: PulumiZitadelProvisionerConfig,
        runner: ZitadelPulumiRunner | None = None,
    ) -> None:
        self._config = config
        self._runner = runner or PulumiAutomationZitadelRunner()

    def ensure_oidc_client(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]:
        spec = self._oidc_spec(context)
        outputs = self._runner.up_oidc(spec)
        return {
            "issuerUrl": self._config.issuer_url,
            "clientId": _required_output(outputs, "clientId"),
            "clientSecret": _required_output(outputs, "clientSecret"),
            "redirectUris": _json_list(spec.redirect_uris),
            "postLogoutRedirectUris": _json_list(spec.post_logout_redirect_uris),
            "authorizationUrl": f"{self._config.issuer_url}/oauth/v2/authorize",
            "tokenUrl": f"{self._config.issuer_url}/oauth/v2/token",
            "jwksUrl": f"{self._config.issuer_url}/oauth/v2/keys",
        }

    def ensure_service_account(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]:
        spec = self._service_account_spec(context)
        outputs = self._runner.up_service_account(spec)
        return {
            "issuerUrl": self._config.issuer_url,
            "serviceAccountId": _required_output(outputs, "serviceAccountId"),
            "keyJson": _required_output(outputs, "keyJson"),
            "audience": self._config.issuer_url,
        }

    def delete_oidc_client(self, context: BindingProvisioningContext) -> None:
        self._runner.destroy_oidc(self._oidc_spec(context))

    def delete_service_account(self, context: BindingProvisioningContext) -> None:
        self._runner.destroy_service_account(self._service_account_spec(context))

    def _oidc_spec(self, context: BindingProvisioningContext) -> ZitadelOidcBindingSpec:
        redirect_uris, post_logout_redirect_uris = _oidc_uris(context)
        stack_name = _stack_name("oidc", context)
        return ZitadelOidcBindingSpec(
            project_name=self._config.project_name,
            stack_name=stack_name,
            work_dir=self._config.work_dir / stack_name,
            state_dir=self._config.state_dir,
            issuer_url=self._config.issuer_url,
            domain=self._config.domain,
            port=self._config.port,
            insecure=self._config.insecure,
            jwt_profile_json=self._config.jwt_profile_json,
            app_slug=context.app_slug,
            alias=context.alias,
            redirect_uris=redirect_uris,
            post_logout_redirect_uris=post_logout_redirect_uris,
        )

    def _service_account_spec(
        self,
        context: BindingProvisioningContext,
    ) -> ZitadelServiceAccountBindingSpec:
        stack_name = _stack_name("jwt", context)
        return ZitadelServiceAccountBindingSpec(
            project_name=self._config.project_name,
            stack_name=stack_name,
            work_dir=self._config.work_dir / stack_name,
            state_dir=self._config.state_dir,
            issuer_url=self._config.issuer_url,
            domain=self._config.domain,
            port=self._config.port,
            insecure=self._config.insecure,
            jwt_profile_json=self._config.jwt_profile_json,
            app_slug=context.app_slug,
            alias=context.alias,
        )


class PulumiAutomationZitadelRunner:
    def up_oidc(self, spec: ZitadelOidcBindingSpec) -> dict[str, str]:
        stack = _create_or_select_zitadel_stack(
            spec,
            program=lambda: _oidc_pulumi_program(spec),
        )
        result = stack.up(color="never", suppress_outputs=True)
        return _automation_outputs(result.outputs)

    def up_service_account(
        self,
        spec: ZitadelServiceAccountBindingSpec,
    ) -> dict[str, str]:
        stack = _create_or_select_zitadel_stack(
            spec,
            program=lambda: _service_account_pulumi_program(spec),
        )
        result = stack.up(color="never", suppress_outputs=True)
        return _automation_outputs(result.outputs)

    def destroy_oidc(self, spec: ZitadelOidcBindingSpec) -> None:
        stack = _create_or_select_zitadel_stack(
            spec,
            program=lambda: _oidc_pulumi_program(spec),
        )
        stack.destroy(color="never", suppress_outputs=True)

    def destroy_service_account(self, spec: ZitadelServiceAccountBindingSpec) -> None:
        stack = _create_or_select_zitadel_stack(
            spec,
            program=lambda: _service_account_pulumi_program(spec),
        )
        stack.destroy(color="never", suppress_outputs=True)


class ZitadelAppScopedProvisioner:
    def __init__(self, client: ZitadelProvisioningClient | None = None) -> None:
        self._client = client

    def provision_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str] | None:
        if _is_oidc(context):
            if self._client is None:
                raise _client_missing("Zitadel")
            return self._client.ensure_oidc_client(context)
        if _is_service_account(context):
            if self._client is None:
                raise _client_missing("Zitadel")
            return self._client.ensure_service_account(context)
        return None

    def deprovision_binding(self, context: BindingProvisioningContext) -> None:
        if self._client is None:
            return
        if _is_oidc(context):
            self._client.delete_oidc_client(context)
        elif _is_service_account(context):
            self._client.delete_service_account(context)


def _create_or_select_zitadel_stack(spec, *, program):
    from pulumi import automation as auto

    _ensure_pulumi_cli()
    _ensure_pulumi_local_backend_passphrase()
    spec.work_dir.mkdir(parents=True, exist_ok=True)
    spec.state_dir.mkdir(parents=True, exist_ok=True)
    return auto.create_or_select_stack(
        stack_name=spec.stack_name,
        project_name=spec.project_name,
        program=program,
        opts=auto.LocalWorkspaceOptions(
            work_dir=str(spec.work_dir),
            env_vars=_pulumi_workspace_env_vars(spec),
            project_settings=auto.ProjectSettings(
                name=spec.project_name,
                runtime="python",
                backend=auto.ProjectBackend(url=spec.backend_url),
            ),
        ),
    )


def _oidc_pulumi_program(spec: ZitadelOidcBindingSpec) -> None:
    import pulumi
    import pulumiverse_zitadel as zitadel

    provider = zitadel.Provider(
        "zitadel",
        domain=spec.domain,
        port=str(spec.port),
        insecure=spec.insecure,
        jwt_profile_json=spec.jwt_profile_json,
    )
    opts = pulumi.ResourceOptions(provider=provider)
    project = zitadel.Project(
        "project",
        name=_display_name(spec.app_slug),
        project_role_assertion=True,
        project_role_check=False,
        opts=opts,
    )
    app = zitadel.ApplicationOidc(
        "application",
        name=_display_name(f"{spec.app_slug}-{spec.alias}"),
        project_id=project.id,
        redirect_uris=list(spec.redirect_uris),
        post_logout_redirect_uris=list(spec.post_logout_redirect_uris),
        response_types=["OIDC_RESPONSE_TYPE_CODE"],
        grant_types=[
            "OIDC_GRANT_TYPE_AUTHORIZATION_CODE",
            "OIDC_GRANT_TYPE_REFRESH_TOKEN",
        ],
        app_type="OIDC_APP_TYPE_WEB",
        auth_method_type="OIDC_AUTH_METHOD_TYPE_BASIC",
        version="OIDC_VERSION_1_0",
        opts=opts,
    )
    pulumi.export("projectId", project.id)
    pulumi.export("applicationId", app.id)
    pulumi.export("clientId", app.client_id)
    pulumi.export("clientSecret", app.client_secret)


def _service_account_pulumi_program(spec: ZitadelServiceAccountBindingSpec) -> None:
    import pulumi
    import pulumiverse_zitadel as zitadel

    provider = zitadel.Provider(
        "zitadel",
        domain=spec.domain,
        port=str(spec.port),
        insecure=spec.insecure,
        jwt_profile_json=spec.jwt_profile_json,
    )
    opts = pulumi.ResourceOptions(provider=provider)
    machine = zitadel.MachineUser(
        "machine-user",
        user_name=_machine_username(spec.app_slug, spec.alias),
        name=_display_name(f"{spec.app_slug}-{spec.alias}"),
        access_token_type="ACCESS_TOKEN_TYPE_JWT",
        opts=opts,
    )
    key = zitadel.MachineKey(
        "machine-key",
        user_id=machine.id,
        key_type="KEY_TYPE_JSON",
        expiration_date="2036-01-01T00:00:00Z",
        opts=opts,
    )
    pulumi.export("serviceAccountId", machine.id)
    pulumi.export("keyJson", key.key_details)


def _is_oidc(context: BindingProvisioningContext) -> bool:
    return context.capability == "oidc" and context.protocol == "oidc"


def _is_service_account(context: BindingProvisioningContext) -> bool:
    return context.capability == "service-account" and context.protocol == "jwt"


def _client_missing(service: str) -> RuntimeBlockedError:
    return RuntimeBlockedError(
        reason="binding_provisioner_unavailable",
        message=(
            f"{service} client is not configured; live external API details "
            "are intentionally blocked until verified."
        ),
    )


def _oidc_uris(
    context: BindingProvisioningContext,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    base_urls = _route_base_urls(context)
    if not base_urls:
        raise RuntimeBlockedError(
            reason="binding_provisioner_unavailable",
            message=(
                "Zitadel OIDC provisioning requires at least one App route and "
                "a default platform domain to derive redirect URIs."
            ),
        )
    redirects = tuple(f"{base_url}/oauth/callback" for base_url in base_urls)
    post_logout = tuple(f"{base_url}/" for base_url in base_urls)
    return redirects, post_logout


def _route_base_urls(context: BindingProvisioningContext) -> tuple[str, ...]:
    default_domain = next(
        (
            str(domain["domain"])
            for domain in context.platform_domains
            if bool(domain.get("default"))
        ),
        None,
    )
    if default_domain is None:
        return ()
    urls = []
    for index, route in enumerate(context.app_routes):
        host_prefix = (
            context.app_slug
            if index == 0
            else f"{route['name']}.{context.app_slug}"
        )
        urls.append(f"http://{host_prefix}.{default_domain}")
    return tuple(urls)


def _stack_name(prefix: str, context: BindingProvisioningContext) -> str:
    return _safe_stack_name(f"zitadel-{prefix}-{context.binding_id}")


def _safe_stack_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-._")
    return cleaned[:100] or "zitadel-binding"


def _display_name(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").title()


def _machine_username(app_slug: str, alias: str) -> str:
    return _safe_stack_name(f"{app_slug}-{alias}")


def _json_list(values: tuple[str, ...]) -> str:
    import json

    return json.dumps(list(values), separators=(",", ":"))


def _automation_outputs(outputs: dict[str, object]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, output in outputs.items():
        value = getattr(output, "value", output)
        values[key] = str(value)
    return values


def _required_output(outputs: dict[str, str], key: str) -> str:
    value = outputs.get(key)
    if not value:
        raise RuntimeBlockedError(
            reason="binding_output_unavailable",
            message=f"Zitadel Pulumi stack did not produce required output {key}.",
        )
    return value
