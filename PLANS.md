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
- Batch 6 health/status decisions are accepted: Nephos status is Nephos-aware and aggregates desired state, reconciliation, Kubernetes readiness/existence, bindings, dependencies, routes, storage, and backup status; Phase 1 implements a minimal subset; removed/destroyed are lifecycle states, not health statuses; backup participates as unsupported in Phase 1; status must include reasons/evidence; Service status includes dependent impact.
- Batch 7 Phase 1 scope decisions are accepted: single-node K3s, minimal cluster lifecycle, App/Service install/start/stop/remove/destroy, `disable` deferred, basic ingress intent, local filesystem catalog from day one with tiny repo-shipped reference entries, no service mesh, multi-component Apps communicate through normal Kubernetes Services/networking, and Paperless + PostgreSQL is the canonical reference scenario.
- Batch 8 runtime boundary decisions are accepted: one namespace per App instance and Service instance, `nephos-system` for control-plane/runtime support components, no default-deny NetworkPolicy in Phase 1, Traefik local ingress first, manual Cloudflare Tunnel compatibility without tunnel automation, stopped Apps keep route intent, Kubernetes Secrets for Phase 1, binding credentials materialized into App namespaces, and secret values redacted by default.
- Batch 9 catalog decisions are accepted: Phase 1 supports repo-shipped reference catalog entries and user-configured local filesystem catalog paths, user-created local entries are allowed without schema stability promise until manifest schema acceptance, local catalog files are trusted local-owner input, remote trust/signing/sandboxing are deferred, and minimal catalog metadata lives in App/Service manifests rather than a separate index.
- Batch 10 development/testing/distribution decisions are accepted: backend local dev uses `uv`, backend tests use `pytest`, lint/format checks use `ruff`, unit tests use mocks/fakes, Kubernetes integration tests use real K3s, Phase 1 backend distribution is local process plus container image, full installer packaging is deferred, CLI workflow belongs to `../nephos-cli`, and Phase 1 has backend/CLI version awareness without strict compatibility blocking.
- Batch 11 contribution/agent workflow decisions are accepted: ADRs are required for architecture-significant changes, ADR statuses have explicit meanings, agents must ask or record open questions before implementing through architectural ambiguity, canonical schemas/examples require Fer approval, temporary draft manifests are allowed only in a clearly marked non-canonical draft workspace outside `schemas/` and `examples/`, architecture-changing work updates ADR/context/open questions in the same change, and architecture decision batches should be committed separately when feasible.
- Batch 12 reference scenario decisions are accepted: `.agents/drafts/manifests/` is the non-canonical draft manifest workspace, Paperless plus PostgreSQL is the canonical Phase 1 reference scenario, Paperless requires only PostgreSQL in the reference scenario, the flow includes install/bind/local route/stop/start/remove/destroy, Service dependency impact is included by attempting to stop PostgreSQL while Paperless depends on it, and route examples stay illustrative with placeholders such as `paperless.<local-domain>`.

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
- Continue the interview with manifest schema or remaining open questions.

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
- `rg -n "Paperless|PostgreSQL|postgres|reference scenario|paperless.<local-domain>|impact list|draft manifests|.agents/drafts/manifests" AGENTS.md .agents/AGENTS.md .agents/context docs/adr .agents/drafts PLANS.md`
- `git diff -- AGENTS.md .agents/AGENTS.md .agents/context docs/adr PLANS.md`

Rollback notes:

- Revert only these documentation edits if the accepted decisions change.
- Do not revert Fer's ADR filename renames.

Open questions:

- Manifest schema details.
- Service operation contract design.
- Dedicated Service sharing policy details.
- Future resource profile design.
- Future auth/RBAC model.
- Concrete backup implementation design.
- Health/status check implementation details.
- Reference scenario manifest sketches and data preservation checks.
- Namespace label/slug details.
- Local ingress hostname/TLS details.
- Secret naming/rotation details.
- Catalog source/trust beyond local filesystem.
- Local development command details.
- Testing command/marker/CI details.
- Backend/CLI release process and future compatibility matrix.
- Reference scenario exact command spelling and status output.
- Draft manifest naming and cleanup conventions.
