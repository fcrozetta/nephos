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

## Current Plan: Architecture Context Completion

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
- Batch 27 database desired-state model is accepted: API 0.0.1 uses SQLite with plain SQL through a small repository/data-access layer, no full ORM, explicit SQL migration files with `migrations/0000_initial.sql` as the initial schema, destructive local reset allowed before the first usable version, normalized table families for app instances/service instances/bindings/platform domains/status snapshots/reconciliation requests/schema migrations, JSON text columns for validated snapshots and flexible payloads, catalog identity/version/source/digest metadata on installed records, latest status snapshots only, DB-persisted reconciliation requests, desired-state mutation and reconciliation request in one transaction, and destroy removes active desired-state rows without requiring audit/history in API 0.0.1.
- Batch 28 catalog/manifest loading is accepted: API 0.0.1 supports one repo-shipped catalog root plus optional backend-local configured filesystem roots, custom roots are not platform DB desired state yet, manifests are read/validated on demand, catalog entries are not imported into SQLite before use, directory slug must match `metadata.name`, duplicate kind/name across roots errors unless source is explicitly selected, validation starts with typed Python/Pydantic domain models, JSON Schema remains blocked, install selects catalog kind/name plus optional source rather than arbitrary path, installed records store catalog kind/name/version-if-present/source and SHA-256 manifest digest, full manifest snapshots are not stored by default, drafts stay non-canonical until API validation models exist and Fer approves promotion, and `metadata.version` remains optional.
- Batch 29 reconciliation execution is accepted: API 0.0.1 uses an API-owned in-process background reconciler with persisted SQLite reconciliation requests; mutating API calls write desired-state changes plus a reconciliation request in one transaction and return after commit; requests target one App instance, Service instance, binding, or platform domain configuration; request states are `pending`, `running`, `succeeded`, `failed`, and `blocked`; handlers must be idempotent and safe to retry; one serialized worker is accepted initially; simple capped retry is intended but automatic retry may be deferred from API 0.0.1 if heavy; the reconciler writes latest status snapshots; failures do not roll back desired state; drift is detected/reported for Nephos-owned resources and reconciled only when desired state or manual reconciliation asks for it.
- Batch 30 API lifecycle action shape is accepted: install mutation uses `POST /apps` and `POST /services` with catalog refs in the body; catalog install endpoints are not primary; lifecycle uses `POST /apps/{appInstance}/actions/start|stop|remove|destroy` and equivalent Service paths; destroy stays a confirmed `POST .../actions/destroy`, not `DELETE`; dependency-blocked Service lifecycle returns `409 Conflict` with impact list unless forced; mutating responses prefer `202 Accepted` with resource/reconciliation request/status metadata; repeated lifecycle requests to the same desired state are idempotent.
- Batch 31 API payload/error shape is accepted: public API paths use installed instance slugs, not opaque UUIDs; install bodies use `catalogRef` with `kind`, `name`, optional `source`, optional `instanceName`, optional `config`, and App install `bindings`; lifecycle action bodies use optional `force` and `confirm`, with `confirm` required only for destroy; mutation responses use `{ resource, reconciliation, status? }`; Nephos-owned domain errors use `{ error: { code, message, details? } }`; dependency-blocked impact details include `requiresForce`, dependent App instance, binding id, binding alias, and capability; FastAPI/Pydantic validation errors may remain framework-shaped for API 0.0.1 and are not stable Nephos product API.
- Batch 32 database schema mechanics are accepted: database relationships use internal stable text ids, user-addressable installed resources use unique public slugs, core domain tables include `id`, `created_at`, and `updated_at`, state fields use SQLite `CHECK` constraints, SQLite foreign keys are enabled with restrictive relationships by default, lifecycle deletes happen through explicit domain transactions rather than broad cascades, JSON text columns are only for validated snapshots/flexible payloads, API 0.0.1 reconciliation requests use the minimal accepted field set, latest status snapshots are keyed by resource target, and `schema_migrations` uses `version TEXT PRIMARY KEY` plus `applied_at TEXT`.
- Batch 33 API read/status/catalog shape is accepted: internal ids use typed prefixes plus UUID4 hex suffixes, timestamps are app-generated UTC ISO strings with `Z`, read payloads are domain snapshots with ids and slugs rather than raw DB rows, status payloads include level/lifecycle/reconciliation/reason/message/evidence/observedAt, manual reconcile uses target-specific action subresources, and read-only catalog endpoints are `/catalog/apps`, `/catalog/apps/{name}`, `/catalog/services`, and `/catalog/services/{name}` with optional source selection.

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
- `git diff -- AGENTS.md .agents/AGENTS.md .agents/context docs/adr PLANS.md`

Rollback notes:

- Revert only these documentation edits if the accepted decisions change.
- Do not revert Fer's ADR filename renames.

Open questions:

- Manifest validation schema details.
- Database exact full column definitions, indexes, migration/reset commands, polymorphic target reference handling, and SQLite locking behavior.
- Catalog root config/env shape, source identifier format, duplicate-entry error shape, and catalog list/read API response field set.
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
- Local development command details.
- Testing command/marker/CI details.
- Backend/CLI release process and future compatibility matrix.
- Reference scenario exact command spelling and status output.
- Draft manifest naming and cleanup conventions.
- Additional reconciliation request columns beyond the accepted minimum, locking, polling, retry count/backoff, and status evidence schema.
- Exact resource-specific response fields, exact status evidence object fields, future validation error normalization, and future rename behavior for installed instance slugs.
