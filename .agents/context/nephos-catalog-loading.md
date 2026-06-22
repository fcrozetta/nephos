# Nephos Catalog Loading

API 0.0.1 loads local filesystem catalog manifests.

The catalog contains available Apps and Services.

Installed App and Service instances live in Nephos desired state.

## Source Roots

API 0.0.1 supports:

- one repo-shipped catalog root
- optional configured local filesystem catalog roots

Custom catalog roots are backend local configuration for API 0.0.1.

The repo-shipped catalog root is:

```text
catalog/
```

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

Catalog source management can become platform configuration later by explicit decision.

## Loading Strategy

Read and validate catalog manifests on demand.

Do not import all catalog entries into SQLite before use in API 0.0.1.

Do not require a startup catalog index in API 0.0.1.

## Read-Only Catalog API

API 0.0.1 exposes read-only catalog endpoints:

```text
GET /catalog/apps
GET /catalog/apps/{name}
GET /catalog/services
GET /catalog/services/{name}
```

Catalog detail endpoints accept optional `source` selection where duplicate catalog entries require disambiguation.

The `source` query parameter uses source ids such as `default` or `local-1`.

Catalog endpoints are for discovery and inspection.

They do not own install mutation.

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

App catalog summaries include:

- `requires`
- `routes`

App catalog `requires` entries use:

- `capability`
- `protocol`
- `alias`
- optional `provider`

If the manifest omits the binding alias, `alias` is defaulted from the capability.

For protocol-aware requirements, `capability + protocol` is the binding match
key. The alias remains the App-local binding name.

App catalog `routes` entries use:

- `name`
- `visibility`
- `target`

Service catalog summaries include:

- `provides`

Service catalog `provides` entries use:

- `capability`
- `protocol`
- optional `alias`
- optional `version`
- `bindingOutputTargets`

For protocol-aware provisions, `capability + protocol` is the Service eligibility
key. Capability alone is not enough for alpha backbone database bindings.

Accepted alpha backbone Service provisions:

- PostgreSQL provides `sql/postgres`.
- ArcadeDB provides `sql/arcadedb`, `opencypher/bolt`, and `opencypher/n4j`.
- ArcadeDB may provide `gremlin/gremlin` and `mongo/mongo` when those protocols
  are enabled.
- SeaweedFS provides `object-storage/s3`.
- Zitadel provides `oidc/oidc` and `service-account/jwt`.

Do not model Zitadel login/admin UI as an App catalog entry. They are Zitadel
Service surfaces/routes.

Do not return raw manifest blobs by default.

Raw or full validated manifest output, if needed later, requires an explicit response field or endpoint decision.

## Entry Layout And Identity

Accepted layout:

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

Ambiguous duplicate entries return `409 Conflict` with Nephos domain error code `catalog_entry_ambiguous`.

`catalog_entry_ambiguous` details include `kind`, `name`, and `sources[]` as source ids.

If a caller requests an unknown source id, return `404 Not Found` with error code `catalog_source_not_found`.

## Validation

Validate manifests with typed Python/Pydantic domain models in API code first.

Do not add canonical JSON Schema files under `schemas/` until Fer approves the concrete validation schema.

Reject unknown manifest fields once canonical validation models exist.

Loose YAML dictionary validation is not the accepted API 0.0.1 direction.

## Install Selection

Install by catalog kind and name.

Allow optional explicit source selection when needed to disambiguate duplicates.

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

## Installed Record Metadata

At install time, store:

- catalog kind
- catalog name
- catalog version when available
- catalog source id
- catalog source path snapshot
- SHA-256 digest of the manifest file content

Do not store a full manifest snapshot by default.

Store a full manifest snapshot only if implementation proves it is necessary for a concrete behavior such as stable replay, import/export, or debugging.

`metadata.version` remains optional for catalog entries.

Installed records store version if present and always store the manifest digest.

## Drafts And Canonical Examples

Temporary draft manifests stay under `.agents/drafts/manifests/`.

Drafts are non-canonical.

Do not promote drafts into `examples/` until API validation models exist and Fer approves promotion.

Do not treat drafts as implementation contracts.
