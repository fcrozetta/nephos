"""Live app-scoped provisioning against ArcadeDB's HTTP admin API.

Every command goes to `POST /api/v1/server` as the server root user. Verified
against `arcadedata/arcadedb:26.5.1`:

    create database <db>                      -> 200 {"result":"ok"}
    create database <db>   (already present)  -> 400 "... already exists"
    create user {json}                        -> 200 {"result":"ok"}
    drop user <name>                          -> 200
    drop user <name>       (absent)           -> 400 "... not found"
    drop database <db>                        -> 200

Both "already exists" and "not found" are treated as success. Provisioning runs
on every binding reconcile, not once, so a create that refuses the second time
would turn a healthy binding into a blocked one on the next pass.

The generated password is persisted in a Kubernetes Secret in the Service
namespace and read back on later calls, the same shape `postgres` uses. Without
that, each reconcile would mint a new password, rewrite the App's binding Secret
with it, and leave the running workload holding a credential ArcadeDB no longer
accepts.
"""

from __future__ import annotations

import base64
import json
import secrets
from dataclasses import dataclass

import httpx
from kubernetes.client.rest import ApiException

from nephos_api.kubernetes_runtime import namespace_name
from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.runtime_errors import RuntimeBlockedError

# Native port per catalog protocol. `sql/arcadedb` and `opencypher/n4j` both
# speak the HTTP command endpoint, which is what serves Cypher.
_PROTOCOL_PORTS = {
    "arcadedb": 2480,
    "n4j": 2480,
    "bolt": 7687,
    "gremlin": 8182,
    "mongo": 27017,
}


@dataclass(frozen=True)
class _ArcadeDBRuntime:
    namespace: str
    host: str
    http_port: int = 2480

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.http_port}"


def _runtime(service_slug: str) -> _ArcadeDBRuntime:
    release = namespace_name("service_instance", service_slug)
    name = f"{release}-arcadedb"
    return _ArcadeDBRuntime(
        namespace=release,
        host=f"{name}.{release}.svc.cluster.local",
    )


def _identifier(context: BindingProvisioningContext) -> str:
    """A database and user name ArcadeDB accepts.

    Slugs carry hyphens; ArcadeDB identifiers are safer with underscores, and
    the pair must be stable across reconciles because it is the lookup key.
    """
    return f"{context.app_slug}_{context.alias}".replace("-", "_")


class KubernetesArcadeDBProvisioningClient:
    """Creates an app-scoped database and user over ArcadeDB's HTTP API."""

    def __init__(
        self,
        *,
        core_v1_api,
        client: httpx.Client | None = None,
        password_factory=lambda: secrets.token_urlsafe(24),
    ) -> None:
        self._core_v1_api = core_v1_api
        self._client = client or httpx.Client(timeout=30.0)
        self._password_factory = password_factory

    def ensure_database_user(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]:
        runtime = _runtime(context.service_slug)
        root_password = _root_password(context)
        identifier = _identifier(context)
        password = self._ensure_credential(context, identifier)

        self._server_command(
            runtime,
            root_password,
            f"create database {identifier}",
            tolerate="already exists",
        )
        self._server_command(
            runtime,
            root_password,
            "create user "
            + json.dumps(
                {
                    "name": identifier,
                    "password": password,
                    "databases": {identifier: ["admin"]},
                }
            ),
            tolerate="already exists",
        )

        protocol = str(context.protocol or "arcadedb")
        port = _PROTOCOL_PORTS.get(protocol, 2480)
        return {
            "host": runtime.host,
            "port": str(port),
            "database": identifier,
            "username": identifier,
            "password": password,
            "protocol": protocol,
            "uri": f"{protocol}://{identifier}@{runtime.host}:{port}/{identifier}",
        }

    def delete_database_user(self, context: BindingProvisioningContext) -> None:
        runtime = _runtime(context.service_slug)
        try:
            root_password = _root_password(context)
        except RuntimeBlockedError:
            # Teardown is best-effort; a Service whose config is already gone
            # must not keep its consumers alive.
            return
        identifier = _identifier(context)
        self._server_command(
            runtime, root_password, f"drop user {identifier}", tolerate="not found"
        )
        self._server_command(
            runtime,
            root_password,
            f"drop database {identifier}",
            tolerate="not found",
        )
        self._delete_credential(context, identifier)

    def _server_command(
        self,
        runtime: _ArcadeDBRuntime,
        root_password: str,
        command: str,
        *,
        tolerate: str,
    ) -> None:
        try:
            response = self._client.post(
                f"{runtime.base_url}/api/v1/server",
                json={"command": command},
                auth=("root", root_password),
            )
        except httpx.HTTPError as exc:
            raise RuntimeBlockedError(
                reason="binding_provisioner_unavailable",
                message=f"ArcadeDB is unreachable at {runtime.host}: {exc}",
            ) from exc

        if response.status_code < 400:
            return
        detail = ""
        try:
            detail = str(response.json().get("detail") or "")
        except ValueError:
            detail = response.text
        if tolerate and tolerate in detail:
            return
        # The verb only, never the payload, and never the server's echo of it.
        # This message is persisted verbatim into the status snapshot, which the
        # API serves; binding-output redaction covers the success path's values
        # dict and nothing here. ArcadeDB quotes the offending command back in
        # `detail` for parse errors, and the create-user command carries the
        # plaintext password.
        verb = command.split("{")[0].strip()
        raise RuntimeBlockedError(
            reason="binding_provisioner_unavailable",
            message=f"ArcadeDB rejected {verb!r} (see the ArcadeDB server log)",
        )

    def _secret_name(self, identifier: str) -> str:
        return f"nephos-arcadedb-{identifier}".replace("_", "-")

    def _ensure_credential(
        self,
        context: BindingProvisioningContext,
        identifier: str,
    ) -> str:
        from kubernetes import client

        namespace = _runtime(context.service_slug).namespace
        name = self._secret_name(identifier)
        try:
            existing = self._core_v1_api.read_namespaced_secret(name, namespace)
        except ApiException as exc:
            # Only "absent" means mint a new one. A transient API error read as
            # absence would mint a second password, then 409 on create -- an
            # exception RuntimeBlockedError does not wrap, so the request lands
            # in `failed`, which nothing retries. A blip would wedge the binding
            # permanently.
            if exc.status != 404:
                raise RuntimeBlockedError(
                    reason="binding_provisioner_unavailable",
                    message=(
                        f"Could not read credential Secret {name}: "
                        f"HTTP {exc.status}"
                    ),
                ) from exc
            existing = None
        if existing is not None:
            # Ownership guard, mirroring postgres._assert_owned_credential_secret.
            # The Secret lives in the *Service* namespace, shared by every App
            # bound to it, and `_identifier` can collide across Apps: `acme` +
            # `graph-primary` and `acme-graph` + `primary` both render
            # `acme_graph_primary`. Without this check a colliding App would read
            # back another App's live password and be handed admin on its
            # database. Refuse rather than reuse.
            _assert_owned(existing, context=context, name=name)
            return base64.b64decode(existing.data["password"]).decode()

        password = self._password_factory()
        self._core_v1_api.create_namespaced_secret(
            namespace=namespace,
            body=client.V1Secret(
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=namespace,
                    labels=_ownership_labels(context),
                ),
                string_data={"username": identifier, "password": password},
            ),
        )
        return password

    def _delete_credential(
        self,
        context: BindingProvisioningContext,
        identifier: str,
    ) -> None:
        namespace = _runtime(context.service_slug).namespace
        try:
            self._core_v1_api.delete_namespaced_secret(
                self._secret_name(identifier), namespace
            )
        except Exception:
            return


def _root_password(context: BindingProvisioningContext) -> str:
    config = context.service_config or {}
    for key in ("root-password", "rootPassword"):
        value = config.get(key)
        if value:
            return str(value)
    raise RuntimeBlockedError(
        reason="binding_provisioner_unavailable",
        message="ArcadeDB Service config is missing required value root-password.",
    )


def _ownership_labels(context: BindingProvisioningContext) -> dict[str, str]:
    return {
        "app.kubernetes.io/managed-by": "nephos",
        "nephos.pro/app-instance": context.app_slug,
        "nephos.pro/binding-alias": context.alias,
    }


def _assert_owned(secret, *, context: BindingProvisioningContext, name: str) -> None:
    """Refuse a credential Secret that belongs to a different binding."""
    labels = (getattr(secret, "metadata", None) and secret.metadata.labels) or {}
    expected = _ownership_labels(context)
    if any(labels.get(key) != value for key, value in expected.items()):
        raise RuntimeBlockedError(
            reason="binding_provisioner_unavailable",
            message=(
                f"Refusing to reuse Secret {name}: it belongs to another "
                "binding. Two Apps have collided on a generated identifier."
            ),
        )
