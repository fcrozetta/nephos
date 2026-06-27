# Catalog and Manifest Loading

- Status: accepted
- Date: 2026-05-18
- Tags: catalog, manifests, api, phase-1

## Context and Problem Statement

Nephos API 0.0.1 installs Apps and Services from local filesystem catalog manifests.

The catalog contains available Apps and Services.

Installed App and Service instances live in Nephos desired state.

The loading boundary must avoid turning arbitrary YAML paths into the primary product model, while still allowing local-first catalog iteration.

## Decision

API 0.0.1 supports:

- one built-in managed first-party registry dependency: `core-registry`
- optional local catalog root overrides for development experiments

Nephos clones and manages the built-in core registry checkout at:

```text
.nephos/registries/core-registry
```

Custom catalog roots are backend local configuration for API 0.0.1 and replace
the managed core registry dependency set when configured.

Catalog root overrides are configured with:

```text
NEPHOS_API_CATALOG_ROOTS
```

`NEPHOS_API_CATALOG_ROOTS` is parsed as a platform path-list, such as `:`-separated paths on macOS/Linux.

Catalog source ids:

- managed core registry or first override root: `default`
- additional override roots: `local-1`, `local-2`, `local-3`, in configured order

Source ids are stable only for the current backend configuration and root order.

Catalog responses expose source ids through `source`.

Catalog responses do not expose raw filesystem paths by default.

`sourcePath` is reserved for future backend/debug/detail contexts.

Do not store custom catalog roots as platform desired state in SQLite for API 0.0.1.

Catalog source management can move into platform configuration later by explicit decision.

The API reads and validates catalog manifests on demand.

Do not import all catalog entries into SQLite before use in API 0.0.1.

Do not build a required startup catalog index for API 0.0.1.

Catalog entries use the accepted directory layout:

```text
catalog/
  apps/
    <app-slug>/
      app.yaml
  services/
    <service-slug>/
      service.yaml
```

The directory slug and manifest `metadata.name` must match.

Do not silently normalize mismatches.

Duplicate catalog entries with the same kind and name across configured roots are an error unless the caller explicitly selects a source.

Do not let later roots silently override earlier roots.

If a duplicate catalog entry is ambiguous, return `409 Conflict` with error code `catalog_entry_ambiguous` and details containing `kind`, `name`, and `sources[]`.

If a caller requests an unknown source id, return `404 Not Found` with error code `catalog_source_not_found`.

Validate manifests with typed Python/Pydantic domain models in API code first.

Do not add canonical JSON Schema files under `schemas/` until Fer approves the concrete validation schema.

Reject unknown manifest fields once canonical validation models exist.

At install time, store catalog identity and version/digest information on installed records:

- catalog kind
- catalog name
- catalog version when available
- catalog source id
- catalog source path snapshot
- SHA-256 digest of the manifest file content

Do not store a full manifest snapshot by default.

Store a full manifest snapshot only if implementation proves it is necessary for a concrete behavior such as stable replay, import/export, or debugging.

Install by catalog kind and name, plus optional explicit source when needed.

API install mutation happens through:

```text
POST /apps
POST /services
```

The catalog reference is carried in the request body.

The request body uses `catalogRef` with `kind`, `name`, and optional `source`.

`catalogRef.source` is optional unless needed to disambiguate duplicate catalog entries.

`catalogRef.source` uses source ids such as `default` or `local-1`.

Catalog endpoints are not the primary owner of install mutation.

Do not make arbitrary install-from-path the main API or UX flow.

Temporary draft manifests stay under `.agents/drafts/manifests/` and remain non-canonical until API validation models exist and Fer approves promotion.

`metadata.version` remains optional for catalog entries.

Installed records store version if present and always store the manifest digest.

## Considered Options

### Managed core registry plus override roots

- Good, because it supports local-first customization without remote catalog complexity.
- Good, because the built-in core registry gives Nephos a real first-party
  default without requiring a user-managed checkout.
- Bad, because custom root management is still backend-local in API 0.0.1.

### Managed core registry only

- Good, because it is simpler.
- Bad, because it blocks user-created local catalog iteration during early platform shaping.

### Arbitrary path install as primary flow

- Good, because it is flexible for development.
- Bad, because it weakens catalog identity.
- Bad, because installed state becomes tied to ad hoc paths instead of catalog entries.

### On-demand manifest loading

- Good, because SQLite stays focused on installed desired state.
- Good, because API 0.0.1 avoids catalog cache invalidation and index lifecycle.
- Bad, because large catalogs may need indexing later.

### Import catalog entries into SQLite first

- Good, because listing can be fast.
- Bad, because it creates a second source of truth for available catalog entries.
- Bad, because it adds update/invalidation behavior before Phase 1 needs it.

### Typed Python/Pydantic validation first

- Good, because API code can enforce the accepted schema without freezing JSON Schema too early.
- Good, because it keeps canonical schema files blocked until Fer approves the concrete shape.
- Bad, because external tooling cannot consume canonical schemas yet.

## Consequences

Catalog loading remains local-first and explicit.

Installed state is protected from catalog file drift by storing catalog identity, optional version, source, and digest.

The API can support user-created local entries without allowing arbitrary path installs to become the normal product model.

Future remote catalogs, catalog indexes, signed catalogs, and platform-managed catalog source configuration remain deferred.

Read-only catalog endpoint shape is refined by [API Read, Status, and Catalog Shape](20260522-api-read-status-and-catalog-shape.md).

Catalog response fields are refined by [API Response Field Details](20260522-api-response-field-details.md).

Catalog summary nested fields are refined by [API Nested Response Entry Fields](20260522-api-nested-response-entry-fields.md).

Catalog root environment configuration is refined by [API Bootstrap Mechanics](20260522-api-bootstrap-mechanics.md).

Catalog source identity and error behavior is refined by [Catalog Source Identity and Errors](20260522-catalog-source-identity-and-errors.md).

## Open Questions

- exact Pydantic/domain validation model names
- whether full manifest snapshots become necessary for stable replay, import/export, or debugging
