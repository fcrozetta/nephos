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

Internal ids use typed prefixes with UUID4 hex suffixes.

Examples:

- `appinst_<uuid4hex>`
- `svcinst_<uuid4hex>`
- `binding_<uuid4hex>`
- `domain_<uuid4hex>`
- `reconcile_<uuid4hex>`
- `status_<uuid4hex>`

Internal ids may appear in read payloads, dependency impact payloads, binding payloads, status payloads, and reconciliation payloads.

Do not use internal ids as the primary public path identity for installed Apps and Services.

## Read Resource Snapshots

Read payloads are domain snapshots, not raw database rows.

Installed App and Service snapshots include:

- `id`
- `slug`
- `kind`
- `lifecycle`
- catalog identity
- config summary
- relationship summaries
- `createdAt`
- `updatedAt`
- optional latest `status`

Installed App snapshots additionally include top-level:

- `catalogRef`
- `config`
- `bindings`
- `routes`
- `status`

App `bindings` entries use:

- `id`
- `alias`
- `capability`
- `serviceInstance`
- `status`

The nested `status` field in App binding entries is a compact object:

- `level`
- `reason`
- `message`
- `observedAt`

App `routes` entries use:

- `name`
- `visibility`
- `target`
- `canonicalUrl`
- `aliases`
- `status`

App route `target` is semantic and uses:

- `port`

The route target matches manifest intent and does not expose raw Kubernetes ingress backend shape by default.

Installed Service snapshots additionally include top-level:

- `catalogRef`
- `config`
- `provides`
- `dependents`
- `status`

Service `provides` entries use:

- `capability`
- optional `alias`
- optional `version`
- `bindingOutputTargets`

Service `dependents` entries use:

- `appInstance`
- `bindingId`
- `bindingAlias`
- `capability`
- `lifecycle`
- `status`

The nested `status` field in App route, Service provides, and Service dependent entries uses the same compact status object:

- `level`
- `reason`
- `message`
- `observedAt`

Bindings and platform domains expose their internal `id` plus their public or semantic identity.

Use camel case in API payloads.

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

`catalogRef.source` uses catalog source ids such as `default` or `local-1`.

`instanceName`, `config`, and `bindings` are optional where accepted defaults are available.

Do not use catalog install action endpoints as the primary API shape.

Do not install directly from arbitrary YAML paths as the primary API model.

## Catalog Boundary

The API reads local filesystem catalog manifests.

API 0.0.1 reads and validates catalog manifests on demand.

Installed records store catalog identity, optional version, catalog source id, catalog source path snapshot, and digest information.

Do not require catalog entries to be imported into SQLite before installation in Phase 1.

Do not install directly from arbitrary YAML paths as the default API model.

Install by catalog kind and name, plus optional explicit source when needed.

Custom catalog roots are backend local configuration for API 0.0.1, not platform desired state.

Additional local catalog roots are configured with `NEPHOS_API_CATALOG_ROOTS`.

Catalog source ids are:

- `default` for the repo-shipped catalog root
- `local-1`, `local-2`, `local-3` for configured local roots in configured order

Source ids are stable only for the current backend configuration and root order.

Read-only catalog endpoints are:

```text
GET /catalog/apps
GET /catalog/apps/{name}
GET /catalog/services
GET /catalog/services/{name}
```

Catalog detail endpoints accept optional `source` selection where duplicate catalog entries require disambiguation.

The catalog detail `source` query parameter uses the catalog source id.

Ambiguous duplicate entries return `409 Conflict` with code `catalog_entry_ambiguous`.

Unknown source ids return `404 Not Found` with code `catalog_source_not_found`.

Catalog endpoints are read-only in API 0.0.1.

Catalog list and detail responses return normalized catalog summaries by default.

Accepted catalog response fields:

- `kind`
- `name`
- `displayName`
- `description`
- `version`
- `source`
- `manifestDigest`
- capability summary
- route summary

Catalog responses expose source ids through `source` and do not expose raw filesystem paths by default.

App catalog summaries include `requires` and `routes`.

App catalog `requires` entries use:

- `capability`
- `alias`
- optional `provider`

If the manifest omits the binding alias, `alias` is defaulted from the capability.

App catalog `routes` entries use:

- `name`
- `visibility`
- `target`

Service catalog summaries include `provides`.

Service catalog `provides` entries use:

- `capability`
- optional `alias`
- optional `version`
- `bindingOutputTargets`

Do not return raw manifest blobs by default.

## Bindings

Bindings are first-class API/database resources.

A binding connects an App instance requirement alias to a Service instance capability.

Bindings are the source of dependent tracking.

Do not infer bindings only from Kubernetes Secret metadata.

Binding read payloads include:

- `id`
- `alias`
- `capability`
- `appInstance`
- `serviceInstance`
- redacted output or Secret summary
- `status`
- `createdAt`
- `updatedAt`

Redacted output or Secret summaries use:

- `target`
- `secretName`
- `namespace`
- `keys`
- `redacted`

`redacted` must be `true` when Secret-related output exists in the summary.

Binding output and Secret summaries must not expose secret values.

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

Destroy does not create a `destroying` lifecycle state.

The desired-state row remains present while teardown is pending and is deleted only after successful teardown.

Pending destroy is visible through reconciliation/action metadata and status.

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

Accepted status payload fields:

- `level`
- `lifecycle`
- `reconciliation`
- `reason`
- `message`
- `evidence`
- `observedAt`

`evidence` is an array of structured facts, not an unbounded raw Kubernetes dump.

Evidence entries use:

- `source`
- `subject`
- `reason`
- `message`
- `observedAt`
- optional redacted `data`

Evidence `data` is for small structured facts only.

Secret values must remain redacted in status payloads.

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

Accepted Phase 1 manual reconcile endpoints:

```text
POST /apps/{appInstance}/actions/reconcile
POST /services/{serviceInstance}/actions/reconcile
POST /bindings/{bindingId}/actions/reconcile
POST /platform/config/domains/actions/reconcile
```

Manual reconcile creates a reconciliation request and returns the normal mutation envelope.

It must not directly mutate Kubernetes inline.

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

Validation error normalization is explicitly deferred until after API 0.0.1.

## Scope

API 0.0.1 defines only the resources needed for the Paperless plus PostgreSQL reference flow.

Future backups, upgrades, auth/RBAC, resource profiles, remote catalogs, and generalized Service operation APIs are deferred.

API 0.0.1 has no rename API.

Installed App and Service slugs are immutable in API 0.0.1.

## Open Questions

None for API 0.0.1 response field shape.
