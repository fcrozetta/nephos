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
- `.agents/context/nephos-phase1.md`
- `.agents/context/nephos-non-goals.md`
- `.agents/context/nephos-service-ownership.md`
- `.agents/context/nephos-packaging.md`
- `.agents/context/nephos-stack.md`
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
- Continue the interview with remaining Phase 1 scope or catalog trust.

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

Validation commands:

- `rg --files .agents/context docs/adr`
- `rg -n "CRD|SQLite|Typer|FastAPI|source of truth|reconciler|nephos-cli" .agents/context docs/adr AGENTS.md .agents/AGENTS.md`
- `rg -n "Nephos manifest|Service operation|Helm|raw Kubernetes|local filesystem catalog" .agents/context docs/adr`
- `rg -n "Service instance|dedicated Service instance|shared Service instance|dependent|impact list|default provider" .agents/context docs/adr`
- `rg -n "resource policy|replicas|BestEffort|single-owner|trusted local CLI|RBAC|autoscaling|HA|Phase 1" .agents/context docs/adr`
- `rg -n "upgrade|backup|restore|rollback|destroy|destructive confirmation|persistent data|manual|pinned" .agents/context docs/adr`
- `rg -n "health status|lifecycle state|status reason|status evidence|Nephos-aware|not_applicable|unsupported" .agents/context docs/adr`
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
- Catalog source/trust beyond local filesystem, remaining Phase 1 scope, contribution workflow, and reference scenario.
