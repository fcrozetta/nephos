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

Accepted `apiVersion`:

- `nephos.pro/v1alpha1`

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
- Service operations, reserved but bounded

Service manifests may include more infrastructure-specific concerns than App manifests because Service authors define capability providers.

## Runtime Deployment References

Runtime deployment references stay underneath Nephos manifests.

Phase 1 remains Helm-primary.

Helm runtime references should carry the chart identity needed for pinned deployment, such as repository, chart name, and chart version.

Raw Kubernetes manifests remain an allowed fallback runtime reference.

Nephos must not expose raw Helm values or raw Kubernetes object specs as the primary product schema.

Nephos should map Nephos-level config, bindings, storage intent, and visibility intent into runtime deployment values later.

Phase 1 route hostnames are generated from route intent and configured ingress root domains:

- default route: `<app-instance>.<root-domain>`
- non-default route: `<route>.<app-instance>.<root-domain>`

App manifests must not carry full hostnames as primary route identity.

## Binding Shape

Binding schema remains minimal at the manifest level for now.

The initial direction is:

- App manifests declare required capabilities such as `postgres`
- Service manifests declare exposed capabilities such as `postgres`
- Nephos resolves and creates bindings outside the manifest

Concrete binding output payload fields are accepted only for the initial PostgreSQL case.

Later accepted direction:

- Phase 1 binding output target is `app-secret`.
- App binding aliases default to `capability` when `as` is omitted.
- Binding aliases must be unique within one App manifest and one installed App instance after defaulting.
- `app-secret` Secret names use `nephos-bind-<alias>` in the consuming App namespace.
- Rebinding an alias to a different Service instance updates the same Secret name after explicit reconciliation or confirmation.
- Binding Secrets include `app.kubernetes.io/managed-by: nephos`, `nephos.pro/app-instance`, `nephos.pro/service-instance`, `nephos.pro/capability`, and `nephos.pro/binding-alias`.
- PostgreSQL binding output fields are `host`, `port`, `database`, `username`, `password`, and `uri`.
- PostgreSQL binding output fields are capability-defined and do not use a manifest `fields:` syntax in Phase 1.
- PostgreSQL `app-secret` outputs use exact lowercase Secret keys: `host`, `port`, `database`, `username`, `password`, and `uri`.
- Other binding targets and non-PostgreSQL payload schemas remain open.
- Phase 1 installable catalog entries require `apiVersion`, `kind`, `metadata.name`, and `spec.runtime`.
- Manifest `metadata.name`, binding aliases, route names, installed instance slugs, and catalog entry slugs use strict DNS-label style machine identifiers.
- Nephos rejects invalid machine identifiers instead of silently normalizing them.
- Default installed instance names equal catalog manifest `metadata.name`.
- Users may override the instance name at install time.
- Platform-visible name collisions fail and require explicit user input.
- Nephos rejects generated Kubernetes names that exceed resource limits after prefixes are added.
- App `spec.requires[]`, `spec.routes[]`, and `spec.config.options[]` default to empty lists.
- Config options use `name`, `type`, optional `label`, optional `description`, optional `default`, and optional `required`.
- Config option `name` is the stable machine key.
- Config option `required` defaults to `false`.
- Phase 1 App config option types are `string`, `integer`, `boolean`, and `enum`.
- Enum config options use object values with `value` and `label`.
- Config option `default` values should match the declared config option type.
- `secret` App config option type is deferred.
- Config validation bounds such as min/max/regex/length are deferred.
- Runtime mappings stay in `spec.runtime.values.mappings[]`, not in config option or binding objects.
- Phase 1 runtime mapping source kinds are `config` and `binding`.
- Config mappings use `from.kind: config`, `from.name`, and `to.helmValue`.
- Binding mappings use `from.kind: binding`, `from.name`, `from.field`, and `to.helmValue`.
- `helmValue` is a dot path in Phase 1.
- Mapping transforms are deferred.
- Missing mapping sources block reconciliation with a reason.
- Service `spec.provides[]` is required non-empty.
- Service `spec.provisioning.mode` is required as either `none` or `app-scoped-resource`.
- `spec.operations[]` is reserved and defaults to an empty list.
- Service operations are typed backend/API-owned actions, not arbitrary shell commands or hooks.
- Phase 1 may use internal typed Service handlers for minimal accepted provisioning work.
- Phase 1 does not expose a general user-facing Service operation API or CLI UX.
- Unknown manifest fields are rejected once canonical schemas exist.
- Raw Kubernetes manifest fallback shape is deferred until first needed.
- Canonical examples remain blocked until manifest validation plus command/status shape are stable enough.

## Draft Sketches

Non-canonical draft manifest sketches may live under:

- `.agents/drafts/manifests/`

The current draft sketches are illustrative only.

They do not define stable schema compatibility.

Do not create canonical files under `schemas/` or `examples/` from this ADR alone.

## Still Open

Need to decide:

- binding output targets beyond `app-secret`
- non-PostgreSQL binding output payload schemas
- future optional binding output payload declaration syntax, if needed
- raw manifest runtime reference shape when first needed
- validation rules beyond unknown-field rejection
- future validation bounds such as min/max/regex/length
- route and storage mapping source kinds
- target path escaping, if Helm values need literal dots in keys
- mapping transforms, if capability outputs stop being sufficient
- command/status shape needed before promoting draft sketches into canonical examples
- when to create files under `schemas/`

## Consequences

The Kubernetes-like envelope gives Nephos a familiar, versionable manifest structure.

Keeping Nephos semantics inside the envelope prevents the manifest from becoming raw Kubernetes UX.

The product-like alternative may be simpler visually, but it would force Nephos to invent more YAML conventions from scratch.

This decision accepts the envelope, not the full schema.

## Notes

Do not implement a CRD-first model from this decision.

Do not treat draft manifests as canonical schemas.
