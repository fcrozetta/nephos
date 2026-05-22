# Nephos Catalog Loading

API 0.0.1 loads local filesystem catalog manifests.

The catalog contains available Apps and Services.

Installed App and Service instances live in Nephos desired state.

## Source Roots

API 0.0.1 supports:

- one repo-shipped catalog root
- optional configured local filesystem catalog roots

Custom catalog roots are backend local configuration for API 0.0.1.

Examples include environment variables or backend config.

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

Catalog endpoints are for discovery and inspection.

They do not own install mutation.

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

Catalog endpoints are not the primary owner of install mutation.

Do not make arbitrary install-from-path the main API or UX flow.

## Installed Record Metadata

At install time, store:

- catalog kind
- catalog name
- catalog version when available
- catalog source path or source identifier
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
