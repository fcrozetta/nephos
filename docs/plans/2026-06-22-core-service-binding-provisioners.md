# Core Service Binding Provisioners Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add typed app-scoped provisioning for PostgreSQL, Zitadel, SeaweedFS, and ArcadeDB so installed Apps receive connection material through Nephos-managed binding Secrets.

**Architecture:** Binding reconciliation calls internal Python provisioners. Provisioners return raw values only to Secret materialization code; repository output summaries, status evidence, logs, and API responses stay redacted. Provisioners match on `capability + protocol`.

**Tech Stack:** Kubernetes Python client, HTTP clients where needed, subprocess/exec only when explicitly bounded and tested, pytest fake clients.

---

## Task 1: Extend binding provisioning context with protocol

**Objective:** Let provisioners distinguish `sql/postgres` from `sql/arcadedb` and `opencypher/bolt` from `opencypher/n4j`.

**Files:**
- Modify: `src/nephos_api/provisioning.py`
- Modify: `src/nephos_api/reconciler.py`
- Tests: `tests/test_postgres_provisioning.py`, `tests/test_reconciler.py`

**Steps:**
1. Add `protocol: str | None` to `BindingProvisioningContext`.
2. Update binding reconciliation to pass the persisted binding protocol.
3. Update tests/fakes.
4. Ensure status/evidence may include protocol but never secret values.

## Task 2: Update PostgreSQL provisioner to `sql/postgres`

**Objective:** Keep existing PostgreSQL provisioning behavior but switch selector semantics.

**Files:**
- Modify: `src/nephos_api/provisioning.py`
- Tests: `tests/test_postgres_provisioning.py`

**Steps:**
1. Change provision condition from `context.capability != "postgres"` to requiring `capability == "sql" and protocol == "postgres"`.
2. Keep returned output keys:
   - `host`
   - `port`
   - `database`
   - `username`
   - `password`
   - `uri`
3. Keep redacted `uri` behavior in summaries.
4. Run targeted tests.

## Task 3: Split provisioners into per-Service modules

**Objective:** Keep the growing provisioner code maintainable for lower-reasoning agents.

**Files:**
- Create: `src/nephos_api/provisioners/__init__.py`
- Create: `src/nephos_api/provisioners/postgres.py`
- Create: `src/nephos_api/provisioners/zitadel.py`
- Create: `src/nephos_api/provisioners/seaweedfs.py`
- Create: `src/nephos_api/provisioners/arcadedb.py`
- Modify: `src/nephos_api/provisioning.py` to preserve public imports or become a compatibility facade.
- Tests: existing provisioning tests plus new tests per module.

**Steps:**
1. Move PostgreSQL code without behavior changes.
2. Keep old imports working for tests until all call sites are updated.
3. Add a composite provisioner that tries registered provisioners in order and returns first non-`None` result.
4. Run existing tests before adding new provider logic.

## Task 4: Implement Zitadel OIDC/service-account provisioner

**Objective:** Provision per-App auth material from the Zitadel Service.

**Files:**
- Create/Modify: `src/nephos_api/provisioners/zitadel.py`
- Tests: `tests/test_zitadel_provisioning.py`

**Research prerequisite:** Verify Zitadel Management API endpoints and auth bootstrap against current Zitadel docs or a local container. Do not guess endpoint shapes.

**Provisioning inputs:**
- `capability=oidc`, `protocol=oidc` for web/client auth.
- `capability=service-account`, `protocol=jwt` or accepted protocol name for machine credentials.

**Expected output keys for `oidc/oidc`:**
- `issuerUrl`
- `clientId`
- `clientSecret`
- `redirectUris` as JSON string if multiple values are needed

**Expected output keys for service account:**
- `issuerUrl`
- `serviceAccountId`
- `privateKey` or `keyJson` depending on verified Zitadel API shape
- `audience`

**Steps:**
1. Add a fake Zitadel client protocol for tests.
2. Implement idempotent ensure-client behavior against the fake first.
3. Redact all secrets in summaries/status.
4. Add live smoke later; unit tests must not require a live Zitadel.

## Task 5: Implement SeaweedFS S3 provisioner

**Objective:** Provision app-scoped S3 bucket and credentials.

**Files:**
- Create/Modify: `src/nephos_api/provisioners/seaweedfs.py`
- Tests: `tests/test_seaweedfs_provisioning.py`

**Research prerequisite:** Verify the safest local SeaweedFS admin/S3 credential provisioning path. Prefer an HTTP/API/SDK path over shelling into pods when available.

**Selector:** `capability=object-storage`, `protocol=s3`.

**Expected output keys:**
- `endpointUrl`
- `bucket`
- `accessKeyId`
- `secretAccessKey`
- `region`

**Steps:**
1. Add fake client protocol.
2. Ensure bucket idempotently.
3. Ensure app-scoped key/secret idempotently.
4. Return connection material for Secret materialization.
5. Keep summaries redacted.

## Task 6: Implement ArcadeDB provisioner

**Objective:** Provision app-scoped ArcadeDB databases/users for supported protocols.

**Files:**
- Create/Modify: `src/nephos_api/provisioners/arcadedb.py`
- Tests: `tests/test_arcadedb_provisioning.py`

**Research prerequisite:** Verify ArcadeDB local/admin HTTP API and supported protocol enablement for `sql`, `opencypher` over `bolt`/`n4j`, optional `gremlin`, and optional `mongo`.

**Selectors:**
- `sql/arcadedb`
- `opencypher/bolt`
- `opencypher/n4j`
- optional `gremlin/gremlin`
- optional `mongo/mongo`

**Expected output keys:**
- `host`
- `port`
- `database`
- `username`
- `password`
- `protocol`
- protocol-specific URI key such as `uri`

**Steps:**
1. Add fake client protocol.
2. Implement idempotent database/user creation.
3. Return protocol-specific host/port/URI.
4. Block unsupported optional protocols with structured `binding_provisioner_unavailable` evidence rather than pretending success.

## Task 7: Update Secret labels/output summaries for protocol

**Objective:** Make App-side binding Secrets and summaries distinguish providers with same capability and different protocols.

**Files:**
- Modify: `src/nephos_api/kubernetes_runtime.py`
- Modify: `src/nephos_api/reconciler.py`
- Tests: `tests/test_kubernetes_runtime.py`, `tests/test_reconciler.py`

**Steps:**
1. Add optional protocol label/annotation if it passes label value rules; otherwise use annotation.
2. Include protocol in redacted `output_summary_json`.
3. Ensure existing Secret names still derive from alias, not capability.
4. Run targeted tests.

## Task 8: Full verification

Run:

```bash
uv lock --check
uv run ruff check .
uv run pytest -q
git diff --check
```

Commit message:

```bash
git commit -m "feat: provision alpha backbone bindings"
```
