# Nephos Packaging

## Core Decision

Installable Apps and Services are defined by Nephos manifests.

Nephos manifests are the package boundary.

Nephos manifests own platform semantics.

Helm charts and raw Kubernetes manifests are runtime deployment implementation details underneath the Nephos manifest layer.

## Manifest Envelope

Nephos manifests use YAML.

Nephos manifests use a Kubernetes-like document envelope with Nephos semantics:

- `apiVersion`
- `kind`
- `metadata`
- `spec`

This does not mean Nephos manifests are Kubernetes CRDs.

This does not make Kubernetes the source of truth.

Accepted manifest kinds:

- `App`
- `Service`

Accepted manifest API version:

- `nephos.pro/v1alpha1`

This is a manifest schema/version lane, not a Nephos product version, App version, Service version, catalog version, or runtime package version.

For Phase 1 installable catalog entries, every App and Service manifest requires:

- `apiVersion`
- `kind`
- `metadata.name`
- `spec.runtime`

This requirement applies to installable catalog entries that Nephos deploys.

Future imported, external, or pre-existing Services may need a different runtime shape, but that requires a later explicit decision.

## Manifest Types

Use separate manifest formats for Apps and Services.

Reason:

- Apps and Services have different roles.
- App authors usually should not need to understand Service internals.
- Service authors need to model capability exposure, provisioning behavior, and Service operations.

Do not collapse App and Service package definitions into one generic deployment format.

## App Manifest

An App manifest describes a user-facing workload/product.

Accepted initial field conventions:

- `metadata.name`
- optional `metadata.displayName`
- optional `metadata.description`
- optional `metadata.version`
- `spec.requires[]`
- `spec.routes[]`
- `spec.config.options[]`
- `spec.runtime`

`spec.requires[]` entries should support `capability`, optional `as`, and optional `provider`.

`spec.routes[]` entries declare route identity and visibility, not final hostnames.

Nephos derives hostnames from App instance name, route name, visibility, and configured domain policy.

Do not put full hostnames in App manifests as the primary route model.

Accepted Phase 1 config option types:

- `string`
- `integer`
- `boolean`
- `enum`

`secret` is deferred as an App config option type.

Do not use App config as a second credential path beside bindings and generated Service credentials.

Do not allow arbitrary object or array config option values in Phase 1.

For Phase 1 App manifests:

- `spec.requires[]` is optional and defaults to an empty list.
- `spec.routes[]` is optional and defaults to an empty list.
- `spec.config.options[]` is optional and defaults to an empty list.

This keeps standalone, worker, internal, and no-route Apps valid.

## Service Manifest

A Service manifest describes shared platform infrastructure that exposes capabilities.

Accepted initial field conventions:

- `metadata.name`
- optional `metadata.displayName`
- optional `metadata.description`
- optional `metadata.version`
- `spec.provides[]`
- `spec.bindings.outputs[]`
- `spec.provisioning.mode`
- `spec.runtime`
- `spec.operations[]`

`spec.provides[]` entries should support `capability`, optional `as`, and optional `version`.

`spec.bindings.outputs[]` starts with `target: app-secret`.

`app-secret` means Nephos materializes binding credentials into the consuming App namespace.

For Phase 1, `app-secret` is the only accepted binding output target.

PostgreSQL binding outputs are capability-defined.

The accepted PostgreSQL logical output fields are:

- `host`
- `port`
- `database`
- `username`
- `password`
- `uri`

Do not add a manifest `fields:` syntax for PostgreSQL outputs in Phase 1.

For PostgreSQL `app-secret` outputs, use these exact lowercase Kubernetes Secret keys:

- `host`
- `port`
- `database`
- `username`
- `password`
- `uri`

Runtime mappings may translate these keys into chart values or environment variables later.

Accepted Phase 1 provisioning modes:

- `app-scoped-resource`
- `none`

`app-scoped-resource` means the Service creates a resource for the consuming App inside the Service instance.

`none` means no Service-side resource is created for the binding.

The provisioning contract is typed and backend/API-owned.

Do not model provisioning as arbitrary user-facing shell scripts or as Helm hooks exposed as product semantics.

The concrete provisioning execution mechanism remains open.

`spec.operations[]` is reserved.

The Service operation contract remains deferred.

For Phase 1 Service manifests:

- `spec.provides[]` is required and must be non-empty.
- `spec.provisioning.mode` is required and must be either `none` or `app-scoped-resource`.
- `spec.operations[]` is optional and defaults to an empty list.
- `spec.bindings.outputs[]` is required when the provided capability contract needs binding output materialization.

For the Phase 1 PostgreSQL Service, `spec.bindings.outputs[]` must include an `app-secret` output.

The broader required/default behavior for Services that expose capabilities without binding outputs remains open.

## Runtime Deployment References

Runtime deployment references point below the Nephos platform model.

Accepted Phase 1 deployment mechanisms:

- Helm chart reference as primary
- raw Kubernetes manifest reference as fallback

Accepted Helm-primary field direction:

- `spec.runtime.type: helm`
- `spec.runtime.chart.repository`
- `spec.runtime.chart.name`
- `spec.runtime.chart.version`
- `spec.runtime.values.mappings[]`

`values.mappings` is reserved for Nephos-owned mapping from Nephos semantics into Helm values.

Do not expose raw Helm values as the primary user schema.

Helm and raw Kubernetes manifests are not the product package model.

The raw Kubernetes manifest fallback shape is deferred until Nephos needs a raw-manifest package.

Do not add raw manifest schema fields now.

## Validation Behavior

Once canonical schemas exist, unknown manifest fields are rejected.

Do not silently ignore unknown fields in canonical manifests.

Before schemas exist, draft manifests remain non-canonical and must not be treated as validation contracts.

## Helm-Primary Policy

Use Helm as the primary underlying deployment mechanism when:

- a credible chart exists
- chart versioning gives leverage
- chart lifecycle aligns with Nephos lifecycle semantics
- Nephos can map platform intent into chart values without exposing Helm as UX

Nephos should pin chart versions.

Nephos should generate values from Nephos-level config, bindings, storage intent, and visibility intent.

Users should not normally edit Helm values directly through Nephos.

## Raw Manifest Fallback Policy

Use raw Kubernetes manifests when:

- no credible Helm chart exists
- the Helm chart is abandoned, too leaky, or unstable
- the workload is simple enough that Helm adds noise
- Nephos deploys its own control-plane or support components
- a curated Nephos-native deployment is clearer than chart wrapping

Raw manifests must remain below the Nephos manifest.

Do not expose arbitrary Kubernetes YAML as the primary package UX.

## Catalog Source

Phase 1 catalog source:

- local filesystem catalogs

Supported Phase 1 sources:

- repo-shipped reference catalog entries
- user-configured local filesystem catalog paths

User-created local catalog entries are allowed in Phase 1.

Until the concrete validation schema is accepted, local user-created entries do not carry a schema stability promise.

Phase 1 treats local catalog files as trusted local-owner input.

For Phase 1, App and Service manifests carry minimal catalog metadata.

A separate catalog index is deferred.

Deferred catalog sources:

- Git repositories
- OCI artifacts or registries
- remote indexes
- signed catalogs
- private remote catalogs

Remote catalog trust, signing, verification, private catalog credentials, and catalog update behavior are deferred.

Catalogs exist to support composition, not app-store behavior.

Catalog entries should reinforce:

- Apps
- Services
- capabilities
- bindings
- lifecycle semantics
- dependency awareness

Accepted catalog entry layout:

```text
catalog/
  apps/
    <app-slug>/
      app.yaml
  services/
    <service-slug>/
      service.yaml
```

The catalog stores available Apps and Services.

Installed App and Service instances live in Nephos desired state, not in the catalog.

## Service Operations

The canonical term is Service operation.

Service management action may be used descriptively, but Service operation is the term to prefer in architecture docs.

A Service operation is a typed backend/API-owned management action exposed by a Service.

Examples:

- provision app-scoped resource
- deprovision app-scoped resource
- rotate credentials
- backup
- restore
- run health diagnostic
- create database
- create bucket or prefix
- compact, vacuum, reindex, or similar Service-specific maintenance

Service operations are optional in Phase 1.

Do not treat Service operations as arbitrary user-facing shell scripts.

The Service operation contract needs later design before schemas are created.

## Binding Output And Provisioning

App manifests use symbolic binding aliases.

Example:

```yaml
spec:
  requires:
    - capability: postgres
      as: database
```

The alias gives the App a stable semantic name for the binding.

Nephos maps binding outputs into runtime deployment values through the reserved `spec.runtime.values.mappings[]` lane.

Service manifests declare logical binding outputs, not final consuming Secret names.

Nephos chooses deterministic Secret names from binding identity.

The exact naming algorithm remains open.

Remove preserves provisioned Service-side resources created for an App.

Destroy deletes provisioned Service-side resources created for an App after destructive confirmation.

## Schema Status

The high-level manifest envelope has been approved:

- YAML
- `apiVersion`
- `kind`
- `metadata`
- `spec`
- separate `App` and `Service` kinds
- `apiVersion: nephos.pro/v1alpha1`
- directory-per-entry catalog layout with `app.yaml` and `service.yaml`

The initial field conventions have been approved, but the concrete validation schema has not.

Do not add files under `schemas/` until Fer approves the concrete validation schema.

Do not add examples under `examples/` until manifest validation plus command/status shape are stable enough that canonical examples will not immediately rot.

Temporary draft manifest sketches may live under `.agents/drafts/manifests/`.

Draft manifests are non-canonical and must not be treated as schema or example source of truth.
