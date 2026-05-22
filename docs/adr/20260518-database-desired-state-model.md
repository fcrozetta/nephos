# Database Desired-State Model

- Status: accepted
- Date: 2026-05-18
- Tags: database, sqlite, desired-state, migrations, phase-1

## Context and Problem Statement

Nephos API/database is the canonical source of desired platform state.

API 0.0.1 needs a persistence model for installed Apps, installed Services, bindings, platform domains, status, and reconciliation requests.

The database model must preserve the boundary:

```text
intent -> desired state -> reconcile into Kubernetes
```

## Decision

Use SQLite with plain SQL through a small repository/data-access layer.

Do not introduce a full ORM for API 0.0.1.

Use explicit SQL migration files.

Before the first usable version, local development may destroy and recreate the database.

The initial schema should live in:

```text
migrations/0000_initial.sql
```

Forward-compatible migration discipline starts after the first usable version is established.

The initial migration contains all API 0.0.1 tables and accepted constraints.

Do not create schema imperatively in Python.

API 0.0.1 should use separate normalized tables for core resources:

- `app_instances`
- `service_instances`
- `bindings`
- `platform_domains`
- `status_snapshots`
- `reconciliation_requests`
- `schema_migrations`

Use normalized columns for core identity, relationship, lifecycle, and lookup fields.

Desired-state domain rows include integer `generation` tracking and increment it on desired-state mutation.

Use SQLite JSON text columns for snapshots and flexible payloads where useful, validated at the API/domain boundary.

Installed App and Service records should store catalog identity and version information, including catalog kind, catalog name, catalog version when available, source path, and SHA-256 manifest digest.

Do not store a full manifest snapshot by default.

Store a full manifest snapshot only if implementation proves it is necessary for a concrete behavior such as stable replay, import/export, or debugging.

Do not recompute installed desired state only from current catalog files.

Status persistence stores the latest status snapshot per resource.

Status event/history storage is deferred.

Reconciliation requests are persisted in the database so the API mutation/reconciler boundary is visible and retryable.

Accepted reconciliation request states are:

- `pending`
- `running`
- `succeeded`
- `failed`
- `blocked`

Each request targets one App instance, Service instance, binding, or platform domain configuration.

API mutations that change desired state must write the desired-state change and reconciliation request in one database transaction.

Destroy keeps the desired-state row present while teardown is pending.

Do not add `destroying` as a lifecycle state.

The in-progress destroy state is represented by reconciliation/action metadata and, where useful, a delete-request timestamp such as `delete_requested_at`.

After successful teardown, destroy removes active desired-state rows.

API 0.0.1 does not require an audit/history table for destroyed resources.

`destroyed` may appear later as terminal history if an audit/history model is accepted.

## Considered Options

### Plain SQL with small repository/data-access layer

- Good, because it keeps SQLite behavior explicit.
- Good, because it avoids ORM complexity before the domain model stabilizes.
- Good, because it matches the current local-first and pragmatic backend stack.
- Bad, because the team must own SQL and row mapping discipline directly.

### SQLModel or SQLAlchemy Core

- Good, because it can reduce some boilerplate.
- Bad, because it adds abstraction before the schema has proven itself.
- Bad, because migrations and SQLite behavior can become less obvious.

### Full ORM model first

- Good, because it gives familiar model objects.
- Bad, because it risks making persistence drive the domain model.
- Bad, because it is too much framework weight for API 0.0.1.

### Normalized tables plus JSON snapshots

- Good, because relationships and lookups stay queryable.
- Good, because catalog/runtime snapshots can evolve without overfitting columns too early.
- Bad, because API/domain validation must keep JSON payloads disciplined.

### JSON-only resources table

- Good, because it is fast to prototype.
- Bad, because bindings, dependents, lifecycle, status, and reconciliation queries become weaker.
- Bad, because it makes the API resource model less explicit.

## Consequences

Implementation should create a small database layer around explicit SQL.

API resource handlers should not issue ad hoc SQL everywhere.

Schema design can start from the accepted table families, but exact columns, indexes, and constraints still need implementation-level design.

Schema mechanics for internal ids, public slugs, timestamps, state constraints, foreign keys, reconciliation request columns, latest status row keying, and migration tracking are refined by [Database Schema Mechanics](20260518-database-schema-mechanics.md).

Destroy timing, durable reconciliation request action context, generation tracking, SQLite WAL behavior, and initial migration shape are refined by [Destroy, Reconciliation, and SQLite Mechanics](20260522-destroy-reconciliation-and-sqlite-mechanics.md).

Concrete API 0.0.1 table fields and accepted indexes are refined by [API 0.0.1 Database Table Shape](20260522-api-0-0-1-database-table-shape.md).

Pre-0.0.1 local development can reset state by destroying and recreating SQLite.

After the first usable version, schema evolution should happen through forward migrations rather than destructive resets.

## Open Questions

- exact SQL column types and nullability
- exact CHECK constraint spelling
- exact migration runner command
- exact local reset command
- exact busy timeout and transaction retry behavior
- exact DB JSON payload fields beyond accepted API snapshot/status shape
- exact target snapshot JSON fields
- exact request claiming behavior, if/when queue leasing becomes necessary
- exact retry count, backoff, and polling/wakeup behavior
