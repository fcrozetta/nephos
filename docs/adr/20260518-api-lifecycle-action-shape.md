# API Lifecycle Action Shape

- Status: accepted
- Date: 2026-05-18
- Tags: api, lifecycle, desired-state, reconciliation, phase-1

## Context and Problem Statement

API 0.0.1 needs concrete endpoint shapes for installing Apps and Services and for lifecycle actions.

The API must remain resource-oriented and desired-state based.

It must not become a thin mirror of CLI command spelling or raw Kubernetes mutation behavior.

Lifecycle actions need confirmation, force, dependency impact, and reconciliation request metadata.

`destroy` is especially sensitive because it deletes persistent data through reconciliation, not just an API row.

## Decision

Use resource creation endpoints for installation:

```text
POST /apps
POST /services
```

The request body uses `catalogRef` and carries the catalog reference, optional explicit source, instance name, config, and binding/provider choices.

Accepted App install shape:

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

Accepted Service install shape:

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

The catalog remains the source of available App and Service definitions, but install mutation belongs to the installed resource collection.

Do not put install mutation under catalog endpoints as the primary API shape.

Do not make arbitrary YAML path install the primary API shape.

Use action subresources for lifecycle operations:

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

Destroy is destructive platform intent with confirmation, possible force, dependency checks, data deletion semantics, and asynchronous reconciliation.

Use an explicit confirmation body for destroy.

Example shape:

```json
{
  "confirm": "destroy paperless",
  "force": false
}
```

Stopping, removing, or destroying a Service instance with dependents returns a blocked response with an impact list unless the request explicitly carries force.

Use HTTP `409 Conflict` for dependency-blocked lifecycle actions.

The blocked response should include the dependent Apps and the binding relationships that cause the block.

The caller may repeat the lifecycle action with `force: true` when force is allowed.

Mutating API calls that create desired-state changes should prefer `202 Accepted`.

The response shape is:

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

Repeated lifecycle requests to the same desired state should be idempotent.

When possible, Nephos should avoid duplicate reconciliation work and return the current resource plus no-op or existing pending reconciliation information.

It is acceptable to enqueue a reconcile request when needed to verify or converge runtime state.

## Considered Options

### Resource creation install endpoints

Use `POST /apps` and `POST /services`.

- Good, because installation creates installed resources.
- Good, because catalog entries remain templates rather than lifecycle owners.
- Good, because the CLI can still expose `nephos app install paperless` while calling the resource API.
- Bad, because the request body must carry a catalog reference rather than putting the catalog name in the URL.

### Catalog install action endpoints

Use endpoints such as `POST /catalog/apps/{name}/install`.

- Good, because it reads naturally from a CLI perspective.
- Bad, because mutation is owned by the catalog path even though the result is an installed App.
- Bad, because it blurs available catalog entries with installed desired-state resources.

### Lifecycle action subresources

Use `POST /apps/{appInstance}/actions/{action}` and equivalent Service paths.

- Good, because lifecycle operations are platform actions on installed resources.
- Good, because request bodies can carry confirmation and force semantics.
- Good, because the API can return reconciliation request metadata consistently.
- Bad, because action subresources are less pure REST than a simple `PATCH`.

### PATCH lifecycle field

Use `PATCH /apps/{appInstance}` with a desired lifecycle state field.

- Good, because lifecycle is desired state.
- Bad, because destructive actions need confirmation and impact semantics that do not fit a simple field update cleanly.
- Bad, because it makes `destroy` look like a normal property change.

### DELETE for destroy

Use `DELETE /apps/{appInstance}` or `DELETE /services/{serviceInstance}` for destroy.

- Good, because the HTTP verb looks destructive.
- Bad, because destroy needs an explicit confirmation body and possible force.
- Bad, because DELETE request bodies are awkward across clients and tooling.
- Bad, because destroy is not just deleting an API resource; it is destructive platform intent reconciled into runtime/data deletion.

## Consequences

Implementation should define request/response models for install and lifecycle actions.

The API can keep exact payload fields minimal in API 0.0.1, but endpoint ownership is accepted.

The CLI should map user-friendly commands to these resource endpoints instead of requiring API paths to mirror CLI syntax.

The exact resource and status snapshot schemas remain implementation details, but the response envelope is accepted.

Read payloads, status payloads, reconciliation request id format, and manual reconcile endpoint shape are refined by [API Read, Status, and Catalog Shape](20260522-api-read-status-and-catalog-shape.md).

Resource-specific response fields and status evidence object fields are refined by [API Response Field Details](20260522-api-response-field-details.md).

Nested App, Service, Binding, and catalog summary entry fields are refined by [API Nested Response Entry Fields](20260522-api-nested-response-entry-fields.md).

Validation error normalization is deferred beyond API 0.0.1 unless a later decision changes that.

## Open Questions

None for API 0.0.1 lifecycle response shape.
