# Nephos Glossary

## App

A user-facing workload or product.

Examples:

- media systems
- source control platforms
- document management systems
- dashboards
- personal cloud applications
- AI applications

Apps may:

- expose routes/ingress
- persist data
- consume Services
- depend on capabilities
- be started/stopped independently
- be removed or destroyed

Apps are not shared infrastructure primitives.

## Service

A shared platform infrastructure component that exposes capabilities to Apps.

Examples:

- PostgreSQL
- Redis
- Object Storage
- Search engines
- Graph databases
- Queues
- SMTP
- Authentication providers
- AI inference backends

Services may:

- expose one or more capabilities
- provision app-scoped resources
- be shared by multiple Apps
- have dependency-aware lifecycle behavior

Do not call Services "plugins".

## Service Instance

An installed concrete Service.

A Service manifest defines an installable Service shape.

A Service instance is the installed platform/runtime instance of that Service.

Examples:

- `postgres-main`
- `redis-main`
- `neo4j-immich`

## Shared Service Instance

A Service instance intended to serve multiple Apps through separate bindings.

Shared Service instances are the default.

Where supported, a shared Service instance provisions app-scoped resources inside one runtime instance.

Example:

- one PostgreSQL Service instance with separate databases and users per App

## Dedicated Service Instance

A Service instance created because an App requests or requires isolation from a Service provider.

Dedicated Service instances are still first-class Services.

They may be explicitly bound by other Apps for integration.

Do not model dedicated Service instances as hidden App internals, embedded dependency containers, or Helm subcharts.

Use dedicated Service instance instead of app-private Service as the architecture term.

## Capability

A typed platform feature exposed by a Service and consumed by an App.

Examples:

- postgres
- sql
- redis
- s3
- graph-db
- document-db
- search
- kv
- smtp
- auth

Apps should depend on capabilities rather than concrete infrastructure whenever possible.

## Machine Identifier

A platform-visible technical name used by Nephos for manifests, routes, binding aliases, instance slugs, and catalog entry slugs.

Machine identifiers use strict DNS-label style:

```text
^[a-z0-9]([-a-z0-9]*[a-z0-9])?$
```

They use lowercase ASCII letters, digits, and hyphens.

They start and end with an alphanumeric character.

Nephos rejects invalid machine identifiers.

Do not silently normalize, truncate, suffix, or randomize machine identifiers.

## Instance Name

The Nephos desired-state name for an installed App instance or Service instance.

By default, an installed instance name equals the catalog manifest `metadata.name`.

Users may provide an explicit instance name at install time.

App instance names are unique within the App instance scope.

Service instance names are unique within the Service instance scope.

Generated runtime namespaces add prefixes:

- `app-<slug>`
- `svc-<slug>`

## Binding

A relationship between an App and a Service capability.

A binding represents how an App receives access to a capability.

Bindings are the source of dependent tracking between Apps and Service instances.

## Binding Alias

A stable semantic name for an App requirement binding.

App manifests may set a binding alias with `as`.

If `as` is omitted, the alias defaults to `capability`.

Binding aliases must be unique within one App manifest and one installed App instance after defaulting.

Example:

```yaml
spec:
  requires:
    - capability: postgres
      as: database
```

The alias in this example is `database`.

## Binding Output

A logical output produced by a Service binding and delivered to a consuming App.

Phase 1 supports one concrete binding output target:

- `app-secret`

`app-secret` means Nephos materializes binding credentials into the consuming App namespace as a Kubernetes Secret.

Service manifests declare logical binding outputs, not final consuming Secret names.

Nephos chooses deterministic Secret names from binding alias.

## Binding Secret

A Kubernetes Secret created by Nephos in a consuming App namespace to deliver binding credentials.

For Phase 1 `app-secret` outputs, the Secret name is:

```text
nephos-bind-<alias>
```

Example:

- binding alias `database`
- Secret name `nephos-bind-database`

Rebinding an alias to a different Service instance updates the same Secret name after explicit reconciliation or confirmation.

Binding Secrets must include:

```yaml
app.kubernetes.io/managed-by: nephos
nephos.pro/app-instance: <app-instance>
nephos.pro/service-instance: <service-instance>
nephos.pro/capability: <capability>
nephos.pro/binding-alias: <alias>
```

## App-Scoped Resource

A Service-side resource created for a consuming App inside a Service instance.

Examples:

- PostgreSQL database and user
- object storage bucket or prefix
- Redis logical database, prefix, or credential scope where supported

App-scoped resources are created through a typed provisioning contract.

They are not separate Apps or hidden Service instances.

Remove preserves app-scoped resources.

Destroy deletes app-scoped resources after destructive confirmation.

## Lifecycle State

The desired or historical lifecycle state of an entity.

Examples:

- installed
- running
- stopped
- disabled
- removed
- destroyed

Lifecycle state is separate from health status.

Removed and destroyed are lifecycle states, not health statuses.

## Health Status

An operational status that answers whether an entity that should be operating is operating correctly.

Accepted health status levels:

- `unknown`
- `pending`
- `healthy`
- `degraded`
- `blocked`
- `stopped`
- `not_applicable`

## Status Reason

An explanation for why an entity has a given health status.

Statuses must include reasons and/or evidence.

Do not expose opaque green/red status without explaining the cause.

## Nephos Manifest

A platform package definition for an App or Service.

Nephos manifests describe platform intent and relationships.

They are not Helm charts and are not raw Kubernetes manifests.

Nephos manifests may reference Helm charts or raw Kubernetes manifests as runtime deployment implementation details.

Nephos manifests are YAML documents with a Kubernetes-like envelope:

- `apiVersion`
- `kind`
- `metadata`
- `spec`

The envelope is for file structure and versioning.

It does not mean Nephos manifests are Kubernetes CRDs.

Accepted manifest API version:

- `nephos.pro/v1alpha1`

## App Manifest

A Nephos manifest that defines an installable App.

Accepted manifest `kind`:

- `App`

An App manifest focuses on user-facing workload concerns:

- required capabilities
- ingress or visibility intent
- storage intent
- config surface
- runtime deployment reference
- health/status expectations

## Config Option

A user-facing App configuration input declared by an App manifest.

Phase 1 config option types:

- `string`
- `integer`
- `boolean`
- `enum`

Config options use required `name` and `type`, plus optional `label`, `description`, `default`, and `required`.

The `name` field is the stable machine key.

The `label` field is display text.

`required` defaults to `false`.

Enum config options use object values with `value` and `label`.

`secret` is deferred as an App config option type.

Config options must not become a second credential path beside bindings and generated Service credentials.

Config options do not carry Helm value paths, environment variables, or Kubernetes field paths.

## Runtime Value Mapping

A mapping from Nephos semantic inputs to lower-level runtime deployment values.

Phase 1 source kinds:

- `config`
- `binding`

Mappings live under:

- `spec.runtime.values.mappings[]`

Mappings use explicit `from` and `to` objects.

The Phase 1 target is `to.helmValue`, a Helm value dot path.

Mappings are not declared inline on config options or binding declarations.

## Service Manifest

A Nephos manifest that defines an installable Service.

Accepted manifest `kind`:

- `Service`

A Service manifest focuses on shared infrastructure concerns:

- exposed capabilities
- supported binding types
- optional provisioning contracts
- optional Service operations
- backup/restore hooks or intent
- runtime deployment reference
- health/status expectations

## Runtime Deployment Reference

A reference from a Nephos manifest to the lower-level runtime deployment implementation.

Accepted Phase 1 deployment reference types:

- Helm chart
- raw Kubernetes manifests

Runtime deployment references are implementation details below the Nephos platform model.

## Catalog Entry

An available App or Service definition in a catalog.

Catalog entries are not installed instances.

Accepted local catalog layout:

- `catalog/apps/<app-slug>/app.yaml`
- `catalog/services/<service-slug>/service.yaml`

## Service Operation

A typed backend/API-owned management action exposed by a Service.

Examples:

- provision app-scoped resource
- deprovision app-scoped resource
- rotate credentials
- backup
- restore
- run health diagnostic
- create database
- create bucket or prefix

Service management action is an acceptable descriptive phrase, but Service operation is the canonical term.

Do not model Service operations as arbitrary user-facing shell scripts.

For Phase 1, Service operations are reserved but bounded:

- internal typed handlers may support required provisioning work
- a general user-facing Service operation API or CLI UX is not included
- canonical operation schemas and examples require a later explicit decision
