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

Exact full column sets and indexes remain implementation details, but the accepted schema mechanics below apply to the initial design.

## Identity And Public Slugs

Use internal stable text ids for database relationships.

Use unique public slugs for user-addressable resources such as installed App instances and Service instances.

Public API paths use installed instance slugs.

Internal foreign-key relationships should use internal ids, not public slugs.

Internal ids use typed prefixes with UUID4 hex suffixes.

Initial prefixes:

- App instance: `appinst_<uuid4hex>`
- Service instance: `svcinst_<uuid4hex>`
- binding: `binding_<uuid4hex>`
- platform domain: `domain_<uuid4hex>`
- reconciliation request: `reconcile_<uuid4hex>`
- status snapshot: `status_<uuid4hex>`

## Timestamps

Core domain tables should include:

- `id`
- `created_at`
- `updated_at`

User-addressable domain tables should also include a unique `slug`.

`schema_migrations` uses `version` and `applied_at` as migration metadata.

Use app-generated UTC ISO timestamp strings with `Z`.

Initial format:

```text
YYYY-MM-DDTHH:MM:SSZ
```

Database columns use snake case, such as `created_at` and `updated_at`.

API payloads use camel case, such as `createdAt`, `updatedAt`, and `observedAt`.

## Constraints And Foreign Keys

Use SQLite `CHECK` constraints for accepted enum-like state fields.

At minimum, enforce:

- lifecycle states: `running`, `stopped`, `removed`
- reconciliation request states: `pending`, `running`, `succeeded`, `failed`, `blocked`
- status levels: `unknown`, `pending`, `healthy`, `degraded`, `blocked`, `stopped`, `not_applicable`

Enable SQLite foreign keys.

Use restrictive relationships by default.

Do not rely on broad `ON DELETE CASCADE` to implement Nephos lifecycle semantics.

Deletes for `remove` and `destroy` must happen through explicit domain transactions that preserve the accepted lifecycle and data-deletion rules.

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

Do not hide authoritative relationships, lifecycle state, binding dependency tracking, or public identity in generic JSON payloads.

## Catalog Identity Snapshot

Installed records store catalog identity and version information.

This should include:

- catalog kind
- catalog name
- catalog version when available
- catalog source path
- SHA-256 manifest digest

Do not store a full manifest snapshot by default.

Store a full manifest snapshot only if implementation proves it is necessary for a concrete behavior such as stable replay, import/export, or debugging.

Do not recompute installed desired state only from current catalog files.

## Status

Persist the latest status snapshot per resource.

Status must include reasons and evidence.

Store latest status as one row per resource target with a unique key over:

- `resource_type`
- `resource_id`

Do not store latest status JSON directly on each resource row as the primary model.

Status event/history storage is deferred.

## Reconciliation Requests

Persist reconciliation requests in SQLite.

The reconciliation request table makes the API mutation/reconciler boundary visible and retryable.

In-memory-only reconciliation queues are not the Phase 1 default.

Do not bypass desired state by mutating Kubernetes inline as the primary API effect.

Each reconciliation request targets one resource target.

Accepted target categories:

- App instance
- Service instance
- binding
- platform domain configuration

Accepted request states:

- `pending`
- `running`
- `succeeded`
- `failed`
- `blocked`

For API 0.0.1, keep the request table minimal.

Accepted minimum fields:

- `id`
- `target_type`
- `target_id`
- `state`
- `error`
- `created_at`
- `updated_at`

Attempt counters, claimed timestamps, requested-by metadata, explicit backoff columns, and richer worker lease fields are deferred unless implementation proves they are needed before API 0.0.1 is usable.

Simple capped retry is intended, but automatic retry may be deferred from API 0.0.1 if it adds too much implementation weight.

Failures update request state and status evidence without rolling back desired state.

## Transactions

API mutations that change desired state must write:

- desired-state changes
- reconciliation request

in one database transaction.

Do not write desired state and enqueue reconciliation as separate best-effort steps.

## Migration Tracking

Track applied migrations with:

```sql
schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT)
```

`schema_migrations` should exist in the initial schema.

## Destroy Semantics

Destroy removes active desired-state rows.

API 0.0.1 does not require an audit/history table for destroyed resources.

`destroyed` may appear later as terminal history if an audit/history model is accepted.
