# SQLite Column and Backend Command Mechanics

- Status: accepted
- Date: 2026-05-22
- Tags: database, sqlite, migrations, backend, cli-boundary, phase-1

## Context and Problem Statement

API 0.0.1 has accepted the table shape for `migrations/0000_initial.sql`.

The remaining SQL mechanics are column type/nullability, CHECK constraints, polymorphic target handling, JSON column treatment, and migration/reset command ownership.

This also needs a naming correction: this backend/API repository should be referred to as `nephos-api`, while product CLI commands belong to the separate `nephos-cli` repository.

When documentation says `nephos <command>`, it refers to the user-facing `nephos-cli` product command, not a backend-local command in `nephos-api`.

## Decision

Use SQLite column types conservatively:

- `TEXT` for ids, slugs, enum values, timestamps, JSON payloads, and digests
- `INTEGER` for `generation`
- `INTEGER` for booleans such as `is_default`

Use `NOT NULL` on required identity, state, generation, and timestamp columns.

Nullable columns are allowed only for optional fields such as:

- `catalog_version`
- `delete_requested_at`
- status `message`
- status `reason` when not applicable
- request `error`
- optional JSON payloads where no payload exists

Use SQLite `CHECK` constraints for:

- lifecycle state
- reconciliation request state
- status level
- `is_default IN (0, 1)`
- `generation >= 1`

Use polymorphic target fields for status and reconciliation:

- `resource_type`/`resource_id` for status snapshots
- `target_type`/`target_id` for reconciliation requests

Use CHECK constraints for allowed target/resource types.

Validate target existence in repository/domain code instead of creating separate status or reconciliation tables per target type.

JSON columns should default to `'{}'` or `'[]'` where the response/domain shape is always present.

Validate JSON payloads in Python/domain models, not through SQLite JSON functions.

Migration and reset commands are backend-local development/ops commands owned by `nephos-api`.

They are not product CLI commands and must not use the `nephos <command>` spelling in this repository.

The accepted backend-local command spelling is defined by [Backend Package and Dev Command Shape](./20260522-backend-package-and-dev-command-shape.md).

Accepted backend-local command shapes include:

- `uv run nephos-api db migrate`
- `uv run nephos-api db reset --force`

Do not document `uv run nephos ...` for backend-local commands.

## Considered Options

### Conservative SQLite types and narrow nullability

- Good, because SQLite remains explicit without overfitting early.
- Good, because required domain identity and state cannot silently disappear.
- Bad, because implementation must choose nullability carefully.

### Broad nullable columns

- Good, because migrations are easier to write quickly.
- Bad, because invalid partial domain rows become easier to create.

### CHECK constraints for accepted enums and counters

- Good, because accepted state values are enforced at the database boundary.
- Good, because `generation >= 1` prevents meaningless generation values.
- Bad, because future enum changes require migrations.

### Python validation only

- Good, because code owns the domain.
- Bad, because database state can drift from accepted constraints.

### Polymorphic target type/id with domain validation

- Good, because status and reconciliation remain cross-resource models.
- Good, because one table can target Apps, Services, bindings, and platform domain configuration.
- Bad, because foreign keys cannot directly enforce every target relationship.

### Separate status and reconciliation tables per target type

- Good, because database relationships can be more concrete.
- Bad, because schema duplication arrives before API 0.0.1 needs it.

### Python-validated JSON columns

- Good, because JSON payload shape remains flexible while validation stays in the domain layer.
- Good, because it avoids depending on SQLite JSON function availability.
- Bad, because SQLite does not validate payload internals.

### SQLite JSON validity checks

- Good, because malformed JSON can be rejected by the database.
- Bad, because JSON function availability can vary and the domain still must validate shape.

### Backend-local migration/reset commands

- Good, because schema management belongs to `nephos-api`.
- Good, because the product CLI boundary stays clean.
- Bad, because backend-local commands are not product UX and must stay clearly documented as developer/ops commands.

### Product CLI migration/reset commands

- Good, because users would have one command surface.
- Bad, because it blurs `nephos-cli` product UX with backend-local development operations too early.

## Consequences

The initial SQL migration should use the accepted SQLite types, nullability rules, and CHECK constraints.

Repository/domain code must validate polymorphic target existence.

JSON payload contents remain part of API/domain validation, not SQLite validation.

Architecture docs must refer to this repository as `nephos-api` when distinguishing it from `nephos-cli`.

Any `nephos <command>` wording is reserved for the `nephos-cli` product command.

Backend-local command spelling is resolved by [Backend Package and Dev Command Shape](./20260522-backend-package-and-dev-command-shape.md).

SQLite busy timeout and app-level retry policy are resolved by [API Bootstrap Mechanics](./20260522-api-bootstrap-mechanics.md).

## Open Questions

- exact `payload_json`, `target_snapshot_json`, `output_summary_json`, and `evidence_json` contents
- exact request claiming behavior
- exact polling/wakeup behavior
- exact retry count and backoff behavior
