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

## Current Plan: API 0.0.1 Runtime Convergence

Goal:

- Deliver Nephos API 0.0.1 end to end: API desired state, persisted reconciliation, and real Kubernetes runtime convergence for the accepted Phase 1 backend flow.

Non-goals:

- Do not implement `nephos-cli` in this repository.
- Do not let Kubernetes, Helm, YAML files, or the CLI become the source of truth.
- Do not let Pulumi state become the Nephos source of truth.
- Do not add canonical schemas under `schemas/`.
- Do not promote draft manifests into canonical `catalog/` entries until manifest validation models exist and Fer approves promotion.
- Do not add Makefile or task-runner wrappers for API 0.0.1.
- Do not start, stop, install, reset, or destroy the selected Kubernetes cluster from this repository.
- Do not expose a general Service operation API or CLI UX.
- Do not implement arbitrary catalog-defined shell commands, Helm hooks, or user scripts as provisioning semantics.

Current understanding:

- This repository is `nephos-api`, the backend/control-plane repository.
- The user-facing CLI belongs to the separate `../nephos-cli` repository.
- Bootstrap foundation exists for migrations, repositories, API skeleton, catalog loading, lifecycle actions, reconciliation requests, status snapshots, and Kubernetes client/runtime primitives.
- Backend package layout is `src/nephos_api/`.
- FastAPI entrypoint is `nephos_api.main:app`.
- Backend-local command is `nephos-api`.
- Accepted backend-local commands are:
  - `uv run nephos-api init`
  - `uv run nephos-api db migrate`
  - `uv run nephos-api db reset --force`
  - `uv run nephos-api serve`
  - `uv run nephos-api dev smoke`
- `uv run nephos-api init` loads backend bootstrap environment, applies pending migrations, and ensures one default internal platform domain without mutating the selected Kubernetes cluster or creating App/Service reconciliation requests.
- The default internal platform domain is `internal` / `nephos.local`; `NEPHOS_API_INTERNAL_DOMAIN` or `uv run nephos-api init --internal-domain <dns-suffix>` overrides the domain suffix on first initialization.
- Local browser testing without `/etc/hosts` should use a resolvable suffix such as `nephos.localhost`; Traefik or another ingress controller does not provide DNS resolution by itself.
- `uv run nephos-api serve` applies pending migrations before starting FastAPI and the reconciler worker.
- SQLite is the canonical Phase 1 desired-state database.
- Default DB path is `.nephos/state/nephos.db` relative to the backend process working directory.
- Bootstrap configuration is environment-only:
  - `NEPHOS_API_DB_PATH`
  - `NEPHOS_API_CATALOG_ROOTS`
  - `NEPHOS_API_KUBECONFIG`
  - `NEPHOS_API_KUBE_CONTEXT`
  - `NEPHOS_API_INTERNAL_DOMAIN`
  - `NEPHOS_API_INGRESS_CLASS`
- Migrations live under `src/nephos_api/migrations/`, run lexically, and record filename stems in `schema_migrations`.
- SQLite connections must enable foreign keys, WAL mode, and `busy_timeout=5000`.
- API 0.0.1 initial schema contains:
  - `app_instances`
  - `service_instances`
  - `bindings`
  - `platform_domains`
  - `status_snapshots`
  - `reconciliation_requests`
  - `schema_migrations`
- Kubernetes runtime tests target the selected kubeconfig/context, are opt-in with `NEPHOS_API_RUN_KUBERNETES_TESTS=1`, and are excluded from default tests.
- Accepted namespace strategy is `app-<slug>` for Apps and `svc-<slug>` for Services.
- Nephos-owned namespaces and resources must carry `app.kubernetes.io/managed-by: nephos` plus accepted relationship labels.
- Reconciler handlers must be idempotent and mutate only Nephos-owned resources.
- Pulumi is accepted as the forward internal provider execution backend: Nephos owns meaning, Pulumi performs labor.
- Nephos API/SQLite desired state remains canonical; Pulumi state is observed provider state.
- API handlers and CLI clients do not call Pulumi directly.
- API 0.0.1 App and Service provider packages are Python-only.
- Expected internal package direction is `src/nephos_api/providers/`.
- The existing direct Helm CLI adapter is superseded as the forward direction by the Pulumi provider boundary, though it may remain as temporary implementation history or fallback while Pulumi provider code lands.
- Direct Helm is secondary for Services because Services need typed provider actions beyond generated config files.
- Service provider actions include lifecycle, app-scoped binding provisioning, deprovisioning, status/evidence, and future maintenance behavior.
- Helm charts may remain implementation inputs underneath Python Pulumi Service providers.
- Manifest runtime references support provider-backed runtimes with `spec.runtime.type: provider` and `spec.runtime.provider.name`; Helm chart metadata is required only for `spec.runtime.type: helm`.
- The default deployer routes provider-backed runtimes to internal Python Pulumi/Kubernetes providers and Helm-backed runtimes to the Pulumi Helm provider.
- PostgreSQL app-scoped provisioning is accepted as a typed backend/API-owned internal handler.
- API 0.0.1 PostgreSQL provisioning uses backend-owned Kubernetes API calls, a Nephos-owned Service-side credential Secret, the PostgreSQL provider administrator Secret convention, and idempotent `psql` execution inside the Nephos-owned PostgreSQL runtime pod.
- PostgreSQL `psql` execution uses an explicit shell exit marker and fails closed when Kubernetes exec output does not prove the command exit code.
- API 0.0.1 generated App Ingress resources route to the internal App runtime Service name `app-<app-instance>` and use App route `target.port` as the backend Service port.
- API 0.0.1 generated App Ingress resources set `ingressClassName` from `NEPHOS_API_INGRESS_CLASS`, or auto-detect exactly one/default cluster `IngressClass`.
- Successful binding materialization enqueues an App reconcile request for the consuming App so App runtime convergence can recover if the initial App install request was blocked on missing binding values.
- Binding reconciliation treats removed or pending-destroy consumer Apps as not applicable and does not provision app-scoped Service resources, create App namespaces, or write binding Secrets for them.
- Successful Service runtime deployment enqueues reconciliation for current dependent bindings so bindings can recover when a Service becomes available after an earlier blocked attempt, without duplicating an already pending or running binding request for the same generation and without waking removed or pending-destroy Apps.
- Existing runtime namespaces are reused only when they carry the expected Nephos ownership labels.
- The default lazy runtime/provisioner wrappers used by `nephos-api serve` forward lifecycle and deprovisioning operations, not just install/provision operations.
- App destroy uninstalls the App runtime before deprovisioning app-scoped Service resources.
- Forced Service destroy best-effort deprovisions dependent bindings, removes App-side binding Secrets, queues dependent App reconciliation, and only then removes dependent binding rows before deleting the Service desired-state row. Missing Service-side runtime during force destroy must not block App-side secret cleanup or Service namespace teardown.
- Kubernetes runtime safety refusals are reported as blocked reconciliation with reason `runtime_safety_blocked`, not generic runtime failures.
- Nested App binding and Service dependent entries expose compact binding status snapshots when status exists.
- Kubernetes runtime deletion helpers wait for Nephos-owned App Ingresses and namespaces to read as absent before reconciliation marks remove/destroy work succeeded.
- Kubernetes runtime refuses to reuse, scale, or reconcile Ingress in terminating namespaces.
- Binding Secret writes and binding Secret reads require an active Nephos-owned App namespace.
- PostgreSQL app-scoped provisioning requires an active Nephos-owned Service namespace before reading administrator Secrets, runtime pods, or Service-side credential Secrets.
- Catalog validation rejects invalid or duplicate App binding aliases, invalid or duplicate App route names, invalid capability/provider identifiers, duplicate provided Service aliases, and duplicate Service binding output names.
- Catalog validation rejects invalid App config option names, config defaults whose value type does not match the declared option type, enum config options without values, and enum defaults outside the allowed values.
- App install explicit provider selection uses `bindings.<alias>.serviceInstance`, where `alias` is the App requirement alias after defaulting and `serviceInstance` is the installed Service instance slug.
- App install validates supplied config against the App manifest's Phase 1 config options before writing desired state.
- App install rejects missing or pending-destroy Service providers with `binding_provider_unavailable`.
- Platform domain reconciliation marks domain desired state reconciled and enqueues App `reconcile` requests for installed, non-removed Apps with route intent so ingress host changes converge through the normal App runtime path.
- Manual platform domain reconciliation is exposed through `POST /platform/config/domains/actions/reconcile` and queues the same platform-domain reconciliation flow.
- Manual App/Service `reconcile` must converge the persisted desired lifecycle. It must not redeploy removed resources or treat stopped resources as running.
- Repeated App/Service lifecycle requests that already match the current desired lifecycle do not bump desired-state generation.
- Pending destroy blocks later `start`, `stop`, and `remove` lifecycle mutations with `409 Conflict`; repeated `destroy` keeps the original `deleteRequestedAt` timestamp.
- Repeated Service `stop`, `remove`, or `destroy` requests that are already no-ops do not require `force` just because dependents still exist.
- Reconciler-written App/Service status snapshots include the persisted desired lifecycle in the status payload.
- App route response entries expose compact App runtime status once reconciliation has observed the App.
- The previous manual reference flow leaked a temporary local chart server and external catalog root into user testing; that path is removed.
- `uv run nephos-api dev smoke` now runs the Nephos-owned runtime proof: it creates a temporary internal reference catalog, reconciles a provider-backed PostgreSQL Service and reference web App through internal Python Pulumi/Kubernetes providers, verifies binding/route/lifecycle behavior, and cleans up owned runtime resources.
- The opt-in Kubernetes runtime test now uses the same provider-backed reference catalog shape and no longer requires a configured reference catalog root.
- Local development and manual testing can put bootstrap variables in `.env`; real environment variables override `.env`.
- Pulumi CLI is installed locally for runtime testing and reports `v3.244.0`.
- Pulumi local backend runtime testing requires `PULUMI_CONFIG_PASSPHRASE` or `PULUMI_CONFIG_PASSPHRASE_FILE`; missing configuration blocks with `pulumi_passphrase_missing`.

Files likely to change:

- `docs/maintainers.md`
- `README.md`
- `PLANS.md`
- `pyproject.toml`
- `uv.lock`
- `src/nephos_api/reconciler.py`
- `src/nephos_api/providers/`
- `src/nephos_api/repository.py`
- `src/nephos_api/kubernetes_runtime.py`
- `src/nephos_api/catalog.py`
- `src/nephos_api/api/resources.py`
- `tests/test_packaging.py`
- `tests/test_reconciler.py`
- `tests/test_kubernetes_runtime.py`
- `tests/test_kubernetes_runtime_integration.py`
- runtime-focused tests under `tests/`
- architecture context or ADRs only if implementation exposes a missing decision, after explicit notice to Fer

Proposed steps:

1. Runtime namespace convergence slice:
   - Inject a Kubernetes runtime adapter into the reconciler.
   - Handle App and Service install requests by ensuring accepted namespaces and labels exist.
   - Mark reconciled install requests `succeeded` only after runtime mutation succeeds.
   - Write `healthy` status snapshots with structured evidence.
   - Keep unsupported targets/actions explicitly blocked rather than pretending full convergence.
2. Runtime lifecycle namespace safety slice:
   - Preserve namespaces for stop/remove.
   - Delete only Nephos-owned namespaces for destroy after the accepted API destroy confirmation path creates a request.
   - Wait for namespace absence before treating destroy runtime teardown as succeeded.
   - Keep desired-state rows until runtime teardown succeeds.
   - Refuse to reuse pre-existing unowned namespaces during install/start/reconcile.
   - Refuse to treat terminating namespaces as valid runtime targets.
   - Forward stop scaling through the lazy runtime path used by `nephos-api serve`.
3. Binding materialization slice:
   - Create App namespace Secrets for binding outputs with accepted names, labels, and redacted summaries.
   - Require the App namespace to be active and Nephos-owned before writing or reading binding Secrets.
   - Keep Secret values out of API status and evidence.
   - Block PostgreSQL credential materialization until provisioning output exists.
   - Enqueue an App reconcile request after binding materialization so dependency ordering races do not strand App install.
   - Allow App install callers to select a provider explicitly when multiple eligible Service instances exist.
4. Helm runtime decision slice:
   - Treat the direct Helm CLI adapter as superseded implementation history.
   - Keep Helm chart identity below Nephos manifests where Helm packaging gives leverage.
5. Pulumi provider boundary slice:
   - Add internal Python provider package boundaries under `src/nephos_api/providers/`. Done.
   - Keep reconciler-owned calls to provider interfaces; do not let API handlers call Pulumi. Done.
   - Add Pulumi-backed App and Service runtime providers behind the existing deploy/uninstall contract. Done.
   - Make Service providers expose typed internal actions beyond Helm install/uninstall/config values.
   - Ensure Pulumi state, previews, and apply outputs are redacted runtime evidence only. Pending evidence-field design.
   - Preserve Nephos SQLite desired state as the source of truth. Done.
   - Keep API 0.0.1 providers Python-only. Done.
6. PostgreSQL provisioning implementation slice:
   - Implement idempotent app-scoped database/user provisioning for the accepted PostgreSQL capability.
   - Return accepted binding output fields: `host`, `port`, `database`, `username`, `password`, and `uri`.
   - Ensure the default lazy provisioner path forwards App destroy deprovisioning.
   - Uninstall App runtime before deprovisioning App-scoped resources.
   - During forced Service destroy, deprovision dependent bindings while the Service runtime still exists when possible, but treat missing provider runtime as best-effort cleanup so App-side binding Secrets, affected App reconciliation, binding row removal, and Service teardown still proceed.
7. End-to-end Kubernetes reference flow:
   - Run opt-in Kubernetes runtime tests only with `NEPHOS_API_RUN_KUBERNETES_TESTS=1`.
   - Requires a pre-existing reachable Kubernetes cluster.
   - Use Nephos-owned temporary provider-backed reference catalog entries; do not require an external catalog root or local chart server.
   - Verify Service install, App install, binding materialization, generated Ingress, route intent/status, lifecycle, App Ingress absence after remove, and namespace absence after destroy.
   - Verify manual App reconcile respects stopped and removed desired lifecycle states.
   - Verify platform domain changes enqueue App route reconciliation rather than leaving platform-domain requests blocked.
   - Keep cluster lifecycle external to this repo.
8. Manual runtime smoke command:
   - Expose the end-to-end runtime proof as `uv run nephos-api dev smoke`.
   - Drive the flow through Nephos API desired state and the reconciler, not pytest as the user interface.
   - Keep reference catalog generation internal and temporary.
   - Do not require Helm, a local chart server, or `NEPHOS_API_K3S_REFERENCE_CATALOG_ROOT`.
   - Keep the command runnable from an installed wheel by packaging runtime dependencies imported by the command path, including FastAPI/Starlette `TestClient`'s `httpx`/`httpx2` dependencies.
9. Code simplification batch:
   - Preserve public API behavior, lifecycle semantics, reconciliation request semantics, and exact Nephos error codes.
   - Consolidate duplicated App/Service lifecycle action application in `api/resources.py`.
   - Consolidate duplicated App/Service desired-state repository insert/update helpers in `repository.py`.
   - Split binding provider resolution in `api/resources.py` into smaller explicit validation/selection helpers.
   - Do not touch reconciler/runtime/provider architecture in this batch.
10. Documentation audience split and comment convention:
   - Keep `README.md` useful for users evaluating or trying Nephos.
   - Move maintainer workflow, verification, architecture links, and comment conventions into Markdown files under `docs/`.
   - Use Better Comments syntax for non-obvious code invariants and API contract warnings.
   - Avoid turning maintainer internals into README content.

Current verification:

- `uv run pytest -m "not kubernetes"` passes.
- `uv run ruff check .` passes.
- `uv lock --check` passes.
- `git diff --check` passes.
- `uv run nephos-api db reset --force` passes against a temp SQLite DB.
- `uv run nephos-api db migrate` passes against a temp SQLite DB.
- `uv run nephos-api serve --port 8765` starts successfully with the Pulumi provider path configured.
- `curl http://127.0.0.1:8765/version` returns `{"name":"nephos-api","version":"0.0.1"}`.
- `curl http://127.0.0.1:8765/healthz` returns `{"status":"ok"}`.
- `uv run pytest -m kubernetes -q` skips Kubernetes runtime tests without explicit opt-in, as intended.
- `uv run nephos-api init` passes against a temp SQLite DB, creates `internal` / configured internal domain, and writes no reconciliation requests.
- Fresh minimal flow passes with `/private/tmp/nephos-flow-check/nephos.db`: `uv run nephos-api init`, `uv run nephos-api serve --port 8766`, `curl /version`, and `curl /healthz`.
- `pulumi version` returns `v3.244.0`.
- `uv run nephos-api dev smoke --timeout-seconds 240` passes against `.env` selecting `NEPHOS_API_KUBE_CONTEXT=docker-desktop`; it verified provider-backed PostgreSQL Service install, reference web App install, binding materialization, generated route `http://reference-web-<suffix>.nephos.localhost`, stop/start lifecycle, and App/Service destroy cleanup.
- Clean installed-wheel smoke passes: build the wheel, install it into a fresh virtualenv without dev dependencies, verify wheel metadata includes `httpx` and `httpx2`, and run installed `nephos-api dev smoke --timeout-seconds 120` successfully.
- `uv run pytest tests/test_kubernetes_runtime_integration.py -m kubernetes -q` passes against `.env` selecting `NEPHOS_API_KUBE_CONTEXT=docker-desktop`: 3 passed, 17 warnings.
- Manual route proof: `curl http://hello-world.nephos.localhost/` returns `200 OK` through the selected cluster ingress controller after generated Ingress uses `ingressClassName: nginx`.

Risks:

- Weakening the desired-state boundary by making FastAPI handlers mutate Kubernetes inline.
- Promoting draft manifests into canonical catalog examples without approval.
- Implementing PostgreSQL provisioning mechanics without an accepted decision.
- Letting reset/migration commands look like `nephos-cli` product UX.
- Hiding authoritative relationships in JSON blobs.
- Letting Kubernetes namespace deletion bypass lifecycle and data-deletion semantics.
- Letting Pulumi stack state, generated programs, or provider outputs become canonical Nephos state.
- Letting Pulumi collapse Nephos lifecycle verbs into create/update/destroy.
- Treating Services as Helm charts plus config files rather than Python provider actions.
- Supporting multiple provider implementation languages before the Python-only API 0.0.1 provider package proves itself.
- Treating framework validation errors as stable Nephos domain errors.
- Overbuilding queue leasing, retry, or concurrency before API 0.0.1 needs it.
- Calling the API 0.0.1 ready while requests still stop at `runtime_handler_missing`.
- Letting Pulumi local backend prerequisites fail as raw Pulumi errors instead of Nephos runtime blockers.

Validation commands:

- `uv run pytest -m "not kubernetes"`
- `uv run ruff check .`
- `uv run nephos-api init`
- `uv run nephos-api db migrate`
- `uv run nephos-api db reset --force`
- `uv run nephos-api serve`
- `uv run nephos-api dev smoke`
- Clean-wheel smoke guard: build `dist/nephos_api-0.0.1-py3-none-any.whl`, install it into a fresh virtualenv without dev dependencies, and run `nephos-api dev smoke` far enough to prove `TestClient` dependencies are present.
- `NEPHOS_API_RUN_KUBERNETES_TESTS=1 PULUMI_CONFIG_PASSPHRASE=<local-passphrase> uv run pytest tests/test_kubernetes_runtime_integration.py -m kubernetes -q`
- `rg --files src tests migrations`
- `git diff --check`

Rollback notes:

- Revert only implementation files from the current slice if the approach changes.
- Keep accepted ADR/context decisions intact unless Fer explicitly changes them.
- Remove `.nephos/state/` generated local state rather than committing it.
- Do not revert unrelated user changes.

Open questions:

- Canonical catalog example promotion.
- Stricter Kubernetes allowed-context/server safety checks beyond explicit opt-in and reachability.
- Future Kubernetes runtime CI job shape.
- Canonicalizing the reference catalog examples in this repository remains unapproved.
- Provider operation lock table shape.
- Exact redacted Pulumi preview/apply evidence fields.
