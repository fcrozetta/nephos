# Nephos Architecture

## High-Level Architecture

Nephos is a platform control plane over Kubernetes.

Architecture:

Nephos CLI
-> Nephos API
-> Nephos Controller / Reconciler
-> Kubernetes Runtime

The Web UI is deferred for Phase 1.

Default runtime backend:

- K3s

## Repository Boundaries

This repository, `nephos`, owns the backend control plane:

- API
- desired-state persistence
- reconciliation orchestration
- platform model
- catalog model
- architecture context and ADRs

The CLI is a separate repository:

- GitHub: `https://github.com/fcrozetta/nephos-cli`
- Local path: `../nephos-cli`

Do not add CLI implementation code to this repository without an explicit decision changing that boundary.

## Main Components

### CLI

The CLI is the primary early user interface.

The CLI is implemented in `../nephos-cli`.

The CLI talks to the Nephos API/local controller.

The CLI must not become an unstructured direct Kubernetes mutation layer.

Phase 1 has backend/CLI version awareness but no strict compatibility blocking.

The backend should expose a version endpoint.

The CLI should report CLI and backend versions and may warn on unknown/newer/older backend versions.

The CLI should not block state-mutating commands solely because of version mismatch in Phase 1.

Setup UX and command implementation belong in the separate CLI repository.

Nephos setup command design is deferred until after Nephos API `0.0.1` is implemented.

It should support:

- nephos cluster *
- nephos app *
- nephos service *

### API

The API should own platform intent.

The API/database is the canonical source of desired platform state.

Platform configuration that affects reconciliation, such as ingress root domains, lives in the API/database as desired state.

API 0.0.1 uses a REST-ish resource model.

Installed Apps are represented internally as `AppInstance` records and may be exposed publicly under `/apps`.

Installed Services are represented internally as `ServiceInstance` records and may be exposed publicly under `/services`.

Public API paths use installed instance slugs, such as `/apps/paperless` and `/services/postgres`.

Internal ids use typed prefixes with UUID4 hex suffixes.

Read payloads may include internal ids, but installed App and Service public paths still use slugs.

Read resource payloads are domain snapshots, not raw database rows.

Installed App and Service snapshots include common fields such as `id`, `slug`, `kind`, `lifecycle`, catalog identity, config summary, relationship summaries, `createdAt`, `updatedAt`, and optional latest `status`.

App snapshots include top-level `bindings` and `routes`.

Service snapshots include top-level `provides` and `dependents`.

Binding snapshots expose alias, capability, App instance, Service instance, redacted output or Secret summary, status, and timestamps.

Install mutation happens through `POST /apps` and `POST /services` with catalog references in the request body.

Install bodies use `catalogRef`, optional `instanceName`, optional `config`, and App install `bindings` when needed.

Lifecycle actions use `POST /apps/{appInstance}/actions/{action}` and `POST /services/{serviceInstance}/actions/{action}`.

Accepted lifecycle actions are:

- `start`
- `stop`
- `remove`
- `destroy`

Destroy remains a `POST` action with explicit confirmation, not a plain `DELETE`.

Lifecycle action bodies use optional `force` and `confirm`.

Bindings are first-class API/database resources connecting App instance requirement aliases to Service instance capabilities.

Ingress root domains are platform configuration resources at `/platform/config/domains`.

Read-only catalog endpoints are `/catalog/apps`, `/catalog/apps/{name}`, `/catalog/services`, and `/catalog/services/{name}` with optional `source` selection for duplicate catalog entries.

Catalog responses return normalized summaries, not raw manifest blobs by default.

Status is separate from lifecycle state and should persist the latest status snapshot with reasons and evidence.

Status payloads include `level`, `lifecycle`, `reconciliation`, `reason`, `message`, `evidence`, and `observedAt`.

Status evidence entries include `source`, `subject`, `reason`, `message`, `observedAt`, and optional redacted `data`.

Mutating API calls update desired state and create a persisted reconciliation request.

Mutating API calls return after the desired-state transaction and reconciliation request commit.

The API should not wait for Kubernetes convergence before returning.

Mutating API calls should prefer `202 Accepted`.

Mutation responses use `{ resource, reconciliation, status? }`.

Nephos-owned domain errors use `{ error: { code, message, details? } }`.

FastAPI/Pydantic framework validation errors may remain framework-shaped for API 0.0.1.

Dependency-blocked Service lifecycle actions should return `409 Conflict` with an impact list unless forced.

Manual reconcile uses target-specific action subresources such as `POST /apps/{appInstance}/actions/reconcile`.

API 0.0.1 has no rename API.

Installed App and Service slugs are immutable in API 0.0.1.

The backend may start with an empty database.

When required platform configuration is missing, the backend should report platform configuration as incomplete until setup creates the required desired state.

For Phase 1, the backend stack is:

- Python
- FastAPI
- SQLite
- simple explicit SQL migrations
- plain SQL through a small repository/data-access layer
- `uv` local development workflow
- `pytest` backend tests
- `ruff` backend linting/formatting checks

API 0.0.1 desired-state storage uses separate normalized table families for App instances, Service instances, bindings, platform domains, latest status snapshots, reconciliation requests, and schema migrations.

Database relationships use internal stable text ids.

Initial internal id format is a typed prefix plus UUID4 hex suffix.

Public API paths use unique installed instance slugs.

Core domain tables should include `id`, `created_at`, and `updated_at`.

Timestamps use app-generated UTC ISO strings with `Z`.

Use SQLite JSON text columns for snapshots and flexible payloads where useful, validated at the API/domain boundary.

JSON text columns must not hide authoritative relationships, lifecycle state, dependency tracking, or public identity.

Use SQLite `CHECK` constraints for accepted enum-like state fields and enable SQLite foreign keys.

Use restrictive relationships by default and implement destructive lifecycle deletes through explicit domain transactions, not broad cascades.

Status snapshots are stored as latest rows keyed by `resource_type` and `resource_id`.

API 0.0.1 reconciliation requests use the accepted minimal column set: `id`, `target_type`, `target_id`, `state`, `error`, `created_at`, and `updated_at`.

API mutations that change desired state must write desired-state changes and the reconciliation request in one database transaction.

Backend unit tests should use mocks/fakes.

Kubernetes integration tests should run against real K3s.

### Controller / Reconciler

The controller reconciles Nephos desired state into Kubernetes resources.

For Phase 1, the controller/reconciler is API-owned and in-process.

API 0.0.1 uses a background reconciler worker over persisted SQLite reconciliation requests.

Each reconciliation request targets one App instance, Service instance, binding, or platform domain configuration target.

Accepted reconciliation request states are:

- `pending`
- `running`
- `succeeded`
- `failed`
- `blocked`

The first implementation uses one serialized worker.

Reconciliation handlers must be idempotent and safe to retry.

Simple capped retry is the intended model, but automatic retry may be deferred from API 0.0.1 if it adds too much implementation weight.

Failures do not roll back desired state.

The reconciler writes latest status snapshots with reasons and evidence.

The reconciler should be isolated behind module boundaries so it can later move to a daemon, worker, or in-cluster controller.

Phase 1 should detect and report drift.

Nephos may reconcile Nephos-owned resources when desired state is explicit or manual reconciliation is requested, but must not mutate Kubernetes resources it does not own.

### Kubernetes Runtime

Kubernetes owns runtime execution.

It owns:

- scheduling
- networking primitives
- Deployments
- StatefulSets
- Services
- Ingress
- PVCs
- Secrets
- ConfigMaps
- Jobs
- CronJobs
- probes

Nephos should use Kubernetes, not reimplement it.

### Runtime Boundaries

Nephos uses separate Kubernetes namespaces for App instances, Service instances, and control-plane components.

Namespace pattern:

- `nephos-system`
- `app-<slug>`
- `svc-<slug>`

Slugs use strict DNS-label style machine identifiers.

Nephos rejects invalid or too-long generated names instead of silently normalizing, suffixing, randomizing, or truncating them.

Default installed instance names equal catalog manifest `metadata.name`.

Users may provide explicit instance names at install time.

App instance names and Service instance names are unique in separate scopes.

Nephos-managed Kubernetes resources use `app.kubernetes.io/managed-by: nephos` and Nephos-owned relationship metadata under `nephos.pro/*`.

Nephos does not use Kubernetes `ownerReferences` to represent platform relationships or lifecycle ownership in Phase 1.

`remove` preserves namespaces.

`destroy` deletes namespaces by default after destructive confirmation when persistent data exists.

Phase 1 does not enable default-deny NetworkPolicy.

Traefik is the Phase 1 default ingress controller because K3s includes it by default.

Nephos owns route and visibility intent.

Kubernetes owns concrete Ingress resources.

Phase 1 implements local visibility.

Public/private/tailnet exposure, Cloudflare Tunnel automation, Tailscale automation, DNS automation, and TLS automation are deferred.

Nephos-generated local ingress should be compatible with a manually configured Cloudflare Tunnel.

Phase 1 supports multiple configured ingress root domains with one default/canonical domain.

At least one root domain is required for generated route hosts.

Nephos generates host rules for each configured root domain.

Root domains are aliases for the same route intent, not separate Apps or separate routes.

Ingress root domains are platform desired state in the Nephos API/database and are managed through Nephos API/CLI platform configuration operations.

They are not App manifest fields.

Default route host pattern:

```text
<app-instance>.<root-domain>
```

Non-default route host pattern:

```text
<route>.<app-instance>.<root-domain>
```

Avoid path-based App routing in Phase 1.

Phase 1 Nephos-managed ingress is HTTP-only.

If generated hostnames collide, Nephos fails and requires explicit user input.

Services do not expose admin routes through Nephos ingress in Phase 1.

Nephos setup must create initial platform configuration before Apps are installed, including at least one ingress root domain and exactly one default/canonical root domain.

Phase 1 uses Kubernetes Secrets.

Service-internal/admin secrets live in Service namespaces.

App binding credentials are materialized into App namespaces.

Binding Secrets use `nephos-bind-<alias>` in the consuming App namespace.

Binding Secrets include metadata identifying App instance, Service instance, capability, and binding alias using:

```yaml
app.kubernetes.io/managed-by: nephos
nephos.pro/app-instance: <app-instance>
nephos.pro/service-instance: <service-instance>
nephos.pro/capability: <capability>
nephos.pro/binding-alias: <alias>
```

Secret values must be redacted in API responses, CLI output, status output, logs, and diagnostics by default.

## Catalog Layer

Nephos should have two catalogs:

- App Catalog
- Service Catalog

Apps declare required capabilities.

Services declare exposed capabilities.

Nephos resolves App requirements to installed or installable Services.

Phase 1 catalog source is local filesystem first.

Supported Phase 1 catalog sources are repo-shipped reference entries and user-configured local filesystem paths.

User-created local catalog entries are allowed in Phase 1, but there is no schema stability promise until the concrete validation schema is accepted.

Phase 1 treats local catalog files as trusted local-owner input.

Git, OCI, remote indexes, signed catalogs, private remote catalogs, and remote trust policy are deferred.

For Phase 1, App and Service manifests carry minimal catalog metadata.

A separate catalog index is deferred.

## Packaging Layer

Nephos uses separate Nephos manifest formats for Apps and Services.

Nephos manifests own platform semantics.

Nephos manifests are YAML documents using a Kubernetes-like envelope with Nephos semantics:

- `apiVersion`
- `kind`
- `metadata`
- `spec`

Accepted manifest kinds are `App` and `Service`.

Accepted manifest API version is `nephos.pro/v1alpha1`.

This does not make Nephos manifests Kubernetes CRDs.

Helm charts are the primary Phase 1 runtime deployment mechanism underneath Nephos manifests.

Raw Kubernetes manifests are a fallback runtime deployment mechanism.

Helm values and Kubernetes object specs must not become the primary Nephos UX.

Service manifests may expose optional Service operations.

Service operation is the canonical term for typed Service management actions.

Service operations are reserved but bounded in Phase 1.

Phase 1 may use internal typed Service handlers for minimal accepted provisioning work.

Phase 1 does not expose a general user-facing Service operation API or CLI UX.

Do not model Service operations as arbitrary shell commands, Helm hooks, Kubernetes jobs, or user-provided scripts exposed as product semantics.

## Binding And Provisioning Model

Apps declare required capabilities.

Services declare exposed capabilities and binding output behavior.

Bindings connect App requirements to Service instance capabilities.

Bindings live in Nephos desired state and are the source of dependent tracking.

Phase 1 supports `app-secret` as the only binding output target.

`app-secret` means Nephos materializes binding credentials into the consuming App namespace as a Kubernetes Secret.

Service manifests declare logical binding outputs, not final consuming Secret names.

Nephos chooses deterministic Secret names from binding alias.

If `as` is omitted in an App requirement, the binding alias defaults to `capability`.

Binding aliases must be unique within one App manifest and one installed App instance after defaulting.

For `app-secret`, Nephos creates the Secret in the consuming App namespace with this name:

```text
nephos-bind-<alias>
```

Rebinding an alias to a different Service instance updates the same Secret name with new contents after explicit reconciliation or confirmation.

For PostgreSQL bindings, the accepted logical output fields are:

- `host`
- `port`
- `database`
- `username`
- `password`
- `uri`

These fields are capability-defined.

Do not add a manifest `fields:` syntax for PostgreSQL outputs in Phase 1.

For PostgreSQL `app-secret` outputs, use exact lowercase Kubernetes Secret keys:

- `host`
- `port`
- `database`
- `username`
- `password`
- `uri`

Phase 1 recognizes two provisioning modes:

- `app-scoped-resource`
- `none`

Provisioning is a typed backend/API-owned contract.

Do not model provisioning as arbitrary user-facing shell scripts.

Remove preserves provisioned Service-side resources created for an App.

Destroy deletes provisioned Service-side resources created for an App after destructive confirmation.

## Manifest Field Requirements

For Phase 1 installable catalog entries, every App and Service manifest requires:

- `apiVersion`
- `kind`
- `metadata.name`
- `spec.runtime`

Future imported, external, or pre-existing Services may need a different runtime shape, but that requires a later explicit decision.

For Phase 1 App manifests, these fields default to empty lists:

- `spec.requires[]`
- `spec.routes[]`
- `spec.config.options[]`

Phase 1 App config option types are:

- `string`
- `integer`
- `boolean`
- `enum`

Config options use required `name` and `type`, plus optional `label`, `description`, `default`, and `required`.

Config option `name` is the stable machine key.

Config option `required` defaults to `false`.

Enum config options use object values with `value` and `label`.

The `secret` App config option type is deferred.

App config must not become a second credential path beside bindings and generated Service credentials.

Config validation bounds such as min/max/regex/length are deferred.

Config options do not carry Helm value paths, environment variables, or Kubernetes field paths.

Config runtime mapping happens through `spec.runtime.values.mappings[]`.

Phase 1 runtime mapping source kinds are:

- `config`
- `binding`

Runtime mappings use explicit `from` and `to` objects.

Config mappings use `from.kind: config`, `from.name`, and `to.helmValue`.

Binding mappings use `from.kind: binding`, `from.name`, `from.field`, and `to.helmValue`.

The `helmValue` target is a dot path in Phase 1.

Mappings have no transforms in Phase 1.

Missing mapping sources block reconciliation with a reason.

Mappings live only under `spec.runtime.values.mappings[]`.

For Phase 1 Service manifests:

- `spec.provides[]` is required and must be non-empty.
- `spec.provisioning.mode` is required and must be either `none` or `app-scoped-resource`.
- `spec.operations[]` defaults to an empty list.

For the Phase 1 PostgreSQL Service, `spec.bindings.outputs[]` must include an `app-secret` output.

Once canonical schemas exist, unknown manifest fields are rejected.

Raw Kubernetes manifest fallback shape is deferred until Nephos needs a raw-manifest package.

## Service Ownership Model

Installed concrete Services are Service instances.

Services are shared by default.

Shared Service instances are expected to serve multiple Apps through bindings.

Where supported, a shared Service instance should provision app-scoped resources inside one runtime instance.

Example:

- one PostgreSQL Service instance
- separate database/user per App
- separate binding per App requirement

Apps may request isolation from a Service provider.

An isolation request creates a dedicated Service instance when required or explicitly requested.

Dedicated Service instances are still first-class Services.

Dedicated Service instances may be explicitly bound by other Apps when integration between Apps requires access to the same provider.

Phase 1 supports shared/global Service instances first and reserves dedicated Service instances as a concept.

Multiple Service instances may expose the same capability.

If exactly one eligible Service instance exposes a required capability, Nephos may auto-bind by default.

If multiple eligible Service instances expose a required capability and no default provider is configured, Nephos must require explicit selection.

Nephos may support a user-configurable default provider per capability.

Bindings are the source of dependent tracking.

Stopping, removing, or destroying a Service instance with dependents must require explicit force and show an impact list.

## State Model

Nephos owns desired platform state.

The canonical state path is:

intent -> API/database desired state -> reconciler -> Kubernetes runtime state

YAML is import/export only.

Kubernetes CRDs and GitOps-as-source-of-truth are deferred until explicit future decisions.

## Resource Policy

Phase 1 does not implement a Nephos resource policy system.

Running Apps and Services use replicas `1`.

Stopped or disabled Apps and Services use replicas `0`.

Resource profiles are reserved for future design but not defined.

Nephos does not expose raw Kubernetes CPU/memory requests and limits as primary UX in Phase 1.

No HA, autoscaling, affinity, anti-affinity, quotas, or scheduling policy are supported in Phase 1.

## Auth Model

Phase 1 is single-owner and local-first.

The CLI is a trusted local client.

No login, multi-user model, roles, or RBAC are required in Phase 1.

The Web UI is deferred.

Friend, cloud, hosted, and multi-user scenarios are out of scope for Phase 1 but not forbidden forever.

## Development And Distribution

This repository owns backend/control-plane development workflow.

The CLI repository owns CLI linting, testing, packaging, and release workflow.

Phase 1 backend distribution is a local development process plus backend container image.

Full installer packaging is deferred.
