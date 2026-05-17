# Nephos Manifest Schema Shape

- Status: accepted
- Date: 2026-05-17
- Tags: manifests, schema, packaging, apps, services

## Context and Problem Statement

Nephos needs a manifest shape for App and Service package definitions.

The manifest must be easy to version and validate, but it must preserve Nephos semantics instead of becoming raw Kubernetes YAML, raw Helm values, or a CRD-first model.

## Decision

Use YAML for Nephos manifests.

Use a Kubernetes-like document envelope with Nephos semantics:

- `apiVersion`
- `kind`
- `metadata`
- `spec`

This is a manifest-file shape decision only.

It does not mean Nephos manifests are Kubernetes CRDs.

It does not make Kubernetes the source of truth.

The accepted manifest kinds are:

- `App`
- `Service`

Apps and Services remain separate manifest kinds because they have different roles and authors.

## App Manifest Direction

An App manifest declares App-level platform intent.

The App `spec` should organize:

- required capabilities
- optional route or visibility intent
- config surface
- runtime deployment reference

An App manifest should not require the App author to know Service internals.

## Service Manifest Direction

A Service manifest declares Service-level platform intent.

The Service `spec` should organize:

- exposed capabilities
- binding outputs
- provisioning behavior, optional or deferred
- runtime deployment reference
- Service operations, optional or deferred

Service manifests may include more infrastructure-specific concerns than App manifests because Service authors define capability providers.

## Runtime Deployment References

Runtime deployment references stay underneath Nephos manifests.

Phase 1 remains Helm-primary.

Helm runtime references should carry the chart identity needed for pinned deployment, such as repository, chart name, and chart version.

Raw Kubernetes manifests remain an allowed fallback runtime reference.

Nephos must not expose raw Helm values or raw Kubernetes object specs as the primary product schema.

Nephos should map Nephos-level config, bindings, storage intent, and visibility intent into runtime deployment values later.

## Binding Shape

Binding schema remains minimal at the manifest level for now.

The initial direction is:

- App manifests declare required capabilities such as `postgres`
- Service manifests declare exposed capabilities such as `postgres`
- Nephos resolves and creates bindings outside the manifest

Concrete binding field names remain open.

## Draft Sketches

Non-canonical draft manifest sketches may live under:

- `.agents/drafts/manifests/`

The current draft sketches are illustrative only.

They do not define stable schema compatibility.

Do not create canonical files under `schemas/` or `examples/` from this ADR alone.

## Still Open

Need to decide:

- exact `apiVersion` value
- exact manifest filenames
- exact field names
- required vs optional fields
- config surface format
- capability requirement syntax
- exposed capability syntax
- runtime deployment reference syntax
- validation rules
- when to promote draft sketches into canonical examples
- when to create files under `schemas/`

## Consequences

The Kubernetes-like envelope gives Nephos a familiar, versionable manifest structure.

Keeping Nephos semantics inside the envelope prevents the manifest from becoming raw Kubernetes UX.

The product-like alternative may be simpler visually, but it would force Nephos to invent more YAML conventions from scratch.

This decision accepts the envelope, not the full schema.

## Notes

Do not implement a CRD-first model from this decision.

Do not treat draft manifests as canonical schemas.
