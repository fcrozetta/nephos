import ast
import json
import os
import re
import select
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nephos_api.providers.pulumi import (
    _ensure_pulumi_cli,
    _ensure_pulumi_local_backend_passphrase,
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
class KubernetesZitadelProvisionerConfig:
    work_dir: Path
    state_dir: Path
    kubeconfig: Path | None = None
    kube_context: str | None = None
    project_name: str = "nephos-zitadel"
    local_bind_address: str = "127.0.0.1"


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
        return f"file://{self.state_dir.resolve()}"


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
        return f"file://{self.state_dir.resolve()}"


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


class KubernetesPulumiZitadelProvisioningClient:
    def __init__(
        self,
        *,
        core_v1_api,
        config: KubernetesZitadelProvisionerConfig,
        runner: ZitadelPulumiRunner | None = None,
    ) -> None:
        self._core_v1_api = core_v1_api
        self._config = config
        self._runner = runner

    def ensure_oidc_client(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]:
        with self._provisioning_endpoint(context) as endpoint:
            return self._pulumi_client(context, endpoint).ensure_oidc_client(context)

    def ensure_service_account(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]:
        with self._provisioning_endpoint(context) as endpoint:
            client = self._pulumi_client(context, endpoint)
            return client.ensure_service_account(context)

    def delete_oidc_client(self, context: BindingProvisioningContext) -> None:
        with self._provisioning_endpoint(context) as endpoint:
            self._pulumi_client(context, endpoint).delete_oidc_client(context)

    def delete_service_account(self, context: BindingProvisioningContext) -> None:
        with self._provisioning_endpoint(context) as endpoint:
            self._pulumi_client(context, endpoint).delete_service_account(context)

    def _pulumi_client(
        self,
        context: BindingProvisioningContext,
        endpoint: "_ForwardEndpoint",
    ) -> "PulumiZitadelProvisioningClient":
        return PulumiZitadelProvisioningClient(
            config=PulumiZitadelProvisionerConfig(
                work_dir=self._config.work_dir,
                state_dir=self._config.state_dir,
                issuer_url=_issuer_url(context),
                domain=endpoint.domain or _provisioning_domain(context),
                port=endpoint.port,
                insecure=endpoint.insecure,
                jwt_profile_json=_bootstrap_machine_key_json(
                    self._core_v1_api,
                    context=context,
                ),
                project_name=self._config.project_name,
            ),
            runner=self._runner,
        )

    def _provisioning_endpoint(
        self,
        context: BindingProvisioningContext,
    ) -> "_ProvisioningEndpointContext":
        if _should_use_internal_forward(context):
            return self._local_forward(context)
        return _StaticProvisioningEndpoint(
            _ForwardEndpoint(
                host=_provisioning_domain(context),
                port=_provisioning_port(context),
                insecure=not _provisioning_secure(context),
                domain=_provisioning_domain(context),
            )
        )

    def _local_forward(
        self,
        context: BindingProvisioningContext,
    ) -> "_KubectlPortForward":
        return _KubectlPortForward(
            namespace=_service_namespace(context.service_slug),
            service_name=_zitadel_service_name(context.service_slug),
            remote_port=8080,
            host=self._config.local_bind_address,
            kubeconfig=self._config.kubeconfig,
            kube_context=self._config.kube_context,
        )


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
            env_vars=_zitadel_pulumi_workspace_env_vars(spec),
            project_settings=auto.ProjectSettings(
                name=spec.project_name,
                runtime="python",
                backend=auto.ProjectBackend(url=spec.backend_url),
            ),
        ),
    )


def _zitadel_pulumi_workspace_env_vars(
    spec: ZitadelOidcBindingSpec | ZitadelServiceAccountBindingSpec,
) -> dict[str, str]:
    env_vars = {"PULUMI_BACKEND_URL": spec.backend_url}
    passphrase = os.environ.get("PULUMI_CONFIG_PASSPHRASE")
    if passphrase:
        env_vars["PULUMI_CONFIG_PASSPHRASE"] = passphrase
    passphrase_file = os.environ.get("PULUMI_CONFIG_PASSPHRASE_FILE")
    if passphrase_file:
        env_vars["PULUMI_CONFIG_PASSPHRASE_FILE"] = passphrase_file
    return env_vars


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


def _service_namespace(service_slug: str) -> str:
    return f"svc-{service_slug}"


def _zitadel_service_name(service_slug: str) -> str:
    namespace = _service_namespace(service_slug)
    return f"{namespace}-zitadel"


def _zitadel_pod_name(service_slug: str) -> str:
    return f"{_zitadel_service_name(service_slug)}-0"


def _bootstrap_machine_key_path(context: BindingProvisioningContext) -> str:
    value = _config_value(
        context,
        "bootstrap-machine-key-path",
        "bootstrapMachineKeyPath",
        default="/var/lib/zitadel-bootstrap/nephos-provisioner-key.json",
    )
    return str(value)


def _bootstrap_machine_key_json(
    core_v1_api,
    *,
    context: BindingProvisioningContext,
) -> str:
    from kubernetes import stream

    namespace = _service_namespace(context.service_slug)
    pod_name = _zitadel_pod_name(context.service_slug)
    key_path = _bootstrap_machine_key_path(context)
    _assert_service_namespace_owned(core_v1_api, context=context, namespace=namespace)
    response = stream.stream(
        core_v1_api.connect_get_namespaced_pod_exec,
        pod_name,
        namespace,
        command=["sh", "-lc", f"cat {shlex_quote(key_path)}"],
        container="bootstrap-reader",
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
    )
    key_text = str(response).strip()
    try:
        parsed = json.loads(key_text)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(key_text)
        except (SyntaxError, ValueError) as exc:
            raise RuntimeBlockedError(
                reason="binding_provisioner_unavailable",
                message="Zitadel bootstrap machine key is not readable yet.",
            ) from exc
    if not isinstance(parsed, dict):
        raise RuntimeBlockedError(
            reason="binding_provisioner_unavailable",
            message="Zitadel bootstrap machine key did not contain a JSON object.",
        )
    return json.dumps(parsed)


def _assert_service_namespace_owned(
    core_v1_api,
    *,
    context: BindingProvisioningContext,
    namespace: str,
) -> None:
    from kubernetes.client.rest import ApiException

    try:
        namespace_resource = core_v1_api.read_namespace(name=namespace)
    except ApiException as exc:
        if exc.status == 404:
            namespace_resource = None
        else:
            raise
    metadata = getattr(namespace_resource, "metadata", None)
    labels = getattr(metadata, "labels", None) or {}
    expected = {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/service-instance": context.service_slug,
    }
    if namespace_resource is None or not all(
        labels.get(key) == value for key, value in expected.items()
    ):
        raise RuntimeBlockedError(
            reason="runtime_safety_blocked",
            message=f"refusing to use unowned namespace {namespace}",
        )


def _provisioning_domain(context: BindingProvisioningContext) -> str:
    return str(_config_value(context, "external-host", "externalHost"))


def _provisioning_port(context: BindingProvisioningContext) -> int:
    return int(
        str(_config_value(context, "external-port", "externalPort", default=443))
    )


def _provisioning_secure(context: BindingProvisioningContext) -> bool:
    return _bool_config_value(
        context,
        "external-secure",
        "externalSecure",
        default=True,
    )


def _should_use_internal_forward(context: BindingProvisioningContext) -> bool:
    domain = _provisioning_domain(context).lower()
    transport = str(
        _config_value(
            context,
            "provisioning-transport",
            "provisioningTransport",
            default="auto",
        )
    ).lower()
    if transport == "issuer-endpoint":
        return False
    if transport == "port-forward":
        return True
    if transport != "auto":
        raise RuntimeBlockedError(
            reason="binding_provisioner_unavailable",
            message=(
                "Zitadel provisioning-transport must be one of auto, "
                "issuer-endpoint, or port-forward."
            ),
        )
    return domain in {"localhost", "127.0.0.1", "::1"} or domain.endswith(
        ".localhost"
    )


def _issuer_url(context: BindingProvisioningContext) -> str:
    host = _provisioning_domain(context)
    port = _provisioning_port(context)
    secure = _provisioning_secure(context)
    scheme = "https" if secure else "http"
    default_port = 443 if secure else 80
    suffix = "" if port == default_port else f":{port}"
    return f"{scheme}://{host}{suffix}"


def _config_value(
    context: BindingProvisioningContext,
    kebab_name: str,
    camel_name: str,
    *,
    default: object | None = None,
) -> object:
    config = context.service_config or {}
    if kebab_name in config:
        return config[kebab_name]
    if camel_name in config:
        return config[camel_name]
    if default is not None:
        return default
    raise RuntimeBlockedError(
        reason="binding_provisioner_unavailable",
        message=f"Zitadel Service config is missing required value {kebab_name}.",
    )


def _bool_config_value(
    context: BindingProvisioningContext,
    kebab_name: str,
    camel_name: str,
    *,
    default: bool,
) -> bool:
    value = _config_value(context, kebab_name, camel_name, default=default)
    if type(value) is bool:
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


class _ProvisioningEndpointContext(Protocol):
    def __enter__(self) -> "_ForwardEndpoint": ...

    def __exit__(self, exc_type, exc, traceback) -> None: ...


@dataclass(frozen=True)
class _ForwardEndpoint:
    host: str
    port: int
    insecure: bool = True
    domain: str | None = None


class _StaticProvisioningEndpoint:
    def __init__(self, endpoint: _ForwardEndpoint) -> None:
        self._endpoint = endpoint

    def __enter__(self) -> _ForwardEndpoint:
        return self._endpoint

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


class _KubectlPortForward:
    def __init__(
        self,
        *,
        namespace: str,
        service_name: str,
        remote_port: int,
        host: str,
        kubeconfig: Path | None,
        kube_context: str | None,
    ) -> None:
        self._namespace = namespace
        self._service_name = service_name
        self._remote_port = remote_port
        self._host = host
        self._kubeconfig = kubeconfig
        self._kube_context = kube_context
        self._process: subprocess.Popen[str] | None = None
        self._local_port = 0

    def __enter__(self) -> _ForwardEndpoint:
        if shutil.which("kubectl") is None:
            raise RuntimeBlockedError(
                reason="kubectl_cli_missing",
                message="kubectl is required for Zitadel internal provisioning.",
            )
        self._local_port = _free_local_port(self._host)
        command = [
            "kubectl",
            "-n",
            self._namespace,
        ]
        if self._kubeconfig is not None:
            command.extend(["--kubeconfig", str(self._kubeconfig)])
        if self._kube_context is not None:
            command.extend(["--context", self._kube_context])
        command.extend(
            [
                "port-forward",
                f"svc/{self._service_name}",
                f"{self._local_port}:{self._remote_port}",
                "--address",
                self._host,
            ]
        )
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            self._wait_ready()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return _ForwardEndpoint(host=self._host, port=self._local_port)

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._process is None:
            return
        process = self._process
        self._process = None
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _wait_ready(self) -> None:
        assert self._process is not None
        deadline = time.monotonic() + 20
        output: list[str] = []
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                remaining = self._process.stdout.read() if self._process.stdout else ""
                raise RuntimeBlockedError(
                    reason="binding_provisioner_unavailable",
                    message=(
                        "Zitadel internal port-forward exited before it became "
                        f"ready: {''.join(output)}{remaining}"
                    ).strip(),
                )
            if self._process.stdout is None:
                time.sleep(0.1)
                continue
            ready, _, _ = select.select([self._process.stdout], [], [], 0.1)
            line = self._process.stdout.readline() if ready else ""
            if line:
                output.append(line)
                if "Forwarding from" in line:
                    return
        raise RuntimeBlockedError(
            reason="binding_provisioner_unavailable",
            message="Timed out waiting for Zitadel internal port-forward.",
        )


def _free_local_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def shlex_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)


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
