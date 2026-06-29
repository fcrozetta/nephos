# Catalog Source and Trust Model

- Status: accepted
- Date: 2026-05-17
- Tags: catalog, trust, manifests, phase-1

## Context and Problem Statement

Nephos needs a catalog model for discovering installable Apps and Services.

The catalog must reinforce the Nephos platform model:

- Apps
- Services
- capabilities
- bindings
- lifecycle semantics
- dependency awareness

The catalog must not become a generic app marketplace detached from composition.

## Decision

Phase 1 uses one managed first-party filesystem registry by default.

Supported Phase 1 catalog sources:

- the Nephos-managed `core-registry` checkout
- user-configured local filesystem catalog paths for development experiments

API 0.0.1 starts with exactly one built-in registry dependency: the first-party
`core-registry`. Nephos clones and manages that checkout locally. If
`NEPHOS_API_CATALOG_ROOTS` is configured, those roots replace the managed
registry dependency set for that backend process.

The managed core registry checkout path is:

```text
.nephos/registries/core-registry
```

The managed core registry URL is:

```text
https://git.fcrozetta.app/nephos/core-registry.git
```

Custom catalog roots are backend local configuration for API 0.0.1.

Local catalog root override paths are configured with:

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

Do not store custom catalog roots as platform desired state in SQLite for API 0.0.1.

Catalog source management can move into platform configuration later by explicit decision.

Nephos must not hardcode App or Service behavior in backend logic.

Even the reference scenario should exercise the catalog and manifest path.

User-created local catalog entries are allowed in Phase 1.

Until the concrete validation schema is accepted, local user-created entries do not carry a schema stability promise.

## Trust Model

Phase 1 treats local catalog files as trusted local-owner input.

This matches the accepted single-owner/local-first model.

Phase 1 does not provide:

- catalog signing
- remote catalog verification
- package sandboxing guarantees
- trust policy for third-party remote catalogs
- private remote catalog credentials

Local trust does not mean Nephos should execute arbitrary shell snippets from catalogs as product behavior.

Service operations and runtime deployment mechanisms still need typed, backend-owned contracts.

## Catalog Metadata

For Phase 1, App and Service manifests carry the minimal catalog metadata needed to list and select entries.

A separate catalog index is deferred.

The manifest should remain the package boundary.

Catalog metadata should not become a second source of truth for package semantics.

Catalog entry slugs use the accepted Nephos machine identifier rule.

For Phase 1, the catalog entry directory slug must match the manifest `metadata.name`.

In API 0.0.1, the directory slug and manifest `metadata.name` must match.

Do not silently normalize mismatches.

Duplicate catalog entries with the same kind and name across configured roots are an error unless the caller explicitly selects a source.

Do not let later roots silently override earlier roots.

Ambiguous duplicate entries return `409 Conflict` with code `catalog_entry_ambiguous`.

Unknown source ids return `404 Not Found` with code `catalog_source_not_found`.

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

## Deferred Sources

Deferred catalog sources:

- Git repositories
- OCI artifacts or registries
- remote indexes
- signed catalogs
- private remote catalogs

These need future trust, versioning, update, and credential decisions.

## Consequences

Local filesystem catalogs keep Phase 1 simple and aligned with local-first infrastructure ownership.

Supporting user-created local catalog entries early lets the platform model be tested without waiting for remote distribution.

Deferring signing and remote trust prevents premature security theater.

The downside is that Phase 1 catalog sharing is manual and local.

Remote catalog UX, private catalogs, and signed distribution remain unresolved future work.

## Notes

Do not introduce remote catalog fetching, signing, or OCI distribution without a new decision.

Do not create schema files under `schemas/` until Fer approves the concrete validation schema.

Catalog root environment configuration is refined by [API Bootstrap Mechanics](20260522-api-bootstrap-mechanics.md).

Catalog source identity and error behavior is refined by [Catalog Source Identity and Errors](20260522-catalog-source-identity-and-errors.md).
