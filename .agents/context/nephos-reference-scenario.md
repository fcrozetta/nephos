# Nephos Reference Scenario

## Canonical Scenario

The canonical Phase 1 reference scenario is:

- Paperless App
- PostgreSQL Service

The scenario must exercise the Nephos platform model:

- local filesystem catalog
- Nephos App manifest
- Nephos Service manifest
- Service capability exposure
- App capability requirement
- binding
- local ingress intent
- lifecycle semantics
- dependency-aware Service impact
- data preservation and deletion behavior

Do not hardcode Paperless or PostgreSQL behavior in backend logic.

## Minimal Phase 1 Dependencies

Paperless requires only PostgreSQL in the Phase 1 reference scenario.

Do not add Redis, object storage, S3, or additional Services to the canonical Phase 1 reference scenario unless a later decision expands it.

## Reference Flow

The canonical flow is:

1. Install PostgreSQL Service from a local filesystem catalog entry.
2. Install Paperless App from a local filesystem catalog entry.
3. Bind Paperless to the `postgres` capability exposed by PostgreSQL.
4. Expose Paperless through local ingress intent.
5. Start Paperless.
6. Verify Paperless has a known route and binding status.
7. Stop Paperless.
8. Start Paperless again.
9. Verify Paperless data is preserved across stop/start.
10. Attempt to stop PostgreSQL while Paperless depends on it.
11. Nephos blocks the Service stop unless forced and shows an impact list.
12. Remove Paperless while preserving persistent data and metadata.
13. Destroy Paperless with destructive confirmation, deleting App-owned persistent data.

Command spelling and status output are not finalized yet.

## Ingress Placeholder

Use an illustrative local route such as:

- `paperless.<local-domain>`

The exact local domain, wildcard behavior, DNS behavior, and TLS behavior remain open.

The route should exercise Nephos-owned route intent and Kubernetes-owned Ingress resources.

## Service Dependency Impact

The reference scenario must include dependency impact for shared Services.

Stopping PostgreSQL while Paperless depends on it should be blocked unless the operation is forced.

The impact list should explain that Paperless depends on PostgreSQL through a binding.

## Data Semantics

Stop/start must preserve data.

Remove must preserve persistent data and metadata.

Destroy deletes App-owned persistent data and requires destructive confirmation when persistent data exists.

PostgreSQL Service data must not be deleted as a side effect of stopping, removing, or destroying Paperless unless a later explicit Service lifecycle decision says otherwise.

## Draft Manifest Rule

Canonical examples under `examples/` are still blocked until Fer approves manifest/example shape.

Draft manifest sketches may live under:

- `.agents/drafts/manifests/`

Draft manifests are non-canonical.

Draft manifests must not be treated as source of truth.

Do not infer concrete schema fields from draft manifests without a later schema decision.
