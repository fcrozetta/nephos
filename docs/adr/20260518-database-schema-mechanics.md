# Database Schema Mechanics

- Status: accepted
- Date: 2026-05-18
- Tags: database, sqlite, schema, api, phase-1

## Context and Problem Statement

The desired-state model already selects SQLite, explicit SQL migrations, normalized table families, and persisted reconciliation requests.

API 0.0.1 now needs tighter schema mechanics so implementation can start without accidentally weakening lifecycle semantics, public naming, or the desired-state/reconciler boundary.

## Decision

Use internal stable text ids for database relationships.

Use unique public slugs for user-addressable resources such as installed App instances and Service instances.

Public API paths continue to use installed instance slugs, not internal ids.

Core domain tables should include:

- `id`
- `created_at`
- `updated_at`

User-addressable domain tables should additionally include a unique `slug`.

Desired-state domain rows should include integer `generation`.

Increment `generation` on desired-state mutation.

`schema_migrations` tracks applied migrations with:

```sql
schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT)
```

Use SQLite `CHECK` constraints for accepted enum-like state fields.

At minimum, enforce:

- lifecycle states: `running`, `stopped`, `removed`
- reconciliation request states: `pending`, `running`, `succeeded`, `failed`, `blocked`
- status levels: `unknown`, `pending`, `healthy`, `degraded`, `blocked`, `stopped`, `not_applicable`

Enable SQLite foreign keys.

SQLite initialization must enable:

```sql
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
```

Use restrictive relationships by default.

Do not rely on broad `ON DELETE CASCADE` to implement Nephos lifecycle semantics.

Deletes for `remove` and `destroy` must happen through explicit domain transactions that preserve the accepted lifecycle and data-deletion rules.

Use SQLite JSON text columns only for validated snapshots and flexible payloads.

Do not hide authoritative domain relationships, lifecycle state, or dependency tracking inside generic JSON blobs.

For API 0.0.1, keep `reconciliation_requests` bounded.

The accepted fields include:

- `id`
- `target_type`
- `target_id`
- `target_generation`
- `action`
- `payload_json`
- `target_snapshot_json`
- `state`
- `error`
- `created_at`
- `updated_at`

Use target snapshots when cleanup or retry cannot safely depend only on the current desired-state row.

Attempt counters, claimed timestamps, requested-by metadata, explicit backoff columns, and richer worker lease fields are deferred unless implementation proves they are needed before API 0.0.1 is usable.

Persist latest status snapshots as one row per resource target.

Use a unique key over:

- `resource_type`
- `resource_id`

Do not store latest status JSON directly on each resource row as the primary model.

Status event history remains deferred.

Status and reconciliation records may record target or observed generation so stale status can be distinguished from current status.

## Considered Options

### Internal ids plus public slugs

- Good, because internal relationships stay stable while public API paths stay readable.
- Good, because future rename behavior can be designed without rewriting every relationship.
- Bad, because implementation must maintain both ids and slugs.

### Slug as primary key

- Good, because it is simpler in the first schema.
- Bad, because future rename or alias behavior becomes more expensive.
- Bad, because internal relationships become coupled to public naming.

### Integer autoincrement ids

- Good, because SQLite supports it naturally.
- Bad, because ids become less portable and less explicit in API/debug output.

### Restrictive foreign keys and explicit lifecycle transactions

- Good, because data deletion stays attached to Nephos lifecycle semantics.
- Good, because it avoids accidental data loss from broad cascades.
- Bad, because domain transactions must delete related rows intentionally.

### Broad cascade behavior

- Good, because it reduces delete code.
- Bad, because it can silently delete relationship/status/reconciliation data outside the lifecycle rules.

### Minimal reconciliation request columns

- Good, because it keeps API 0.0.1 implementation small.
- Good, because the accepted serialized worker model does not need a full queue/lease schema immediately.
- Bad, because retry accounting, worker leases, and richer diagnostics need later schema additions.

## Consequences

The initial SQL migration should reflect these mechanics.

The initial migration should contain all API 0.0.1 tables and accepted constraints.

Do not create schema imperatively in Python.

Implementation should treat slugs as public identity and internal ids as relationship identity.

Database writes should enable and rely on SQLite foreign key enforcement.

Domain code must perform destructive lifecycle operations explicitly instead of delegating semantics to broad cascades.

Future reconciliation concurrency, retry backoff, queue leasing, and status history can be added through later migrations.

Internal id and timestamp formats are refined by [API Read, Status, and Catalog Shape](20260522-api-read-status-and-catalog-shape.md).

Status evidence object fields are refined by [API Response Field Details](20260522-api-response-field-details.md).

Destroy timing, durable reconciliation request action context, generation tracking, SQLite WAL behavior, and initial migration shape are refined by [Destroy, Reconciliation, and SQLite Mechanics](20260522-destroy-reconciliation-and-sqlite-mechanics.md).

Concrete API 0.0.1 table fields and accepted indexes are refined by [API 0.0.1 Database Table Shape](20260522-api-0-0-1-database-table-shape.md).

SQLite column types, nullability, CHECK constraints, polymorphic target handling, JSON validation policy, and backend-local command ownership are refined by [SQLite Column and Backend Command Mechanics](20260522-sqlite-column-and-backend-command-mechanics.md).

Backend-local command spelling is refined by [Backend Package and Dev Command Shape](20260522-backend-package-and-dev-command-shape.md).

SQLite busy timeout and app-level retry policy are refined by [API Bootstrap Mechanics](20260522-api-bootstrap-mechanics.md).

## Open Questions

- exact DB JSON payload fields beyond accepted API snapshot/status shape
- exact target snapshot JSON fields
- retry count, backoff, and polling/wakeup behavior
