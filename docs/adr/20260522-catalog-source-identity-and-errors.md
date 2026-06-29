# Catalog Source Identity and Errors

- Status: accepted
- Date: 2026-05-22
- Tags: catalog, api, errors, identifiers, phase-1

## Context and Problem Statement

API 0.0.1 loads catalog entries from the managed first-party `core-registry`
checkout by default. When `NEPHOS_API_CATALOG_ROOTS` is set, those local roots
replace the managed registry dependency set for development experiments.

Duplicate catalog entries with the same kind and name are already defined as ambiguous unless the caller explicitly selects a source.

The remaining implementation blockers are:

- exact catalog source identifiers
- whether API responses expose raw filesystem paths
- duplicate-entry error contract
- missing-source error shape
- how installed records preserve source identity

## Decision

Use stable source ids within the current backend configuration.

The managed core registry, or the first configured override root, uses source id:

```text
default
```

Additional configured override roots use source ids in configured order:

```text
local-1
local-2
local-3
```

API catalog responses expose the source id through the existing `source` field.

Catalog responses do not expose raw filesystem paths by default.

`sourcePath` is reserved for future backend/debug/detail contexts and is not part of default catalog list output.

Explicit source selection uses the source id.

Accepted source selection locations:

- `catalogRef.source`
- catalog detail query parameter `?source=`

Examples:

```json
{
  "catalogRef": {
    "kind": "App",
    "name": "paperless",
    "source": "default"
  }
}
```

```text
GET /catalog/apps/paperless?source=local-1
```

If a catalog kind/name exists in more than one configured source and the caller does not provide `source`, return HTTP `409 Conflict`.

Use Nephos-owned domain error code:

```text
catalog_entry_ambiguous
```

Accepted ambiguous catalog entry error shape:

```json
{
  "error": {
    "code": "catalog_entry_ambiguous",
    "message": "Catalog entry exists in multiple sources. Select a source.",
    "details": {
      "kind": "App",
      "name": "paperless",
      "sources": ["default", "local-1"]
    }
  }
}
```

Do not silently pick the first matching catalog root.

If a caller provides a source id that does not exist in the current backend configuration, return HTTP `404 Not Found`.

Use Nephos-owned domain error code:

```text
catalog_source_not_found
```

Accepted missing source error shape:

```json
{
  "error": {
    "code": "catalog_source_not_found",
    "message": "Catalog source was not found.",
    "details": {
      "source": "local-9"
    }
  }
}
```

Source ids are stable only for the current backend configuration and root order.

Persisted installed App and Service records store both:

- catalog source id
- catalog source path snapshot

The API 0.0.1 database columns are:

- `catalog_source_id`
- `catalog_source_path`

Future non-filesystem catalog sources may reinterpret the path snapshot as a source locator or identifier by explicit later decision.

## Considered Options

### `default`, `local-1`, `local-2`

- Good, because it avoids exposing local filesystem paths as product identifiers.
- Good, because it is deterministic for one backend configuration.
- Bad, because ids can change if `NEPHOS_API_CATALOG_ROOTS` order changes.

### Raw filesystem paths as source ids

- Good, because they are stable if the path remains stable.
- Bad, because they leak local machine paths into API/CLI output.
- Bad, because they make source selection verbose and OS-specific.

### Named catalog config now

- Good, because user-provided names could be more stable.
- Bad, because it requires a backend config file or platform catalog-source model before API 0.0.1 needs it.

### Hide raw paths by default

- Good, because catalog output stays product-shaped.
- Good, because local machine paths are not exposed in normal CLI/API output.
- Bad, because deeper debugging may need an explicit diagnostic surface later.

### Include raw paths everywhere

- Good, because debugging source resolution is direct.
- Bad, because path leakage becomes default API behavior.

### `409 Conflict` for ambiguous catalog entries

- Good, because multiple valid matching sources are a conflict requiring explicit selection.
- Good, because it matches dependency-blocked lifecycle conflict behavior.
- Bad, because some clients may expect catalog lookup ambiguity to be `400 Bad Request`.

### `404 Not Found` for missing source id

- Good, because the requested source resource does not exist in the current backend configuration.
- Good, because it is distinct from an ambiguous catalog entry.
- Bad, because source ids are backend-local configuration rather than persisted platform resources.

### Store both source id and source path snapshot

- Good, because API reads can show stable source ids while installed state preserves the exact local source used at install time.
- Good, because it avoids recomputing installed desired state only from current catalog files.
- Bad, because table shape grows by one column.

### Store only source id

- Good, because the installed table is smaller.
- Bad, because `local-1` may refer to a different path after backend configuration order changes.

## Consequences

Catalog source resolution must assign source ids from backend configuration before loading manifests.

Catalog list/detail responses use source ids, not raw paths, by default.

Install requests and catalog detail requests select sources by source id.

Ambiguous catalog lookups must fail with `catalog_entry_ambiguous` and list available source ids.

Missing source ids must fail with `catalog_source_not_found`.

Installed App and Service database rows must store `catalog_source_id` and `catalog_source_path`.

## Open Questions

- exact Pydantic/domain validation model names
- whether full manifest snapshots become necessary for stable replay, import/export, or debugging
