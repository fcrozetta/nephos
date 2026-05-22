# Destroy, Reconciliation, and SQLite Mechanics

- Status: accepted
- Date: 2026-05-22
- Tags: api, database, reconciliation, lifecycle, sqlite, phase-1

## Context and Problem Statement

API 0.0.1 already accepts SQLite desired state, persisted reconciliation requests, explicit lifecycle actions, and destroy as destructive platform intent.

The remaining blocker is how destroy, reconciliation requests, desired-state freshness, SQLite write behavior, and the initial migration should work together without adding a misleading lifecycle state or making cleanup depend on raw Kubernetes inference.

## Decision

Destroy keeps the desired-state row present while teardown is pending.

Do not add `destroying` as a lifecycle state.

The existing active lifecycle states remain:

- `running`
- `stopped`
- `removed`

`destroyed` remains terminal history or absent after deletion, not a normal active desired-state lifecycle value.

The in-progress destroy state is represented by reconciliation/action metadata and, where useful, a delete-request timestamp such as `delete_requested_at`.

After successful teardown, the desired-state row is deleted.

Reconciliation requests include durable action context.

Accepted request fields include:

- `target_generation`
- `action`
- `payload_json`
- `target_snapshot_json`

Use target snapshots when cleanup or retry cannot safely depend only on the current desired-state row.

Desired-state domain rows include an integer `generation`.

Increment `generation` on desired-state mutation.

Reconciliation and status records may record the target or observed generation so clients can distinguish fresh status from stale status.

SQLite write behavior for API 0.0.1:

- one API process
- one serialized reconciler
- short explicit transactions
- `PRAGMA foreign_keys=ON`
- WAL mode

The initial schema lives in a single migration:

```text
migrations/0000_initial.sql
```

The initial migration should contain all API 0.0.1 tables and accepted constraints.

Do not create schema imperatively in Python.

## Considered Options

### Keep destroy rows until teardown succeeds

- Good, because reconciliation can still see desired-state identity while deleting runtime/data.
- Good, because failed destroy can report status against the resource.
- Good, because it avoids adding a misleading `destroying` lifecycle state.
- Bad, because reads must make pending destroy visible through reconciliation/status instead of lifecycle alone.

### Delete desired-state row immediately with a teardown snapshot

- Good, because active desired-state rows disappear right away.
- Bad, because cleanup becomes dependent on a snapshot path earlier than necessary.
- Bad, because failed cleanup is harder to expose through normal resource reads.

### Delete immediately and infer cleanup from Kubernetes labels

- Good, because database state is simpler.
- Bad, because it weakens Nephos as the source of platform intent.
- Bad, because data cleanup cannot safely be inferred from runtime labels alone.

### Durable action and payload fields on reconciliation requests

- Good, because destroy, force, confirmation, retry, and manual reconcile semantics remain visible.
- Good, because reconciliation does not need to infer intent only from current rows.
- Bad, because request schema is no longer the absolute minimum.

### Infer all request intent from current desired state

- Good, because the request table stays smaller.
- Bad, because destroy and retry behavior become ambiguous.

### Desired-state generation

- Good, because status freshness can be checked without relying only on timestamps.
- Good, because reconciliation can identify the desired-state version it observed.
- Bad, because every desired-state mutation must consistently bump generation.

### Updated-at only

- Good, because no extra counter is needed.
- Bad, because timestamps are a weaker stale-status guard.

### Serialized SQLite writer with WAL

- Good, because it matches single-user local-first API 0.0.1.
- Good, because WAL improves read/write behavior without adding Postgres.
- Bad, because future multi-process or multi-user behavior will need a stronger concurrency decision.

### Imperative schema creation in Python

- Good, because it is quick to bootstrap.
- Bad, because it hides the schema contract and weakens migration discipline.

## Consequences

Destroy handlers must not delete desired-state rows before teardown has succeeded.

The API must make pending destroy visible through reconciliation/status rather than a new lifecycle enum.

Reconciliation request rows need durable action context and enough payload or target snapshot data to retry destructive cleanup safely.

Desired-state tables need generation tracking and mutation code must bump the counter consistently.

Status freshness should compare observed generation against current desired-state generation where applicable.

SQLite initialization must enable foreign keys, WAL mode, and a 5000 ms busy timeout.

The first implementation can stay single-process and serialized, but must keep transactions short.

Concrete API 0.0.1 table fields and accepted indexes are refined by [API 0.0.1 Database Table Shape](20260522-api-0-0-1-database-table-shape.md).

SQLite busy timeout and app-level retry policy are refined by [API Bootstrap Mechanics](20260522-api-bootstrap-mechanics.md).

## Open Questions

- exact target snapshot JSON fields
- exact polling/wakeup behavior
- exact retry count and backoff behavior
