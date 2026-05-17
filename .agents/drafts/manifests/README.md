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
- PostgreSQL logical output fields are `host`, `port`, `database`, `username`, `password`, and `uri`
- PostgreSQL output fields are capability-defined; there is no Phase 1 manifest `fields:` syntax
- Phase 1 provisioning modes are `app-scoped-resource` and `none`
- `apiVersion`, `kind`, `metadata.name`, and `spec.runtime` are required for Phase 1 installable catalog entries
- App `spec.requires[]`, `spec.routes[]`, and `spec.config.options[]` default to empty lists
- Service `spec.provides[]` is required and non-empty
- Service `spec.provisioning.mode` is required as `none` or `app-scoped-resource`
- the exact Secret key serialization and provisioning execution mechanism remain open
