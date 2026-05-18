# Draft Manifests

This directory is for temporary, non-canonical manifest sketches while Nephos designs App and Service manifest schemas.

Rules:

- draft manifests here are not source of truth
- draft manifests here are not accepted examples
- draft manifests here do not define schema compatibility
- draft manifest field names reflect accepted field conventions but not a canonical validation schema
- canonical schemas must not be added under `schemas/` until Fer approves the concrete validation schema
- canonical examples must not be added under `examples/` until manifest validation plus command/status shape are stable enough and Fer approves promotion
- draft manifests should be deleted, moved, or converted after the schema/example shape is accepted

Use this directory only to make schema discussions concrete.

Current draft catalog layout:

```text
catalog/
  apps/
    paperless/
      app.yaml
  services/
    postgres/
      service.yaml
```

This mirrors the accepted directory-per-entry catalog layout, but remains non-canonical until Fer approves canonical examples.

Accepted binding/provisioning decisions reflected in the current draft sketches:

- Phase 1 binding output target is `app-secret`
- App binding aliases default to `capability` when `as` is omitted
- binding aliases are unique per App manifest and installed App instance
- `app-secret` Secret names use `nephos-bind-<alias>` in the consuming App namespace
- rebinding updates the same Secret name after explicit reconciliation or confirmation
- binding Secrets include `app.kubernetes.io/managed-by: nephos`, `nephos.pro/app-instance`, `nephos.pro/service-instance`, `nephos.pro/capability`, and `nephos.pro/binding-alias`
- machine identifiers use strict DNS-label style and invalid identifiers are rejected
- default installed instance names equal catalog manifest `metadata.name`
- explicit user-provided instance names are allowed at install time
- name collisions fail and require explicit input
- generated Kubernetes names must fit resource limits after prefixes are added
- PostgreSQL logical output fields are `host`, `port`, `database`, `username`, `password`, and `uri`
- PostgreSQL output fields are capability-defined; there is no Phase 1 manifest `fields:` syntax
- PostgreSQL `app-secret` outputs use exact lowercase Secret keys `host`, `port`, `database`, `username`, `password`, and `uri`
- Phase 1 config option types are `string`, `integer`, `boolean`, and `enum`
- config options use required `name` and `type`, plus optional `label`, `description`, `default`, and `required`
- config option `required` defaults to `false`
- enum config options use object values with `value` and `label`
- `secret` App config option type is deferred
- config validation bounds such as min/max/regex/length are deferred
- config runtime mapping happens through `spec.runtime.values.mappings[]`
- Phase 1 runtime mapping source kinds are `config` and `binding`
- runtime mapping target is `to.helmValue` as a dot path
- missing mapping sources block reconciliation with a reason
- Phase 1 provisioning modes are `app-scoped-resource` and `none`
- `apiVersion`, `kind`, `metadata.name`, and `spec.runtime` are required for Phase 1 installable catalog entries
- App `spec.requires[]`, `spec.routes[]`, and `spec.config.options[]` default to empty lists
- Service `spec.provides[]` is required and non-empty
- Service `spec.provisioning.mode` is required as `none` or `app-scoped-resource`
- unknown manifest fields are rejected once canonical schemas exist
- raw Kubernetes manifest fallback shape is deferred until first needed
- the provisioning execution mechanism remains open
