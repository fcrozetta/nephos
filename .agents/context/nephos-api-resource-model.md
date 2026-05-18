# Nephos API Resource Model

API 0.0.1 uses a REST-ish resource API.

The API/database is the canonical desired-state source.

Kubernetes is runtime state.

Lifecycle operations modify desired state and trigger reconciliation.

Do not model API 0.0.1 as a direct CLI-command mirror or raw Kubernetes mutation layer.

## Primary Resources

API 0.0.1 primary resources:

- installed Apps
- installed Services
- bindings
- platform configuration domains
- status

Installed Apps are represented internally as `AppInstance` records.

Installed Services are represented internally as `ServiceInstance` records.

The public API may expose installed App instances under `/apps`.

The public API may expose installed Service instances under `/services`.

Catalog App and Service manifests are separate from installed instances.

## Catalog Boundary

The API reads local filesystem catalog manifests.

Installed records store catalog identity and version snapshot information.

Do not require catalog entries to be imported into SQLite before installation in Phase 1.

Do not install directly from arbitrary YAML paths as the default API model.

## Bindings

Bindings are first-class API/database resources.

A binding connects an App instance requirement alias to a Service instance capability.

Bindings are the source of dependent tracking.

Do not infer bindings only from Kubernetes Secret metadata.

## Platform Domains

Ingress root domains are platform configuration resources in the API/database.

Accepted Phase 1 API path:

```text
/platform/config/domains
```

These are Nephos ingress root domain resources, not generic DNS-management resources.

## Lifecycle

Lifecycle state is desired state.

Active lifecycle states for API 0.0.1:

- `running`
- `stopped`
- `removed`

`destroyed` is terminal history or absent after deletion.

It is not a normal active desired-state lifecycle value.

## Status

Status is separate from lifecycle state.

API 0.0.1 should persist the latest status snapshot.

Status includes reasons and evidence.

Do not mix health/status into lifecycle fields.

## Reconciliation

Mutating API calls update desired state and trigger or enqueue reconciliation.

A manual reconcile endpoint is allowed for debugging.

The primary effect of a mutating API call must not be direct Kubernetes mutation that bypasses desired state and reconciliation.

## Scope

API 0.0.1 defines only the resources needed for the Paperless plus PostgreSQL reference flow.

Future backups, upgrades, auth/RBAC, resource profiles, remote catalogs, and generalized Service operation APIs are deferred.

## Open Questions

- exact HTTP method and sub-action shape for lifecycle operations
- exact status response schema
- exact manual reconcile endpoint shape
- exact catalog read/list endpoint shape
- exact error envelope and validation response shape
