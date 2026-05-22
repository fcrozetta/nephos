# API Nested Response Entry Fields

- Status: accepted
- Date: 2026-05-22
- Tags: api, responses, bindings, routes, catalog, phase-1

## Context and Problem Statement

Nephos API 0.0.1 already accepts domain-shaped read payloads and resource-specific response groups for Apps, Services, Bindings, status evidence, and catalog summaries.

The remaining field-level decision is the concrete shape of nested App binding entries, App route entries, Service capability entries, Service dependent entries, redacted Binding output summaries, and catalog summary entry fields.

These shapes must keep Nephos relationships visible without leaking raw database rows, raw Kubernetes objects, or secret values.

## Decision

App `bindings` entries use:

- `id`
- `alias`
- `capability`
- `serviceInstance`
- `status`

The nested `status` field is a compact status summary:

- `level`
- `reason`
- `message`
- `observedAt`

App `routes` entries use:

- `name`
- `visibility`
- `target`
- `canonicalUrl`
- `aliases`
- `status`

The App route `target` is semantic and matches manifest intent:

- `port`

Do not expose raw Kubernetes ingress backend shape as the default route target response.

Service `provides` entries use:

- `capability`
- optional `alias`
- optional `version`
- `bindingOutputTargets`

Service `dependents` entries use:

- `appInstance`
- `bindingId`
- `bindingAlias`
- `capability`
- `lifecycle`
- `status`

Binding redacted output or Secret summaries use:

- `target`
- `secretName`
- `namespace`
- `keys`
- `redacted`

`redacted` must be `true` when Secret-related output exists in the summary.

Do not expose Secret values.

Catalog summaries keep normalized top-level metadata.

App catalog summaries include:

- `requires`
- `routes`

App catalog `requires` entries use:

- `capability`
- `alias`
- optional `provider`

If the manifest omits the binding alias, `alias` is defaulted from the capability.

App catalog `routes` entries use:

- `name`
- `visibility`
- `target`

Service catalog summaries include:

- `provides`

Service catalog `provides` entries use:

- `capability`
- optional `alias`
- optional `version`
- `bindingOutputTargets`

Do not return raw manifest blobs by default.

Validation error normalization is explicitly deferred for API 0.0.1.

FastAPI/Pydantic framework validation errors may remain framework-shaped and are not a stable Nephos product API.

## Considered Options

### Full nested relationship entries

- Good, because App, Service, and Binding reads expose the relationships users need to inspect.
- Good, because Service impact and binding health are visible without extra endpoint hops.
- Bad, because reads require relationship aggregation.

### Minimal nested entries

- Good, because response assembly is smaller.
- Bad, because clients must issue follow-up requests for common inspection workflows.

### Raw ids only

- Good, because it is simple.
- Bad, because it makes the API opaque and weakens local-first operational transparency.

### Redacted Secret summaries

- Good, because users can verify what was materialized without seeing secret values.
- Good, because it supports debugging binding output shape.
- Bad, because even redacted summaries need care around metadata exposure.

### No Secret summaries

- Good, because it minimizes exposure.
- Bad, because binding and provisioning debugging becomes weaker.

### Normalized catalog nested summaries

- Good, because catalog discovery can show requirements, routes, and provided capabilities without returning raw manifests.
- Good, because it keeps catalog responses aligned with Nephos semantics.
- Bad, because response mapping must summarize manifest fields.

### Compact nested status summaries

- Good, because nested relationship entries stay scannable.
- Good, because full status evidence remains available on primary status payloads.
- Bad, because clients that need full evidence may need to follow the primary resource or status payload.

### Full status object everywhere

- Good, because every nested entry carries full diagnostic context.
- Bad, because App and Service reads become noisy and duplicate status evidence.

### Status level string only

- Good, because it is the smallest possible shape.
- Bad, because it loses the reason and observed timestamp needed for operational transparency.

### Semantic route target

- Good, because it preserves Nephos platform semantics.
- Good, because clients do not need Kubernetes ingress backend knowledge for normal route inspection.
- Bad, because low-level runtime debugging may need a separate diagnostic surface later.

### Raw Kubernetes route target

- Good, because it exposes runtime detail directly.
- Bad, because it makes Kubernetes internals part of the primary API contract.

### Deferred validation error normalization

- Good, because API 0.0.1 avoids building custom error infrastructure before the domain model is implemented.
- Good, because Nephos-owned domain errors are still stable.
- Bad, because framework validation errors are not yet product-shaped.

## Consequences

Implementation should create explicit nested response models for these entries.

Nested response entries should stay camelCase where names require multiple words.

Secret summaries must redact values and should list only keys and location metadata required for operational transparency.

Catalog response mappers should summarize `requires`, `routes`, and `provides` from validated manifests without treating raw manifests as the response contract.

Framework validation error normalization can be revisited after API 0.0.1, but it is not part of the initial stable product API.

## Open Questions

None for API 0.0.1 nested response entry fields.
