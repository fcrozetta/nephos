# SeaweedFS Turnkey Install and S3 Binding Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `seaweedfs` install with zero operator input and provision a real per-binding bucket plus a bucket-scoped S3 identity for every `object-storage/s3` binding.

**Architecture:** The SeaweedFS runtime stops passing `-s3.config`, which moves S3 identities into the filer store where they can be written at runtime and hot-reload without a restart. A service lifecycle provisioner seeds the `nephos-admin` identity right after deploy (closing the anonymous-S3 window), and an `object-storage` provisioning engine executes `weed shell` inside the Service pod to create a bucket and a scoped identity per binding.

**Tech Stack:** Python 3.14, Pulumi Kubernetes provider, Kubernetes Python client (`stream.stream` exec), pytest with fake clients, uv, Ruff.

**Spec:** `docs/adr/20260816-seaweedfs-filer-backed-s3-provisioning.md`

## Global Constraints

- SeaweedFS image floor is `chrislusf/seaweedfs:3.85`. All `weed shell` flags below are verified against that tag.
- Binding output keys are fixed by ADR 20260630 and MUST be exactly: `endpointUrl`, `bucket`, `accessKeyId`, `secretAccessKey`, `region`. Do not add, rename, or drop keys.
- `region` is always the literal string `us-east-1`.
- The provisioning engine name is `object-storage` (engine name follows capability name, matching `sql` / `oidc` / `opencypher`).
- The `object-storage` engine recognizes **no** entitlements: `recognized_entitlements = frozenset()`.
- No new third-party Python dependency. Specifically: do NOT add `boto3` or any S3 client.
- Generated credential values must be alphanumeric only (`string.ascii_letters + string.digits`). Other characters are not verified against SigV4 signing.
- Never regenerate a credential that already exists. Every ensure path is read-existing-else-create, mirroring `PostgresAppScopedProvisioner._ensure_credential_secret`.
- Kubernetes names must be <= 63 characters, lowercase. Use the `hashlib.sha256(binding_id)[:12]` suffix truncation pattern from `_credential_secret_name`.
- No migration path for existing installs. A pre-existing SeaweedFS install must be destroyed and reinstalled.

**Runtime coordinates** (slug `seaweedfs`, derived via `namespace_name("service_instance", slug)`):

| Thing | Value |
|---|---|
| Namespace | `svc-seaweedfs` |
| StatefulSet / Service / Secret | `svc-seaweedfs-seaweedfs` |
| Pod | `svc-seaweedfs-seaweedfs-0` |
| S3 endpoint | `http://svc-seaweedfs-seaweedfs.svc-seaweedfs.svc.cluster.local:8333` |

---

## Task 1: Make the catalog entry turnkey

**Objective:** `entry_is_turnkey()` returns `True` for `seaweedfs`, so it installs with `config={}` and becomes eligible for lazy dependency install.

**Files:**
- Modify: `.nephos/registries/core-registry/services/seaweedfs/service.yaml`
- Test: `tests/test_catalog_loader.py`

**Interfaces:**
- Consumes: `entry_is_turnkey(entry)` from `nephos_api.catalog` (existing).
- Produces: nothing consumed by later tasks; this task is manifest-only.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_catalog_loader.py`:

```python
def test_seaweedfs_catalog_entry_is_turnkey() -> None:
    """SeaweedFS must install with no operator input so it can be lazily
    installed as an object-storage/s3 dependency provider."""
    from nephos_api.catalog import entry_is_turnkey

    entry = _core_registry_service_entry("seaweedfs")

    blocking = [
        option["name"]
        for option in entry["config"]["options"]
        if option["required"] and option["default"] is None and not option["generated"]
    ]
    assert blocking == []
    assert entry_is_turnkey(entry) is True
```

If `_core_registry_service_entry` does not already exist in that test module, add this helper next to it:

```python
def _core_registry_service_entry(name: str) -> dict:
    from nephos_api.catalog import CatalogLoader

    loader = CatalogLoader(sources=(("core-registry", _CORE_REGISTRY_ROOT),))
    for entry in loader.list_services():
        if entry["name"] == name:
            return entry
    raise AssertionError(f"no core-registry service entry named {name}")
```

Match the loader construction to how the other tests in that file build a `CatalogLoader`; if they use a fixture, reuse the fixture instead of constructing one.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_catalog_loader.py::test_seaweedfs_catalog_entry_is_turnkey -v`
Expected: FAIL — `blocking` contains `['s3-access-key', 's3-secret-key']`.

- [ ] **Step 3: Make the two credential options generated**

In `.nephos/registries/core-registry/services/seaweedfs/service.yaml`, replace the two credential options:

```yaml
    - name: s3-access-key
      type: string
      label: S3 access key
      description: Admin S3 access key for this SeaweedFS instance. Generated by Nephos when left unset.
      generate:
        kind: password
        length: 20
    - name: s3-secret-key
      type: string
      label: S3 secret key
      description: Admin S3 secret key for this SeaweedFS instance. Generated by Nephos when left unset.
      generate:
        kind: password
        length: 40
```

Note what changed: `required: true` is gone from both, and `generate` replaces it. Lengths 20/40 mirror the conventional AWS access-key/secret-key shapes. Leave every other option in the file untouched.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_catalog_loader.py::test_seaweedfs_catalog_entry_is_turnkey -v`
Expected: PASS

- [ ] **Step 5: Validate the registry manifest still parses**

Run: `(cd .nephos/registries/core-registry && NEPHOS_SRC="$PWD/../../../src" python3 scripts/validate_catalog.py)`
Expected: no validation errors.

If `scripts/validate_catalog.py` is not present at that path, skip this step and rely on the loader test.

- [ ] **Step 6: Commit**

```bash
git add .nephos/registries/core-registry/services/seaweedfs/service.yaml tests/test_catalog_loader.py
git commit -m "feat(seaweedfs): generate S3 admin credentials so install is turnkey"
```

---

## Task 2: Move the runtime off the static S3 config file

**Objective:** The StatefulSet stops passing `-s3.config` and stops mounting an `s3.json` document, so the S3 API server reads identities from the filer and hot-reloads them. The Secret keeps carrying the admin credentials as plain keys.

**Files:**
- Modify: `src/nephos_api/providers/kubernetes.py:985-1082` (`_seaweedfs_service`, `_seaweedfs_s3_config_json`)
- Test: `tests/test_pulumi_kubernetes_provider.py:604`

**Interfaces:**
- Consumes: `_required_string_value`, `_string_value`, `_labels`, `_volume_claim_template` (all existing in `kubernetes.py`).
- Produces: Secret `svc-seaweedfs-seaweedfs` with string keys `access-key` and `secret-key`. Tasks 4 and 5 read those exact key names.

- [ ] **Step 1: Write the failing test**

Replace the body of `test_seaweedfs_service_forwards_values_to_runtime_resources` in `tests/test_pulumi_kubernetes_provider.py` with these two tests (keep the existing `PulumiKubernetesWorkloadSpec` construction shown at lines 604-624 in both):

```python
def test_seaweedfs_service_stores_admin_credentials_as_plain_secret_keys() -> None:
    """ADR 20260816: identities live in the filer, so the Secret carries the
    admin credential as data the lifecycle seeder reads -- not as an s3.json
    document mounted into the pod."""
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-seaweedfs",
        work_dir=Path("/tmp/workspaces/svc-seaweedfs"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-seaweedfs",
        namespace="svc-seaweedfs",
        workload="seaweedfs-service",
        values={
            "image": "chrislusf/seaweedfs:3.85",
            "storageSize": "2Gi",
            "s3AccessKey": "alpha-access",
            "s3SecretKey": "alpha-secret",
        },
    )

    _seaweedfs_service(spec, k8s=k8s, opts=None)

    secret = k8s.secret.calls[0]
    assert secret["string_data"] == {
        "access-key": "alpha-access",
        "secret-key": "alpha-secret",
    }
    assert "s3.json" not in secret["string_data"]


def test_seaweedfs_service_does_not_pass_static_s3_config() -> None:
    """-s3.config disables the filer /etc/ subscription, which would make every
    runtime-provisioned identity invisible (InvalidAccessKeyId)."""
    k8s = RecordingKubernetes()
    spec = PulumiKubernetesWorkloadSpec(
        project_name="nephos-api",
        stack_name="svc-seaweedfs",
        work_dir=Path("/tmp/workspaces/svc-seaweedfs"),
        state_dir=Path("/tmp/state"),
        kubeconfig=None,
        kube_context=None,
        runtime_name="svc-seaweedfs",
        namespace="svc-seaweedfs",
        workload="seaweedfs-service",
        values={
            "image": "chrislusf/seaweedfs:3.85",
            "storageSize": "2Gi",
            "s3AccessKey": "alpha-access",
            "s3SecretKey": "alpha-secret",
        },
    )

    _seaweedfs_service(spec, k8s=k8s, opts=None)

    stateful_set = k8s.stateful_set.calls[0]
    container = stateful_set["spec"]["template"]["spec"]["containers"][0]
    assert not any(arg.startswith("-s3.config") for arg in container["args"])
    mount_paths = {mount["mountPath"] for mount in container["volumeMounts"]}
    assert "/etc/seaweedfs" not in mount_paths
```

The attribute names `k8s.secret` / `k8s.stateful_set` must match whatever `RecordingKubernetes` in that module already exposes; read the class near line 34 and use its actual accessors.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pulumi_kubernetes_provider.py -k seaweedfs -v`
Expected: FAIL — the Secret still contains `s3.json`, and the container args still contain `-s3.config=/etc/seaweedfs/s3.json`.

- [ ] **Step 3: Rewrite the workload**

In `src/nephos_api/providers/kubernetes.py`, replace `_seaweedfs_service` with:

```python
def _seaweedfs_service(
    spec: PulumiKubernetesWorkloadSpec,
    *,
    k8s,
    opts,
) -> None:
    name = f"{spec.runtime_name}-seaweedfs"
    labels = _labels(spec)
    selector = {"app.kubernetes.io/name": name}
    image = _string_value(spec.values, "image", "chrislusf/seaweedfs:3.85")
    access_key = _required_string_value(spec.values, "s3AccessKey")
    secret_key = _required_string_value(spec.values, "s3SecretKey")
    # ADR 20260816: no -s3.config. A static config file makes the S3 API server
    # skip its filer /etc/ subscription, so every identity written at runtime is
    # invisible and app-scoped provisioning is impossible. The admin credential
    # lives here as plain keys for the lifecycle seeder to read.
    k8s.core.v1.Secret(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        type="Opaque",
        string_data={"access-key": access_key, "secret-key": secret_key},
        opts=opts,
    )
    k8s.core.v1.Service(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        spec={
            "ports": [{"name": "s3", "port": 8333, "targetPort": "s3"}],
            "selector": selector,
        },
        opts=opts,
    )
    k8s.apps.v1.StatefulSet(
        name,
        metadata={
            "name": name,
            "namespace": spec.namespace,
            "labels": labels,
        },
        spec={
            "serviceName": name,
            "replicas": 1,
            "selector": {"matchLabels": selector},
            "template": {
                "metadata": {"labels": {**labels, **selector}},
                "spec": {
                    "containers": [
                        {
                            "name": "seaweedfs",
                            "image": image,
                            "args": [
                                "server",
                                "-s3",
                                "-s3.port=8333",
                                "-dir=/data",
                            ],
                            "ports": [{"name": "s3", "containerPort": 8333}],
                            "volumeMounts": [
                                {"name": "data", "mountPath": "/data"},
                            ],
                        }
                    ],
                },
            },
            "volumeClaimTemplates": [_volume_claim_template(spec, labels)],
        },
        opts=opts,
    )
```

Then delete `_seaweedfs_s3_config_json` entirely (it has no other caller). If `json` becomes an unused import in the module, leave it — `_arcadedb_service` and others may still use it; Ruff will tell you in Step 5.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pulumi_kubernetes_provider.py -k seaweedfs -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Lint and run the full provider suite**

Run: `uv run ruff check src/nephos_api/providers/kubernetes.py tests/test_pulumi_kubernetes_provider.py && uv run pytest tests/test_pulumi_kubernetes_provider.py -q`
Expected: no lint errors, all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/nephos_api/providers/kubernetes.py tests/test_pulumi_kubernetes_provider.py
git commit -m "feat(seaweedfs): drop static s3.config so filer-backed IAM can be provisioned"
```

---

## Task 3: Generalize the service-lifecycle hook to a provider-keyed map

**Objective:** `ProviderRuntimeDeployer` stops naming `openbao` in an `if`, so a second Service can own a post-deploy lifecycle.

**Files:**
- Modify: `src/nephos_api/providers/deployer.py:50-83`
- Modify: `src/nephos_api/main.py:379-413`
- Test: `tests/test_provider_deployer.py`

**Interfaces:**
- Consumes: `ServiceLifecycleProvisioner` protocol (`reconcile(context) -> None`) from `nephos_api.providers.service_lifecycle`.
- Produces: `ProviderRuntimeDeployer(..., service_lifecycles: Mapping[str, ServiceLifecycleProvisioner] | None = None)`. Task 4 registers `"seaweedfs"` in that mapping.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_provider_deployer.py`:

```python
def test_service_lifecycle_runs_for_its_own_provider_only() -> None:
    """The lifecycle hook is keyed by provider name, so a second Service can own
    a post-deploy lifecycle without editing an if-statement in the deployer."""

    class RecordingLifecycle:
        def __init__(self) -> None:
            self.contexts: list[object] = []

        def reconcile(self, context) -> None:
            self.contexts.append(context)

    openbao = RecordingLifecycle()
    seaweedfs = RecordingLifecycle()
    deployer = _deployer_for_service(
        provider_name="seaweedfs",
        service_lifecycles={"openbao": openbao, "seaweedfs": seaweedfs},
    )

    deployer.deploy(target_type="service_instance", slug="seaweedfs")

    assert len(seaweedfs.contexts) == 1
    assert openbao.contexts == []


def test_service_lifecycle_absent_for_provider_is_a_no_op() -> None:
    deployer = _deployer_for_service(
        provider_name="postgres",
        service_lifecycles={"openbao": object()},
    )

    deployer.deploy(target_type="service_instance", slug="postgres")
```

Build `_deployer_for_service` from the fakes this module already uses to construct a `ProviderRuntimeDeployer` — reuse the existing fake repository / fake provider rather than inventing new ones. It must return a deployer whose repository yields a `service_instance` row for the given slug with a manifest whose `runtime.provider.name` is `provider_name`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_provider_deployer.py -k service_lifecycle -v`
Expected: FAIL — `ProviderRuntimeDeployer.__init__() got an unexpected keyword argument 'service_lifecycles'`.

- [ ] **Step 3: Replace the singular hook with a mapping**

In `src/nephos_api/providers/deployer.py`, change the constructor parameter and field:

```python
        service_lifecycles: Mapping[str, ServiceLifecycleProvisioner] | None = None,
    ) -> None:
        ...
        self._service_lifecycles = dict(service_lifecycles or {})
```

Add `Mapping` to the `collections.abc` import if it is not already imported.

Then replace the hardcoded branch in `deploy`:

```python
    def deploy(self, *, target_type: str, slug: str) -> None:
        context = self._context(target_type=target_type, slug=slug)
        self._provider_for(target_type).deploy(context)
        # A Service that needs post-deploy bootstrap (openbao init/unseal,
        # seaweedfs admin identity) registers a lifecycle under its provider
        # name. Keyed rather than branched so a second consumer needs no deployer
        # edit.
        if target_type == "service_instance":
            lifecycle = self._service_lifecycles.get(str(context.provider_name))
            if lifecycle is not None:
                lifecycle.reconcile(context)
```

- [ ] **Step 4: Update the single production call site**

In `src/nephos_api/main.py`, inside `default_provider_deployer_factory`, change the local variable and the argument. Replace `openbao_lifecycle = None` with:

```python
    service_lifecycles: dict[str, ServiceLifecycleProvisioner] = {}
```

Replace the assignment inside the `if settings.openbao_persistent:` branch:

```python
        service_lifecycles["openbao"] = KubernetesOpenBaoLifecycle(
            core_v1_api=core_v1_api,
            kv_mount=settings.bao_kv_mount,
        )
```

Replace the `ProviderRuntimeDeployer(...)` keyword `service_lifecycle=openbao_lifecycle` with:

```python
        service_lifecycles=service_lifecycles,
```

Add `ServiceLifecycleProvisioner` to the existing local import from `nephos_api.providers.service_lifecycle` at the top of the function.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_provider_deployer.py tests/test_openbao_lifecycle.py tests/test_main.py -q`
Expected: PASS. If any test constructs `ProviderRuntimeDeployer(service_lifecycle=...)`, update it to `service_lifecycles={"openbao": ...}`.

- [ ] **Step 6: Commit**

```bash
git add src/nephos_api/providers/deployer.py src/nephos_api/main.py tests/test_provider_deployer.py
git commit -m "refactor(deployer): key service lifecycle by provider name"
```

---

## Task 4: Seed the admin identity after deploy

**Objective:** SeaweedFS never serves anonymous S3 once Nephos has reconciled it. This is the security floor from the ADR.

**Files:**
- Create: `src/nephos_api/providers/seaweedfs_lifecycle.py`
- Modify: `src/nephos_api/main.py` (register the lifecycle)
- Test: `tests/test_seaweedfs_lifecycle.py`

**Interfaces:**
- Consumes: `ProviderContext` (`target_type`, `slug`, `provider_name`), `namespace_name` from `nephos_api.kubernetes_runtime`.
- Produces:
  - `class SeaweedShellRunner(Protocol)` with `run(*, core_v1_api, namespace, pod_name, commands: list[str]) -> str` — Task 5 imports and reuses this exact protocol.
  - `class KubernetesSeaweedShellRunner` implementing it.
  - `class KubernetesSeaweedFSLifecycle` with `reconcile(context) -> None`.
  - Module constants `ADMIN_IDENTITY = "nephos-admin"`, `ACCESS_KEY_SECRET_KEY = "access-key"`, `SECRET_KEY_SECRET_KEY = "secret-key"` — Task 5 imports these.

- [ ] **Step 1: Write the failing test**

Create `tests/test_seaweedfs_lifecycle.py`:

```python
import base64

import pytest

from nephos_api.providers.base import ProviderContext
from nephos_api.providers.seaweedfs_lifecycle import KubernetesSeaweedFSLifecycle


class FakeSecret:
    def __init__(self, data: dict[str, str]) -> None:
        self.data = {
            key: base64.b64encode(value.encode()).decode()
            for key, value in data.items()
        }
        self.metadata = type("Meta", (), {"name": "svc-seaweedfs-seaweedfs"})()


class FakeCoreV1Api:
    def __init__(self, secret: FakeSecret) -> None:
        self._secret = secret

    def read_namespaced_secret(self, *, namespace: str, name: str) -> FakeSecret:
        return self._secret

    def read_namespaced_pod(self, *, namespace: str, name: str) -> object:
        return object()


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, *, core_v1_api, namespace, pod_name, commands):
        self.commands.append(commands)
        return ""


def _context() -> ProviderContext:
    return ProviderContext(
        target_type="service_instance",
        slug="seaweedfs",
        runtime_name="svc-seaweedfs",
        manifest=None,
        chart=None,
        values={},
        provider_name="seaweedfs",
    )


def test_reconcile_seeds_admin_identity_from_the_service_secret() -> None:
    runner = RecordingRunner()
    lifecycle = KubernetesSeaweedFSLifecycle(
        core_v1_api=FakeCoreV1Api(
            FakeSecret({"access-key": "ADMINKEY", "secret-key": "ADMINSECRET"})
        ),
        exec_runner=runner,
    )

    lifecycle.reconcile(_context())

    assert len(runner.commands) == 1
    command = runner.commands[0][0]
    assert "s3.configure" in command
    assert "-user nephos-admin" in command
    assert "-access_key ADMINKEY" in command
    assert "-secret_key ADMINSECRET" in command
    assert "-actions Admin,Read,Write,List,Tagging" in command
    assert "-apply" in command
    # No -buckets: the admin identity is deliberately unscoped.
    assert "-buckets" not in command


def test_reconcile_targets_the_service_namespace_and_pod() -> None:
    runner = RecordingRunner()

    class CapturingRunner(RecordingRunner):
        def run(self, *, core_v1_api, namespace, pod_name, commands):
            self.namespace = namespace
            self.pod_name = pod_name
            return super().run(
                core_v1_api=core_v1_api,
                namespace=namespace,
                pod_name=pod_name,
                commands=commands,
            )

    capturing = CapturingRunner()
    lifecycle = KubernetesSeaweedFSLifecycle(
        core_v1_api=FakeCoreV1Api(
            FakeSecret({"access-key": "K", "secret-key": "S"})
        ),
        exec_runner=capturing,
    )

    lifecycle.reconcile(_context())

    assert capturing.namespace == "svc-seaweedfs"
    assert capturing.pod_name == "svc-seaweedfs-seaweedfs-0"


def test_reconcile_blocks_when_the_admin_secret_is_missing_a_key() -> None:
    from nephos_api.runtime_errors import RuntimeBlockedError

    lifecycle = KubernetesSeaweedFSLifecycle(
        core_v1_api=FakeCoreV1Api(FakeSecret({"access-key": "K"})),
        exec_runner=RecordingRunner(),
    )

    with pytest.raises(RuntimeBlockedError) as excinfo:
        lifecycle.reconcile(_context())
    assert excinfo.value.reason == "seaweedfs_admin_credentials_missing"
```

If `ProviderContext` requires additional fields, read its definition in `src/nephos_api/providers/base.py` and fill them in; keep `provider_name="seaweedfs"` and `slug="seaweedfs"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_seaweedfs_lifecycle.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nephos_api.providers.seaweedfs_lifecycle'`.

- [ ] **Step 3: Implement the lifecycle**

Create `src/nephos_api/providers/seaweedfs_lifecycle.py`:

```python
"""Post-deploy bootstrap for the SeaweedFS Service (ADR 20260816).

SeaweedFS serves S3 anonymously while its identity list is empty, so the admin
identity is not a convenience -- it is what closes the store. Seeding runs right
after deploy, mirroring KubernetesOpenBaoLifecycle.
"""

import base64
import shlex
from typing import Protocol

from kubernetes import client, stream

from nephos_api.kubernetes_runtime import namespace_name
from nephos_api.providers.base import ProviderContext
from nephos_api.runtime_errors import RuntimeBlockedError

ADMIN_IDENTITY = "nephos-admin"
ACCESS_KEY_SECRET_KEY = "access-key"
SECRET_KEY_SECRET_KEY = "secret-key"
ADMIN_ACTIONS = "Admin,Read,Write,List,Tagging"
_EXIT_MARKER = "NEPHOS_EXIT"


class SeaweedShellRunner(Protocol):
    def run(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        commands: list[str],
    ) -> str: ...


class KubernetesSeaweedShellRunner:
    """Pipe commands into `weed shell` inside the SeaweedFS pod.

    `weed shell` reads commands from stdin, so a batch is one exec. It exits 0
    even for a failed subcommand, so callers must inspect the returned text
    rather than trusting the exit code.
    """

    def run(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        namespace: str,
        pod_name: str,
        commands: list[str],
    ) -> str:
        # -filer is explicit on purpose. Relying on master discovery alone was
        # observed to fail with "error: getOrCreateConnection : fail to dial"
        # when the filer had not yet registered with the master, which would
        # make provisioning flaky on a freshly started pod.
        script = (
            "weed shell -master=localhost:9333 -filer=localhost:8888 "
            "<<'NEPHOS_WEED'\n"
            + "\n".join(commands)
            + "\nNEPHOS_WEED\n"
            f"printf '\\n{_EXIT_MARKER}:%s\\n' \"$?\""
        )
        response = stream.stream(
            core_v1_api.connect_get_namespaced_pod_exec,
            pod_name,
            namespace,
            command=["sh", "-lc", script],
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            _preload_content=False,
        )
        stdout: list[str] = []
        stderr: list[str] = []
        while response.is_open():
            response.update(timeout=1)
            if response.peek_stdout():
                stdout.append(response.read_stdout())
            if response.peek_stderr():
                stderr.append(response.read_stderr())
        response.close()
        return "".join(stdout) + "".join(stderr)


def s3_configure_command(
    *,
    user: str,
    access_key: str,
    secret_key: str,
    actions: str,
    bucket: str | None = None,
) -> str:
    parts = [
        "s3.configure",
        f"-user {shlex.quote(user)}",
        f"-access_key {shlex.quote(access_key)}",
        f"-secret_key {shlex.quote(secret_key)}",
        f"-actions {actions}",
    ]
    if bucket is not None:
        parts.append(f"-buckets {shlex.quote(bucket)}")
    parts.append("-apply")
    return " ".join(parts)


def seaweedfs_runtime(service_slug: str) -> tuple[str, str, str]:
    """(namespace, pod_name, secret_name) for a SeaweedFS Service instance."""
    release = namespace_name("service_instance", service_slug)
    name = f"{release}-seaweedfs"
    return release, f"{name}-0", name


class KubernetesSeaweedFSLifecycle:
    def __init__(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        exec_runner: SeaweedShellRunner | None = None,
    ) -> None:
        self._core_v1_api = core_v1_api
        self._exec_runner = exec_runner or KubernetesSeaweedShellRunner()

    def reconcile(self, context: ProviderContext) -> None:
        namespace, pod_name, secret_name = seaweedfs_runtime(context.slug)
        secret = self._core_v1_api.read_namespaced_secret(
            namespace=namespace, name=secret_name
        )
        access_key = _decode(secret, ACCESS_KEY_SECRET_KEY)
        secret_key = _decode(secret, SECRET_KEY_SECRET_KEY)
        self._core_v1_api.read_namespaced_pod(namespace=namespace, name=pod_name)
        # Re-applying an identical identity is a verified no-op, so this is safe
        # on every reconcile and does not rotate a live credential.
        self._exec_runner.run(
            core_v1_api=self._core_v1_api,
            namespace=namespace,
            pod_name=pod_name,
            commands=[
                s3_configure_command(
                    user=ADMIN_IDENTITY,
                    access_key=access_key,
                    secret_key=secret_key,
                    actions=ADMIN_ACTIONS,
                )
            ],
        )


def _decode(secret: object, key: str) -> str:
    data = getattr(secret, "data", None) or {}
    value = data.get(key)
    if value is None:
        raise RuntimeBlockedError(
            reason="seaweedfs_admin_credentials_missing",
            message=(
                f"SeaweedFS admin Secret is missing key {key!r}; the S3 API "
                "cannot be closed to anonymous access until it is present."
            ),
        )
    return base64.b64decode(value).decode()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_seaweedfs_lifecycle.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Register the lifecycle**

In `src/nephos_api/main.py`, in `default_provider_deployer_factory`, add after the openbao block:

```python
    # ADR 20260816: seed the SeaweedFS admin identity right after deploy.
    # SeaweedFS serves S3 anonymously while its identity list is empty.
    from nephos_api.providers.seaweedfs_lifecycle import KubernetesSeaweedFSLifecycle

    service_lifecycles["seaweedfs"] = KubernetesSeaweedFSLifecycle(
        core_v1_api=core_v1_api
    )
```

- [ ] **Step 6: Verify wiring and commit**

Run: `uv run ruff check src/nephos_api/providers/seaweedfs_lifecycle.py src/nephos_api/main.py tests/test_seaweedfs_lifecycle.py && uv run pytest tests/test_main.py tests/test_seaweedfs_lifecycle.py -q`
Expected: no lint errors, all tests pass.

```bash
git add src/nephos_api/providers/seaweedfs_lifecycle.py src/nephos_api/main.py tests/test_seaweedfs_lifecycle.py
git commit -m "feat(seaweedfs): seed the admin S3 identity after deploy"
```

---

## Task 5: Provision a bucket and a scoped identity per binding

**Objective:** An `object-storage/s3` binding gets its own bucket and its own identity restricted to that bucket, returning the five ADR 20260630 keys.

**Files:**
- Create: `src/nephos_api/provisioners/seaweedfs_client.py`
- Modify: `src/nephos_api/provisioners/seaweedfs.py` (add `recognized_entitlements`)
- Modify: `src/nephos_api/provisioners/__init__.py` and `src/nephos_api/provisioning.py` (export the client)
- Test: `tests/test_seaweedfs_provisioning.py`

**Interfaces:**
- Consumes: `SeaweedShellRunner`, `s3_configure_command`, `seaweedfs_runtime` from `nephos_api.providers.seaweedfs_lifecycle` (Task 4); `BindingProvisioningContext`; `binding_secret_labels`, `namespace_labels`, `namespace_name`, `KubernetesRuntimeSafetyError` from `nephos_api.kubernetes_runtime`.
- Produces: `KubernetesSeaweedFSProvisioningClient(core_v1_api=..., exec_runner=None, key_factory=None)` satisfying the existing `SeaweedFSProvisioningClient` protocol (`ensure_s3_binding`, `delete_s3_binding`). Task 6 constructs it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_seaweedfs_provisioning.py`:

```python
import base64

import pytest

from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.provisioners.seaweedfs_client import (
    KubernetesSeaweedFSProvisioningClient,
)


class FakeSecret:
    def __init__(self, data: dict[str, str], labels: dict[str, str] | None = None):
        self.data = {
            key: base64.b64encode(value.encode()).decode()
            for key, value in data.items()
        }
        self.metadata = type(
            "Meta",
            (),
            {"name": "s", "namespace": "svc-seaweedfs", "labels": labels or {}},
        )()


class FakeCoreV1Api:
    def __init__(self) -> None:
        self.secrets: dict[str, FakeSecret] = {}
        self.created: list[dict] = []
        self.deleted: list[str] = []
        self.namespace_labels: dict[str, str] = {}

    def read_namespace(self, *, name: str):
        return type(
            "NS",
            (),
            {
                "metadata": type(
                    "Meta",
                    (),
                    {"labels": self.namespace_labels, "deletion_timestamp": None},
                )()
            },
        )()

    def read_namespaced_secret(self, *, namespace: str, name: str):
        from kubernetes.client.rest import ApiException

        if name not in self.secrets:
            raise ApiException(status=404)
        return self.secrets[name]

    def create_namespaced_secret(self, *, namespace: str, body):
        self.created.append({"namespace": namespace, "body": body})
        self.secrets[body.metadata.name] = FakeSecret(
            dict(body.string_data), dict(body.metadata.labels or {})
        )

    def delete_namespaced_secret(self, *, namespace: str, name: str):
        self.deleted.append(name)
        self.secrets.pop(name, None)

    def read_namespaced_pod(self, *, namespace: str, name: str):
        return object()


class RecordingRunner:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def run(self, *, core_v1_api, namespace, pod_name, commands):
        self.batches.append(commands)
        return ""


def _context() -> BindingProvisioningContext:
    return BindingProvisioningContext(
        binding_id="bind-1",
        app_slug="notes",
        service_slug="seaweedfs",
        alias="blobs",
        capability="object-storage",
        protocol="s3",
    )


def _client(api: FakeCoreV1Api, runner: RecordingRunner):
    from nephos_api.kubernetes_runtime import namespace_labels

    api.namespace_labels = dict(namespace_labels("service_instance", "seaweedfs"))
    api.secrets["svc-seaweedfs-seaweedfs"] = FakeSecret(
        {"access-key": "ADMINKEY", "secret-key": "ADMINSECRET"}
    )
    keys = iter(["APPKEY", "APPSECRET"])
    return KubernetesSeaweedFSProvisioningClient(
        core_v1_api=api,
        exec_runner=runner,
        key_factory=lambda length: next(keys),
    )


def test_ensure_returns_the_adr_output_contract() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()

    values = _client(api, runner).ensure_s3_binding(_context())

    assert set(values) == {
        "endpointUrl",
        "bucket",
        "accessKeyId",
        "secretAccessKey",
        "region",
    }
    assert values["region"] == "us-east-1"
    assert values["endpointUrl"] == (
        "http://svc-seaweedfs-seaweedfs.svc-seaweedfs.svc.cluster.local:8333"
    )
    assert values["bucket"] == "nephos-notes-blobs"
    assert values["accessKeyId"] == "APPKEY"
    assert values["secretAccessKey"] == "APPSECRET"


def test_ensure_creates_the_bucket_and_scopes_the_identity_to_it() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()

    _client(api, runner).ensure_s3_binding(_context())

    commands = runner.batches[0]
    assert commands[0] == "s3.bucket.create -name nephos-notes-blobs"
    configure = commands[1]
    assert "-user nephos-notes-blobs" in configure
    assert "-buckets nephos-notes-blobs" in configure
    assert "-actions Read,Write,List,Tagging" in configure
    assert "Admin" not in configure


def test_ensure_is_idempotent_and_never_rotates_an_existing_credential() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()
    client = _client(api, runner)

    first = client.ensure_s3_binding(_context())
    second = client.ensure_s3_binding(_context())

    assert first == second
    assert len(api.created) == 1


def test_delete_revokes_the_identity_and_removes_the_bucket() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()
    client = _client(api, runner)
    client.ensure_s3_binding(_context())

    client.delete_s3_binding(_context())

    commands = runner.batches[-1]
    assert commands[0] == "s3.configure -user nephos-notes-blobs -delete -apply"
    assert commands[1] == "s3.bucket.delete -name nephos-notes-blobs"
    assert "nephos-s3-notes-blobs" in api.deleted


def test_delete_is_a_no_op_when_nothing_was_provisioned() -> None:
    api, runner = FakeCoreV1Api(), RecordingRunner()

    _client(api, runner).delete_s3_binding(_context())

    assert runner.batches == []
    assert api.deleted == []


def test_refuses_an_unowned_service_namespace() -> None:
    from nephos_api.kubernetes_runtime import KubernetesRuntimeSafetyError

    api, runner = FakeCoreV1Api(), RecordingRunner()
    client = _client(api, runner)
    api.namespace_labels = {"app.kubernetes.io/managed-by": "someone-else"}

    with pytest.raises(KubernetesRuntimeSafetyError):
        client.ensure_s3_binding(_context())


def test_shell_failure_blocks_loudly() -> None:
    from nephos_api.runtime_errors import RuntimeBlockedError

    class FailingRunner(RecordingRunner):
        def run(self, *, core_v1_api, namespace, pod_name, commands):
            super().run(
                core_v1_api=core_v1_api,
                namespace=namespace,
                pod_name=pod_name,
                commands=commands,
            )
            return "error: bucket already exists with different owner"

    api, runner = FakeCoreV1Api(), FailingRunner()

    with pytest.raises(RuntimeBlockedError) as excinfo:
        _client(api, runner).ensure_s3_binding(_context())
    assert excinfo.value.reason == "seaweedfs_provisioning_failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_seaweedfs_provisioning.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nephos_api.provisioners.seaweedfs_client'`.

- [ ] **Step 3: Implement the client**

Create `src/nephos_api/provisioners/seaweedfs_client.py`:

```python
"""Live SeaweedFS S3 provisioning over `weed shell` (ADR 20260816).

One bucket and one bucket-scoped identity per binding. Credentials are cached in
an owned Secret in the Service namespace so a reconcile re-reads rather than
rotates -- an App holding a working key must never have it changed underneath it.
"""

import base64
import hashlib
import secrets
import string
from collections.abc import Callable

from kubernetes import client
from kubernetes.client.rest import ApiException

from nephos_api.kubernetes_runtime import (
    KubernetesRuntimeSafetyError,
    binding_secret_labels,
    namespace_labels,
)
from nephos_api.providers.seaweedfs_lifecycle import (
    SeaweedShellRunner,
    KubernetesSeaweedShellRunner,
    s3_configure_command,
    seaweedfs_runtime,
)
from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.runtime_errors import RuntimeBlockedError

REGION = "us-east-1"
BINDING_ACTIONS = "Read,Write,List,Tagging"
_ALPHABET = string.ascii_letters + string.digits
# `weed shell` exits 0 even when a subcommand fails, so failure is detected in
# the output text. Deliberately narrow: SeaweedFS prefixes real failures with
# "error:", and a broader match (e.g. the bare word "failed") false-positives on
# the body of those same messages. Verified no-ops that must NOT trip this:
# re-creating an existing bucket, deleting a missing bucket, deleting a missing
# identity -- all three print no error.
_ERROR_MARKERS = ("error:", "panic:")


def _generate_key(length: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


class KubernetesSeaweedFSProvisioningClient:
    def __init__(
        self,
        *,
        core_v1_api: client.CoreV1Api,
        exec_runner: SeaweedShellRunner | None = None,
        key_factory: Callable[[int], str] | None = None,
    ) -> None:
        self._core_v1_api = core_v1_api
        self._exec_runner = exec_runner or KubernetesSeaweedShellRunner()
        self._key_factory = key_factory or _generate_key

    def ensure_s3_binding(
        self,
        context: BindingProvisioningContext,
    ) -> dict[str, str]:
        namespace, pod_name, _ = seaweedfs_runtime(context.service_slug)
        _assert_active_owned_service_namespace(
            self._core_v1_api,
            service_slug=context.service_slug,
            namespace=namespace,
        )
        bucket = _bucket_name(context)
        credentials = self._ensure_credential_secret(
            context, namespace=namespace, bucket=bucket
        )
        self._core_v1_api.read_namespaced_pod(namespace=namespace, name=pod_name)
        self._shell(
            namespace=namespace,
            pod_name=pod_name,
            commands=[
                f"s3.bucket.create -name {bucket}",
                s3_configure_command(
                    user=bucket,
                    access_key=credentials["accessKeyId"],
                    secret_key=credentials["secretAccessKey"],
                    actions=BINDING_ACTIONS,
                    bucket=bucket,
                ),
            ],
        )
        return {
            "endpointUrl": _endpoint_url(context.service_slug),
            "bucket": bucket,
            "accessKeyId": credentials["accessKeyId"],
            "secretAccessKey": credentials["secretAccessKey"],
            "region": REGION,
        }

    def delete_s3_binding(self, context: BindingProvisioningContext) -> None:
        namespace, pod_name, _ = seaweedfs_runtime(context.service_slug)
        _assert_active_owned_service_namespace(
            self._core_v1_api,
            service_slug=context.service_slug,
            namespace=namespace,
        )
        name = _credential_secret_name(context)
        existing = _read_optional_secret(
            self._core_v1_api, namespace=namespace, name=name
        )
        if existing is None:
            return
        _assert_owned_credential_secret(existing, context=context, name=name)
        bucket = _bucket_name(context)
        self._core_v1_api.read_namespaced_pod(namespace=namespace, name=pod_name)
        self._shell(
            namespace=namespace,
            pod_name=pod_name,
            commands=[
                f"s3.configure -user {bucket} -delete -apply",
                f"s3.bucket.delete -name {bucket}",
            ],
        )
        self._core_v1_api.delete_namespaced_secret(namespace=namespace, name=name)

    def _shell(self, *, namespace: str, pod_name: str, commands: list[str]) -> str:
        output = self._exec_runner.run(
            core_v1_api=self._core_v1_api,
            namespace=namespace,
            pod_name=pod_name,
            commands=commands,
        )
        if any(marker in output for marker in _ERROR_MARKERS):
            raise RuntimeBlockedError(
                reason="seaweedfs_provisioning_failed",
                message=f"weed shell reported a failure: {output.strip()[:400]}",
            )
        return output

    def _ensure_credential_secret(
        self,
        context: BindingProvisioningContext,
        *,
        namespace: str,
        bucket: str,
    ) -> dict[str, str]:
        name = _credential_secret_name(context)
        existing = _read_optional_secret(
            self._core_v1_api, namespace=namespace, name=name
        )
        if existing is not None:
            _assert_owned_credential_secret(existing, context=context, name=name)
            return {
                "accessKeyId": _decode_secret_key(existing, "accessKeyId"),
                "secretAccessKey": _decode_secret_key(existing, "secretAccessKey"),
            }
        credentials = {
            "accessKeyId": self._key_factory(20),
            "secretAccessKey": self._key_factory(40),
        }
        self._core_v1_api.create_namespaced_secret(
            namespace=namespace,
            body=client.V1Secret(
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=namespace,
                    labels=binding_secret_labels(
                        app_slug=context.app_slug,
                        service_slug=context.service_slug,
                        alias=context.alias,
                        capability=context.capability,
                        protocol=context.protocol,
                    ),
                ),
                type="Opaque",
                string_data=credentials,
            ),
        )
        return credentials


def _endpoint_url(service_slug: str) -> str:
    namespace, _, name = seaweedfs_runtime(service_slug)
    return f"http://{name}.{namespace}.svc.cluster.local:8333"


def _bucket_name(context: BindingProvisioningContext) -> str:
    # S3 bucket names are DNS labels: lowercase, 3-63 chars, no underscores.
    base = f"nephos-{context.app_slug}-{context.alias}".lower().replace("_", "-")
    if len(base) <= 63:
        return base
    suffix = hashlib.sha256(context.binding_id.encode()).hexdigest()[:12]
    return f"{base[: 63 - len(suffix) - 1].rstrip('-')}-{suffix}"


def _credential_secret_name(context: BindingProvisioningContext) -> str:
    base = f"nephos-s3-{context.app_slug}-{context.alias}"
    if len(base) <= 63:
        return base
    suffix = hashlib.sha256(context.binding_id.encode()).hexdigest()[:12]
    return f"{base[: 63 - len(suffix) - 1].rstrip('-')}-{suffix}"


def _read_optional_secret(core_v1_api, *, namespace: str, name: str):
    try:
        return core_v1_api.read_namespaced_secret(namespace=namespace, name=name)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise


def _decode_secret_key(secret, key: str) -> str:
    data = secret.data or {}
    value = data.get(key)
    if value is None:
        raise RuntimeError(f"Secret {secret.metadata.name} is missing key {key}")
    return base64.b64decode(value).decode()


def _assert_active_owned_service_namespace(
    core_v1_api, *, service_slug: str, namespace: str
) -> None:
    try:
        namespace_resource = core_v1_api.read_namespace(name=namespace)
    except ApiException as exc:
        if exc.status == 404:
            namespace_resource = None
        else:
            raise
    if namespace_resource is None or namespace_resource.metadata is None:
        raise KubernetesRuntimeSafetyError(
            f"refusing to use unowned namespace {namespace}"
        )
    labels = namespace_resource.metadata.labels or {}
    expected = namespace_labels("service_instance", service_slug)
    if not all(labels.get(key) == value for key, value in expected.items()):
        raise KubernetesRuntimeSafetyError(
            f"refusing to use unowned namespace {namespace}"
        )
    if namespace_resource.metadata.deletion_timestamp is not None:
        raise KubernetesRuntimeSafetyError(
            f"refusing to use terminating namespace {namespace}"
        )


def _assert_owned_credential_secret(
    secret, *, context: BindingProvisioningContext, name: str
) -> None:
    if secret.metadata is None:
        raise KubernetesRuntimeSafetyError(f"refusing to use unowned Secret {name}")
    labels = secret.metadata.labels or {}
    expected = binding_secret_labels(
        app_slug=context.app_slug,
        service_slug=context.service_slug,
        alias=context.alias,
        capability=context.capability,
        protocol=context.protocol,
    )
    if not all(labels.get(key) == value for key, value in expected.items()):
        namespace = getattr(secret.metadata, "namespace", "?")
        raise KubernetesRuntimeSafetyError(
            f"refusing to use unowned Secret {namespace}/{name}"
        )
```

- [ ] **Step 4: Declare the engine's entitlement surface**

In `src/nephos_api/provisioners/seaweedfs.py`, add to `SeaweedFSS3Provisioner`, directly above `__init__`:

```python
    # ADR 20260721 + ADR 20260816: the object-storage engine grants no elevated
    # entitlements. There is no cross-bucket admin grant for S3; a consumer that
    # needs one must arrive with its own decision.
    recognized_entitlements = frozenset()
```

- [ ] **Step 5: Export the client**

In `src/nephos_api/provisioners/__init__.py`, add the import and `__all__` entry:

```python
from nephos_api.provisioners.seaweedfs_client import (
    KubernetesSeaweedFSProvisioningClient,
)
```

Add `"KubernetesSeaweedFSProvisioningClient"` to `__all__`, keeping the list alphabetically sorted. Make the same two additions in `src/nephos_api/provisioning.py`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_seaweedfs_provisioning.py -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Lint and commit**

Run: `uv run ruff check src/nephos_api/provisioners/ tests/test_seaweedfs_provisioning.py && uv run pytest tests/test_alpha_backbone_provisioning.py -q`
Expected: no lint errors, existing provisioning tests still pass.

```bash
git add src/nephos_api/provisioners/ src/nephos_api/provisioning.py tests/test_seaweedfs_provisioning.py
git commit -m "feat(seaweedfs): provision a scoped bucket and identity per S3 binding"
```

---

## Task 6: Register the object-storage engine

**Objective:** A binding declaring `object-storage/s3` against `seaweedfs` routes to the live provisioner instead of blocking.

**Files:**
- Modify: `.nephos/registries/core-registry/services/seaweedfs/service.yaml`
- Modify: `src/nephos_api/main.py:541-579` (`_build_provisioning_engines`)
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `SeaweedFSS3Provisioner` and `KubernetesSeaweedFSProvisioningClient` (Task 5).
- Produces: `_build_provisioning_engines()` returns a mapping including key `"object-storage"`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_main.py`:

```python
def test_provisioning_engines_include_object_storage() -> None:
    from nephos_api.main import _build_provisioning_engines

    engines = _build_provisioning_engines(_settings(), core_v1_api=object())

    assert "object-storage" in engines
    assert engines["object-storage"].recognized_entitlements == frozenset()


def test_seaweedfs_manifest_declares_the_object_storage_engine() -> None:
    entry = _core_registry_service_manifest("seaweedfs")

    assert entry.spec.provisioning.engine == "object-storage"
```

Use whatever settings helper the module already has in place of `_settings()`, and whatever manifest-loading helper exists in place of `_core_registry_service_manifest`; if neither exists, load the manifest with the catalog loader the other tests in this file use.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main.py -k "object_storage or seaweedfs" -v`
Expected: FAIL — `"object-storage" not in engines`, and `engine` is `None`.

- [ ] **Step 3: Declare the engine in the manifest**

In `.nephos/registries/core-registry/services/seaweedfs/service.yaml`, change the `provisioning` block to:

```yaml
  provisioning:
    mode: app-scoped-resource
    # ADR 20260718 + ADR 20260816: route object-storage bindings to the
    # backend object-storage engine. Engine name follows the capability name,
    # matching sql / oidc / opencypher.
    engine: object-storage
```

- [ ] **Step 4: Register the engine**

In `src/nephos_api/main.py`, inside `_build_provisioning_engines`, add the import alongside the existing `arcadedb_client` import:

```python
    from nephos_api.provisioners.seaweedfs_client import (
        KubernetesSeaweedFSProvisioningClient,
    )
```

Add to the returned dict, after the `opencypher` entry:

```python
        # ADR 20260816: one bucket and one bucket-scoped identity per binding,
        # applied through `weed shell` inside the Service pod.
        "object-storage": SeaweedFSS3Provisioner(
            client=KubernetesSeaweedFSProvisioningClient(core_v1_api=core_v1_api),
        ),
```

Add `SeaweedFSS3Provisioner` to the existing `from nephos_api.provisioning import (...)` list inside that function.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_main.py -k "object_storage or seaweedfs" -v`
Expected: PASS

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run ruff check . && uv run pytest -q && uv lock --check`
Expected: no lint errors, full suite green, lockfile unchanged.

```bash
git add src/nephos_api/main.py .nephos/registries/core-registry/services/seaweedfs/service.yaml tests/test_main.py
git commit -m "feat(seaweedfs): register the object-storage provisioning engine"
```

---

## Task 7: Prove it against the live cluster and document it

**Objective:** Demonstrate the whole loop on k3d — one-click install, a real binding, verified isolation, clean teardown — and update the Service README. Nothing here is complete until the observable state is checked, not the exit code.

**Files:**
- Modify: `.nephos/registries/core-registry/services/seaweedfs/README.md`
- Modify: `PLANS.md` (mark the addendum done)

**Interfaces:**
- Consumes: everything from Tasks 1-6.
- Produces: no code.

- [ ] **Step 1: Deploy the rebuilt control plane**

Follow the `run-nephos-api` skill's k3d deploy flow (docker build → `k3d image import` → `kubectl rollout restart`). Then confirm the new code is actually running rather than trusting the rollout's exit code:

```bash
kubectl -n nephos-system get pods -l app=nephos-api
kubectl -n nephos-system exec deploy/nephos-api -- \
  python -c "import nephos_api.providers.seaweedfs_lifecycle as m; print(m.ADMIN_IDENTITY)"
```

Expected: prints `nephos-admin`. If the module is missing, the image did not update — re-import and restart.

- [ ] **Step 2: Install SeaweedFS with an empty config**

Install `seaweedfs` from the core registry passing `config={}` (via the console or the API, whichever the `run-nephos-api` skill documents). Expected: install succeeds with no `service_config_required` error. Then:

```bash
kubectl -n svc-seaweedfs get statefulset,pod,secret
kubectl -n svc-seaweedfs get pod svc-seaweedfs-seaweedfs-0 -o jsonpath='{.spec.containers[0].args}'
```

Expected: pod Running; args contain `-s3` but **no** `-s3.config`; Secret `svc-seaweedfs-seaweedfs` has keys `access-key` and `secret-key`.

- [ ] **Step 3: Verify the admin identity was seeded and anonymous access is closed**

```bash
kubectl -n svc-seaweedfs exec svc-seaweedfs-seaweedfs-0 -- \
  sh -lc "echo s3.configure | weed shell -master=localhost:9333 -filer=localhost:8888" | sed -n '/{/,$p'
```

Expected: JSON containing an identity named `nephos-admin` with `Admin` in its actions.

```bash
kubectl -n svc-seaweedfs exec svc-seaweedfs-seaweedfs-0 -- \
  wget -qO- -S http://localhost:8333/ 2>&1 | head -5
```

Expected: `403` / `AccessDenied`. A `200` here means the store is open — stop and fix before continuing.

- [ ] **Step 4: Bind an App and verify isolation end to end**

Install an App that requires `object-storage/s3` (use `mythos-mail-ingress`, or add a temporary App manifest requiring `object-storage/s3`). Then:

```bash
kubectl -n svc-seaweedfs get secrets | grep nephos-s3-
kubectl -n svc-seaweedfs exec svc-seaweedfs-seaweedfs-0 -- \
  sh -lc "echo s3.bucket.list | weed shell -master=localhost:9333 -filer=localhost:8888"
```

Expected: a `nephos-s3-<app>-<alias>` Secret exists, and the bucket list contains `nephos-<app>-<alias>`.

Confirm the App-side Secret carries exactly the five ADR keys:

```bash
kubectl -n app-<app-slug> get secret -l nephos.pro/capability=object-storage \
  -o jsonpath='{.items[0].data}' | python3 -m json.tool
```

Expected keys: `endpointUrl`, `bucket`, `accessKeyId`, `secretAccessKey`, `region` — and nothing else.

Then prove the scoping actually holds by using the binding's own credentials against a second bucket. Create a decoy bucket and confirm the App identity is refused:

```bash
kubectl -n svc-seaweedfs exec svc-seaweedfs-seaweedfs-0 -- \
  sh -lc "echo 's3.bucket.create -name decoy' | weed shell -master=localhost:9333 -filer=localhost:8888"
kubectl -n svc-seaweedfs exec svc-seaweedfs-seaweedfs-0 -- \
  sh -lc "echo s3.configure | weed shell -master=localhost:9333 -filer=localhost:8888" | sed -n '/{/,$p'
```

Expected: the App's identity lists actions as `Read:nephos-<app>-<alias>` etc. — bucket-suffixed, never bare `Read`, and never `Admin`. Clean up the decoy with `s3.bucket.delete -name decoy`.

- [ ] **Step 5: Verify teardown**

Uninstall the App, then:

```bash
kubectl -n svc-seaweedfs get secrets | grep nephos-s3- || echo "credential secret gone"
kubectl -n svc-seaweedfs exec svc-seaweedfs-seaweedfs-0 -- \
  sh -lc "echo s3.configure | weed shell -master=localhost:9333 -filer=localhost:8888" | sed -n '/{/,$p'
```

Expected: the credential Secret is gone and the App identity no longer appears; `nephos-admin` is still present.

Then destroy the Service and confirm the namespace terminates.

- [ ] **Step 6: Update the Service README**

Rewrite `.nephos/registries/core-registry/services/seaweedfs/README.md` to state: install requires no operator input (both S3 admin keys are generated); identities live in the filer, so the S3 API is provisioned at runtime; each binding receives a dedicated bucket and a bucket-scoped identity; and the binding output keys are `endpointUrl`, `bucket`, `accessKeyId`, `secretAccessKey`, `region`. Note the ADR by filename.

- [ ] **Step 7: Record the outcome and commit**

Add a "Result" line to the PLANS.md addendum stating what was verified live, including the 403-anonymous check and the bucket-scoped action list. If anything in Task 1-6 turned out wrong during live verification, append it to the plan's flaw log rather than silently fixing it.

```bash
git add .nephos/registries/core-registry/services/seaweedfs/README.md PLANS.md
git commit -m "docs(seaweedfs): record turnkey install and S3 binding provisioning"
```

---

## Verification Commands

Run before opening a PR:

```bash
uv run ruff check .
uv run pytest -q
uv lock --check
git diff --check
```

---

## Flaw Log

Append here whenever executing this plan proves part of it wrong. The point is
not the fix — it is the evidence about how the plan was built.

- **2026-08-16, found during self-review, before execution.** The plan
  originally specified `weed shell -master=localhost:9333` with no `-filer`,
  copied from an earlier successful probe where the filer happened to be
  discovered through the master. Re-probing on a freshly started container
  showed master-only discovery failing with
  `error: getOrCreateConnection : fail to dial : failed to exit idle mode`, which
  would have made provisioning intermittently fail on a cold pod and produced a
  confusing `seaweedfs_provisioning_failed` rather than an obvious cause.
  *Root cause of the planning error:* asserting a command form from one
  observation instead of testing the form the plan actually prescribed. The same
  pass also revealed the `_ERROR_MARKERS` list was too broad (`"failed"` matches
  the body of SeaweedFS's own error text). Both fixed before Task 1 began.
