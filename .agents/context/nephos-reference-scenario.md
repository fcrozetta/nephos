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
4. PostgreSQL provisions an app-scoped database/user for Paperless.
5. Nephos materializes PostgreSQL binding outputs into the Paperless App namespace.
6. Expose Paperless through local ingress intent.
7. Start Paperless.
8. Verify Paperless has a known route and binding status.
9. Verify the binding exposes PostgreSQL logical fields `host`, `port`, `database`, `username`, `password`, and `uri`.
10. Stop Paperless.
11. Start Paperless again.
12. Verify Paperless data is preserved across stop/start.
13. Attempt to stop PostgreSQL while Paperless depends on it.
14. Nephos blocks the Service stop unless forced and shows an impact list.
15. Remove Paperless while preserving persistent data and metadata.
16. Verify remove preserves the app-scoped PostgreSQL resource and binding metadata.
17. Destroy Paperless with destructive confirmation, deleting persistent data and app-scoped PostgreSQL resources associated with Paperless.

Command spelling and status output are not finalized yet.

## Ingress Placeholder

Use an illustrative local route such as:

- `paperless.nephos.local`
- `paperless.nephos.fcrozetta.app`

These are examples of two configured ingress root domains for the same Paperless route.

One configured root domain is canonical/default.

The other generated hostnames are aliases.

The ingress root domains are platform desired state created during Nephos setup before Apps are installed.

The setup UX and command implementation are deferred to `nephos-cli` after Nephos API `0.0.1`.

DNS, Cloudflare Tunnel, and TLS termination remain user-managed in Phase 1.

The route should exercise Nephos-owned route intent and Kubernetes-owned Ingress resources.

## Service Dependency Impact

The reference scenario must include dependency impact for shared Services.

Stopping PostgreSQL while Paperless depends on it should be blocked unless the operation is forced.

The impact list should explain that Paperless depends on PostgreSQL through a binding.

## Data Semantics

Stop/start must preserve data.

Remove must preserve persistent data and metadata.

Destroy deletes persistent data associated with the App lifecycle and requires destructive confirmation when persistent data exists.

Removing Paperless must preserve PostgreSQL app-scoped resources created for Paperless.

Destroying Paperless deletes PostgreSQL app-scoped resources created for Paperless after destructive confirmation.

The PostgreSQL Service instance itself must not be deleted as a side effect of stopping, removing, or destroying Paperless.

## Draft Manifest Rule

Canonical examples under `examples/` are still blocked until manifest validation plus command/status shape are stable enough and Fer approves promotion.

Draft manifest sketches may live under:

- `.agents/drafts/manifests/`

Current draft sketches:

- `.agents/drafts/manifests/catalog/apps/paperless/app.yaml`
- `.agents/drafts/manifests/catalog/services/postgres/service.yaml`

Draft manifests are non-canonical.

Draft manifests must not be treated as source of truth.

Do not infer concrete schema fields from draft manifests without a later schema decision.
