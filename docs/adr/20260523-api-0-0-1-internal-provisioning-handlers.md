# API 0.0.1 Internal Provisioning Handlers

- Status: accepted
- Date: 2026-05-23
- Tags: api, reconciliation, provisioning, bindings, phase-1

## Context and Problem Statement

API 0.0.1 needs real binding convergence for the Paperless plus PostgreSQL reference flow.

Previous decisions accepted typed backend/API-owned Service operations and rejected arbitrary scripts, Helm hooks, Kubernetes jobs, or user-provided shell commands as product semantics.

The remaining gap is how binding reconciliation obtains app-scoped Service outputs without exposing a general Service operation API or storing secret values in public API payloads.

## Decision

For API 0.0.1, app-scoped provisioning is implemented by internal backend-owned provisioning handlers.

Provisioning handlers are Python adapter code called by the reconciler during binding reconciliation.

Handlers are selected by accepted capability and provisioning behavior, starting with the `postgres` capability and `app-scoped-resource` behavior.

The handler contract is internal. It is not a public API, CLI, manifest operation schema, shell script surface, Helm hook contract, or Kubernetes Job authoring model.

For API 0.0.1, the PostgreSQL handler uses backend-owned Kubernetes API calls:

- derive a stable app-scoped PostgreSQL database/user identity from the Binding desired state.
- read or create a Nephos-owned Service-side credential Secret in the PostgreSQL Service namespace.
- read the PostgreSQL administrator password from the Helm release Secret using the API 0.0.1 chart convention.
- execute idempotent `psql` statements inside the Nephos-owned PostgreSQL runtime pod.
- return the accepted logical output fields: `host`, `port`, `database`, `username`, `password`, and `uri`.

The Kubernetes exec and chart-convention details are adapter internals for API 0.0.1.

The public product contract remains the capability plus provisioning behavior, not pod names, Secret names, SQL scripts, Helm chart internals, or exec commands.

Binding reconciliation is responsible for:

- loading the Binding desired state.
- asking the internal provisioning handler for binding output values when values are not already available in the current reconciliation attempt.
- materializing the accepted `app-secret` Secret in the consuming App namespace.
- writing redacted binding output summary to SQLite.
- writing reconciliation status.

Secret values are passed from provisioning handler to runtime Secret materialization.

Secret values are not exposed through API responses or status evidence.

SQLite binding output summaries store only redacted metadata such as target, Secret name, namespace, and output key names.

Do not persist raw binding secret values in `output_summary_json`.

If a required provisioning handler is unavailable or cannot produce values, the Binding reconciliation request becomes `blocked` with a reason and status evidence.

Handler failures become `failed` reconciliation requests with structured status evidence.

## Consequences

API 0.0.1 can implement PostgreSQL app-scoped provisioning without creating a general Service operation UX.

The reconciler remains the only path from desired state into runtime mutation.

Binding Secret materialization remains idempotent and retryable.

The database stays safe for inspectability because credential values are not stored in redacted output summaries.

Future generalized Service operations still require a separate ADR and schema/API design.

## Open Questions

- future public Service operation API shape
- future operation audit/history beyond latest status snapshots
