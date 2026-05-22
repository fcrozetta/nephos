# Nephos Stack

## Repository Boundary

Nephos is split across repositories.

This repository, `nephos`, owns the backend control plane:

- API
- desired-state persistence
- reconciliation orchestration
- catalog and platform model
- architecture context and ADRs

The CLI lives in a separate repository:

- GitHub: `https://github.com/fcrozetta/nephos-cli`
- Local path: `../nephos-cli`

The CLI repository is adjacent to this repository but still needs project setup/configuration.

Setup UX and command implementation belong in the CLI repository after Nephos API `0.0.1` is implemented.

Do not implement CLI code in this repository unless Fer explicitly changes the repository boundary.

## Accepted Phase 1 Stack

Backend language:

- Python

API framework:

- FastAPI

CLI language/framework:

- Python
- Typer
- Implemented in `../nephos-cli`, not this repository

Frontend:

- Deferred for Phase 1
- No frontend framework is selected yet

Persistence:

- SQLite is the canonical Phase 1 desired-state database
- The Nephos API/database is the source of truth for desired platform state
- Use plain SQL through a small repository/data-access layer
- Do not introduce a full ORM for API 0.0.1
- Platform configuration that affects reconciliation, such as ingress root domains, is stored in the API/database as desired state
- The backend may start with an empty database and report platform configuration as incomplete until setup creates required desired state
- API 0.0.1 uses REST-ish resource APIs over installed Apps, installed Services, bindings, platform configuration domains, and status
- Installed Apps are internal `AppInstance` records and may be exposed under `/apps`
- Installed Services are internal `ServiceInstance` records and may be exposed under `/services`
- public paths use installed instance slugs such as `/apps/paperless` and `/services/postgres`
- install mutation uses `POST /apps` and `POST /services`
- lifecycle actions use `POST /apps/{appInstance}/actions/{action}` and `POST /services/{serviceInstance}/actions/{action}`
- destroy is a confirmed `POST .../actions/destroy`, not plain `DELETE`
- destroy keeps desired-state rows present while teardown is pending and deletes them only after successful teardown
- mutating responses prefer `202 Accepted` with `{ resource, reconciliation, status? }`
- Ingress root domains are exposed at `/platform/config/domains`
- Mutating API calls update desired state and create a persisted reconciliation request
- Database relationships use internal stable text ids
- Internal ids use typed prefixes with UUID4 hex suffixes
- Public API paths use unique installed instance slugs
- Read payloads may include internal ids, but App and Service paths remain slug-based
- Read payloads are domain snapshots, not raw database rows
- App snapshots include `bindings` and `routes`
- Service snapshots include `provides` and `dependents`
- Binding snapshots are exposed directly with redacted output or Secret summary
- Nested response entries use accepted field sets for App bindings/routes, Service provides/dependents, and Binding Secret summaries
- Nested response entry status summaries use `level`, `reason`, `message`, and `observedAt`
- App route targets are semantic and expose `port`
- Catalog responses use normalized summaries, not raw manifest blobs by default
- Catalog summaries include App `requires` and `routes`, and Service `provides`
- Catalog summary entries use normalized Nephos fields, not raw manifest blobs or Kubernetes shapes
- Installed App and Service slugs are immutable in API 0.0.1
- Core domain tables include `id`, `created_at`, and `updated_at`
- Desired-state rows include integer `generation`
- Timestamps use app-generated UTC ISO strings with `Z`
- Enum-like state fields use SQLite `CHECK` constraints
- SQLite foreign keys are enabled with restrictive relationships by default
- SQLite uses WAL mode for API 0.0.1
- JSON text columns are limited to validated snapshots and flexible payloads
- Latest status snapshots are keyed by `resource_type` and `resource_id`
- API 0.0.1 reconciliation requests include `action`, `payload_json`, and target snapshot fields where needed
- Manual reconcile uses target-specific action subresources
- Catalog read endpoints are `/catalog/apps`, `/catalog/apps/{name}`, `/catalog/services`, and `/catalog/services/{name}`

Migrations:

- Simple explicit SQL migrations
- No ORM-driven migration framework is selected for Phase 1
- Before the first usable version, local development may destroy and recreate the SQLite database
- Initial schema should live in `migrations/0000_initial.sql`
- `migrations/0000_initial.sql` contains all API 0.0.1 tables and accepted constraints
- do not create schema imperatively in Python
- `schema_migrations` uses `version TEXT PRIMARY KEY` and `applied_at TEXT`
- `schema_migrations` should exist in the initial schema
- Forward-compatible migration discipline starts after the first usable version is established

Controller/reconciler:

- API-owned in-process reconciler for Phase 1
- background worker over persisted SQLite reconciliation requests
- one API process and one serialized reconciler for API 0.0.1
- one serialized worker initially
- request states are `pending`, `running`, `succeeded`, `failed`, and `blocked`
- request targets are App instances, Service instances, bindings, or platform domain configuration
- requests carry durable action context
- reconciliation handlers must be idempotent and safe to retry
- simple capped retry is intended, but automatic retry may be deferred from API 0.0.1 if implementation weight is too high
- failures update request/status state without rolling back desired state
- The reconciler must be isolated behind module boundaries so it can later move to a daemon, worker, or in-cluster controller

Kubernetes client:

- Official Python Kubernetes client

Local development:

- `uv` is the canonical backend Python workflow
- backend runs as a local process during development
- CLI points at the local backend/API during development

Testing:

- `pytest` for backend tests
- `ruff` for backend linting/formatting checks
- mocks/fakes for backend unit tests
- real K3s for Kubernetes integration tests

Packaging/distribution:

- backend container image for runtime packaging
- full installer packaging deferred
- CLI packaging/test/lint/release workflow lives in `../nephos-cli`

CLI/API boundary:

- The CLI talks to the Nephos API/local controller
- The CLI must not become an unstructured direct Kubernetes mutation layer
- Phase 1 has backend/CLI version awareness but no strict compatibility blocking
- Backend should expose a version endpoint
- CLI should report CLI and backend versions
- CLI may warn on unknown/newer/older backend version
- CLI should not block state-mutating commands solely because of version mismatch in Phase 1

State import/export:

- YAML is import/export only
- YAML is not the canonical source of truth

Deferred architecture:

- Kubernetes CRDs are deferred
- GitOps as source of truth is deferred
- Nephos state backup is deferred to the broader backup model

## Drift Policy

Phase 1 should detect and report drift.

Nephos may reconcile Nephos-owned resources when desired state is explicit, especially during lifecycle operations or explicit reconciliation.

Nephos must not mutate Kubernetes resources it does not own.

Nephos-owned runtime resources should be labeled and/or annotated so drift detection and reconciliation can identify ownership.

Nephos-managed Kubernetes resources should use `app.kubernetes.io/managed-by: nephos`.

Nephos-owned relationship metadata uses `nephos.pro/*` keys.

Nephos does not use Kubernetes `ownerReferences` to represent platform relationships in Phase 1.

## Still To Decide

Exact developer commands are not finalized.

Need to decide:

- exact `uv` commands
- exact local SQLite initialization/reset commands
- exact migration command
- exact K3s startup/reset workflow
- exact integration test markers
- backend image layout and registry
- cross-repo release process
