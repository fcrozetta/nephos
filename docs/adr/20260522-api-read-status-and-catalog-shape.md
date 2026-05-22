# API Read, Status, and Catalog Shape

- Status: accepted
- Date: 2026-05-22
- Tags: api, status, catalog, identifiers, phase-1

## Context and Problem Statement

API 0.0.1 already has accepted install, lifecycle, mutation response, error, and reconciliation boundaries.

The remaining implementation blockers are the concrete internal id format, timestamp format, read resource snapshot shape, status payload shape, manual reconcile endpoint shape, and read-only catalog endpoint shape.

These details must keep the API resource-oriented without making public paths depend on opaque ids or exposing raw database rows and Kubernetes internals as product API.

## Decision

Use typed internal text ids with a resource prefix and UUID4 hex suffix.

Initial prefixes:

- App instance: `appinst_<uuid4hex>`
- Service instance: `svcinst_<uuid4hex>`
- binding: `binding_<uuid4hex>`
- platform domain: `domain_<uuid4hex>`
- reconciliation request: `reconcile_<uuid4hex>`
- status snapshot: `status_<uuid4hex>`

Public API paths still use installed instance slugs for Apps and Services.

Use app-generated UTC ISO timestamp strings with `Z`.

The initial timestamp representation is:

```text
YYYY-MM-DDTHH:MM:SSZ
```

Database columns use snake case such as `created_at` and `updated_at`.

API payloads use camel case such as `createdAt`, `updatedAt`, and `observedAt`.

Read resource snapshots are domain snapshots, not raw database rows.

Installed App and Service read payloads include:

- `id`
- `slug`
- `kind`
- `lifecycle`
- catalog identity
- config summary
- relationship summaries
- `createdAt`
- `updatedAt`
- optional latest `status`

Bindings and platform domains also expose their internal `id` plus their public or semantic identity.

Do not hide internal ids from read payloads.

Do not use internal ids as the primary public path identity for installed Apps and Services.

Use structured status payloads.

Accepted status payload fields:

- `level`
- `lifecycle`
- `reconciliation`
- `reason`
- `message`
- `evidence`
- `observedAt`

`evidence` is an array of structured facts, not an unbounded raw Kubernetes dump.

Secret values must remain redacted in status payloads.

Manual reconcile uses action subresources.

Accepted Phase 1 endpoints:

```text
POST /apps/{appInstance}/actions/reconcile
POST /services/{serviceInstance}/actions/reconcile
POST /bindings/{bindingId}/actions/reconcile
POST /platform/config/domains/actions/reconcile
```

Manual reconcile does not directly mutate Kubernetes inline.

It creates a reconciliation request and returns the normal mutation envelope.

Read-only catalog endpoints are:

```text
GET /catalog/apps
GET /catalog/apps/{name}
GET /catalog/services
GET /catalog/services/{name}
```

Catalog detail endpoints accept optional `source` selection where duplicate catalog entries require disambiguation.

Catalog endpoints are read-only in API 0.0.1.

Install mutation remains owned by:

```text
POST /apps
POST /services
```

## Considered Options

### Typed prefixed UUID4 ids

- Good, because ids are stable and easy to recognize in logs, errors, and API payloads.
- Good, because it avoids external dependencies for sortable ids.
- Bad, because ids are not naturally time-sortable.

### Bare UUID ids

- Good, because the format is common.
- Bad, because errors and relationship payloads become less readable.

### Integer autoincrement ids

- Good, because SQLite supports them naturally.
- Bad, because they are less portable and less explicit in API/debug output.

### App-generated UTC ISO timestamps

- Good, because the API and database can use one explicit timestamp convention.
- Good, because it avoids SQLite timestamp formatting quirks.
- Bad, because application code must set timestamps consistently.

### SQLite-generated timestamps

- Good, because it reduces application code.
- Bad, because update semantics and output formatting are weaker.

### Resource snapshots with ids and slugs

- Good, because public UX remains slug-oriented while debugging and relationship payloads remain precise.
- Good, because bindings, reconciliation requests, and status snapshots can reference stable ids.
- Bad, because API clients see internal ids they should not treat as primary path identity.

### Slug-only read payloads

- Good, because the product surface is simpler.
- Bad, because dependency, binding, reconciliation, and debugging payloads become weaker.

### Structured status payload

- Good, because CLI and future UI can explain state without scraping Kubernetes.
- Good, because Nephos status can include lifecycle, reconciliation, dependency, and runtime evidence together.
- Bad, because status producers must normalize evidence instead of dumping raw runtime objects.

### Raw runtime status dump

- Good, because it is fast to expose.
- Bad, because it turns status into a Kubernetes dashboard leak.
- Bad, because it weakens Nephos platform semantics.

### Manual reconcile action subresources

- Good, because it matches the accepted action-subresource API pattern.
- Good, because reconcile remains target-specific and desired-state aware.
- Bad, because `reconcile` is operational rather than lifecycle-oriented.

### Generic reconciliation request endpoint

- Good, because it models the queue directly.
- Bad, because clients must understand queue target internals too early.

## Consequences

Implementation should add small helpers for id generation and timestamp generation instead of scattering formatting logic.

API response models should be domain-shaped snapshots and must not leak raw database row shape as the public contract.

Status writers must produce structured reasons, messages, and evidence.

Catalog read endpoints can support CLI discovery without making catalog paths own install mutation.

Future APIs may add richer status evidence and catalog response fields without changing the accepted endpoint boundary.

Resource-specific response fields, status evidence object fields, catalog response fields, and installed slug rename behavior are refined by [API Response Field Details](20260522-api-response-field-details.md).

Nested App, Service, Binding, and catalog summary entry fields are refined by [API Nested Response Entry Fields](20260522-api-nested-response-entry-fields.md).

## Open Questions

None for API 0.0.1 read/status/catalog response field shape.
