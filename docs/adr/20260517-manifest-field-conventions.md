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

## Required Field Matrix

For Phase 1 installable catalog entries, every App and Service manifest requires:

- `apiVersion`
- `kind`
- `metadata.name`
- `spec.runtime`

This requirement applies to installable catalog entries that Nephos deploys.

Future imported, external, or pre-existing Services may need a different runtime shape, but that requires a later explicit decision.

## App Fields

Use `spec.requires[]` for capability requirements.

Each requirement should support:

- `capability`
- `as`
- `provider`

If `as` is omitted, the binding alias defaults to `capability`.

Binding aliases must be unique within one App manifest and one installed App instance after defaulting.

If an App needs more than one binding for the same capability, it must set explicit aliases.

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

Each config option supports:

- `name`
- `type`
- `label`
- `description`
- `default`
- `required`

Required config option fields:

- `name`
- `type`

Optional config option fields:

- `label`
- `description`
- `default`
- `required`

`name` is the stable machine key.

Use `label` for display text.

Accepted Phase 1 config option types:

- `string`
- `integer`
- `boolean`
- `enum`

`required` defaults to `false`.

`secret` is deferred as an App config option type.

Do not use App config as a second credential path beside bindings and generated Service credentials.

Do not allow arbitrary object or array config option values in Phase 1.

Do not add validation bounds such as `min`, `max`, `regex`, or length constraints in Phase 1.

Config option `default` values should still match the declared config option type.

For `enum`, use:

```yaml
values:
  - value: daily
    label: Daily
  - value: weekly
    label: Weekly
```

Enum `value` is the stored value.

Enum `label` is display text.

Config options are semantic inputs.

Do not put Helm value paths, environment variables, or Kubernetes field paths directly in config option objects.

Mapping config options into runtime deployment values happens through `spec.runtime.values.mappings[]`.

Phase 1 mapping source kinds:

- `config`
- `binding`

Route and storage mapping source kinds are deferred.

Config mapping shape:

```yaml
from:
  kind: config
  name: paperless_ocr_language
to:
  helmValue: paperless.ocr.language
```

Binding mapping shape:

```yaml
from:
  kind: binding
  name: database
  field: uri
to:
  helmValue: env.DATABASE_URL
```

For binding sources, `name` references the App binding alias.

For binding sources, `field` references a binding output field such as `uri`.

The binding mapping shape may be revisited after a fuller Nephos manifest is evaluated.

The `helmValue` target is a dot path in Phase 1.

Do not use raw nested Helm value fragments as mapping targets in Phase 1.

Do not support mapping transforms in Phase 1.

If a mapping source is missing, reconciliation fails with `blocked` status and a reason.

Mappings live only under `spec.runtime.values.mappings[]`.

Do not define runtime mappings inline on config options or binding declarations.

Do not model App config as arbitrary environment variables in the primary schema.

For Phase 1 App manifests:

- `spec.requires[]` is optional and defaults to an empty list.
- `spec.routes[]` is optional and defaults to an empty list.
- `spec.config.options[]` is optional and defaults to an empty list.

This keeps standalone, worker, internal, and no-route Apps valid.

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

For `app-secret`, Nephos creates the Secret in the consuming App namespace with this name:

```text
nephos-bind-<alias>
```

Rebinding an alias to a different Service instance updates the same Secret name with new contents after explicit reconciliation or confirmation.

Binding Secrets must include metadata identifying App instance, Service instance, capability, binding alias, and `managed-by=nephos`.

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

For Phase 1 Service manifests:

- `spec.provides[]` is required and must be non-empty.
- `spec.provisioning.mode` is required and must be either `none` or `app-scoped-resource`.
- `spec.operations[]` is optional and defaults to an empty list.
- `spec.bindings.outputs[]` is required when the provided capability contract needs binding output materialization.

For the Phase 1 PostgreSQL Service, `spec.bindings.outputs[]` must include an `app-secret` output.

The broader required/default behavior for Services that expose capabilities without binding outputs remains open.

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

The raw Kubernetes manifest fallback shape is deferred until Nephos needs a raw-manifest package.

Do not add raw manifest schema fields now.

## Validation Behavior

Once canonical schemas exist, unknown manifest fields are rejected.

Do not silently ignore unknown fields in canonical manifests.

Before schemas exist, draft manifests remain non-canonical and must not be treated as validation contracts.

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

- binding output targets beyond `app-secret`
- non-PostgreSQL binding output payload schemas
- future optional binding output payload declaration syntax, if needed
- non-PostgreSQL Secret key serialization
- required/default behavior for Services that expose capabilities without binding outputs
- provisioning execution mechanism
- Service operation contract
- raw manifest runtime reference shape when first needed
- validation rules beyond unknown-field rejection
- future validation bounds such as min/max/regex/length
- route and storage mapping source kinds
- target path escaping, if Helm values need literal dots in keys
- mapping transforms, if capability outputs stop being sufficient
- exact promotion path from draft sketches to canonical examples after command/status shape is stable
- when to create schema files under `schemas/`

## Consequences

The initial field convention is concrete enough for design sketches and implementation planning.

The catalog layout gives each App or Service entry room for docs, future assets, patches, and tests.

Hostnames remain controlled by Nephos domain policy instead of being baked into App manifests.

The remaining schema details are still intentionally open.

## Notes

Do not treat this ADR as approval to add canonical JSON Schema or canonical examples.

Do not expose raw Helm values, raw Kubernetes Ingress, raw Secret templates, or arbitrary scripts as the primary manifest UX.
