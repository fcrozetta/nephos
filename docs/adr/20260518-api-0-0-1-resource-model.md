# API 0.0.1 Resource Model

- Status: accepted
- Date: 2026-05-18
- Tags: api, phase-1, desired-state, resources

## Context and Problem Statement

Nephos API 0.0.1 needs enough resource structure to implement the Paperless plus PostgreSQL reference flow without turning the API into a thin CLI mirror or direct Kubernetes mutation layer.

The API/database is the canonical desired-state source.

Kubernetes remains runtime state.

## Decision

Use a REST-ish resource API for API 0.0.1.

The primary API resources are:

- installed Apps
- installed Services
- bindings
- platform configuration domains
- status

Lifecycle operations are actions on resources, not raw Kubernetes commands.

Installed Apps are represented internally as `AppInstance` records.

Installed Services are represented internally as `ServiceInstance` records.

The public API may expose installed App instances under `/apps` and installed Service instances under `/services`.

Catalog App and Service manifests are separate from installed instances.

The API reads local filesystem catalog manifests and installation records store catalog identity, version when available, source, and manifest digest information.

Do not require catalog entries to be imported into the database before installation in Phase 1.

Bindings are first-class API/database resources connecting an App instance requirement alias to a Service instance capability.

Bindings are not embedded only inside App desired state and are not inferred from Kubernetes Secret metadata.

Ingress root domains are platform configuration resources in the API/database.

Use this Phase 1 API path for root domain resources:

```text
/platform/config/domains
```

These domain resources represent Nephos ingress root domains.

They are not a generic DNS management API.

Lifecycle state is desired state.

Phase 1 active lifecycle states are:

- `running`
- `stopped`
- `removed`

`destroyed` is terminal history or absent after deletion, not a normal active desired-state lifecycle value.

Status is separate from lifecycle state.

API 0.0.1 should persist the latest status snapshot with reason and evidence fields.

Mutating API calls update desired state and create a persisted reconciliation request.

The API returns after desired state and the reconciliation request are committed.

The API should not wait for Kubernetes convergence before returning.

A manual reconcile endpoint is allowed for debugging.

Do not mutate Kubernetes inline as the primary effect of an API command while bypassing desired state and reconciliation.

Reconciliation requests target one App instance, Service instance, binding, or platform domain configuration.

Accepted reconciliation request states are `pending`, `running`, `succeeded`, `failed`, and `blocked`.

API 0.0.1 should define only the resources needed for the Paperless plus PostgreSQL reference flow.

Do not add placeholder APIs for future backups, upgrades, auth, RBAC, resource profiles, remote catalogs, or generalized Service operations.

## Considered Options

### REST-ish resource API

Use resource roots such as Apps, Services, bindings, platform config domains, and status.

- Good, because it matches Nephos desired state and relationship modeling.
- Good, because CLI and future UI can share the same API contract.
- Good, because lifecycle actions remain platform semantics instead of raw Kubernetes commands.
- Bad, because it requires more domain modeling before the first endpoint.

### Command/action API first

Expose endpoints around commands such as install App, stop Service, or destroy App.

- Good, because it can be fast to map from CLI commands.
- Bad, because it makes relationships and desired state harder to model cleanly.
- Bad, because it tends to become a remote procedure API instead of a platform model.

### Mirror CLI commands directly

Shape HTTP paths around CLI spelling.

- Good, because it is easy to explain in the short term.
- Bad, because CLI UX churn would leak into backend API compatibility.
- Bad, because it risks turning the API into a transport wrapper for commands.

## Consequences

Implementation should create domain models around App instances, Service instances, bindings, root domain configuration, lifecycle, reconciliation, and status.

The CLI can remain thin, but it should call resource APIs instead of owning platform mutation logic.

Catalog loading can stay local-filesystem based while installed desired state remains in SQLite.

Later APIs must extend this model deliberately rather than adding raw Kubernetes or CLI-shaped shortcuts.

## Open Questions

- exact HTTP method and sub-action shape for lifecycle operations
- exact status response schema
- exact manual reconcile endpoint shape
- exact catalog read/list endpoint shape
- exact error envelope and validation response shape
