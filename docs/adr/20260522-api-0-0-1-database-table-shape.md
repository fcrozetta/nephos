# API 0.0.1 Database Table Shape

- Status: accepted
- Date: 2026-05-22
- Tags: database, sqlite, schema, api, phase-1

## Context and Problem Statement

Nephos has accepted SQLite as the canonical API 0.0.1 desired-state database, explicit SQL migrations, normalized table families, durable reconciliation requests, generation tracking, and destroy rows that remain present until teardown succeeds.

API 0.0.1 now needs the concrete table and index shape for `migrations/0000_initial.sql`.

This ADR defines the intended table shape only.

It does not create the migration file.

## Decision

`app_instances` uses explicit domain columns:

- `id`
- `slug`
- `catalog_kind`
- `catalog_name`
- `catalog_version`
- `catalog_source`
- `manifest_digest`
- `lifecycle`
- `generation`
- `config_json`
- `delete_requested_at`
- `created_at`
- `updated_at`

`service_instances` uses the same explicit domain columns:

- `id`
- `slug`
- `catalog_kind`
- `catalog_name`
- `catalog_version`
- `catalog_source`
- `manifest_digest`
- `lifecycle`
- `generation`
- `config_json`
- `delete_requested_at`
- `created_at`
- `updated_at`

`bindings` uses explicit relationship columns:

- `id`
- `app_instance_id`
- `service_instance_id`
- `alias`
- `capability`
- `generation`
- `output_summary_json`
- `created_at`
- `updated_at`

`platform_domains` uses one row per root domain:

- `id`
- `name`
- `domain`
- `is_default`
- `generation`
- `created_at`
- `updated_at`

`status_snapshots` uses one latest row per resource target:

- `id`
- `resource_type`
- `resource_id`
- `level`
- `lifecycle`
- `reconciliation`
- `reason`
- `message`
- `evidence_json`
- `observed_generation`
- `observed_at`
- `created_at`
- `updated_at`

`reconciliation_requests` uses durable action context:

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

`schema_migrations` uses:

- `version`
- `applied_at`

Accepted indexes and uniqueness rules:

- unique App instance slugs
- unique Service instance slugs
- unique binding alias per App instance
- one default platform domain
- unique latest status snapshot per `resource_type` and `resource_id`
- reconciliation queue index by `state` and `created_at`

Do not hide App, Service, Binding, Domain, Status, or Reconciliation identity in generic JSON blobs.

JSON columns are accepted only for validated flexible payloads and snapshots.

## Considered Options

### Explicit App and Service columns

- Good, because installed resource identity, catalog identity, lifecycle, generation, and pending destroy are queryable.
- Good, because `delete_requested_at` supports pending destroy without adding a `destroying` lifecycle.
- Bad, because the first migration has more columns.

### App and Service JSON blobs

- Good, because it is fast to prototype.
- Bad, because it hides lifecycle, catalog identity, and generation from the control plane.

### Explicit Binding relationship columns

- Good, because bindings are core Nephos relationships.
- Good, because dependency tracking can query App, Service, alias, and capability directly.
- Bad, because output details still require a validated JSON snapshot.

### Binding JSON blob

- Good, because it avoids early column decisions.
- Bad, because it turns first-class bindings into opaque metadata.

### One row per platform root domain

- Good, because ingress root domains are platform desired state.
- Good, because the API path `/platform/config/domains` maps naturally to rows.
- Bad, because single-row platform config would be slightly simpler.

### Single platform config JSON row

- Good, because platform config starts small.
- Bad, because it hides domain identity and default-domain uniqueness.

### Normalized status snapshot columns plus evidence JSON

- Good, because status level, reason, lifecycle, reconciliation, observed generation, and timestamp are queryable.
- Good, because evidence remains flexible and structured.
- Bad, because status writers must map status into explicit columns.

### Status JSON on each resource row

- Good, because reads can load status with the resource row.
- Bad, because status is a cross-resource model and should not be duplicated across tables.

### Reconciliation request action and snapshot fields

- Good, because destroy, retry, force, and manual reconcile have durable context.
- Good, because target snapshots can support cleanup when current desired-state rows are insufficient.
- Bad, because exact snapshot contents still need implementation discipline.

### Reconciliation target and state only

- Good, because the table is tiny.
- Bad, because destructive cleanup becomes ambiguous.

## Consequences

`migrations/0000_initial.sql` should create these tables and accepted indexes.

Implementation should keep public slugs unique while using internal ids for relationships.

Bindings should enforce alias uniqueness within an App instance.

Platform domains should enforce one default root domain.

Status snapshots should enforce one latest status row per target.

Reconciliation workers should use the `state, created_at` queue index for pending work selection.

SQLite column types, nullability, CHECK constraints, polymorphic target handling, JSON validation policy, and backend-local command ownership are refined by [SQLite Column and Backend Command Mechanics](20260522-sqlite-column-and-backend-command-mechanics.md).

Backend-local command spelling is refined by [Backend Package and Dev Command Shape](20260522-backend-package-and-dev-command-shape.md).

Database path, migration runner behavior, SQLite busy timeout, and app-level retry policy are refined by [API Bootstrap Mechanics](20260522-api-bootstrap-mechanics.md).

## Open Questions

- exact target snapshot JSON fields
- exact `payload_json`, `output_summary_json`, and `evidence_json` contents
- exact request claiming behavior
- exact polling/wakeup behavior
- exact retry count and backoff behavior
