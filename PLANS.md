# Nephos Planning Rules

Use a plan for any task that changes architecture, public interfaces, schemas, lifecycle semantics, runtime behavior, or app/service catalog behavior.

A plan must include:

- Goal
- Non-goals
- Current understanding
- Files likely to change
- Proposed steps
- Risks
- Validation commands
- Rollback notes
- Open questions

Do not implement until blocking questions are resolved or explicitly deferred.

---

## Current Plan: API 0.0.1 Draft Runtime Handler Spike

Status:

- Implemented and validated for the API 0.0.1 backend/runtime slice.

Goal:

- Add the first opt-in real runtime path behind the reconciler using draft-documented assumptions: Helm subprocess deployment for App/Service runtime apply, Kubernetes Secret materialization for bindings, and a typed PostgreSQL provisioning-output assumption that remains honest about unimplemented SQL provisioning.

Non-goals:

- Do not mark the draft Helm/PostgreSQL assumptions as accepted architecture.
- Do not implement K3s lifecycle management in `nephos-api`.
- Do not expose arbitrary Helm, kubectl, shell, or Service operation commands as public Nephos semantics.
- Do not implement stop/remove/destroy runtime teardown until teardown semantics are accepted and tested.
- Do not promote draft manifests into canonical catalog examples.

Current understanding:

- Fer chose to proceed with a minimal Helm subprocess plus typed PostgreSQL provisioning assumption and document it as draft.
- The draft ADR is `docs/adr/20260523-minimal-runtime-handler-assumptions.md`.
- Runtime should stay behind the persisted reconciler boundary and should be opt-in/configurable so unit tests and desired-state-only workflows do not require Helm/Kubernetes.
- The first runtime mode can support apply/start/reconcile for installed Services and Apps, and binding Secret materialization for PostgreSQL app-secret outputs.
- Runtime status evidence must explicitly identify draft assumptions and any missing SQL-level provisioning.

Files likely to change:

- `PLANS.md`
- `docs/adr/20260523-minimal-runtime-handler-assumptions.md`
- `pyproject.toml`
- `uv.lock`
- `src/nephos_api/config.py`
- `src/nephos_api/runtime.py`
- `src/nephos_api/reconciler.py`
- `tests/test_runtime.py`
- `tests/test_reconciler.py`

Proposed steps:

1. Add draft ADR for Helm subprocess and PostgreSQL provisioning assumptions.
2. Add runtime config for an opt-in `helm` runtime mode while preserving shell behavior by default.
3. Add a Helm subprocess wrapper that generates temporary values files and runs `helm upgrade --install`.
4. Add a Kubernetes Secret client boundary for app namespace Secret materialization.
5. Add a runtime handler that resolves installed App/Service catalog entries, applies semantic config/binding mappings into Helm values, and delegates to Helm.
6. Add typed PostgreSQL binding output generation and app-secret materialization that reuses existing Secret data when available.
7. Wire the reconciler to call runtime handlers only in `helm` runtime mode; shell mode keeps the existing blocked behavior.
8. Keep stop/remove/destroy runtime actions blocked with clear status evidence.
9. Add fake-backed unit tests for Helm command generation, binding Secret materialization, and reconciler helm-mode success without requiring a live cluster.
10. Run `uv run pytest -m "not k3s"`, `uv run ruff check .`, `uv run nephos-api db migrate`, and command help checks.

Risks:

- Accidentally presenting draft runtime assumptions as accepted product behavior.
- Generating credentials without stable reuse would break idempotent retries.
- Helm chart conventions may differ; status evidence must not overclaim database/user creation until SQL provisioning is real.
- Introducing a Kubernetes dependency must not make normal unit tests require a cluster.

Validation commands:

- `uv run pytest -m "not k3s"`
- `uv run ruff check .`
- `uv run nephos-api db migrate`
- `uv run nephos-api serve --help`
- `uv run nephos-api reconcile drain --help`

Rollback notes:

- Runtime mode can be disabled by using shell/default mode.
- Revert `src/nephos_api/runtime.py`, reconciler runtime wiring, and the draft ADR if Fer rejects the temporary runtime assumptions.

Open questions:

- Whether Helm subprocess remains acceptable after the spike.
- Exact PostgreSQL admin credential discovery and SQL provisioning execution.
- Stop/remove/destroy Helm/PVC/Secret/app-scoped-resource teardown semantics.

---

## Previous Plan: API 0.0.1 Lifecycle And Manual Reconcile Desired-State Implementation

Goal:

- Implement accepted API `0.0.1` desired-state lifecycle actions and manual reconciliation entrypoints for installed Apps, installed Services, bindings, and platform domain configuration, keeping runtime teardown/apply work behind reconciliation requests.

Non-goals:

- Do not implement real Kubernetes, Helm, Service provisioning, binding Secret materialization, or route/Ingress mutation in this batch.
- Do not delete desired-state rows during destroy before successful runtime teardown.
- Do not add retry/backoff/lease table columns.
- Do not decide CLI setup command spelling or move implementation into `nephos-cli`.
- Do not change canonical catalog schemas or examples.

Current understanding:

- Install/read, auto-binding, and the reconciler shell are implemented.
- Accepted API shape includes lifecycle action subresources for Apps and Services: `start`, `stop`, `remove`, and `destroy`.
- Accepted manual reconcile endpoints exist for Apps, Services, bindings, and platform domain configuration.
- Lifecycle mutations update desired state and enqueue reconciliation; they must not mutate Kubernetes inline.
- `destroy` requires confirmation, keeps the desired-state row present while teardown is pending, and should be represented by `delete_requested_at` plus reconciliation/status metadata rather than a `destroying` lifecycle value.
- Service lifecycle actions that affect dependents must return `409 Conflict` with an impact list unless forced.

Files likely to change:

- `PLANS.md`
- `src/nephos_api/repositories.py`
- `src/nephos_api/schemas.py`
- `src/nephos_api/routers/apps.py`
- `src/nephos_api/routers/services.py`
- `src/nephos_api/routers/bindings.py`
- `src/nephos_api/routers/platform_domains.py`
- `src/nephos_api/main.py`
- `tests/test_lifecycle_api.py`
- `tests/test_bindings_api.py`

Proposed steps:

1. Add a shared lifecycle action request model with optional `force` and `confirm`.
2. Add App lifecycle methods for start, stop, remove, destroy, and manual reconcile.
3. Add Service lifecycle methods for start, stop, remove, destroy, and manual reconcile.
4. Implement dependency impact detection from binding rows for Service stop/remove/destroy, requiring `force: true` when dependents exist.
5. Require exact destroy confirmation text before enqueueing destroy requests.
6. Preserve desired-state rows during destroy by setting `delete_requested_at` and enqueuing a destroy reconciliation request.
7. Add Binding read snapshots and binding manual reconcile by id.
8. Add platform-domain manual reconcile for the default configured domain while keeping broader setup semantics deferred.
9. Register routers and return accepted mutation envelopes with pending status snapshots.
10. Add tests for idempotent lifecycle state changes, destroy confirmation, Service dependent blocking/force, binding read/reconcile, and manual reconcile request creation.
11. Run `uv run pytest -m "not k3s"`, `uv run ruff check .`, `uv run nephos-api db migrate`, and command help checks.

Risks:

- Accidentally deleting desired-state rows before runtime teardown would violate accepted destroy semantics.
- Treating lifecycle actions as direct Kubernetes commands would weaken the desired-state/reconciler boundary.
- Returning dependency impact without binding ids/aliases/capabilities would break the accepted error shape.
- Platform-domain manual reconcile target selection is not fully expressive for multi-domain config; this batch should keep it narrow and transparent.

Validation commands:

- `uv run pytest -m "not k3s"`
- `uv run ruff check .`
- `uv run nephos-api db migrate`
- `uv run nephos-api serve --help`
- `uv run nephos-api reconcile drain --help`

Rollback notes:

- Revert lifecycle/router/repository changes if lifecycle semantics need to change before real runtime handlers.
- No migration rollback is expected because this batch uses accepted existing columns, including `delete_requested_at`.

Open questions:

- Exact platform-domain manual reconcile behavior for multiple root domains remains deferred; this batch can target the default configured domain to avoid adding an unapproved aggregate target shape.
- Real remove/destroy runtime cleanup behavior remains deferred to the runtime handler batch.
- Helm execution mechanics and PostgreSQL provisioning handler boundaries remain blockers for honest real runtime reconciliation.

---

## Previous Plan: API 0.0.1 Reconciler Shell Implementation

Goal:

- Implement the API-owned reconciler shell for API `0.0.1`: drain persisted `pending` reconciliation requests from SQLite, transition requests through `running` into terminal `succeeded`, `blocked`, or `failed` states, and write latest status snapshots with structured evidence, without performing real Kubernetes/Helm mutation yet.

Non-goals:

- Do not implement real Kubernetes, Helm, Service provisioning, binding Secret materialization, or route/Ingress mutation in this batch.
- Do not add distributed workers, leases, attempt counters, backoff columns, or automatic retry.
- Do not change the accepted reconciliation request table shape.
- Do not add canonical catalog examples or schemas.
- Do not implement lifecycle actions beyond the existing install/read/domain operations.

Current understanding:

- Fer wants progress toward API `0.0.1` and approved continuing from App install into the reconciler shell.
- Accepted architecture requires an API-owned, in-process reconciler over persisted SQLite requests, with one serialized worker initially.
- API mutations already persist reconciliation requests and initial pending status snapshots in the same transaction.
- This batch should prove queue claiming/draining, request state transitions, idempotent shell handlers, and latest status writes before real runtime handlers.
- Because this shell does not mutate Kubernetes, runtime-facing App/Service/Binding work should remain visibly `pending` or `blocked` through status evidence rather than falsely claiming real runtime health.
- Platform domain requests can succeed as desired-state-only reconciliation because there is no runtime object to apply yet in this backend slice.

Files likely to change:

- `PLANS.md`
- `src/nephos_api/reconciler.py`
- `src/nephos_api/repositories.py`
- `src/nephos_api/main.py`
- `src/nephos_api/cli.py`
- `tests/test_reconciler.py`
- existing API tests if TestClient startup needs explicit reconciler disablement

Proposed steps:

1. Add repository/helper methods to claim the oldest pending request, mark requests terminal, and write latest status snapshots in short explicit transactions.
2. Add a `Reconciler` service with `run_once()` and `drain()` entrypoints.
3. Implement idempotent shell handlers for `platform_domain`, `service_instance`, `app_instance`, and `binding` targets.
4. Mark platform-domain desired-state requests as succeeded with status evidence that no runtime mutation is needed in this shell.
5. For installed Service/App/Binding targets, update request/status honestly for the shell: block or leave pending where required runtime handlers are not implemented, with evidence explaining the blocker.
6. Detect App route blockers when no root domain is configured.
7. Add an optional in-process background loop hook for the FastAPI app without making existing unit tests race-prone.
8. Add a backend-local `nephos-api reconcile run-once` or equivalent command to drain persisted requests deterministically in tests/dev.
9. Add tests for pending -> running -> terminal transitions, status snapshots, structured evidence, deleted platform-domain snapshot handling, no-op empty drain, and CLI command behavior where practical.
10. Run `uv run pytest -m "not k3s"`, `uv run ruff check .`, `uv run nephos-api db migrate`, and `uv run nephos-api serve --help`.

Risks:

- Marking runtime reconciliation as `succeeded` before any Kubernetes/Helm mutation exists would misrepresent platform health.
- Starting the background worker automatically in tests could race existing pending-state assertions.
- Overbuilding retry/lease mechanics before API `0.0.1` needs them would conflict with the accepted bounded table shape.
- Blocking App reconciliation on missing root domains must remain status/reconciliation behavior, not App install-time policy, until setup semantics are implemented.

Validation commands:

- `uv run pytest -m "not k3s"`
- `uv run ruff check .`
- `uv run nephos-api db migrate`
- `uv run nephos-api serve --help`

Rollback notes:

- Revert `src/nephos_api/reconciler.py`, CLI/app hook changes, and reconciler tests if request drain semantics need a different shape before runtime handlers.
- No database migration rollback is expected because this batch uses the accepted existing reconciliation/status table shape.

Open questions:

- Exact retry count, backoff, lease/claiming mechanics, and polling interval remain implementation details deferred beyond this shell unless API `0.0.1` proves they are needed.
- Exact runtime handler boundaries for Helm, PostgreSQL provisioning, binding Secret materialization, and route/Ingress remain deferred to the runtime batch.
- Whether App install itself should require platform setup remains deferred; this shell may report route reconciliation blocked until root domains exist.

---

## Previous Plan: API 0.0.1 App Install Auto-Binding Implementation

Goal:

- Implement `POST /apps`, `GET /apps`, and `GET /apps/{appInstance}` for API `0.0.1` using validated catalog App entries, installed Service capability providers, persisted App desired state, first-class binding rows, and a persisted reconciliation request in the same transaction.

Non-goals:

- Do not freeze the manual App install binding-selection request shape in this batch.
- Do not implement lifecycle actions beyond install/read.
- Do not implement real Kubernetes, Helm, route/Ingress reconciliation, or Service provisioning runtime behavior.
- Do not add canonical repo catalog entries, schemas, or examples.
- Do not add a general `/bindings` API surface yet.

Current understanding:

- Fer approved a narrow App install slice that auto-binds only when each required capability has exactly one eligible installed Service provider.
- App install mutation is accepted as `POST /apps` with `catalogRef`, optional `instanceName`, optional `config`, and optional `bindings` reserved for future explicit provider selection.
- This batch may accept an omitted or empty `bindings` object, but must reject non-empty explicit binding selections instead of interpreting an unapproved shape.
- Installed Apps are internal `AppInstance` records exposed under `/apps` by public slug.
- Default instance name equals the catalog manifest `metadata.name`.
- Binding rows connect App requirement aliases to Service instances and are the source of dependent tracking.
- Missing providers and multiple eligible providers should fail clearly before creating desired state in this batch.
- Mutating API calls must write desired state and a reconciliation request in one transaction, returning the accepted mutation envelope.
- Runtime reconciliation and binding Secret materialization may remain pending until the reconciler/runtime batch.

Files likely to change:

- `PLANS.md`
- `src/nephos_api/repositories.py`
- `src/nephos_api/schemas.py`
- `src/nephos_api/routers/apps.py`
- `src/nephos_api/main.py`
- `tests/test_apps_api.py`

Proposed steps:

1. Add App install request model with `catalogRef`, `instanceName`, `config`, and reserved `bindings`.
2. Add App repository methods for list/get/install snapshots.
3. Resolve and validate an App catalog entry during install.
4. Reject non-empty explicit binding selections until Fer approves the manual binding request shape.
5. Resolve each App requirement alias to exactly one installed Service provider by capability.
6. Reject zero-provider and multi-provider cases with Nephos domain errors that include requirement aliases and candidates.
7. Insert the App instance and auto-created binding rows in one transaction.
8. Create one persisted App reconciliation request in the same transaction as App and binding desired state.
9. Return App snapshots with catalogRef, config, bindings, routes, timestamps, and status.
10. Include Service dependents from binding rows in Service snapshots.
11. Register the App router and add tests using temporary catalog roots.
12. Run `uv run pytest -m "not k3s"` and `uv run ruff check .`.

Risks:

- Accidentally freezing the explicit binding-selection request contract before approval.
- Creating App desired state without binding rows, weakening dependent tracking.
- Creating multiple reconciliation requests prematurely before the reconciler target strategy is implemented.
- Treating route host generation as settled before platform setup and route reconciliation are implemented.
- Recomputing too much installed Service semantics from mutable catalog files instead of persisted desired-state identity.

Validation commands:

- `uv run pytest -m "not k3s"`
- `uv run ruff check .`

Rollback notes:

- Revert App router/repository/schema additions if App install or binding selection semantics change before the reconciler batch.
- Existing database table shape already contains `app_instances` and `bindings`; no migration shape change is expected.

Open questions:

- Exact explicit App install binding-selection request shape remains deferred.
- Whether App install should create additional binding-level reconciliation requests remains deferred until the reconciler shell.
- Route canonical URL behavior when platform root domains are missing remains deferred to reconciler/platform setup semantics.
- Real binding Secret materialization and Service app-scoped provisioning handler boundaries remain deferred.

---

## Previous Plan: API 0.0.1 Service Install Implementation

Goal:

- Implement the first installed-resource mutation for API `0.0.1`: `POST /services` installs a Service instance from a validated catalog entry, persists desired state, creates a reconciliation request in the same transaction, and exposes read snapshots under `/services`.

Non-goals:

- Do not implement App install or binding creation in this batch.
- Do not implement lifecycle actions beyond install/read.
- Do not implement real Kubernetes, Helm, or provisioning runtime behavior.
- Do not add canonical repo catalog entries.
- Do not make catalog endpoints own install mutation.

Current understanding:

- Service install mutation is accepted as `POST /services` with `catalogRef`, optional `instanceName`, and optional `config`.
- Installed Services are internal `ServiceInstance` records exposed under `/services` by public slug.
- Default instance name equals the catalog manifest `metadata.name`.
- Installed records store catalog kind/name/version/source id/source path and manifest digest.
- Mutating API calls must write desired state and a reconciliation request in one transaction, returning the accepted mutation envelope.
- Runtime reconciliation may remain pending until the reconciler/runtime batch.

Files likely to change:

- `PLANS.md`
- `src/nephos_api/catalog.py`
- `src/nephos_api/repositories.py`
- `src/nephos_api/schemas.py`
- `src/nephos_api/routers/services.py`
- `src/nephos_api/main.py`
- `tests/`

Proposed steps:

1. Expose a catalog resolver that returns validated entry metadata needed by install mutations.
2. Add Service install request models with `catalogRef`, `instanceName`, and `config`.
3. Add repository methods to create and read Service instance snapshots.
4. Validate instance slugs with accepted machine identifier rules and reject collisions.
5. Persist catalog identity, source id, source path snapshot, manifest digest, lifecycle, generation, and config JSON.
6. Create a persisted reconciliation request in the same transaction as the Service instance row.
7. Add read endpoints for `/services` and `/services/{serviceInstance}`.
8. Register the service router and add tests using temporary catalog roots.
9. Run `uv run pytest -m "not k3s"` and `uv run ruff check .`.

Risks:

- Returning raw database rows instead of domain snapshots.
- Accidentally waiting for or faking Kubernetes convergence in the install response.
- Overbuilding App/binding behavior before Service install is proven.
- Losing catalog source-path/digest snapshot needed for future debugging and install provenance.

Validation commands:

- `uv run pytest -m "not k3s"`
- `uv run ruff check .`

Rollback notes:

- Revert Service router/repository/schema additions if install payload or snapshot shape changes before App install.
- Existing migration table shape is already accepted and should not need rollback for this batch.

Open questions:

- App install binding selection shape remains for the next batch.
- Real Service runtime handler and Helm execution mechanics remain deferred.
- PostgreSQL app-scoped provisioning handler boundary remains deferred.

---

## Previous Plan: API 0.0.1 Catalog Loader Implementation

Goal:

- Implement read-only catalog loading for API `0.0.1` using local filesystem manifests, typed Pydantic validation models, source ids, manifest digests, normalized catalog summaries, and duplicate-source error handling.

Non-goals:

- Do not promote draft manifests into canonical repo `catalog/` entries in this batch.
- Do not add JSON Schema files under `schemas/`.
- Do not implement App or Service install mutations yet.
- Do not implement Kubernetes, Helm, or provisioning runtime behavior.
- Do not make catalog endpoints own install mutation.

Current understanding:

- Catalog loading follows the accepted API/database boundary: catalog entries are available package definitions, while installed Apps and Services live in desired state.
- API `0.0.1` reads and validates local filesystem catalog manifests on demand.
- Source ids are `default` for the repo-shipped `catalog/` root and `local-1`, `local-2`, `local-3` for configured local roots.
- Duplicate catalog entries with the same kind/name across roots are ambiguous unless the caller selects a source.
- Catalog responses should return normalized summaries, not raw manifest blobs by default.
- Tests should use fixtures or temporary catalog roots, not canonical examples.

Files likely to change:

- `PLANS.md`
- `src/nephos_api/config.py`
- `src/nephos_api/catalog.py`
- `src/nephos_api/routers/catalog.py`
- `src/nephos_api/main.py`
- `tests/`

Proposed steps:

1. Add typed Pydantic catalog manifest models for accepted App and Service manifest fields needed by API `0.0.1` summaries.
2. Add catalog source root discovery from repo default plus `NEPHOS_API_CATALOG_ROOTS` configured local paths.
3. Implement on-demand manifest loading from accepted layout `catalog/apps/<slug>/app.yaml` and `catalog/services/<slug>/service.yaml`.
4. Validate directory slug equals `metadata.name` and reject unknown manifest fields through Pydantic models.
5. Compute SHA-256 manifest digests from file bytes.
6. Normalize App catalog summaries with `requires` and `routes`.
7. Normalize Service catalog summaries with `provides` and binding output targets.
8. Implement duplicate-source ambiguity and missing source errors with Nephos error shape.
9. Add read-only endpoints for `/catalog/apps`, `/catalog/apps/{name}`, `/catalog/services`, and `/catalog/services/{name}`.
10. Add tests using temporary local catalog roots for list, detail, source selection, duplicate ambiguity, unknown source, invalid manifests, and missing entries.
11. Run `uv run pytest -m "not k3s"` and `uv run ruff check .`.

Risks:

- Accidentally freezing draft manifest sketches as canonical examples.
- Over-validating fields whose exact runtime shape is still deferred.
- Returning raw manifest content and accidentally exposing schema details as product API.
- Silently overriding duplicate catalog entries instead of reporting ambiguity.

Validation commands:

- `uv run pytest -m "not k3s"`
- `uv run ruff check .`

Rollback notes:

- Revert catalog loader files and endpoint registration if manifest validation direction changes before App/Service install.
- Test fixture roots can be deleted without touching project state.

Open questions:

- Future promotion path from draft manifests to canonical repo-shipped `catalog/` entries.
- Raw Kubernetes manifest fallback field shape remains deferred.
- Helm execution mechanics remain deferred until runtime reconciliation.

---

## Previous Plan: API 0.0.1 Backend Bootstrap Implementation

Goal:

- Implement the first Nephos API `0.0.1` backend slice from accepted ADRs: package scaffold, SQLite migration/database layer, backend-local commands, API skeleton, and the smallest desired-state mutation path.

Non-goals:

- Do not implement `nephos-cli` behavior in this repository.
- Do not install, start, stop, reset, or destroy K3s from `nephos-api`.
- Do not implement real Helm/Kubernetes runtime reconciliation in this batch.
- Do not promote draft manifests into canonical `catalog/`, `examples/`, or `schemas/` without Fer approval.
- Do not add new architecture decisions unless implementation reveals a documented blocker.

Current understanding:

- The accepted implementation order is migration/database layer, API skeleton, catalog loader, then reconciler.
- This repo currently has architecture/docs but no Python backend scaffold.
- `src/nephos_api/` is the accepted package layout.
- `nephos_api.main:app` is the accepted FastAPI entrypoint.
- `nephos-api` is the accepted backend-local command name.
- SQLite is the canonical desired-state database for Phase 1.
- `.nephos/state/nephos.db` is the default database path when `NEPHOS_API_DB_PATH` is unset.
- Mutating API calls must write desired state and create a persisted reconciliation request in one transaction.
- A platform-domain mutation slice is small enough to prove the API/database/reconciliation-request contract before catalog and runtime complexity.

Files likely to change:

- `PLANS.md`
- `pyproject.toml`
- `src/nephos_api/`
- `migrations/0000_initial.sql`
- `tests/`

Proposed steps:

1. Scaffold the Python backend package, FastAPI app entrypoint, and `nephos-api` Typer command.
2. Add pytest and ruff configuration with accepted markers.
3. Implement environment bootstrap configuration for `NEPHOS_API_DB_PATH`, `NEPHOS_API_CATALOG_ROOTS`, `NEPHOS_API_KUBECONFIG`, and `NEPHOS_API_KUBE_CONTEXT`.
4. Implement SQLite connection setup with accepted pragmas.
5. Add `migrations/0000_initial.sql` with accepted API `0.0.1` table families and constraints.
6. Implement `uv run nephos-api db migrate` and `uv run nephos-api db reset --force`.
7. Add domain helpers for timestamps, typed ids, machine identifiers, root-domain validation, and Nephos domain errors.
8. Add a small repository layer for platform domains, status snapshots, and reconciliation requests.
9. Add FastAPI routes for version and platform-domain list/add/set-default/remove/reconcile behavior where accepted endpoint shape is clear enough.
10. Ensure platform-domain mutations return the accepted `{ resource, reconciliation, status? }` envelope.
11. Add unit/API tests for migrations, reset behavior, validation, mutation envelopes, and transactional reconciliation request creation.
12. Run `uv run pytest -m "not k3s"` and `uv run ruff check .`.

Risks:

- Accidentally turning implementation details into public CLI behavior.
- Accidentally bypassing persisted reconciliation requests in API handlers.
- Over-deciding exact runtime/Helm/provisioning mechanics before the runtime batch.
- Accidentally treating draft manifests as canonical validation inputs.
- Choosing unresolved platform-domain endpoint details that should remain deferred.

Validation commands:

- `uv run nephos-api db migrate`
- `uv run nephos-api db reset --force`
- `uv run pytest -m "not k3s"`
- `uv run ruff check .`
- `uv run nephos-api serve --help`

Rollback notes:

- Revert this implementation batch if the package/database command boundary changes.
- Remove `.nephos/` local state if reset leaves local development artifacts.

Open questions:

- Helm execution mechanics before real runtime reconciliation.
- PostgreSQL app-scoped provisioning handler boundary before real reference-flow runtime implementation.
- Exact K3s integration-test namespace naming and stricter cluster safety checks.
- Future catalog promotion from draft manifests to canonical repo-shipped entries.

---

## Previous Plan: Architecture Context Completion

Goal:

- Complete missing Nephos architecture context and ADRs through explicit Fer-approved decisions.

Non-goals:

- Do not invent schema shapes without approval.
- Do not implement runtime code.
- Do not change Nephos into a raw Kubernetes UX, generic container UI, or CLI-driven kubectl wrapper.

Current understanding:

- Nephos is the backend/control-plane repository.
- `../nephos-cli` is the separate CLI repository and still needs configuration.
- K3s is the default real runtime backend.
- Kubernetes is the runtime substrate.
- Nephos owns platform intent, desired state, lifecycle semantics, capability binding, and reconciliation.
- Batch 1 decisions are accepted: Python/FastAPI backend, Python/Typer CLI, SQLite canonical desired-state DB, simple SQL migrations, YAML import/export, CRDs/GitOps deferred, API-owned in-process reconciler for Phase 1, official Python Kubernetes client, Web UI deferred, state backup deferred.
- Batch 2 packaging decisions are accepted: separate App and Service Nephos manifest formats, Helm-primary runtime deployment underneath, raw Kubernetes manifests as fallback, local filesystem catalog first, optional Phase 1 Service provisioning contracts, and `Service operation` as the canonical term for typed Service management actions.
- Batch 3 Service ownership decisions are accepted: installed concrete Services are Service instances, Services are shared by default, shared providers provision app-scoped resources in one instance by default where supported, App-requested isolation creates dedicated Service instances, dedicated instances remain first-class Services and may be explicitly shared with other Apps, bindings are the source of dependent tracking, provider defaults are supported, and destructive Service lifecycle operations with dependents require force plus impact list.
- Batch 4 resource/auth decisions are accepted: Phase 1 has no Nephos resource policy system, replicas are 1 when running and 0 when stopped/disabled, resource profiles are reserved but not defined, CPU/memory requests and limits are not exposed as primary UX, no HA/autoscaling/affinity/quotas in Phase 1, single-owner/local-first auth model, trusted local CLI, Web UI deferred, and multi-user/friend/cloud scenarios are Phase 1 non-goals.
- Batch 5 upgrade/backup decisions are accepted: versions are pinned, upgrades are explicit/manual, no automatic latest, Service upgrades with persistent data are risky by default, rollback is best-effort in Phase 1, Nephos owns backup intent/policy/status while Services own data-aware implementation, no backup implementation in Phase 1, stop/remove preserve data, and destroy deletes data and requires destructive confirmation when persistent data exists.
- Batch 6 health/status decisions are accepted: Nephos status is Nephos-aware and aggregates desired state, reconciliation, Kubernetes readiness/existence, bindings, dependencies, routes, storage, and backup status; Phase 1 implements a minimal subset; removed/destroyed are lifecycle states, not health statuses; for API 0.0.1, `destroyed` is terminal history or absent after deletion rather than a normal active desired-state value; backup participates as unsupported in Phase 1; status must include reasons/evidence; Service status includes dependent impact.
- Batch 7 Phase 1 scope decisions are accepted: single-node K3s, minimal cluster lifecycle, App/Service install/start/stop/remove/destroy, `disable` deferred, basic ingress intent, local filesystem catalog from day one with tiny repo-shipped reference entries, no service mesh, multi-component Apps communicate through normal Kubernetes Services/networking, and Paperless + PostgreSQL is the canonical reference scenario.
- Batch 8 runtime boundary decisions are accepted: one namespace per App instance and Service instance, `nephos-system` for control-plane/runtime support components, no default-deny NetworkPolicy in Phase 1, Traefik local ingress first, manual Cloudflare Tunnel compatibility without tunnel automation, stopped Apps keep route intent, Kubernetes Secrets for Phase 1, binding credentials materialized into App namespaces, and secret values redacted by default.
- Batch 9 catalog decisions are accepted: Phase 1 supports repo-shipped reference catalog entries and user-configured local filesystem catalog paths, user-created local entries are allowed without schema stability promise until concrete validation schema acceptance, local catalog files are trusted local-owner input, remote trust/signing/sandboxing are deferred, and minimal catalog metadata lives in App/Service manifests rather than a separate index.
- Batch 10 development/testing/distribution decisions are accepted: backend local dev uses `uv`, backend tests use `pytest`, lint/format checks use `ruff`, unit tests use mocks/fakes, Kubernetes integration tests use real K3s, Phase 1 backend distribution is local process plus container image, full installer packaging is deferred, CLI workflow belongs to `../nephos-cli`, and Phase 1 has backend/CLI version awareness without strict compatibility blocking.
- Batch 11 contribution/agent workflow decisions are accepted: ADRs are required for architecture-significant changes, ADR statuses have explicit meanings, agents must ask or record open questions before implementing through architectural ambiguity, canonical schemas/examples require Fer approval, temporary draft manifests are allowed only as non-canonical drafts under `.agents/drafts/manifests/`, architecture-changing work updates ADR/context/open questions in the same change, and architecture decision batches should be committed separately when feasible.
- Batch 12 reference scenario decisions are accepted: `.agents/drafts/manifests/` is the non-canonical draft manifest workspace, Paperless plus PostgreSQL is the canonical Phase 1 reference scenario, Paperless requires only PostgreSQL in the reference scenario, the flow includes install/bind/local route/stop/start/remove/destroy, Service dependency impact is included by attempting to stop PostgreSQL while Paperless depends on it, and route examples use generated hosts such as `paperless.nephos.local` and `paperless.nephos.fcrozetta.app`.
- Batch 13 manifest schema shape decisions are accepted: Nephos manifests are YAML, use a Kubernetes-like `apiVersion`/`kind`/`metadata`/`spec` envelope with Nephos semantics, accepted manifest kinds are `App` and `Service`, this does not imply CRDs, runtime references stay below Nephos manifests with Helm-primary pinned chart identity and raw manifest fallback, binding remains minimal at manifest level, and non-canonical draft sketches were added under `.agents/drafts/manifests/`.
- Batch 14 manifest field convention decisions are accepted: manifest `apiVersion` is `nephos.pro/v1alpha1`, local catalogs use directory-per-entry layout with `catalog/apps/<app-slug>/app.yaml` and `catalog/services/<service-slug>/service.yaml`, catalogs contain available Apps/Services while installed instances live in Nephos desired state, App manifests use `spec.requires[]`, `spec.routes[]`, `spec.config.options[]`, and `spec.runtime`, Service manifests use `spec.provides[]`, `spec.bindings.outputs[]`, `spec.provisioning.mode`, `spec.runtime`, and `spec.operations[]`, routes do not carry full hostnames, and Nephos derives hostnames from App instance name, route name, visibility, and domain policy.
- Batch 15 binding/provisioning decisions are accepted: Phase 1 binding output target is `app-secret`, PostgreSQL logical binding fields are `host`, `port`, `database`, `username`, `password`, and `uri`, Service manifests declare logical outputs rather than final Secret names, Nephos chooses deterministic binding Secret names, App manifests consume bindings through symbolic aliases such as `as: database`, Phase 1 provisioning modes are `app-scoped-resource` and `none`, provisioning is a typed backend/API-owned contract, remove preserves provisioned Service-side resources, and destroy deletes them after destructive confirmation.
- Batch 16 manifest field requirement decisions are accepted: Phase 1 installable catalog entries require `apiVersion`, `kind`, `metadata.name`, and `spec.runtime`; App `spec.requires[]`, `spec.routes[]`, and `spec.config.options[]` default to empty lists; Service `spec.provides[]` is required non-empty; Service `spec.provisioning.mode` is required as `none` or `app-scoped-resource`; PostgreSQL output fields are capability-defined without manifest `fields:` syntax in Phase 1; canonical examples remain blocked until manifest validation plus command/status shape are stable enough.
- Batch 17 manifest validation/config decisions are accepted: PostgreSQL `app-secret` outputs use exact lowercase Secret keys `host`, `port`, `database`, `username`, `password`, and `uri`; Phase 1 App config option types are `string`, `integer`, `boolean`, and `enum`; `secret` App config option type is deferred; unknown manifest fields are rejected once canonical schemas exist; raw Kubernetes manifest fallback shape is deferred until first needed.
- Batch 18 config option object decisions are accepted: config options use required `name` and `type`, optional `label`, `description`, `default`, and `required`; `name` is the stable machine key; `required` defaults to `false`; enum options use object values with `value` and `label`; validation bounds such as min/max/regex/length are deferred; config options do not carry Helm value paths, env vars, or Kubernetes field paths; runtime mapping happens through `spec.runtime.values.mappings[]`, whose exact shape remains open.
- Batch 19 runtime value mapping decisions are accepted: Phase 1 mapping source kinds are `config` and `binding`; mappings use explicit `from` and `to` objects; config mappings use `from.kind: config`, `from.name`, and `to.helmValue`; binding mappings use `from.kind: binding`, `from.name`, `from.field`, and `to.helmValue`; `helmValue` is a dot path; transforms are deferred; missing sources block reconciliation with a reason; mappings live only under `spec.runtime.values.mappings[]`.
- Batch 20 binding identity decisions are accepted: if `as` is omitted, binding alias defaults to `capability`; aliases are unique within one App manifest and installed App instance; Phase 1 `app-secret` names use `nephos-bind-<alias>` in the consuming App namespace; rebinding an alias updates the same Secret name after explicit reconciliation or confirmation; binding Secrets include relationship metadata; slug normalization was finalized in Batch 21.
- Batch 21 naming/metadata decisions are accepted: manifest `metadata.name`, binding aliases, route names, installed instance slugs, and catalog entry slugs use strict DNS-label style machine identifiers; invalid names are rejected; default installed instance names equal catalog manifest `metadata.name`; explicit install-time instance names are allowed; name collisions fail and require explicit input; generated Kubernetes names must fit resource limits after prefixes; runtime metadata uses `app.kubernetes.io/managed-by: nephos` plus `nephos.pro/app-instance`, `nephos.pro/service-instance`, `nephos.pro/capability`, and `nephos.pro/binding-alias`; Nephos does not use Kubernetes `ownerReferences` for platform relationships.
- Batch 22 ingress/domain decisions are accepted: Phase 1 supports multiple configured ingress root domains with one default/canonical domain and at least one root domain required for generated route hosts; Nephos generates host rules for every configured root domain; default route hostnames use `<app-instance>.<root-domain>` and non-default route hostnames use `<route>.<app-instance>.<root-domain>`; root domains are aliases for the same route intent; path-based App routing is out of scope; manual Cloudflare Tunnel remains compatible but user-managed; Nephos-managed ingress is HTTP-only; generated hostname collisions fail; Services do not expose admin routes through Nephos ingress.
- Batch 23 ingress root domain config decisions are accepted: ingress root domains are platform desired state in the Nephos API/database, managed through Nephos API/CLI platform configuration operations, not App manifest fields; semantic shape is `rootDomains[]` with `name`, `domain`, and `default`; `domain` is a DNS suffix only and rejects URLs, paths, wildcards, schemes, and ports; operations are add/list/remove/set-default; setup creates initial platform configuration before Apps are installed, including at least one root domain and exactly one default/canonical domain; App status shows canonical URL plus aliases.
- Batch 24 setup/CLI boundary is deferred: setup UX and command implementation belong in `nephos-cli` after Nephos API `0.0.1`; this repo should not decide command spelling yet. Accepted backend-side behavior: the backend may start with an empty database and reports platform configuration as incomplete until setup creates required desired state.
- Batch 25 Service operation boundary is accepted: Service operations are typed backend/API-owned Service management actions; they are reserved but bounded in Phase 1; arbitrary shell commands, Helm hooks, Kubernetes jobs, and user-provided scripts are not product semantics; Phase 1 may use internal typed Service handlers for minimal accepted provisioning work; no general user-facing Service operation API or CLI UX is included.
- Batch 26 API resource model is accepted: API 0.0.1 uses REST-ish resources, installed Apps are internal `AppInstance` records exposed publicly under `/apps`, installed Services are internal `ServiceInstance` records exposed under `/services`, bindings are first-class API/database resources, root domain resources use `/platform/config/domains`, lifecycle and status are separate, latest status is persisted with reasons/evidence, mutating API calls update desired state and create a persisted reconciliation request, and API 0.0.1 scope is limited to the Paperless plus PostgreSQL reference flow.
- Batch 27 database desired-state model is accepted: API 0.0.1 uses SQLite with plain SQL through a small repository/data-access layer, no full ORM, explicit SQL migration files with `migrations/0000_initial.sql` as the initial schema, destructive local reset allowed before the first usable version, normalized table families for app instances/service instances/bindings/platform domains/status snapshots/reconciliation requests/schema migrations, JSON text columns for validated snapshots and flexible payloads, catalog identity/version/source/digest metadata on installed records, latest status snapshots only, DB-persisted reconciliation requests, desired-state mutation and reconciliation request in one transaction, and destroy removes active desired-state rows after successful teardown without requiring audit/history in API 0.0.1.
- Batch 28 catalog/manifest loading is accepted: API 0.0.1 supports one repo-shipped catalog root plus optional backend-local configured filesystem roots, custom roots are not platform DB desired state yet, manifests are read/validated on demand, catalog entries are not imported into SQLite before use, directory slug must match `metadata.name`, duplicate kind/name across roots errors unless source is explicitly selected, validation starts with typed Python/Pydantic domain models, JSON Schema remains blocked, install selects catalog kind/name plus optional source rather than arbitrary path, installed records store catalog kind/name/version-if-present/source and SHA-256 manifest digest, full manifest snapshots are not stored by default, drafts stay non-canonical until API validation models exist and Fer approves promotion, and `metadata.version` remains optional.
- Batch 29 reconciliation execution is accepted: API 0.0.1 uses an API-owned in-process background reconciler with persisted SQLite reconciliation requests; mutating API calls write desired-state changes plus a reconciliation request in one transaction and return after commit; requests target one App instance, Service instance, binding, or platform domain configuration; request states are `pending`, `running`, `succeeded`, `failed`, and `blocked`; handlers must be idempotent and safe to retry; one serialized worker is accepted initially; simple capped retry is intended but automatic retry may be deferred from API 0.0.1 if heavy; the reconciler writes latest status snapshots; failures do not roll back desired state; drift is detected/reported for Nephos-owned resources and reconciled only when desired state or manual reconciliation asks for it.
- Batch 30 API lifecycle action shape is accepted: install mutation uses `POST /apps` and `POST /services` with catalog refs in the body; catalog install endpoints are not primary; lifecycle uses `POST /apps/{appInstance}/actions/start|stop|remove|destroy` and equivalent Service paths; destroy stays a confirmed `POST .../actions/destroy`, not `DELETE`; dependency-blocked Service lifecycle returns `409 Conflict` with impact list unless forced; mutating responses prefer `202 Accepted` with resource/reconciliation request/status metadata; repeated lifecycle requests to the same desired state are idempotent.
- Batch 31 API payload/error shape is accepted: public API paths use installed instance slugs, not opaque UUIDs; install bodies use `catalogRef` with `kind`, `name`, optional `source`, optional `instanceName`, optional `config`, and App install `bindings`; lifecycle action bodies use optional `force` and `confirm`, with `confirm` required only for destroy; mutation responses use `{ resource, reconciliation, status? }`; Nephos-owned domain errors use `{ error: { code, message, details? } }`; dependency-blocked impact details include `requiresForce`, dependent App instance, binding id, binding alias, and capability; FastAPI/Pydantic validation errors may remain framework-shaped for API 0.0.1 and are not stable Nephos product API.
- Batch 32 database schema mechanics are accepted: database relationships use internal stable text ids, user-addressable installed resources use unique public slugs, core domain tables include `id`, `created_at`, and `updated_at`, state fields use SQLite `CHECK` constraints, SQLite foreign keys are enabled with restrictive relationships by default, lifecycle deletes happen through explicit domain transactions rather than broad cascades, JSON text columns are only for validated snapshots/flexible payloads, API 0.0.1 reconciliation requests use the bounded accepted field set, latest status snapshots are keyed by resource target, and `schema_migrations` uses `version TEXT PRIMARY KEY` plus `applied_at TEXT`.
- Batch 33 API read/status/catalog shape is accepted: internal ids use typed prefixes plus UUID4 hex suffixes, timestamps are app-generated UTC ISO strings with `Z`, read payloads are domain snapshots with ids and slugs rather than raw DB rows, status payloads include level/lifecycle/reconciliation/reason/message/evidence/observedAt, manual reconcile uses target-specific action subresources, and read-only catalog endpoints are `/catalog/apps`, `/catalog/apps/{name}`, `/catalog/services`, and `/catalog/services/{name}` with optional source selection.
- Batch 34 API response field details are accepted: App read payloads expose top-level `bindings` and `routes`; Service read payloads expose top-level `provides` and `dependents`; Binding read payloads expose alias, capability, App instance, Service instance, redacted output or Secret summary, status, and timestamps; status evidence entries use `source`, `subject`, `reason`, `message`, `observedAt`, and optional redacted `data`; catalog responses use normalized summaries by default rather than raw manifest blobs; API 0.0.1 has no rename API and installed App/Service slugs are immutable.
- Batch 35 nested response entry fields are accepted: App `bindings[]` entries use id/alias/capability/serviceInstance/status; App `routes[]` entries use name/visibility/target/canonicalUrl/aliases/status; Service `provides[]` entries use capability/optional alias/optional version/bindingOutputTargets; Service `dependents[]` entries use appInstance/bindingId/bindingAlias/capability/lifecycle/status; Binding redacted output or Secret summaries use target/secretName/namespace/keys/redacted true; App catalog summaries include requires/routes and Service catalog summaries include provides.
- Batch 36 nested response subfields are accepted: nested entry status summaries use level/reason/message/observedAt; App route targets are semantic and expose port; App catalog requires entries use capability/alias/optional provider; App catalog routes entries use name/visibility/target; Service catalog provides entries use capability/optional alias/optional version/bindingOutputTargets; validation error normalization is deferred until after API 0.0.1.
- Batch 37 destroy/reconciliation/database mechanics are accepted: destroy keeps desired-state rows present while teardown is pending and deletes them only after successful teardown; no `destroying` lifecycle state is added; reconciliation requests include durable `action`, `payload_json`, and target snapshot support; desired-state rows include integer `generation`; status/reconciliation may record target or observed generation; SQLite uses one API process, one serialized reconciler, short explicit transactions, foreign keys on, and WAL mode; `migrations/0000_initial.sql` contains all API 0.0.1 tables and accepted constraints.
- Batch 38 API 0.0.1 database table shape is accepted: App/Service tables use explicit catalog identity, lifecycle, generation, config, pending destroy, and timestamp columns; bindings use explicit App/Service relationship, alias, capability, generation, output summary, and timestamp columns; platform domains are one row per root domain; status snapshots use target/status columns plus evidence JSON and observed generation; reconciliation requests use target generation, action, payload JSON, and target snapshot JSON; indexes enforce unique slugs, binding alias per App, one default domain, one latest status per target, and reconciliation queue lookup by state/created_at.
- Batch 39 SQLite and command-boundary mechanics are accepted: refer to this backend/API repo as `nephos-api` when distinguishing from `nephos-cli`; `nephos <command>` belongs to the user-facing `nephos-cli` product command; backend-local migration/reset commands are `nephos-api` dev/ops commands, with exact spelling resolved in Batch 40; SQLite uses TEXT for ids/slugs/enums/timestamps/JSON/digests, INTEGER for generation/booleans, narrow NOT NULL rules, CHECK constraints for state/is_default/generation, polymorphic type/id targets with domain validation, and Python/domain validation for JSON payloads.
- Batch 40 backend package and dev command shape is accepted: this repository uses `src/nephos_api/`, exposes backend-local `nephos-api` commands, uses `nephos_api.main:app` as the FastAPI entrypoint, accepts `uv run nephos-api db migrate`, `uv run nephos-api db reset --force`, and `uv run nephos-api serve`, keeps `nephos <command>` reserved for `nephos-cli`, and starts API 0.0.1 implementation with the migration/database layer before API skeleton, catalog loader, and reconciler.
- Batch 41 API bootstrap mechanics are accepted: API 0.0.1 backend bootstrap config is env-only with `NEPHOS_API_DB_PATH` and `NEPHOS_API_CATALOG_ROOTS`; SQLite defaults to `.nephos/state/nephos.db`; migrations apply `*.sql` files lexically and record filename-stem versions; dirty migration state fails without automatic repair; rollback/downgrade are out of scope; SQLite uses foreign keys, WAL, and `busy_timeout=5000` with no app-level write retry; repo catalog root is `catalog/`; pytest markers are `unit`, `integration`, and `k3s`; default backend tests exclude `k3s`; Makefile/task-runner wrappers are deferred.
- Batch 42 catalog source identity and errors are accepted: repo-shipped catalog source id is `default`; configured local roots use `local-1`, `local-2`, and `local-3` in configured order; source ids are stable only for the current backend configuration/order; API responses expose source ids but not raw paths by default; `catalogRef.source` and catalog detail `?source=` use source ids; ambiguous duplicate entries return `409 Conflict` with code `catalog_entry_ambiguous`; missing source ids return `404 Not Found` with code `catalog_source_not_found`; installed App/Service rows store `catalog_source_id` and `catalog_source_path`.
- Batch 43 K3s dev integration mechanics are accepted: `nephos-api` tests require a pre-existing reachable K3s cluster and must not install/start/stop/reset/destroy K3s; backend runtime and K3s tests use normal Kubernetes client config resolution with optional `NEPHOS_API_KUBECONFIG` and `NEPHOS_API_KUBE_CONTEXT`; K3s tests require `NEPHOS_API_RUN_K3S_TESTS=1` plus Kubernetes API reachability; default CI excludes K3s integration; K3s tests use generated namespaces/resources labeled `app.kubernetes.io/managed-by: nephos`; cleanup is limited to generated labeled test resources; cluster setup/lifecycle remains user-managed or `nephos-cli`-managed.

Files likely to change:

- `AGENTS.md`
- `.agents/AGENTS.md`
- `.agents/context/nephos-architecture.md`
- `.agents/context/nephos-decisions.md`
- `.agents/context/nephos-glossary.md`
- `.agents/context/nephos-open-questions.md`
- `.agents/context/nephos-auth.md`
- `.agents/context/nephos-resource-policy.md`
- `.agents/context/nephos-upgrades.md`
- `.agents/context/nephos-backups.md`
- `.agents/context/nephos-health-status.md`
- `.agents/context/nephos-runtime-boundaries.md`
- `.agents/context/nephos-phase1.md`
- `.agents/context/nephos-non-goals.md`
- `.agents/context/nephos-service-ownership.md`
- `.agents/context/nephos-packaging.md`
- `.agents/context/nephos-catalog.md`
- `.agents/context/nephos-stack.md`
- `.agents/context/nephos-reconciliation.md`
- `.agents/context/nephos-dev-workflow.md`
- `.agents/context/nephos-contribution-and-agent-workflow.md`
- `.agents/context/nephos-reference-scenario.md`
- `docs/adr/20260517-source-of-truth-for-desired-state.md`
- `docs/adr/20260517-controller-and-reconciliation-architecture.md`
- `docs/adr/20260517-initial-implementation-stack.md`
- `docs/adr/20260517-app-and-service-package-format.md`
- `docs/adr/20260517-app-service-ownership-semantics.md`
- `docs/adr/20260517-resource-policy-philosophy.md`
- `docs/adr/20260517-auth-and-user-model.md`
- `docs/adr/20260517-upgrade-policy.md`
- `docs/adr/20260517-storage-and-backup-semantics.md`
- `docs/adr/20260517-app-and-service-lifecycle-semantics.md`
- `docs/adr/20260517-health-and-status-model.md`
- `docs/adr/20260517-phase-1-scope.md`
- `docs/adr/20260517-namespace-strategy.md`
- `docs/adr/20260517-ingress-and-visibility-model.md`
- `docs/adr/20260517-secrets-model.md`
- `docs/adr/20260517-catalog-source-and-trust-model.md`
- `docs/adr/20260517-local-development-testing-and-distribution.md`
- `docs/adr/20260517-architecture-decision-and-agent-workflow.md`
- `docs/adr/20260517-reference-scenario.md`
- `docs/adr/20260517-nephos-manifest-schema-shape.md`
- `docs/adr/20260517-manifest-field-conventions.md`
- `docs/adr/20260518-reconciliation-execution-model.md`
- `docs/adr/20260518-api-lifecycle-action-shape.md`
- `docs/adr/20260518-api-payload-and-error-shape.md`
- `docs/adr/20260518-database-schema-mechanics.md`
- `docs/adr/20260522-api-read-status-and-catalog-shape.md`
- `docs/adr/20260522-api-response-field-details.md`
- `docs/adr/20260522-api-nested-response-entry-fields.md`

Proposed steps:

- Add the agent rule requiring explicit notice before ADR/context writes.
- Record the accepted stack and repository-boundary decision.
- Accept the source-of-truth ADR.
- Accept the controller/reconciler ADR.
- Update architecture and open-question context.
- Accept the App and Service package format ADR.
- Add packaging context and Service operation terminology.
- Accept the App/Service ownership semantics ADR.
- Add Service instance, shared Service instance, and dedicated Service instance terminology.
- Accept the resource policy ADR.
- Accept the auth and user model ADR.
- Add Phase 1 and non-goal context for resource/auth scope.
- Accept the upgrade policy ADR.
- Accept the storage and backup semantics ADR.
- Update lifecycle semantics for destructive confirmation.
- Add upgrade and backup context.
- Accept the health and status model ADR.
- Add health/status context and terminology.
- Accept the Phase 1 scope ADR.
- Update Phase 1 and non-goal context.
- Accept the namespace strategy ADR.
- Accept the ingress and visibility model ADR.
- Accept the secrets model ADR.
- Add runtime-boundary context.
- Accept the catalog source and trust model ADR.
- Add catalog context.
- Accept the local development, testing, and distribution ADR.
- Add development workflow context.
- Accept the architecture decision and agent workflow ADR.
- Add contribution and agent workflow context.
- Accept the reference scenario ADR.
- Add reference scenario context and draft manifest workspace README.
- Accept the manifest schema shape ADR.
- Add non-canonical draft manifest sketches under `.agents/drafts/manifests/`.
- Accept the manifest field conventions ADR.
- Move draft sketches into directory-per-entry catalog layout under `.agents/drafts/manifests/`.
- Accept the binding model ADR.
- Update binding output and provisioning context.
- Accept required/optional manifest field rules.
- Record the decision not to add PostgreSQL output `fields:` syntax in Phase 1.
- Accept PostgreSQL `app-secret` key serialization.
- Accept Phase 1 config option type set.
- Accept unknown-field rejection after schemas exist.
- Defer raw Kubernetes manifest fallback shape.
- Accept config option object field shape.
- Accept enum option value shape.
- Defer config validation bounds.
- Keep runtime mapping outside config option objects.
- Accept Phase 1 runtime value mapping shape.
- Defer route/storage mapping source kinds and transforms.
- Accept the reconciliation execution model.
- Add reconciliation context and ADR.
- Accept the API lifecycle action shape.
- Accept the API payload and error shape.
- Accept the database schema mechanics.
- Accept the API read/status/catalog shape.
- Accept the API response field details.
- Accept the nested API response entry fields.
- Continue the interview with API implementation details or remaining open questions.

Risks:

- Over-specifying implementation details too early.
- Accidentally documenting the CLI as part of this repository.
- Letting Phase 1 pragmatism weaken the desired-state boundary.
- Letting Helm values become the Nephos product model.
- Pretending Service operation design is finished before real Services prove the contract.
- Reintroducing hidden per-App infrastructure by failing to model dedicated Service instances as Services.
- Duplicating dependent tracking outside bindings.
- Accidentally implying Phase 1 has production-grade resource isolation.
- Designing resource profiles before real workload data exists.
- Designing auth around future multi-user scenarios before the local-first core exists.
- Implying Phase 1 has working backup/restore when it only tracks semantics.
- Treating Kubernetes PVC snapshots as sufficient for database correctness.
- Making Service upgrades look safe without backup support.
- Flattening health into raw Kubernetes readiness and losing Nephos-specific relationship failures.
- Mixing lifecycle state with health status.
- Showing opaque green/red status without reasons.
- Letting Phase 1 expand into Web UI, backup implementation, service mesh, or HA before the platform model exists.
- Hardcoding app behavior instead of exercising the local filesystem catalog/manifest path.
- Accidentally making Cloudflare Tunnel/Tailscale foundational instead of compatible future/manual exposure options.
- Breaking local-first App-to-Service communication by adding default-deny NetworkPolicy before a policy model exists.
- Leaking secrets through status/logs while trying to improve operational transparency.
- Treating local catalog trust as permission to execute arbitrary shell from catalog entries.
- Creating a separate catalog index before manifest metadata proves insufficient.
- Prematurely enforcing strict backend/CLI compatibility before the API, manifest schema, and release matrix stabilize.
- Letting unit tests require a Kubernetes cluster.
- Letting this repository quietly become responsible for CLI implementation workflow.
- Letting agents silently create architecture by implementation.
- Treating draft manifests as accepted schemas or examples.
- Rewriting accepted ADR history instead of superseding/amending decisions.
- Accidentally inferring concrete manifest schema from the reference scenario.
- Letting the Paperless reference scenario expand with Redis/object storage before Phase 1 proves the minimal model.
- Mistaking the Kubernetes-like manifest envelope for CRD-first source of truth.
- Treating draft manifest field names as accepted schema fields.
- Confusing catalog entries with installed App/Service instances.
- Baking full hostnames into App manifests before domain policy is decided.
- Letting binding output details accidentally become raw Secret templates.
- Treating provisioning as arbitrary shell or Helm hooks instead of a typed Nephos contract.
- Letting API handlers mutate Kubernetes inline and bypass the persisted reconciliation request model.
- Overbuilding reconciliation concurrency before single-user/local-first needs it.
- Making drift correction too aggressive and hiding operator changes.
- Making install mutation look owned by the catalog instead of the installed App/Service collection.
- Using `DELETE` for destroy and losing confirmation/force/body semantics.
- Treating framework validation errors as a stable public contract before deciding normalization.
- Exposing opaque ids publicly and weakening local-first inspectability.
- Coupling public slugs to foreign-key relationships and making future rename behavior unnecessarily painful.
- Letting broad database cascades bypass Nephos lifecycle and data-deletion semantics.
- Letting JSON columns become generic untyped resource blobs.
- Overbuilding queue leasing and retry columns before the serialized local-first worker proves it needs them.
- Returning raw database rows as API payloads and freezing persistence shape as product API.
- Dumping raw Kubernetes objects into status and weakening Nephos-aware status semantics.
- Making catalog endpoints own install mutation after deciding install belongs to `/apps` and `/services`.
- Hiding Service dependents behind another endpoint and weakening operational impact visibility.
- Returning raw manifest blobs as catalog responses and freezing draft manifest shape too early.
- Implementing slug rename before route, binding, and relationship consequences are designed.
- Making nested response entries too thin and forcing common inspection workflows into unnecessary follow-up requests.
- Exposing Secret values while trying to make Binding output summaries transparent.

Validation commands:

- `rg --files .agents/context docs/adr`
- `rg -n "CRD|SQLite|Typer|FastAPI|source of truth|reconciler|nephos-cli" .agents/context docs/adr AGENTS.md .agents/AGENTS.md`
- `rg -n "Nephos manifest|Service operation|Helm|raw Kubernetes|local filesystem catalog" .agents/context docs/adr`
- `rg -n "Service instance|dedicated Service instance|shared Service instance|dependent|impact list|default provider" .agents/context docs/adr`
- `rg -n "resource policy|replicas|BestEffort|single-owner|trusted local CLI|RBAC|autoscaling|HA|Phase 1" .agents/context docs/adr`
- `rg -n "upgrade|backup|restore|rollback|destroy|destructive confirmation|persistent data|manual|pinned" .agents/context docs/adr`
- `rg -n "health status|lifecycle state|status reason|status evidence|Nephos-aware|not_applicable|unsupported" .agents/context docs/adr`
- `rg -n "single-node|minimal cluster lifecycle|disable|service mesh|multi-component|Paperless|PostgreSQL|local filesystem catalog" .agents/context docs/adr`
- `rg -n "namespace|NetworkPolicy|Traefik|Cloudflare|Tailscale|Kubernetes Secrets|redacted|route intent" .agents/context docs/adr`
- `rg -n "local filesystem catalog|repo-shipped reference|user-configured|user-created|trusted local-owner|catalog index|remote catalog|signing|sandbox" .agents/context docs/adr`
- `rg -n "uv|pytest|ruff|mocks|fakes|K3s integration|container image|version endpoint|strict compatibility|nephos-cli" .agents/context docs/adr`
- `rg -n "ADR|required|draft|proposed|accepted|superseded|open question|schemas|examples|temporary draft|non-canonical|same change|separate commits" AGENTS.md .agents/AGENTS.md .agents/context docs/adr`
- `rg -n "Paperless|PostgreSQL|postgres|reference scenario|paperless.nephos.local|impact list|draft manifests|.agents/drafts/manifests" AGENTS.md .agents/AGENTS.md .agents/context docs/adr .agents/drafts PLANS.md`
- `rg -n "apiVersion|kind|metadata|spec|Kubernetes-like|CRD|YAML|non-canonical|catalog/apps/paperless|catalog/services/postgres" .agents/context docs/adr .agents/drafts PLANS.md`
- `rg -n "nephos.pro/v1alpha1|catalog/apps|catalog/services|app.yaml|service.yaml|spec.requires|spec.provides|spec.routes|app-secret|values.mappings|full hostnames|domain policy" .agents/context docs/adr .agents/drafts PLANS.md`
- `rg -n "app-secret|host|port|database|username|password|uri|app-scoped-resource|provisioning|deterministic Secret|Secret key serialization" .agents/context docs/adr .agents/drafts PLANS.md`
- `rg -n "required|defaults to an empty list|fields:|canonical examples|manifest validation|command/status shape" .agents/context docs/adr .agents/drafts PLANS.md`
- `rg -n "Secret keys|secret App config|unknown manifest fields|raw Kubernetes manifest fallback shape|string|integer|boolean|enum" .agents/context docs/adr .agents/drafts PLANS.md`
- `rg -n "config options use required|stable machine key|required.*false|value.*label|validation bounds|spec.runtime.values.mappings" .agents/context docs/adr .agents/drafts PLANS.md`
- `rg -n "from.kind|to.helmValue|helmValue|mapping source|missing mapping|transforms|dot path" .agents/context docs/adr .agents/drafts PLANS.md`
- `rg -n "reconciliation request|pending|running|succeeded|failed|blocked|serialized worker|idempotent|retry|drift" .agents/context docs/adr PLANS.md`
- `rg -n "POST /apps|POST /services|actions/destroy|DELETE|202 Accepted|409 Conflict|force|impact list|idempotent" .agents/context docs/adr PLANS.md`
- `rg -n "catalogRef|instanceName|resource.*reconciliation|dependency_blocked|requiresForce|bindingAlias|validation errors|/apps/paperless" .agents/context docs/adr PLANS.md`
- `rg -n "internal stable text|unique public|created_at|updated_at|CHECK|foreign key|ON DELETE|schema_migrations|target_type|target_id|resource_type|resource_id|JSON text" .agents/context docs/adr PLANS.md`
- `rg -n "appinst_|svcinst_|binding_|domain_|reconcile_|status_|createdAt|updatedAt|observedAt|/catalog/apps|/catalog/services|actions/reconcile|status payload|domain snapshots" .agents/context docs/adr PLANS.md`
- `rg -n "bindings|routes|provides|dependents|redacted output|Secret summary|source|subject|manifestDigest|raw manifest|rename API|immutable" .agents/context docs/adr PLANS.md`
- `rg -n "serviceInstance|canonicalUrl|bindingOutputTargets|bindingAlias|secretName|namespace|redacted|requires|aliases|target" .agents/context docs/adr PLANS.md`
- `git diff -- AGENTS.md .agents/AGENTS.md .agents/context docs/adr PLANS.md`

Rollback notes:

- Revert only these documentation edits if the accepted decisions change.
- Do not revert Fer's ADR filename renames.

Open questions:

- Manifest validation schema details.
- Service operation declaration/schema/API/CLI design beyond the accepted boundary.
- Dedicated Service sharing policy details.
- Future resource profile design.
- Future auth/RBAC model.
- Concrete backup implementation design.
- Health/status check implementation details.
- Reference scenario manifest sketches and data preservation checks.
- Exact CLI command spelling for ingress root domain operations.
- Whether Nephos setup is interactive, flag-driven, or both.
- Exact setup command spelling in `nephos-cli`.
- Setup idempotency behavior.
- App install behavior when setup is missing.
- Secret rotation details.
- Catalog source/trust beyond local filesystem.
- `../nephos-cli` local backend configuration details.
- Exact `nephos-cli` cluster setup/reset workflow.
- Exact generated K3s test namespace name format, stricter allowed-context/server safety checks, future K3s CI job shape, Kubernetes client fixture implementation, and coverage expectations.
- Backend/CLI release process and future compatibility matrix.
- Reference scenario exact command spelling and status output.
- Draft manifest naming and cleanup conventions.
- Target snapshot JSON fields, request claiming behavior, polling, retry count/backoff, and status evidence data payloads.
- Additional implementation-only response model names and exact FastAPI/Pydantic validation model names.
