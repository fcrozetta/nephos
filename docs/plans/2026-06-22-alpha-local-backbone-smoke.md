# Alpha Local Backbone Smoke Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add a local runtime smoke that installs the alpha backbone Services and verifies app-local connection material for auth, SQL, S3 object storage, and graph access.

**Architecture:** The smoke drives Nephos through API desired state and persisted reconciliation, not direct provider calls. It uses temporary catalog roots and temporary SQLite state. It verifies Kubernetes resources only through Nephos-owned labels/namespaces and connection behavior through app-side binding Secrets.

**Tech Stack:** Existing `nephos-api dev smoke` pattern, FastAPI TestClient, Kubernetes Python client, Pulumi local backend, pytest.

---

## Task 1: Create temporary alpha backbone catalog generator

**Objective:** Generate non-canonical temporary catalog entries for smoke tests.

**Files:**
- Modify: `src/nephos_api/dev_reference.py` or create `src/nephos_api/dev_backbone.py`
- Tests: `tests/test_dev_reference.py` or new `tests/test_dev_backbone.py`

**Catalog entries:**
- Service `postgres`: provides `sql/postgres`.
- Service `zitadel`: provides `oidc/oidc` and `service-account/jwt`; exposes service surfaces as metadata only if the accepted manifest shape exists.
- Service `seaweedfs`: provides `object-storage/s3`.
- Service `arcadedb`: provides `sql/arcadedb`, `opencypher/bolt`, `opencypher/n4j`, optional `gremlin/gremlin`, optional `mongo/mongo`.
- App `backbone-check`: requires `sql/postgres`, `oidc/oidc`, `object-storage/s3`, `opencypher/bolt`.

**Steps:**
1. Generate manifests under a temp directory, not repo `catalog/`.
2. Validate them with `CatalogLoader` in tests.
3. Do not promote to canonical examples in this task.

## Task 2: Add `nephos-api dev backbone-smoke` command

**Objective:** Provide a human-run alpha proof separate from the existing small reference smoke.

**Files:**
- Modify: `src/nephos_api/cli.py`
- Create/Modify: `src/nephos_api/dev_backbone.py`
- Tests: `tests/test_cli.py`, `tests/test_packaging.py`

**Steps:**
1. Add command:
   ```bash
   uv run nephos-api dev backbone-smoke --timeout-seconds 600
   ```
2. Reuse command structure from existing `dev smoke`.
3. Require `PULUMI_CONFIG_PASSPHRASE` or pass through existing runtime blocker cleanly.
4. Ensure packaging test includes new module.

## Task 3: Implement desired-state install flow

**Objective:** Install Services and App through API endpoints and wait for reconciliation.

**Files:**
- Create/Modify: `src/nephos_api/dev_backbone.py`

**Steps:**
1. Init temp DB and internal domain.
2. Start app/reconciler using TestClient pattern.
3. POST `/services` for each backbone Service.
4. Wait until each Service status is healthy/running or blocked with actionable evidence.
5. POST `/apps` for `backbone-check`, selecting providers explicitly by binding alias.
6. Wait for bindings and App reconcile.
7. Print a concise success/failure summary.

## Task 4: Verify binding Secret material without leaking values

**Objective:** Prove each app-side Secret has expected keys while logs/status remain redacted.

**Files:**
- Create/Modify: `src/nephos_api/dev_backbone.py`
- Tests: use fake Kubernetes client where possible.

**Expected App Secret key checks:**
- SQL/Postgres: `host`, `port`, `database`, `username`, `password`, `uri`.
- OIDC: `issuerUrl`, `clientId`, `clientSecret`.
- S3: `endpointUrl`, `bucket`, `accessKeyId`, `secretAccessKey`, `region`.
- openCypher/Bolt: `host`, `port`, `database`, `username`, `password`, `protocol`, `uri`.

**Steps:**
1. Read Secrets from App namespace using Kubernetes API.
2. Verify keys exist and values are non-empty.
3. Do not print raw values.
4. Verify API binding summaries do not include raw secret values.

## Task 5: Add optional in-cluster connection probe

**Objective:** Prove local connections work from inside the cluster when safe.

**Files:**
- Create/Modify: `src/nephos_api/dev_backbone.py`

**Steps:**
1. Create a short-lived Nephos-owned Kubernetes Job/Pod in the App namespace or reuse a simple app container.
2. Mount binding Secret values as env vars.
3. Probe each enabled backend with minimal commands/clients.
4. Mark this probe optional if adding client images would slow the alpha proof too much; Secret materialization remains the minimum required proof.

## Task 6: Cleanup and lifecycle proof

**Objective:** Ensure the smoke leaves no Nephos-owned runtime resources behind.

**Files:**
- Create/Modify: `src/nephos_api/dev_backbone.py`

**Steps:**
1. Destroy the App first.
2. Destroy Services in reverse dependency order.
3. Wait for Nephos-owned namespaces to be absent.
4. Preserve failure diagnostics if cleanup fails.
5. Do not delete unowned namespaces/resources.

## Task 7: Full verification

Run default checks:

```bash
uv lock --check
uv run ruff check .
uv run pytest -q
git diff --check
```

Run live smoke only on a disposable local cluster:

```bash
PULUMI_CONFIG_PASSPHRASE=local-dev \
  uv run nephos-api dev backbone-smoke --timeout-seconds 600
```

Commit message:

```bash
git commit -m "test: add alpha backbone runtime smoke"
```
