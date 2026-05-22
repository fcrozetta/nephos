# Service Operation Contract Boundary

- Status: accepted
- Date: 2026-05-18
- Tags: services, operations, lifecycle, phase-1

## Context and Problem Statement

Services may need management actions beyond install, start, stop, remove, and destroy.

Examples include provisioning an app-scoped database, rotating credentials, running diagnostics, and future backup or restore actions.

Nephos needs to reserve this concept without turning Service manifests into arbitrary command runners or exposing an unstable operation API before the core API exists.

## Decision

Reserve Service operations as typed backend/API-owned Service management actions.

Service operations are not arbitrary shell commands, Helm hooks, Kubernetes jobs, or user-provided scripts exposed as product semantics.

Phase 1 may use internal typed Service handlers for the minimal provisioning work required by accepted capabilities, such as PostgreSQL app-scoped database and credential creation.

Phase 1 does not include a general user-facing Service operation API or CLI UX.

`spec.operations[]` remains reserved in Service manifests and defaults to an empty list.

Do not define canonical operation input/output schemas under `schemas/` until Fer approves the concrete shape.

Do not promote Service operation examples under `examples/` until the operation contract is accepted beyond this boundary decision.

When user-facing or risky Service operations are introduced later, they must be dependency-aware and status/audit visible.

Destructive or risky operations must require explicit confirmation.

## Considered Options

### Typed backend-owned operations, internal first

Service operations are named typed actions implemented by Nephos backend code or approved adapters.

They may be used internally for provisioning while the general API/CLI remains deferred.

- Good, because it preserves the Nephos platform boundary.
- Good, because it avoids arbitrary code execution from catalog manifests.
- Good, because API 0.0.1 can implement necessary provisioning without committing to a broad operation UX.
- Bad, because Service authors cannot yet extend operations freely through manifests.

### Manifest-declared scripts or hooks

Service manifests declare commands, scripts, or hooks to run for provisioning and management.

- Good, because it is flexible.
- Bad, because it turns the catalog into a code execution surface.
- Bad, because it blurs Nephos semantics with runtime implementation details.
- Bad, because it makes trust, idempotency, audit, retries, and safety prompts much harder.

### Defer the concept entirely

Remove or ignore Service operations until a concrete Service needs them.

- Good, because it avoids premature schema work.
- Bad, because provisioning and future backup/restore behavior would likely grow ad hoc.
- Bad, because Services already need a named place for management actions distinct from App lifecycle.

## Consequences

Service provisioning remains a typed backend/API contract, not a script surface.

Phase 1 may implement only the internal handlers needed by supported capabilities.

General user-facing Service operations, rich operation schemas, permission models, and CLI command shapes remain deferred.

Future operation work must update ADRs and context before schemas or canonical examples are added.

## Open Questions

- operation declaration format
- input/output schema
- API route shape
- CLI command shape
- audit/status persistence model
- idempotency and retry semantics
- relationship to backup/restore operations
- how third-party Service authors add supported operations safely
