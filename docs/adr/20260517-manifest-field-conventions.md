# Manifest Field Conventions

- Status: accepted
- Date: 2026-05-17
- Tags: manifests, schema, catalog, apps, services

## Context and Problem Statement

Nephos has accepted a Kubernetes-like manifest envelope with Nephos semantics.

The next decision is the initial field convention for App and Service manifests, while still avoiding canonical `schemas/` files until the concrete validation schema is approved.

## Decision

Use this manifest API version:

- `nephos.pro/v1alpha1`

This is a Nephos manifest schema/version lane.

It is not a Nephos product version, App version, Service version, catalog version, or runtime package version.

Use directory-per-entry catalog layout:

```text
catalog/
  apps/
    <app-slug>/
      app.yaml
  services/
    <service-slug>/
      service.yaml
```

The catalog contains available Apps and Services.

Installed App and Service instances are desired state in the Nephos API/database, not catalog entries.

## Metadata

Use:

- `metadata.name`
- `metadata.displayName`
- `metadata.description`
- `metadata.version`

`metadata.name` is required.

The others are optional.

## App Fields

Use `spec.requires[]` for capability requirements.

Each requirement should support:

- `capability`
- `as`
- `provider`

Use `spec.routes[]` for route intent.

Routes declare route identity and visibility, not final hostnames.

Route shape:

```yaml
spec:
  routes:
    - name: web
      visibility: local
      target:
        port: http
```

Nephos derives hostnames from App instance name, route name, visibility, and configured domain policy.

The same route identity should be usable across local, public, and tailnet/tunnel contexts.

Exact local domain, public root domain, wildcard behavior, MagicDNS/tailnet behavior, and TLS remain open.

Do not put full hostnames in App manifests as the primary route model.

Use `spec.config.options[]` as the config surface.

Option fields such as name, type, default, and required are reserved for later refinement.

Do not model App config as arbitrary environment variables in the primary schema.

## Service Fields

Use `spec.provides[]` for exposed capabilities.

Each provided capability should support:

- `capability`
- `as`
- `version`

Use `spec.bindings.outputs[]` for binding outputs.

Initial binding output direction:

```yaml
spec:
  bindings:
    outputs:
      - name: connection
        target: app-secret
```

`app-secret` means Nephos materializes binding credentials into the consuming App namespace.

For Phase 1, `app-secret` is the only accepted binding output target.

For PostgreSQL bindings, the accepted logical output fields are:

- `host`
- `port`
- `database`
- `username`
- `password`
- `uri`

The exact manifest syntax for declaring payload fields and the exact Secret key serialization remain open.

Use `spec.provisioning.mode` for Service-side binding provisioning behavior.

Accepted Phase 1 modes:

- `app-scoped-resource`
- `none`

`app-scoped-resource` means the Service creates a resource for the consuming App inside the Service instance.

`none` means no Service-side resource is created for the binding.

The provisioning contract is typed and backend/API-owned.

The concrete provisioning execution mechanism remains open.

Use `spec.operations: []` to reserve Service operations.

The Service operation contract remains deferred.

## Runtime Reference

Use `spec.runtime`.

Helm-primary shape:

```yaml
spec:
  runtime:
    type: helm
    chart:
      repository: ...
      name: ...
      version: ...
    values:
      mappings: []
```

`values.mappings` is reserved for Nephos-owned mapping from Nephos semantics into Helm values.

Do not expose raw Helm values as the primary user schema.

Raw Kubernetes manifest runtime references remain a fallback, but their exact field shape remains open.

## Draft Sketches

Non-canonical draft sketches live under:

```text
.agents/drafts/manifests/catalog/apps/paperless/app.yaml
.agents/drafts/manifests/catalog/services/postgres/service.yaml
```

These sketches show selected field conventions, but they are still not canonical examples and do not define a validation schema.

Do not create files under `schemas/` or `examples/` from this ADR alone.

## Still Open

Need to decide:

- exact required vs optional field matrix
- config option object shape
- accepted config option types
- binding output targets beyond `app-secret`
- non-PostgreSQL binding output payload schemas
- exact binding output payload declaration syntax
- exact Secret key serialization
- provisioning execution mechanism
- Service operation contract
- raw manifest runtime reference shape
- validation rules
- promotion path from draft sketches to canonical examples
- when to create schema files under `schemas/`

## Consequences

The initial field convention is concrete enough for design sketches and implementation planning.

The catalog layout gives each App or Service entry room for docs, future assets, patches, and tests.

Hostnames remain controlled by Nephos domain policy instead of being baked into App manifests.

The remaining schema details are still intentionally open.

## Notes

Do not treat this ADR as approval to add canonical JSON Schema or canonical examples.

Do not expose raw Helm values, raw Kubernetes Ingress, raw Secret templates, or arbitrary scripts as the primary manifest UX.
