# Draft Manifests

This directory is for temporary, non-canonical manifest sketches while Nephos designs App and Service manifest schemas.

Rules:

- draft manifests here are not source of truth
- draft manifests here are not accepted examples
- draft manifests here do not define schema compatibility
- draft manifest field names reflect accepted field conventions but not a canonical validation schema
- canonical schemas must not be added under `schemas/` until Fer approves the concrete validation schema
- canonical examples must not be added under `examples/` until Fer approves the manifest/example shape
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
