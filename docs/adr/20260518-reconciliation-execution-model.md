# Reconciliation Execution Model

- Status: accepted
- Date: 2026-05-18
- Tags: reconciliation, controller, api, database, status, phase-1

## Context and Problem Statement

Nephos already accepts an API-owned in-process reconciler for Phase 1.

API 0.0.1 still needs a concrete execution model for how API mutations cross into reconciliation, how requests are tracked, what states they use, how status is written, and how failures or drift behave.

The model must preserve the boundary:

```text
intent -> desired state -> reconcile into Kubernetes
```

It must also avoid turning the CLI or API handlers into direct unstructured Kubernetes mutation code.

## Decision

Use an API-owned in-process background reconciler for API 0.0.1.

Mutating API calls write desired-state changes and a reconciliation request in one database transaction.

The API returns after the database transaction succeeds and the reconciliation request is persisted.

The API should not wait for Kubernetes convergence before returning.

Reconciliation requests are persisted in SQLite.

Reconciliation requests include durable action context.

Accepted request fields include:

- `target_generation`
- `action`
- `payload_json`
- `target_snapshot_json`

Use target snapshots when cleanup or retry cannot safely depend only on the current desired-state row.

Each reconciliation request targets one resource target:

- App instance
- Service instance
- binding
- platform domain configuration

Accepted request states are:

- `pending`
- `running`
- `succeeded`
- `failed`
- `blocked`

Reconciliation handlers must be idempotent and safe to retry.

The first implementation uses one serialized background worker.

API 0.0.1 uses one API process and one serialized reconciler with short explicit SQLite transactions.

This is acceptable for Nephos' single-user local-first model, including beyond API 0.0.1 until real usage proves queue concurrency is needed.

Simple capped retry is the intended model.

Automatic retry may be deferred from API 0.0.1 if it adds too much implementation weight.

The reconciler writes latest status snapshots with reasons and evidence.

Reconciliation and status records may record target or observed desired-state generation.

Failures do not roll back desired state.

When reconciliation fails, desired state remains intact and Nephos updates reconciliation request state plus status evidence.

Blocked requests require desired-state changes, user input, or explicit manual reconciliation after the blocker is resolved.

Destroy keeps the desired-state row present while teardown is pending.

Do not add `destroying` as a lifecycle state.

Pending destroy is visible through reconciliation/action metadata and status.

After successful teardown, the desired-state row is deleted.

Phase 1 detects and reports drift for Nephos-owned resources.

Nephos may reconcile Nephos-owned resources when desired state is explicit or manual reconciliation is requested.

Nephos should not continuously overwrite runtime drift in ways that hide operator changes without reporting them.

Nephos must not mutate resources it does not own.

## Considered Options

### API-owned background reconciler with persisted request queue

- Good, because API mutation, desired state, reconciliation requests, and status are visible in one control plane.
- Good, because it works for CLI now and future Web UI later.
- Good, because it keeps CLI behavior thin and avoids direct Kubernetes mutation from CLI code.
- Bad, because the API process now owns a background worker and queue claiming logic.

### Inline API reconciliation before returning

- Good, because the first implementation can feel simpler.
- Bad, because API latency becomes Kubernetes latency.
- Bad, because failed network/runtime calls make desired-state mutation semantics harder to reason about.
- Bad, because it tempts API handlers to become direct Kubernetes command handlers.

### CLI-owned reconciliation

- Good, because it avoids a backend worker at first.
- Bad, because it makes future UI/API behavior weaker.
- Bad, because it turns the CLI into a mutation engine instead of a client.
- Bad, because it weakens the source-of-truth boundary.

### In-cluster controller first

- Good, because it is closer to Kubernetes operator patterns.
- Bad, because it pulls Nephos toward CRD/operator complexity too early.
- Bad, because Phase 1 is local-first and does not need leader election or cluster-resident controller machinery.

### Multi-worker queue first

- Good, because independent resources could reconcile concurrently.
- Bad, because concurrency, locking, ordering, and dependency handling add complexity before the single-user path proves it needs throughput.

## Consequences

Implementation needs a reconciliation request table with request target identity, target generation, action context, payload/snapshot fields, state, timestamps, and error/status evidence fields.

The API 0.0.1 bounded column set is refined by [Database Schema Mechanics](20260518-database-schema-mechanics.md).

Manual reconcile endpoint shape and reconciliation request id format are refined by [API Read, Status, and Catalog Shape](20260522-api-read-status-and-catalog-shape.md).

Status evidence object fields are refined by [API Response Field Details](20260522-api-response-field-details.md).

Destroy timing, durable reconciliation request action context, generation tracking, SQLite WAL behavior, and initial migration shape are refined by [Destroy, Reconciliation, and SQLite Mechanics](20260522-destroy-reconciliation-and-sqlite-mechanics.md).

Concrete reconciliation request table fields are refined by [API 0.0.1 Database Table Shape](20260522-api-0-0-1-database-table-shape.md).

Mutating API handlers must not write desired state without a matching reconciliation request in the same transaction.

The reconciler must own status snapshot writes for reconciliation outcomes.

Reconciliation code should be isolated so the in-process worker can later become a daemon, worker process, in-cluster controller, or scheduled process.

Queue concurrency starts serialized.

This deliberately trades throughput for clarity because Nephos is single-user/local-first in Phase 1.

## Open Questions

- exact target snapshot JSON fields
- exact request claiming behavior in SQLite, if/when queue leasing becomes necessary
- exact polling/wakeup mechanism
- exact retry count and backoff behavior
- whether automatic retry lands in API 0.0.1 or immediately after
- exact status evidence `data` payloads for reconciliation evidence
