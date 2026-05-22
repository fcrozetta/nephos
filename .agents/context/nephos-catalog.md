# Nephos Catalog

## Purpose

The catalog exists to support platform composition.

It is not merely an app marketplace.

Catalog entries must reinforce:

- Apps
- Services
- capabilities
- bindings
- lifecycle semantics
- dependency awareness

## Phase 1 Sources

Phase 1 uses local filesystem catalogs.

Supported Phase 1 sources:

- repo-shipped reference catalog entries
- user-configured local filesystem catalog paths

API 0.0.1 supports one repo-shipped catalog root plus optional configured local filesystem catalog roots.

The repo-shipped catalog root is:

```text
catalog/
```

Custom catalog roots are backend local configuration for API 0.0.1.

Additional local catalog roots are configured with:

```text
NEPHOS_API_CATALOG_ROOTS
```

`NEPHOS_API_CATALOG_ROOTS` is parsed as a platform path-list, such as `:`-separated paths on macOS/Linux.

Catalog source ids:

- repo-shipped catalog root: `default`
- configured local roots: `local-1`, `local-2`, `local-3`, in configured order

Source ids are stable only for the current backend configuration and root order.

Catalog responses expose source ids through `source`.

Catalog responses do not expose raw filesystem paths by default.

`sourcePath` is reserved for future backend/debug/detail contexts and is not part of default catalog list output.

Do not store custom catalog roots as platform desired state in SQLite for API 0.0.1.

Catalog source management can move into platform configuration later by explicit decision.

The repo may ship a tiny reference catalog.

The backend must not hardcode App or Service behavior.

Reference scenarios should exercise the catalog and manifest path.

The catalog stores available Apps and Services.

Installed App and Service instances live in Nephos desired state, not in catalog files.

Accepted local catalog layout:

```text
catalog/
  apps/
    <app-slug>/
      app.yaml
  services/
    <service-slug>/
      service.yaml
```

Catalog entry slugs use the accepted Nephos machine identifier rule.

For Phase 1, the catalog entry directory slug must match the manifest `metadata.name`.

In API 0.0.1, the directory slug and manifest `metadata.name` must match.

Do not silently normalize mismatches.

Duplicate catalog entries with the same kind and name across configured roots are an error unless the caller explicitly selects a source.

Do not let later roots silently override earlier roots.

Ambiguous duplicate entries return `409 Conflict` with Nephos domain error code `catalog_entry_ambiguous`.

`catalog_entry_ambiguous` details include `kind`, `name`, and `sources[]` as source ids.

If a caller requests an unknown source id, return `404 Not Found` with error code `catalog_source_not_found`.

By default, an installed instance name equals the catalog manifest `metadata.name`.

Users may provide an explicit instance name at install time.

## Loading And Validation

API 0.0.1 reads and validates catalog manifests on demand.

Do not import all catalog entries into SQLite before use.

Do not require a startup catalog index.

Validate manifests with typed Python/Pydantic domain models in API code first.

Do not add canonical JSON Schema files under `schemas/` until Fer approves the concrete validation schema.

Reject unknown manifest fields once canonical validation models exist.

Install by catalog kind and name, plus optional explicit source when needed.

Do not make arbitrary install-from-path the main API or UX flow.

At install time, store catalog kind, catalog name, catalog version when available, catalog source id, catalog source path snapshot, and SHA-256 digest of the manifest file content.

Do not store a full manifest snapshot by default.

Store a full manifest snapshot only if implementation proves it is necessary for a concrete behavior such as stable replay, import/export, or debugging.

## User-Created Entries

User-created local catalog entries are allowed in Phase 1.

Until the concrete validation schema is accepted, local user-created entries do not carry a schema stability promise.

Do not create schema files under `schemas/` until Fer approves the concrete validation schema.

Do not create examples under `examples/` until manifest validation plus command/status shape are stable enough and Fer approves promotion.

Temporary draft manifest sketches may live under `.agents/drafts/manifests/`.

Draft manifests are non-canonical and do not define schema compatibility.

## Trust Model

Phase 1 treats local catalog files as trusted local-owner input.

There is no Phase 1 support for:

- catalog signing
- remote catalog verification
- package sandboxing guarantees
- third-party remote catalog trust policy
- private remote catalog credentials

Local trust does not allow arbitrary catalog shell scripts to become a product feature.

Runtime deployment and Service operations must still flow through Nephos-owned typed contracts.

## Metadata Model

For Phase 1, App and Service manifests carry minimal catalog metadata.

A separate catalog index is deferred.

Catalog metadata must not become a second source of truth for package semantics.

The Nephos manifest remains the package boundary.

## Deferred Sources

Deferred catalog sources:

- Git repositories
- OCI artifacts or registries
- remote indexes
- signed catalogs
- private remote catalogs

Future remote catalogs need explicit decisions for:

- trust model
- signing and verification
- credentials
- versioning
- update behavior
- compatibility metadata
