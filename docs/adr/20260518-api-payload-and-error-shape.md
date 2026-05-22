# API Payload and Error Shape

- Status: accepted
- Date: 2026-05-18
- Tags: api, payloads, errors, lifecycle, phase-1

## Context and Problem Statement

API 0.0.1 needs a stable enough request and response shape for installed App and Service operations.

The API already uses installed resource collections and lifecycle action subresources.

The remaining decision is how clients identify resources in paths, how install and lifecycle action bodies are shaped, how mutation responses expose reconciliation, and how errors are returned.

The contract must support the CLI without making the API mirror CLI syntax.

## Decision

Use installed instance slugs in public resource paths.

Examples:

```text
/apps/paperless
/services/postgres
```

Do not expose opaque UUIDs as the primary public path identifiers in API 0.0.1.

Install bodies use `catalogRef`.

Accepted App install shape:

```json
{
  "catalogRef": {
    "kind": "App",
    "name": "paperless",
    "source": "default"
  },
  "instanceName": "paperless",
  "config": {},
  "bindings": {}
}
```

Accepted Service install shape:

```json
{
  "catalogRef": {
    "kind": "Service",
    "name": "postgres",
    "source": "default"
  },
  "instanceName": "postgres",
  "config": {}
}
```

`catalogRef.source` is optional unless needed to disambiguate duplicate catalog entries.

`instanceName`, `config`, and `bindings` are optional where the operation can use accepted defaults.

Lifecycle action bodies use one common shape:

```json
{
  "force": false,
  "confirm": "destroy paperless"
}
```

`force` is optional and defaults to `false`.

`confirm` is required only for `destroy`.

Mutation responses use this envelope:

```json
{
  "resource": {},
  "reconciliation": {
    "id": "reconcile_...",
    "state": "pending"
  },
  "status": {}
}
```

`status` is optional.

The `reconciliation` object must include the reconciliation request id and state.

Nephos-owned errors use this envelope:

```json
{
  "error": {
    "code": "dependency_blocked",
    "message": "Service has dependent Apps.",
    "details": {}
  }
}
```

`details` is optional.

Dependency-blocked lifecycle errors use HTTP `409 Conflict` and include impact details.

Accepted dependency impact shape:

```json
{
  "error": {
    "code": "dependency_blocked",
    "message": "Service has dependent Apps.",
    "details": {
      "requiresForce": true,
      "dependents": [
        {
          "appInstance": "paperless",
          "bindingId": "binding_...",
          "bindingAlias": "database",
          "capability": "postgres"
        }
      ]
    }
  }
}
```

FastAPI/Pydantic framework validation errors may remain in their default framework shape for API 0.0.1.

Normalize validation errors into the Nephos error envelope later by explicit decision.

## Considered Options

### Instance slugs in public paths

- Good, because names are human-readable and match Nephos' local-first CLI UX.
- Good, because installed instance slugs already have strict DNS-label validation.
- Bad, because future rename semantics must be explicit if rename is ever supported.

### Opaque UUIDs in public paths

- Good, because internal identity is stable even if names change.
- Bad, because it makes CLI UX and manual debugging worse.
- Bad, because Nephos already treats instance names as platform identity in Phase 1.

### `catalogRef` install body

- Good, because catalog identity is grouped and explicit.
- Good, because it composes with optional source selection.
- Bad, because clients must send a nested object rather than flat fields.

### Flat install fields

- Good, because it is slightly simpler to type by hand.
- Bad, because catalog kind/name/source become loose siblings beside instance config.

### Nephos error envelope

- Good, because product errors become stable and structured.
- Good, because dependency-blocked responses can carry impact details.
- Bad, because FastAPI validation errors need extra normalization work if full consistency is required.

### Problem Details

- Good, because it follows a known HTTP error pattern.
- Bad, because it is more ceremony than API 0.0.1 needs.

### Raw framework errors everywhere

- Good, because it is fastest to implement.
- Bad, because client behavior becomes coupled to framework defaults.

## Consequences

API handlers should use installed instance slugs as public path identifiers.

Internal database ids may still exist, but they are not the primary public path identity.

Request/response models should use the accepted payload names unless a later ADR changes them.

Nephos-owned domain errors should use the accepted error envelope.

FastAPI/Pydantic validation errors are explicitly not stable product API in API 0.0.1.

Read payloads, status payloads, and reconciliation request id format are refined by [API Read, Status, and Catalog Shape](20260522-api-read-status-and-catalog-shape.md).

## Open Questions

- exact resource-specific response fields beyond the accepted common snapshot shape
- exact status evidence object fields
- future validation error normalization
- future rename behavior for installed instance slugs
