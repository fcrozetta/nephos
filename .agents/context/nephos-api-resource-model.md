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

Public resource paths use installed instance slugs.

Examples:

```text
/apps/paperless
/services/postgres
```

Opaque UUIDs are not the primary public path identifiers in API 0.0.1.

## Install Endpoints

Install Apps and Services through installed resource collections:

```text
POST /apps
POST /services
```

The request body uses `catalogRef`.

App install shape:

```json
{
  "catalogRef": {
    "kind": "App",
    "name": "paperless",
    "source": "default"
  },
  "instanceName": "paperless",
  "config": {},
  "bindings": {}
}
```

Service install shape:

```json
{
  "catalogRef": {
    "kind": "Service",
    "name": "postgres",
    "source": "default"
  },
  "instanceName": "postgres",
  "config": {}
}
```

`catalogRef.source` is optional unless needed to disambiguate duplicate catalog entries.

`instanceName`, `config`, and `bindings` are optional where accepted defaults are available.

Do not use catalog install action endpoints as the primary API shape.

Do not install directly from arbitrary YAML paths as the primary API model.

## Catalog Boundary

The API reads local filesystem catalog manifests.

API 0.0.1 reads and validates catalog manifests on demand.

Installed records store catalog identity, optional version, source, and digest information.

Do not require catalog entries to be imported into SQLite before installation in Phase 1.

Do not install directly from arbitrary YAML paths as the default API model.

Install by catalog kind and name, plus optional explicit source when needed.

Custom catalog roots are backend local configuration for API 0.0.1, not platform desired state.

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

Lifecycle actions use action subresources:

```text
POST /apps/{appInstance}/actions/start
POST /apps/{appInstance}/actions/stop
POST /apps/{appInstance}/actions/remove
POST /apps/{appInstance}/actions/destroy

POST /services/{serviceInstance}/actions/start
POST /services/{serviceInstance}/actions/stop
POST /services/{serviceInstance}/actions/remove
POST /services/{serviceInstance}/actions/destroy
```

Keep `destroy` as `POST .../actions/destroy`, not `DELETE`.

Destroy requires an explicit confirmation body.

Lifecycle action bodies use one common shape:

```json
{
  "force": false,
  "confirm": "destroy paperless"
}
```

`force` is optional and defaults to `false`.

`confirm` is required only for `destroy`.

Stopping, removing, or destroying a Service instance with dependents returns `409 Conflict` with an impact list unless the request explicitly carries `force: true`.

Repeated lifecycle requests to the same desired state should be idempotent.

When possible, avoid duplicate reconciliation work and return the current resource plus no-op or existing pending reconciliation information.

## Status

Status is separate from lifecycle state.

API 0.0.1 should persist the latest status snapshot.

Status includes reasons and evidence.

Do not mix health/status into lifecycle fields.

## Reconciliation

Mutating API calls update desired state and create a persisted reconciliation request.

The API returns after the desired-state mutation and reconciliation request are committed.

The API should not wait for Kubernetes convergence before returning.

Mutating API calls should prefer `202 Accepted`.

Mutation responses use:

```json
{
  "resource": {},
  "reconciliation": {
    "id": "reconcile_...",
    "state": "pending"
  },
  "status": {}
}
```

`status` is optional.

The `reconciliation` object must include reconciliation request id and state.

A manual reconcile endpoint is allowed for debugging.

The primary effect of a mutating API call must not be direct Kubernetes mutation that bypasses desired state and reconciliation.

Reconciliation requests are persisted in SQLite.

API mutations that change desired state write the desired-state change and reconciliation request in one database transaction.

In-memory-only reconciliation queues are not the Phase 1 default.

Each reconciliation request targets one App instance, Service instance, binding, or platform domain configuration.

Accepted reconciliation request states:

- `pending`
- `running`
- `succeeded`
- `failed`
- `blocked`

Failures do not roll back desired state.

The reconciler updates request state and latest status snapshots with reasons and evidence.

Simple capped retry is intended, but automatic retry may be deferred from API 0.0.1 if it adds too much implementation weight.

## Errors

Nephos-owned domain errors use:

```json
{
  "error": {
    "code": "dependency_blocked",
    "message": "Service has dependent Apps.",
    "details": {}
  }
}
```

`details` is optional.

Dependency-blocked lifecycle errors use HTTP `409 Conflict`.

Dependency impact details include:

- `requiresForce`
- dependent App instance
- binding id
- binding alias
- capability

Accepted shape:

```json
{
  "error": {
    "code": "dependency_blocked",
    "message": "Service has dependent Apps.",
    "details": {
      "requiresForce": true,
      "dependents": [
        {
          "appInstance": "paperless",
          "bindingId": "binding_...",
          "bindingAlias": "database",
          "capability": "postgres"
        }
      ]
    }
  }
}
```

FastAPI/Pydantic framework validation errors may remain in their default framework shape for API 0.0.1.

Do not treat framework validation error shape as a stable Nephos product API.

## Scope

API 0.0.1 defines only the resources needed for the Paperless plus PostgreSQL reference flow.

Future backups, upgrades, auth/RBAC, resource profiles, remote catalogs, and generalized Service operation APIs are deferred.

## Open Questions

- exact status response schema
- exact manual reconcile endpoint shape
- exact catalog read/list endpoint shape
- exact resource snapshot schema
- exact reconciliation request id format
- future validation error normalization
- future rename behavior for installed instance slugs
