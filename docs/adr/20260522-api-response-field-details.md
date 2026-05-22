# API Response Field Details

- Status: accepted
- Date: 2026-05-22
- Tags: api, responses, status, catalog, phase-1

## Context and Problem Statement

Nephos API 0.0.1 already accepts domain-shaped read payloads, structured status payloads, and read-only catalog endpoints.

The remaining decision is which resource-specific fields those payloads should expose so implementation can start without leaking raw database rows, raw Kubernetes object dumps, or raw manifest blobs as the primary API contract.

## Decision

Installed App read payloads use the accepted common snapshot fields and add App-specific top-level arrays:

- `bindings`
- `routes`

Installed App read payloads also include:

- `catalogRef`
- `config`
- `status`

Do not hide App relationships under one generic relationship blob as the primary shape.

Installed Service read payloads use the accepted common snapshot fields and add Service-specific top-level arrays:

- `provides`
- `dependents`

Installed Service read payloads also include:

- `catalogRef`
- `config`
- `status`

`dependents` is included directly so Service impact is visible without requiring a separate endpoint for API 0.0.1.

Binding read payloads expose bindings directly.

Accepted Binding fields:

- `id`
- `alias`
- `capability`
- `appInstance`
- `serviceInstance`
- redacted output or Secret summary
- `status`
- `createdAt`
- `updatedAt`

Binding output and Secret summaries must not expose secret values.

Status `evidence` entries use structured evidence objects.

Accepted evidence object fields:

- `source`
- `subject`
- `reason`
- `message`
- `observedAt`
- optional redacted `data`

Evidence `data` is for small structured facts only.

Do not expose raw Kubernetes objects, full Helm output, Secret values, or unbounded runtime dumps through evidence.

Catalog list and detail responses return normalized catalog summaries by default.

Accepted catalog response fields:

- `kind`
- `name`
- `displayName`
- `description`
- `version`
- `source`
- `manifestDigest`
- capability summary
- route summary

Do not return raw manifest blobs by default.

Raw or full validated manifest output, if needed later, requires an explicit response field or endpoint decision.

API 0.0.1 has no rename API.

Installed App and Service slugs are immutable in API 0.0.1.

Future rename, alias, or display metadata update behavior requires a separate decision.

## Considered Options

### App payload with top-level bindings and routes

- Good, because App relationships are central to Nephos and should be easy to inspect.
- Good, because it avoids hiding platform relationships in a generic blob.
- Bad, because the payload is less minimal than a generic relationship object.

### App payload with generic relationships object

- Good, because the top-level payload is simpler.
- Bad, because clients must understand nested generic relationship types.

### Service payload with provides and dependents

- Good, because Service capabilities and dependent impact are central operational information.
- Good, because users can see what a Service provides and what breaks if it stops.
- Bad, because dependents require relationship lookup during reads.

### Service payload without dependents

- Good, because Service reads are cheaper.
- Bad, because impact visibility moves behind another endpoint too early.

### Direct Binding payloads

- Good, because bindings are first-class Nephos resources and dependent tracking source of truth.
- Good, because dependency impact and reconciliation can reference binding ids explicitly.
- Bad, because the API exposes more platform relationship detail.

### Hide bindings from API 0.0.1

- Good, because it reduces endpoint surface.
- Bad, because it contradicts bindings being first-class API/database resources.

### Structured evidence objects

- Good, because status remains explainable and machine-readable.
- Good, because it avoids turning status into raw Kubernetes dashboard output.
- Bad, because status producers must normalize facts.

### Raw runtime evidence dumps

- Good, because it is fast to expose.
- Bad, because it leaks Kubernetes internals as product API.
- Bad, because it can expose secrets or unstable runtime object details.

### Normalized catalog summaries

- Good, because catalog discovery stays product-shaped.
- Good, because it avoids making raw manifest shape the catalog response contract.
- Bad, because detail endpoints need explicit summary mapping.

### Raw manifest detail responses

- Good, because implementation can return validated input directly.
- Bad, because the API becomes coupled to manifest internals before schemas are final.

### Immutable installed slugs in API 0.0.1

- Good, because it keeps identity and routing simple for the first API.
- Good, because future rename behavior can be designed deliberately.
- Bad, because changing an installed resource name requires destroy/reinstall or a later migration path.

## Consequences

Implementation should create explicit response models for Apps, Services, Bindings, status evidence, and catalog summaries.

Response models should stay separate from raw database rows and raw manifest models.

Status evidence generation must redact sensitive data and normalize runtime facts.

Catalog response mapping must summarize capabilities and routes without returning raw manifest blobs by default.

No rename endpoints should be implemented in API 0.0.1.

Nested App, Service, Binding, and catalog summary entry fields are refined by [API Nested Response Entry Fields](20260522-api-nested-response-entry-fields.md).

## Open Questions

None for API 0.0.1 response field shape.
