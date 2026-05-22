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

App `routes` entries use:

- `name`
- `visibility`
- `target`
- `canonicalUrl`
- `aliases`
- `status`

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

Service catalog summaries include:

- `provides`

Do not return raw manifest blobs by default.

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

## Consequences

Implementation should create explicit nested response models for these entries.

Nested response entries should stay camelCase where names require multiple words.

Secret summaries must redact values and should list only keys and location metadata required for operational transparency.

Catalog response mappers should summarize `requires`, `routes`, and `provides` from validated manifests without treating raw manifests as the response contract.

## Open Questions

- exact status object fields embedded in nested entries
- exact `target` subfields for App route entries
- exact `requires` summary fields in App catalog responses
- exact `routes` summary fields in App catalog responses
- exact `provides` summary fields in Service catalog responses
- future validation error normalization
