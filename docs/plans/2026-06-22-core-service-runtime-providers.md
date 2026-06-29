# Core Service Runtime Providers Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add Pulumi-backed runtime providers for the Nephos alpha backbone Services: PostgreSQL, Zitadel, SeaweedFS, and ArcadeDB.

**Architecture:** Runtime providers live behind `src/nephos_api/providers/`. Raw Pulumi Kubernetes resources are preferred where simple. Helm may be used inside Pulumi provider code for complex Services, but Service manifests and API responses must not become Helm-shaped.

**Tech Stack:** Pulumi Automation API, Pulumi Kubernetes provider, optional Pulumi Helm Release, Kubernetes Python client for status checks, pytest fake runners.

---

## Service Provider Strategy

| Service | Initial install strategy | Reason |
| --- | --- | --- |
| PostgreSQL | Existing raw Pulumi StatefulSet, adapted to `sql/postgres` | Already proven by smoke. |
| Zitadel | Helm through Pulumi unless raw resources prove simpler | Multi-component auth system; chart likely reduces bootstrap risk. |
| SeaweedFS | Helm through Pulumi unless a single-node raw deployment is simple enough | S3 API wiring and volumes are easier from chart defaults. |
| ArcadeDB | Raw Pulumi StatefulSet first | Single server is enough for alpha and avoids chart dependence if no good chart exists. |

## Task 1: Replace workload enum with provider registry shape

**Objective:** Avoid hardcoding only `reference-app` and `postgres-service` in `PulumiKubernetesProvider`.

**Files:**
- Modify: `src/nephos_api/providers/kubernetes.py`
- Modify: `src/nephos_api/providers/router.py` if needed
- Tests: `tests/test_pulumi_kubernetes_provider.py`, `tests/test_provider_router.py`

**Steps:**
1. Introduce a registry mapping provider runtime names to Pulumi program functions, for example:
   ```python
   _WORKLOAD_PROGRAMS = {
       "reference-app": _reference_app,
       "postgres-service": _postgres_service,
       "zitadel-service": _zitadel_service,
       "seaweedfs-service": _seaweedfs_service,
       "arcadedb-service": _arcadedb_service,
   }
   ```
2. Keep current names backward compatible.
3. Add tests for unknown runtime provider blocking with `runtime_provider_unknown` or clear provider error.
4. Run targeted tests.

## Task 2: Keep PostgreSQL provider green under new naming

**Objective:** Ensure PostgreSQL still deploys and is selected as `sql/postgres` after protocol-aware catalog support lands.

**Files:**
- Modify: `src/nephos_api/providers/kubernetes.py`
- Modify: `src/nephos_api/dev_reference.py` only if not already changed by Agent A
- Tests: `tests/test_pulumi_kubernetes_provider.py`, `tests/test_postgres_provisioning.py`

**Steps:**
1. Keep Kubernetes resource names stable enough for existing provisioner conventions:
   - namespace: `svc-<slug>`
   - admin Secret: `svc-<slug>-postgresql`
   - pod: `svc-<slug>-postgresql-0`
   - host: `svc-<slug>-postgresql.svc-<slug>.svc.cluster.local`
2. Do not change secret key names without updating `PostgresAppScopedProvisioner` tests.
3. Run targeted tests.

## Task 3: Add Zitadel runtime provider stub and tests

**Objective:** Add a provider route for Zitadel that can be unit-tested before live cluster deployment.

**Files:**
- Modify: `src/nephos_api/providers/kubernetes.py` or create `src/nephos_api/providers/zitadel.py`
- Tests: `tests/test_pulumi_kubernetes_provider.py`

**Steps:**
1. Add `_zitadel_service(spec, k8s, opts)` or a Helm-backed helper.
2. Required alpha values:
   - external/local host suffix from Nephos platform domain mapping later
   - admin bootstrap username/password generated or provided by config
   - database mode suitable for local alpha
3. If using Helm, wrap `pulumi_kubernetes.helm.v3.Release` inside the Pulumi program, not a direct CLI call.
4. Unit-test that the Pulumi runner receives workload `zitadel-service` and values are forwarded.
5. Do not claim live health until smoke verifies it.

## Task 4: Add SeaweedFS runtime provider stub and tests

**Objective:** Add the `seaweedfs-service` provider route with S3 endpoint intent.

**Files:**
- Modify/Create provider module under `src/nephos_api/providers/`
- Tests: `tests/test_pulumi_kubernetes_provider.py`

**Steps:**
1. Choose Helm-under-Pulumi or raw single-node deployment.
2. Expose internal S3 endpoint with stable Service name for binding provisioners.
3. Provide admin/access credentials as Kubernetes Secret values under Nephos-owned namespace.
4. Unit-test provider dispatch and redaction-safe values handling.

## Task 5: Add ArcadeDB runtime provider stub and tests

**Objective:** Add raw Pulumi Kubernetes runtime for a single-node local ArcadeDB Service.

**Files:**
- Modify/Create provider module under `src/nephos_api/providers/`
- Tests: `tests/test_pulumi_kubernetes_provider.py`

**Steps:**
1. Create Secret for root/admin credential.
2. Create Service exposing HTTP and any enabled binary/client ports needed for alpha.
3. Create StatefulSet with PVC.
4. Make Gremlin and Mongo ports/features controlled by explicit values and default them off if enabling them requires extra runtime config.
5. Unit-test resource program dispatch with fake runner.

## Task 6: Add catalog draft manifests for provider testing only

**Objective:** Provide non-canonical draft manifests for agent tests and smoke before promotion.

**Files:**
- Create under `.agents/drafts/manifests/core/services/<service>/service.yaml` unless Fer approves canonical catalog promotion.
- Tests may generate temporary catalog roots instead of reading drafts.

**Draft Service provides:**

```yaml
postgres:   sql/postgres
zitadel:    oidc/oidc, service-account/jwt
seaweedfs:  object-storage/s3
arcadedb:   sql/arcadedb, opencypher/bolt, opencypher/n4j, optional gremlin/gremlin, optional mongo/mongo
```

## Task 7: Full verification

Run:

```bash
uv lock --check
uv run ruff check .
uv run pytest -q
git diff --check
```

Commit message:

```bash
git commit -m "feat: add alpha backbone service providers"
```
