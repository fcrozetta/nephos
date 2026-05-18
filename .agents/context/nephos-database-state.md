# Nephos Database State

SQLite is the canonical Phase 1 desired-state database.

Use plain SQL through a small repository/data-access layer.

Do not introduce a full ORM for API 0.0.1.

## Migration Baseline

Use explicit SQL migration files.

Before the first usable version, local development may destroy and recreate the database.

Initial schema file:

```text
migrations/0000_initial.sql
```

Forward-compatible migration discipline starts after the first usable version is established.

Exact migration runner and local reset commands are still open.

## API 0.0.1 Tables

Accepted table families:

- `app_instances`
- `service_instances`
- `bindings`
- `platform_domains`
- `status_snapshots`
- `reconciliation_requests`
- `schema_migrations`

Exact columns, indexes, constraints, and foreign-key behavior are implementation details still to define.

## Normalized State And JSON Snapshots

Use normalized columns for:

- identity
- instance names/slugs
- catalog identity
- relationships
- lifecycle state
- lookup fields

Use SQLite JSON text columns for snapshots and flexible payloads where useful.

JSON payloads must be validated at the API/domain boundary.

Do not use unvalidated JSON blobs as the main domain model.

## Catalog Identity Snapshot

Installed records store catalog identity and version snapshot information.

This should include:

- catalog kind
- catalog name
- catalog version when available
- catalog source path
- manifest digest or manifest snapshot

Do not recompute installed desired state only from current catalog files.

## Status

Persist the latest status snapshot per resource.

Status must include reasons and evidence.

Status event/history storage is deferred.

## Reconciliation Requests

Persist reconciliation requests in SQLite.

The reconciliation request table makes the API mutation/reconciler boundary visible and retryable.

In-memory-only reconciliation queues are not the Phase 1 default.

Do not bypass desired state by mutating Kubernetes inline as the primary API effect.

## Transactions

API mutations that change desired state must write:

- desired-state changes
- reconciliation request

in one database transaction.

Do not write desired state and enqueue reconciliation as separate best-effort steps.

## Destroy Semantics

Destroy removes active desired-state rows.

API 0.0.1 does not require an audit/history table for destroyed resources.

`destroyed` may appear later as terminal history if an audit/history model is accepted.
