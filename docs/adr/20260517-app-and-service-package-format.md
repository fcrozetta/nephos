# App and Service Package Format

- Status: accepted
- Date: 2026-05-17
- Tags: catalog, manifests, apps, services, schema

## Context and Problem Statement

Nephos needs a format for defining installable Apps and Services.

The format must support catalog entries, runtime deployment, capability requirements, exposed capabilities, provisioning contracts, Service operations, health checks, and lifecycle behavior.

## Decision

Use Nephos manifests as the package boundary for Apps and Services.

Use separate manifest formats for Apps and Services because they have different roles, authors, and internal concerns.

App creators should not need to understand Service internals.

Service creators should model infrastructure capabilities, provisioning behavior, and Service operations.

The Nephos manifest layer owns platform semantics.

Helm charts are the primary Phase 1 runtime deployment mechanism underneath Nephos manifests.

Raw Kubernetes manifests are allowed as a fallback runtime deployment mechanism.

The local filesystem is the first catalog source.

Git, OCI, remote indexes, private catalogs, and signed catalogs are deferred.

## Nephos Manifest

A Nephos manifest describes platform intent.

Nephos manifests use YAML.

Nephos manifests use a Kubernetes-like envelope with Nephos semantics:

- `apiVersion`
- `kind`
- `metadata`
- `spec`

Accepted manifest kinds:

- `App`
- `Service`

Accepted manifest API version:

- `nephos.pro/v1alpha1`

This does not mean Nephos manifests are Kubernetes CRDs.

It speaks in Nephos concepts:

- Apps
- Services
- capabilities
- bindings
- ingress or visibility intent
- storage intent
- config surface
- health and status intent
- lifecycle semantics
- Service operations
- runtime deployment references

A Nephos manifest is not a Helm chart and is not raw Kubernetes YAML.

## Runtime Deployment References

A Nephos manifest may point to runtime deployment implementation:

- Helm chart
- raw Kubernetes manifests

Helm-primary runtime references use `spec.runtime` with chart repository, name, and version.

`spec.runtime.values.mappings[]` is reserved for Nephos-owned mapping from Nephos semantics into Helm values.

Helm and raw Kubernetes manifests stay below the Nephos product model.

Users should not normally interact with Helm values or Kubernetes object specs as the primary Nephos UX.

## Helm-Primary Deployment

Use Helm as the primary underlying deployment mechanism when a credible chart exists or when Helm lifecycle/versioning gives leverage.

Nephos should pin chart versions and map Nephos-level config, bindings, storage intent, and visibility intent into Helm values.

Do not expose arbitrary Helm values as the primary product model.

## Raw Kubernetes Manifest Fallback

Use raw Kubernetes manifests when:

- no credible Helm chart exists
- the available Helm chart is abandoned, too leaky, or too unstable
- the deployment is simple enough that Helm adds noise
- Nephos deploys its own control-plane or support components
- Nephos needs a curated deployment where direct ownership of runtime objects is clearer

Raw manifests are fallback runtime plumbing.

They are not the Nephos package model.

## Service Operations

The canonical term is Service operation.

Service management action is an acceptable descriptive phrase, but not the preferred term.

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

Do not model Service operations as arbitrary user-facing shell scripts.

The detailed Service operation contract still needs design.

## Example App Concept

An App manifest declares:

- `metadata.name`
- optional `metadata.displayName`
- optional `metadata.description`
- optional `metadata.version`
- `spec.requires[]`
- `spec.routes[]`
- `spec.config.options[]`
- `spec.runtime`

## Example Service Concept

A Service manifest declares:

- `metadata.name`
- optional `metadata.displayName`
- optional `metadata.description`
- optional `metadata.version`
- `spec.provides[]`
- `spec.bindings.outputs[]`
- `spec.provisioning.mode`
- `spec.runtime`
- `spec.operations[]`

Later accepted binding/provisioning direction:

- Phase 1 installable catalog entries require `apiVersion`, `kind`, `metadata.name`, and `spec.runtime`
- App `spec.requires[]`, `spec.routes[]`, and `spec.config.options[]` default to empty lists
- Service `spec.provides[]` is required non-empty
- Service `spec.provisioning.mode` is required as either `none` or `app-scoped-resource`
- Phase 1 binding output target is `app-secret`
- PostgreSQL binding output fields are `host`, `port`, `database`, `username`, `password`, and `uri`
- Phase 1 provisioning modes are `app-scoped-resource` and `none`
- provisioning is a typed backend/API-owned contract
- PostgreSQL output fields are capability-defined without a manifest `fields:` syntax in Phase 1
- PostgreSQL `app-secret` outputs use exact lowercase Secret keys `host`, `port`, `database`, `username`, `password`, and `uri`
- Phase 1 App config option types are `string`, `integer`, `boolean`, and `enum`
- config options use required `name` and `type`, plus optional `label`, `description`, `default`, and `required`
- config option `required` defaults to `false`
- enum config options use object values with `value` and `label`
- `secret` App config option type is deferred
- config validation bounds such as min/max/regex/length are deferred
- config runtime mapping happens through `spec.runtime.values.mappings[]`
- unknown manifest fields are rejected once canonical schemas exist
- raw Kubernetes manifest fallback shape is deferred until first needed
- the provisioning execution mechanism remains open

## Decision Outcome

Chosen option: "Separate App and Service Nephos manifests with Helm-primary runtime deployment and raw manifest fallback", because it preserves Nephos platform semantics while using existing Kubernetes packaging where that gives leverage.

## Status Notes

This decision is accepted.

Do not invent concrete package fields silently in implementation without updating ADR/context or adding an approved schema file.

The high-level manifest envelope is approved.

No concrete schema file is approved yet.
