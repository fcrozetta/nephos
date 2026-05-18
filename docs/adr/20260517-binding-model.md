# Binding Model

- Status: accepted
- Date: 2026-05-17
- Tags: bindings, capabilities, services, apps

## Context and Problem Statement

The binding layer is the heart of Nephos.

Apps consume capabilities exposed by Services.

Nephos needs to define how an App requirement is resolved to a Service and how credentials/configuration are delivered.

## Decision

A binding connects an App requirement to a Service instance capability.

Apps declare capability requirements.

Services declare exposed capabilities and binding output behavior.

Nephos resolves App requirements to Service instances and stores the binding as platform desired state.

Bindings are the source of dependent tracking.

## Binding Outputs

Phase 1 supports one binding output target:

- `app-secret`

`app-secret` means Nephos materializes binding credentials into the consuming App namespace as a Kubernetes Secret.

Service manifests declare logical binding outputs.

They do not hardcode the final consuming Secret name.

Nephos chooses a deterministic Secret name from binding alias so reconciliation and debugging remain stable.

For `app-secret`, the Secret is created in the consuming App namespace with this name:

```text
nephos-bind-<alias>
```

The exact slug normalization for `<alias>` follows the future shared Nephos name/slug rules.

PostgreSQL binding outputs are capability-defined.

For PostgreSQL bindings, the accepted logical output fields are:

- `host`
- `port`
- `database`
- `username`
- `password`
- `uri`

Do not add a manifest `fields:` syntax for PostgreSQL binding outputs in Phase 1.

For PostgreSQL `app-secret` outputs, use these exact lowercase Kubernetes Secret keys:

- `host`
- `port`
- `database`
- `username`
- `password`
- `uri`

Runtime mappings may translate these keys into chart values or environment variables later.

## App Consumption

App manifests use symbolic binding aliases.

Example:

```yaml
spec:
  requires:
    - capability: postgres
      as: database
```

The alias gives the App a stable semantic name for the binding.

If `as` is omitted, the alias defaults to `capability`.

Aliases must be unique within one App manifest and one installed App instance after defaulting.

If an App needs more than one binding for the same capability, the App manifest must set explicit aliases.

Nephos maps binding outputs into runtime deployment values later through the accepted `spec.runtime.values.mappings[]` lane.

Phase 1 binding runtime mappings use:

```yaml
from:
  kind: binding
  name: database
  field: uri
to:
  helmValue: env.DATABASE_URL
```

The binding source `name` references the App binding alias.

The binding source `field` references a binding output field such as `uri`.

The binding mapping source shape may be revisited after a fuller Nephos manifest is evaluated.

Do not make Apps depend on Service namespace Secrets.

Do not expose raw Kubernetes Secret templates or raw environment variables as the primary Nephos manifest UX.

## Binding Secret Identity

An App binding Secret is identified by the App namespace and binding alias.

For Phase 1, the Secret name is:

```text
nephos-bind-<alias>
```

This means a Paperless App requirement declared as `as: database` receives binding credentials through `nephos-bind-database` in the Paperless App namespace.

Rebinding an alias to a different Service instance updates the same Secret name with new contents after explicit reconciliation or confirmation.

Rebinding does not create a new Secret name by default.

Binding Secrets must include metadata that identifies:

- App instance
- Service instance
- capability
- binding alias
- `managed-by=nephos`

The exact Kubernetes label and annotation key names remain open.

## Provisioning Modes

Phase 1 recognizes two provisioning modes:

- `app-scoped-resource`
- `none`

`app-scoped-resource` means the Service creates a resource for the consuming App inside the Service instance.

Examples:

- PostgreSQL database plus user
- object storage bucket or prefix
- Redis logical database, prefix, or credential scope where supported

`none` means no Service-side resource is created for the binding.

Nephos may still materialize connection details for the App when a binding exists.

Any other provisioning modes are deferred.

## Provisioning Contract

Provisioning is a typed Nephos backend/API-owned contract.

The contract should let a Service provider create, update, and deprovision app-scoped resources and return binding outputs.

Do not model provisioning as arbitrary user-facing shell scripts.

Do not make Helm hooks the product-level provisioning contract.

The concrete execution mechanism remains open.

## Deprovisioning Lifecycle

Removing an App preserves provisioned Service-side resources created for that App.

Destroying an App deletes provisioned Service-side resources created for that App after destructive confirmation.

For `none`, there is no Service-side provisioned resource to delete.

Binding materialized Secrets follow the accepted secret lifecycle:

- stop preserves Secrets
- remove preserves Secrets
- destroy deletes Secrets created for the destroyed entity after destructive confirmation when credentials or persistent data are involved

## Example

An App requires:

- postgres

An installed PostgreSQL Service exposes:

- postgres
- sql

Nephos resolves the requirement, provisions app-scoped database/user credentials, creates an App namespace Secret, and maps connection configuration into the App runtime.

## Open Questions

Need to define:

- required vs optional capabilities
- concrete engine preference
- exact shared slug normalization for binding aliases and Secret names
- exact Kubernetes label and annotation key names for binding Secret metadata
- future optional manifest syntax for binding output payload fields, if needed
- non-PostgreSQL Secret key serialization
- credential rotation
- whether apps can bind to multiple providers of the same capability
- provisioning execution mechanism
- idempotency and failure semantics for provisioning
- status/audit model for provisioning operations

## Consequences

Apps can depend on capabilities rather than concrete infrastructure whenever possible.

Service providers keep control over how app-scoped resources are created.

Credential delivery is simple enough for Phase 1 because Kubernetes Secrets are the only concrete target.

The model still leaves room for future external secret managers, mounted files, direct Service endpoints, or other output targets without changing the core binding relationship.

## Notes

Bindings are platform relationships, not just config injection.

Do not flatten bindings into environment variables only.

Do not make the CLI perform direct ad hoc Kubernetes mutation to create binding credentials.
