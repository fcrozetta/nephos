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

Files likely to change:

- `AGENTS.md`
- `.agents/AGENTS.md`
- `.agents/context/nephos-architecture.md`
- `.agents/context/nephos-decisions.md`
- `.agents/context/nephos-open-questions.md`
- `.agents/context/nephos-stack.md`
- `docs/adr/20260517-source-of-truth-for-desired-state.md`
- `docs/adr/20260517-controller-and-reconciliation-architecture.md`
- `docs/adr/20260517-initial-implementation-stack.md`

Proposed steps:

- Add the agent rule requiring explicit notice before ADR/context writes.
- Record the accepted stack and repository-boundary decision.
- Accept the source-of-truth ADR.
- Accept the controller/reconciler ADR.
- Update architecture and open-question context.
- Continue the interview with packaging and Service ownership.

Risks:

- Over-specifying implementation details too early.
- Accidentally documenting the CLI as part of this repository.
- Letting Phase 1 pragmatism weaken the desired-state boundary.

Validation commands:

- `rg --files .agents/context docs/adr`
- `rg -n "CRD|SQLite|Typer|FastAPI|source of truth|reconciler|nephos-cli" .agents/context docs/adr AGENTS.md .agents/AGENTS.md`
- `git diff -- AGENTS.md .agents/AGENTS.md .agents/context docs/adr PLANS.md`

Rollback notes:

- Revert only these documentation edits if the accepted decisions change.
- Do not revert Fer's ADR filename renames.

Open questions:

- App and Service package format.
- Service ownership and sharing semantics.
- Resource policy, auth, upgrades, catalog source, health/status, backups, Phase 1 scope, non-goals, contribution workflow, and reference scenario.
