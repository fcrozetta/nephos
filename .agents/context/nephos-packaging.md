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

## Manifest Types

Use separate manifest formats for Apps and Services.

Reason:

- Apps and Services have different roles.
- App authors usually should not need to understand Service internals.
- Service authors need to model capability exposure, provisioning behavior, and Service operations.

Do not collapse App and Service package definitions into one generic deployment format.

## App Manifest

An App manifest describes a user-facing workload/product.

It should eventually include:

- metadata
- required capabilities
- optional capability preferences
- runtime deployment reference
- ingress or visibility intent
- storage intent
- config surface
- secret/environment mapping
- health/status expectations
- lifecycle behavior

## Service Manifest

A Service manifest describes shared platform infrastructure that exposes capabilities.

It should eventually include:

- metadata
- exposed capabilities
- runtime deployment reference
- optional provisioning contracts
- optional Service operations
- backup/restore hooks or intent
- health/status expectations
- secret outputs
- supported binding types
- lifecycle behavior

## Runtime Deployment References

Runtime deployment references point below the Nephos platform model.

Accepted Phase 1 deployment mechanisms:

- Helm chart reference as primary
- raw Kubernetes manifest reference as fallback

Helm and raw Kubernetes manifests are not the product package model.

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

Until the manifest schema is accepted, local user-created entries do not carry a schema stability promise.

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

## Schema Status

The high-level manifest envelope has been approved:

- YAML
- `apiVersion`
- `kind`
- `metadata`
- `spec`
- separate `App` and `Service` kinds

The concrete field schema has not been approved yet.

Do not add files under `schemas/` until Fer approves the concrete manifest field schema.

Do not add examples under `examples/` until the example shape is approved.

Temporary draft manifest sketches may live under `.agents/drafts/manifests/`.

Draft manifests are non-canonical and must not be treated as schema or example source of truth.
