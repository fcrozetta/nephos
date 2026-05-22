# Nephos Open Questions

## Namespace Details

Question:

What exact namespace naming and metadata rules should Nephos use?

Accepted direction:

- one namespace per App instance
- one namespace per Service instance
- `nephos-system` for Nephos control-plane/runtime support components
- `app-<slug>` naming for Apps
- `svc-<slug>` naming for Services
- strict DNS-label style machine identifiers
- invalid slugs are rejected rather than silently normalized
- default installed instance names equal catalog manifest `metadata.name`
- explicit user-provided instance names are allowed at install time
- name collisions fail and require explicit input
- generated Kubernetes names must fit resource limits after prefixes are added
- namespaces should use `app.kubernetes.io/managed-by: nephos`
- App namespaces should use `nephos.pro/app-instance`
- Service namespaces should use `nephos.pro/service-instance`
- remove preserves namespaces
- destroy deletes namespaces by default after destructive confirmation when persistent data exists
- no default-deny NetworkPolicy in Phase 1

Need to decide:

- future NetworkPolicy model
- exact cross-namespace connection metadata in bindings

## Local Ingress And Exposure Details

Question:

What exact local hostname, wildcard domain, DNS, and TLS strategy should Nephos use?

Accepted direction:

- Traefik default for Phase 1 because K3s includes it
- Nephos owns route/visibility intent
- Kubernetes owns Ingress resources
- Phase 1 implements local visibility
- private, public, and tailnet visibility are reserved
- Cloudflare Tunnel and Tailscale automation are deferred
- manually configured Cloudflare Tunnel must work with Nephos local ingress
- multiple configured ingress root domains are supported
- exactly one ingress root domain is the default/canonical domain
- at least one root domain is required for generated route hosts
- ingress root domains are platform desired state in the Nephos API/database
- ingress root domains are managed through Nephos API/CLI platform configuration operations
- ingress root domains are not App manifest fields
- root domain config uses `name`, `domain`, and `default`
- `name` is a Nephos machine identifier
- `domain` is a DNS suffix
- domains reject URLs, paths, wildcards, schemes, and ports
- Nephos generates host rules for each configured root domain
- root domains are aliases for the same route intent, not separate Apps or routes
- default route host pattern is `<app-instance>.<root-domain>`
- non-default route host pattern is `<route>.<app-instance>.<root-domain>`
- path-based App routing is out of Phase 1
- Phase 1 Nephos-managed ingress is HTTP-only
- Cloudflare Tunnel or other user-managed systems may terminate TLS outside Nephos
- generated hostname collisions fail and require explicit route, App instance, or domain policy changes
- Services do not expose admin routes through Nephos ingress in Phase 1
- root domain operations are add, list, remove, and set default
- root domain API path is `/platform/config/domains`
- removing a root domain removes that domain's generated host aliases from reconciled ingress after explicit confirmation when existing routes use it
- Nephos setup creates initial platform configuration before Apps are installed
- setup includes at least one ingress root domain and exactly one default/canonical root domain
- App status shows canonical URL from the default root domain plus aliases from other root domains
- stopped Apps keep route intent and may keep runtime ingress
- remove/destroy remove runtime ingress

Need to decide:

- exact CLI command spelling for root domain operations
- whether setup is interactive, flag-driven, or both
- future Cloudflare adapter shape
- future Tailscale adapter shape

## Setup And Platform Config Commands

Question:

What exact CLI/API command shape should initialize and manage Nephos platform configuration?

Accepted direction:

- setup UX and command implementation belong in the separate `nephos-cli` repository
- setup command design is deferred until after Nephos API `0.0.1` is implemented
- setup creates initial platform configuration before Apps are installed
- setup includes at least one ingress root domain and exactly one default/canonical root domain
- backend may start with an empty database
- backend reports platform configuration as incomplete until setup creates required desired state
- ingress root domain operations are platform configuration operations, not App manifest fields

Need to decide later in the `nephos-cli` phase:

- exact setup command spelling
- whether setup is interactive, flag-driven, or both
- exact root domain command group spelling
- setup idempotency behavior
- App install behavior when setup is missing
- exact API paths used by broader CLI setup operations beyond root domain config

## API 0.0.1 Resource Model

Question:

What resources should API 0.0.1 expose?

Accepted direction:

- API 0.0.1 uses a REST-ish resource model
- installed Apps are represented internally as `AppInstance` records
- installed Services are represented internally as `ServiceInstance` records
- public API may expose installed App instances under `/apps`
- public API may expose installed Service instances under `/services`
- public resource paths use installed instance slugs, such as `/apps/paperless` and `/services/postgres`
- opaque UUIDs are not the primary public path identifiers in API 0.0.1
- install Apps and Services through `POST /apps` and `POST /services`
- install request body uses `catalogRef` and carries optional source, instance name, config, and binding/provider choices
- catalog endpoints are not the primary owner of install mutation
- catalog App and Service manifests are separate from installed instances
- bindings are first-class API/database resources
- root domain resources use `/platform/config/domains`
- root domain resources are ingress root domains, not generic DNS management
- lifecycle state is desired state
- active lifecycle states are `running`, `stopped`, and `removed`
- `destroyed` is terminal history or absent after deletion, not a normal active desired-state lifecycle value
- lifecycle actions use `POST /apps/{appInstance}/actions/{action}` and `POST /services/{serviceInstance}/actions/{action}`
- accepted action names are `start`, `stop`, `remove`, and `destroy`
- destroy remains `POST .../actions/destroy` with explicit confirmation, not plain `DELETE`
- Service lifecycle actions blocked by dependents return `409 Conflict` with an impact list unless forced
- lifecycle action body uses common optional fields `force` and `confirm`
- `force` defaults to `false`
- `confirm` is required only for `destroy`
- status is separate from lifecycle state
- API 0.0.1 should persist the latest status snapshot with reasons and evidence
- API reads local filesystem catalog manifests
- installed records store catalog identity, version when available, source, and manifest digest information
- mutating API calls update desired state and create a persisted reconciliation request
- mutating API calls return after desired state and the reconciliation request commit
- mutating API calls should prefer `202 Accepted`
- mutation responses use `{ resource, reconciliation, status? }`
- reconciliation response object must include reconciliation request id and state
- API does not wait for Kubernetes convergence before returning
- manual reconcile endpoint is allowed for debugging
- manual reconcile uses action subresources: `POST /apps/{appInstance}/actions/reconcile`, `POST /services/{serviceInstance}/actions/reconcile`, `POST /bindings/{bindingId}/actions/reconcile`, and `POST /platform/config/domains/actions/reconcile`
- reconciliation requests target one App instance, Service instance, binding, or platform domain configuration
- request states are `pending`, `running`, `succeeded`, `failed`, and `blocked`
- the reconciler writes latest status snapshots with reasons and evidence
- reconciliation request ids use `reconcile_<uuid4hex>`
- failures do not roll back desired state
- one serialized background worker is accepted initially
- simple capped retry is intended, but automatic retry may be deferred from API 0.0.1 if it adds too much implementation weight
- Nephos-owned domain errors use `{ error: { code, message, details? } }`
- dependency-blocked lifecycle errors use `409 Conflict` with impact details including required force flag, dependent App instance, binding id, binding alias, and capability
- FastAPI/Pydantic framework validation errors may remain in default framework shape for API 0.0.1
- read payloads are domain snapshots, not raw database rows
- installed App and Service snapshots include `id`, `slug`, `kind`, `lifecycle`, catalog identity, config summary, relationship summaries, `createdAt`, `updatedAt`, and optional latest `status`
- status payloads include `level`, `lifecycle`, `reconciliation`, `reason`, `message`, `evidence`, and `observedAt`
- status evidence is structured and must not be an unbounded raw Kubernetes dump
- catalog read endpoints are `GET /catalog/apps`, `GET /catalog/apps/{name}`, `GET /catalog/services`, and `GET /catalog/services/{name}`
- API 0.0.1 defines only resources needed for the Paperless plus PostgreSQL reference flow

Need to decide:

- exact resource-specific response fields beyond the accepted common snapshot shape
- exact status evidence object fields
- exact catalog list/read response field set
- future validation error normalization
- future rename behavior for installed instance slugs

## API Lifecycle Action Shape

Question:

What concrete HTTP shape should API 0.0.1 use for install and lifecycle actions?

Accepted direction:

- install mutation happens through `POST /apps` and `POST /services`
- install request body uses `catalogRef` and carries optional source, instance name, config, and binding/provider choices
- catalog install action endpoints are not the primary API shape
- arbitrary YAML path install is not the primary API shape
- lifecycle actions use `POST /apps/{appInstance}/actions/{action}` and `POST /services/{serviceInstance}/actions/{action}`
- accepted action names are `start`, `stop`, `remove`, and `destroy`
- destroy remains `POST .../actions/destroy`, not `DELETE`
- destroy requires explicit confirmation in the request body
- Service lifecycle actions blocked by dependents return `409 Conflict` with an impact list unless the request carries `force: true`
- callers may repeat blocked lifecycle actions with `force: true` when force is allowed
- mutating API calls should prefer `202 Accepted`
- mutation responses use `{ resource, reconciliation, status? }`
- `reconciliation` includes request id and state
- manual reconcile uses action subresources for App, Service, binding, and platform domain configuration targets
- read payloads are domain snapshots, not raw database rows
- installed App and Service snapshots include ids and slugs
- status payloads use the accepted structured status shape
- repeated lifecycle requests to the same desired state should be idempotent
- Nephos should avoid duplicate reconciliation work when possible, but may enqueue reconciliation when needed to verify or converge runtime state

Need to decide:

- exact resource-specific response fields beyond the accepted common snapshot shape
- exact status evidence object fields
- future validation error normalization
- future rename behavior for installed instance slugs

## API Payload And Error Shape

Question:

What request, response, path id, and error payload shapes should API 0.0.1 use?

Accepted direction:

- public resource paths use installed instance slugs
- examples are `/apps/paperless` and `/services/postgres`
- opaque UUIDs are not the primary public path identifiers in API 0.0.1
- install bodies use `catalogRef`
- App install shape uses `catalogRef`, optional `instanceName`, optional `config`, and optional `bindings`
- Service install shape uses `catalogRef`, optional `instanceName`, and optional `config`
- `catalogRef` contains `kind`, `name`, and optional `source`
- `catalogRef.source` is required only when needed to disambiguate duplicate catalog entries
- lifecycle action body uses common optional fields `force` and `confirm`
- `force` defaults to `false`
- `confirm` is required only for `destroy`
- mutation responses use `{ resource, reconciliation, status? }`
- `reconciliation` includes request id and state
- read resource payloads are domain snapshots with ids and slugs where applicable
- status payloads use the accepted structured status shape
- reconciliation request ids use `reconcile_<uuid4hex>`
- Nephos-owned domain errors use `{ error: { code, message, details? } }`
- dependency-blocked lifecycle errors use `409 Conflict`
- dependency impact details include `requiresForce`, dependent App instance, binding id, binding alias, and capability
- FastAPI/Pydantic framework validation errors may remain in their default framework shape for API 0.0.1
- default framework validation error shape is not stable Nephos product API

Need to decide:

- exact resource-specific response fields beyond the accepted common snapshot shape
- exact status evidence object fields
- future validation error normalization
- future rename behavior for installed instance slugs

## Database Desired-State Model

Question:

How should API 0.0.1 persist desired state?

Accepted direction:

- SQLite is the canonical Phase 1 desired-state database
- use plain SQL through a small repository/data-access layer
- do not introduce a full ORM for API 0.0.1
- use explicit SQL migration files
- before the first usable version, local development may destroy and recreate the database
- initial schema should live in `migrations/0000_initial.sql`
- forward-compatible migration discipline starts after the first usable version is established
- API 0.0.1 table families are `app_instances`, `service_instances`, `bindings`, `platform_domains`, `status_snapshots`, `reconciliation_requests`, and `schema_migrations`
- use normalized columns for core identity, relationship, lifecycle, and lookup fields
- use SQLite JSON text columns for snapshots and flexible payloads where useful
- validate JSON payloads at the API/domain boundary
- installed records store catalog identity and version information
- installed records should include catalog kind, catalog name, catalog version when available, catalog source path, and SHA-256 manifest digest
- do not store a full manifest snapshot by default
- store a full manifest snapshot only if implementation proves it is necessary for concrete behavior such as stable replay, import/export, or debugging
- do not recompute installed desired state only from current catalog files
- persist the latest status snapshot per resource
- status event/history storage is deferred
- reconciliation requests are persisted in SQLite
- domain/resource relationships use internal stable text ids
- internal ids use typed prefixes with UUID4 hex suffixes
- user-addressable installed resources use unique public slugs
- public API paths continue to use installed instance slugs
- core domain tables include `id`, `created_at`, and `updated_at`
- timestamps use app-generated UTC ISO strings with `Z`
- user-addressable domain tables additionally include unique `slug`
- enum-like state fields should use SQLite `CHECK` constraints
- SQLite foreign keys are enabled
- relationships are restrictive by default
- broad `ON DELETE CASCADE` is not used to implement Nephos lifecycle semantics
- destructive lifecycle deletes happen through explicit domain transactions
- JSON text columns are only for validated snapshots and flexible payloads
- authoritative relationships, lifecycle state, dependency tracking, and public identity are not hidden in generic JSON blobs
- `reconciliation_requests` keeps a minimal API 0.0.1 column set: `id`, `target_type`, `target_id`, `state`, `error`, `created_at`, and `updated_at`
- attempt counters, claimed timestamps, requested-by metadata, explicit backoff columns, and richer worker lease fields are deferred unless implementation proves they are needed before API 0.0.1 is usable
- `status_snapshots` stores one latest row per `resource_type` and `resource_id`
- `schema_migrations` uses `version TEXT PRIMARY KEY` and `applied_at TEXT`
- API mutations that change desired state write desired-state changes and reconciliation request in one database transaction
- destroy removes active desired-state rows
- API 0.0.1 does not require an audit/history table for destroyed resources

Need to decide:

- exact full column definitions
- exact indexes beyond required uniqueness
- exact migration runner command
- exact local reset command
- transaction retry and SQLite locking behavior
- exact status evidence object fields
- exact DB JSON payload fields beyond accepted API snapshot/status shape
- exact treatment of polymorphic target references in `status_snapshots` and `reconciliation_requests`
- additional reconciliation request columns beyond the accepted API 0.0.1 minimum
- exact request claiming and locking behavior, if/when queue leasing becomes necessary
- exact retry count, backoff, and polling/wakeup behavior

## Reconciliation Execution Model

Question:

How should API 0.0.1 execute reconciliation requests?

Accepted direction:

- API 0.0.1 uses an API-owned in-process background reconciler
- mutating API calls write desired-state changes and a reconciliation request in one database transaction
- API calls return after that transaction commits
- API calls do not wait for Kubernetes convergence
- reconciliation requests are persisted in SQLite
- each request targets one App instance, Service instance, binding, or platform domain configuration target
- request states are `pending`, `running`, `succeeded`, `failed`, and `blocked`
- reconciliation request ids use `reconcile_<uuid4hex>`
- API 0.0.1 keeps `reconciliation_requests` minimal with `id`, `target_type`, `target_id`, `state`, `error`, `created_at`, and `updated_at`
- attempt counters, claimed timestamps, requested-by metadata, explicit backoff columns, and richer worker lease fields are deferred unless implementation proves they are needed before API 0.0.1 is usable
- handlers must be idempotent and safe to retry
- one serialized background worker is the initial model
- serialized queueing is acceptable for the single-user local-first model beyond API 0.0.1 until real usage proves concurrency is needed
- simple capped retry is intended
- automatic retry may be deferred from API 0.0.1 if it adds too much implementation weight
- the reconciler writes latest status snapshots with reasons and evidence
- failures do not roll back desired state
- drift is detected and reported for Nephos-owned resources
- Nephos reconciles drift only when desired state is explicit or manual reconciliation is requested
- manual reconcile uses action subresources for App, Service, binding, and platform domain configuration targets
- Nephos does not mutate resources it does not own

Need to decide:

- exact additional `reconciliation_requests` columns beyond the accepted API 0.0.1 minimum, if any
- exact request claiming and locking behavior in SQLite, if/when queue leasing becomes necessary
- exact polling/wakeup mechanism
- exact retry count and backoff behavior
- whether automatic retry lands in API 0.0.1 or immediately after
- exact status evidence object fields for reconciliation evidence

## Secrets Details

Question:

What exact secret naming, labeling, rotation, and backup behavior should Nephos use?

Accepted direction:

- Kubernetes Secrets in Phase 1
- external secret managers deferred
- future secret managers may be modeled as Services
- Service-internal/admin secrets live in Service namespaces
- App binding credentials are materialized into App namespaces
- Apps should not read Service namespace Secrets directly
- Service manifests declare logical binding outputs, not final consuming Secret names
- Nephos chooses deterministic Secret names from binding alias
- `app-secret` Secret names use `nephos-bind-<alias>` in the consuming App namespace
- rebinding an alias to a different Service instance updates the same Secret name after explicit reconciliation or confirmation
- binding Secrets include `app.kubernetes.io/managed-by: nephos`, `nephos.pro/app-instance`, `nephos.pro/service-instance`, `nephos.pro/capability`, and `nephos.pro/binding-alias`
- stop/remove preserve Secrets
- destroy deletes Secrets for the destroyed entity
- secret values are redacted by default

Need to decide:

- rotation behavior
- whether/how secrets are included in Nephos state backup
- future explicit reveal command behavior
- external secret manager integration model
- non-PostgreSQL Secret key serialization
- binding credential materialization schemas beyond accepted PostgreSQL logical fields

## Manifest Schema Details

Question:

What are the concrete App and Service manifest schemas?

Accepted direction:

- YAML manifests
- `apiVersion: nephos.pro/v1alpha1`
- Kubernetes-like envelope with Nephos semantics:
  - `apiVersion`
  - `kind`
  - `metadata`
  - `spec`
- accepted manifest kinds are `App` and `Service`
- directory-per-entry catalog layout:
  - `catalog/apps/<app-slug>/app.yaml`
  - `catalog/services/<service-slug>/service.yaml`
- separate App and Service Nephos manifest formats
- Helm-primary runtime deployment references
- raw Kubernetes manifest fallback
- App manifests use `metadata.name`, optional `metadata.displayName`, optional `metadata.description`, optional `metadata.version`, `spec.requires[]`, `spec.routes[]`, `spec.config.options[]`, and `spec.runtime`
- `spec.requires[]` supports `capability`, optional `as`, and optional `provider`
- Service manifests use `metadata.name`, optional `metadata.displayName`, optional `metadata.description`, optional `metadata.version`, `spec.provides[]`, `spec.bindings.outputs[]`, `spec.provisioning.mode`, `spec.runtime`, and `spec.operations[]`
- `spec.provides[]` supports `capability`, optional `as`, and optional `version`
- `spec.bindings.outputs[]` starts with `target: app-secret`
- Phase 1 supports only `app-secret` as the binding output target
- PostgreSQL binding outputs use logical fields `host`, `port`, `database`, `username`, `password`, and `uri`
- Service manifests declare logical binding outputs, not final consuming Secret names
- Nephos chooses deterministic Secret names from binding alias
- Apps consume bindings through symbolic aliases such as `as: database`
- App binding aliases default to `capability` when `as` is omitted
- binding aliases must be unique within one App manifest and one installed App instance after defaulting
- `app-secret` Secret names use `nephos-bind-<alias>` in the consuming App namespace
- rebinding an alias to a different Service instance updates the same Secret name after explicit reconciliation or confirmation
- machine identifiers use strict DNS-label style and invalid identifiers are rejected
- default installed instance names equal catalog manifest `metadata.name`
- user-provided explicit instance names are allowed at install time
- name collisions fail and require explicit input
- generated Kubernetes names must fit resource limits after prefixes are added
- binding Secrets include `app.kubernetes.io/managed-by: nephos`, `nephos.pro/app-instance`, `nephos.pro/service-instance`, `nephos.pro/capability`, and `nephos.pro/binding-alias`
- Nephos maps binding outputs into runtime values through the reserved `spec.runtime.values.mappings[]` lane
- PostgreSQL binding output fields are capability-defined and do not use a manifest `fields:` syntax in Phase 1
- PostgreSQL `app-secret` outputs use exact lowercase Secret keys `host`, `port`, `database`, `username`, `password`, and `uri`
- Phase 1 config option types are `string`, `integer`, `boolean`, and `enum`
- config options use required `name` and `type`, plus optional `label`, `description`, `default`, and `required`
- config option `name` is the stable machine key
- config option `required` defaults to `false`
- enum config options use object values with `value` and `label`
- `secret` App config option type is deferred
- App config must not become a second credential path beside bindings and generated Service credentials
- arbitrary object and array config option values are not supported in Phase 1
- config validation bounds such as min/max/regex/length are deferred
- config options do not carry Helm value paths, environment variables, or Kubernetes field paths
- config runtime mapping happens through `spec.runtime.values.mappings[]`
- Phase 1 runtime mapping source kinds are `config` and `binding`
- config mappings use `from.kind: config`, `from.name`, and `to.helmValue`
- binding mappings use `from.kind: binding`, `from.name`, `from.field`, and `to.helmValue`
- binding source `name` references the App binding alias
- binding source `field` references a binding output field such as `uri`
- `helmValue` is a dot path in Phase 1
- mapping transforms are deferred
- missing mapping sources block reconciliation with a reason
- mappings live only under `spec.runtime.values.mappings[]`
- runtime mappings are not defined inline on config options or binding declarations
- Phase 1 provisioning modes are `app-scoped-resource` and `none`
- `app-scoped-resource` means the Service creates a resource for the consuming App inside the Service instance
- `none` means no Service-side resource is created for the binding
- provisioning is a typed backend/API-owned contract, not arbitrary user-facing shell
- remove preserves provisioned Service-side resources created for an App
- destroy deletes provisioned Service-side resources created for an App after destructive confirmation
- `spec.operations[]` is reserved
- App says it needs a capability, Service says it provides a capability, Nephos resolves and creates bindings outside the manifest
- routes declare identity/visibility/target, not full hostnames
- Nephos derives hostnames from App instance name, route name, visibility, and configured domain policy
- Phase 1 supports multiple configured ingress root domains with one default/canonical domain
- default route host pattern is `<app-instance>.<root-domain>`
- non-default route host pattern is `<route>.<app-instance>.<root-domain>`
- root domain config lives in platform desired state, not App manifests
- root domain config uses `name`, `domain`, and `default`
- domains reject URLs, paths, wildcards, schemes, and ports
- path-based App routing is out of Phase 1
- Phase 1 Nephos-managed ingress is HTTP-only
- Phase 1 installable catalog entries require `apiVersion`, `kind`, `metadata.name`, and `spec.runtime`
- App `spec.requires[]`, `spec.routes[]`, and `spec.config.options[]` default to empty lists
- Service `spec.provides[]` is required and must be non-empty
- Service `spec.provisioning.mode` is required and must be either `none` or `app-scoped-resource`
- `spec.operations[]` defaults to an empty list
- PostgreSQL Service `spec.bindings.outputs[]` must include an `app-secret` output
- unknown manifest fields are rejected once canonical schemas exist
- raw Kubernetes manifest fallback shape is deferred until first needed
- canonical examples remain blocked until manifest validation plus command/status shape are stable enough
- no schema file until Fer approves the concrete validation schema

Need to decide:

- binding output targets beyond `app-secret`
- non-PostgreSQL binding output payload schemas
- future optional binding output payload declaration syntax, if needed
- non-PostgreSQL Secret key serialization
- required/default behavior for Services that expose capabilities without binding outputs
- raw manifest runtime reference shape when first needed
- validation rules beyond unknown-field rejection
- future validation bounds such as min/max/regex/length
- route and storage mapping source kinds
- target path escaping, if Helm values need literal dots in keys
- mapping transforms, if capability outputs stop being sufficient
- whether to revise binding mapping source shape after seeing a fuller Nephos manifest
- command/status shape needed before promoting draft sketches into canonical examples

## Dedicated Service Sharing Policy Details

Question:

How should explicit sharing of dedicated Service instances work?

Accepted direction:

- dedicated Service instances are created because an App requests or requires isolation
- dedicated Service instances remain first-class Services
- other Apps may explicitly bind to a dedicated Service instance for integration
- Phase 1 reserves the concept and supports shared/global Service instances first

Need to decide:

- whether a dedicated Service instance has an owning/initiating App field
- whether explicit sharing requires owner confirmation
- whether dedicated instances advertise capabilities normally or behind a sharing flag
- whether default provider selection may choose a dedicated instance
- how backup/restore lifecycle works when several Apps bind to a dedicated instance
- how destroy impact lists represent initiating App vs later dependents

## Service Operation Contract

Question:

What is the concrete contract for Service operations?

Accepted direction:

- Service operation is the canonical term
- Service management action is only a descriptive phrase
- Service operations are reserved but bounded in Phase 1
- Service operations must be backend/API-owned and typed
- Service operations must not be arbitrary user-facing shell scripts
- Phase 1 may use internal typed Service handlers for minimal accepted provisioning work
- Phase 1 does not expose a general user-facing Service operation API or CLI UX
- canonical Service operation schemas and examples require later explicit approval

Need to decide:

- operation declaration format
- input/output schema
- API route shape
- CLI command shape
- execution model
- audit/status model
- permissions and safety prompts
- idempotency expectations
- relationship to binding lifecycle
- relationship to backup/restore lifecycle

## Future Catalog Source and Trust

Question:

How should non-local catalogs work after Phase 1?

Accepted direction:

- Phase 1 supports repo-shipped reference catalog entries
- Phase 1 supports user-configured local filesystem catalog paths
- user-created local catalog entries are allowed
- local catalog files are trusted local-owner input
- App and Service manifests carry minimal catalog metadata in Phase 1
- a separate catalog index is deferred

Deferred:

- Git repositories
- OCI artifacts or registries
- remote indexes
- signed catalogs
- private remote catalogs
- remote catalog trust policy
- package sandboxing guarantees

Need to decide:

- signing/verifying catalog entries
- private catalog credentials
- catalog versioning
- catalog update behavior
- remote catalog source format
- future separate catalog index format, if needed
- compatibility metadata

## Catalog And Manifest Loading

Question:

How should API 0.0.1 load and validate local catalog manifests?

Accepted direction:

- API 0.0.1 supports one repo-shipped catalog root
- API 0.0.1 supports optional configured local filesystem catalog roots
- custom catalog roots are backend local configuration for API 0.0.1, such as environment or backend config
- custom catalog roots are not platform desired state in SQLite for API 0.0.1
- catalog source management can move into platform configuration later by explicit decision
- API reads and validates catalog manifests on demand
- do not import all catalog entries into SQLite before use
- do not require a startup catalog index
- directory slug and manifest `metadata.name` must match
- do not silently normalize slug/name mismatches
- duplicate catalog entries with the same kind and name across configured roots are an error unless the caller explicitly selects a source
- do not let later roots silently override earlier roots
- validate manifests with typed Python/Pydantic domain models in API code first
- do not add canonical JSON Schema files under `schemas/` until Fer approves the concrete validation schema
- reject unknown manifest fields once canonical validation models exist
- install by catalog kind and name, plus optional explicit source when needed
- do not make arbitrary install-from-path the main API or UX flow
- store catalog kind, catalog name, catalog version when available, catalog source path or source identifier, and SHA-256 manifest digest at install time
- do not store a full manifest snapshot by default
- store a full manifest snapshot only if implementation proves it is necessary for concrete behavior such as stable replay, import/export, or debugging
- temporary draft manifests stay under `.agents/drafts/manifests/` and remain non-canonical until API validation models exist and Fer approves promotion
- `metadata.version` remains optional for catalog entries
- installed records store version if present and always store the manifest digest

Need to decide:

- exact backend config/env variable shape for custom local catalog roots
- exact source identifier format when more than one root is configured
- exact duplicate-entry error shape
- exact Pydantic/domain validation model names
- exact catalog list/read API response shape
- whether full manifest snapshots become necessary for stable replay, import/export, or debugging

## Draft Manifest Naming Details

Question:

What naming and cleanup conventions should temporary draft manifests use while Nephos is designing manifest schemas?

Accepted direction:

- temporary draft manifests are allowed during schema design
- temporary draft manifests live under `.agents/drafts/manifests/`
- they must be clearly marked non-canonical
- they must not live under `schemas/`
- they must not live under `examples/`
- they must not be treated as source of truth
- they must be deleted, moved, or converted after shape approval

Need to decide:

- naming convention
- cleanup policy after schema acceptance

## Backend and CLI Packaging

Question:

How should the backend and CLI be packaged and distributed?

Accepted direction:

- backend/control plane lives in `nephos`
- CLI lives in `../nephos-cli`
- backend Phase 1 distribution is local development process plus backend container image
- full installer packaging is deferred
- CLI workflow belongs to the separate CLI repository
- Phase 1 has backend/CLI version awareness without strict compatibility blocking

Need to decide:

- backend package layout
- backend container image strategy
- CLI installation path
- release process across the two repositories
- future strict compatibility matrix

## Local Development Workflow Details

Question:

What are the exact local development commands and conventions for Nephos?

Accepted direction:

- `uv` is the canonical backend Python workflow
- CLI points at local backend/API during development

Need to decide:

- exact `uv` commands
- whether to use Makefile/task runner wrappers
- how SQLite state is initialized/reset
- how migrations are run locally
- how K3s is started/reset for local development
- how `../nephos-cli` points to a local backend

## Testing Details

Question:

What exact test commands, tags, and CI boundaries should Nephos use?

Accepted direction:

- `pytest` for backend tests
- `ruff` for backend linting/formatting checks
- mocks/fakes for unit tests
- real K3s for Kubernetes integration tests
- CLI tests live in the separate CLI repository

Need to decide:

- exact test command names
- pytest marker names
- integration test setup/teardown
- whether CI runs K3s integration tests by default
- fixture strategy for Kubernetes clients
- coverage expectations

## Future Resource Profile Design

Question:

How should Nephos model resource profiles after Phase 1?

Accepted Phase 1 direction:

- no Nephos resource policy system
- replicas are `1` when running and `0` when stopped/disabled
- resource profiles are reserved but not defined
- raw Kubernetes CPU/memory knobs are not primary UX
- no HA/autoscaling/affinity/quotas

Need to decide later:

- profile names and semantics
- CPU/memory request and limit mapping
- Service-specific defaults
- App-specific defaults
- capacity warnings
- override model
- validation behavior

## Future Auth and RBAC Model

Question:

What auth model is needed after Phase 1?

Accepted Phase 1 direction:

- single-owner local-first
- trusted local CLI
- Web UI deferred
- no login/RBAC in Phase 1
- friend/cloud/multi-user scenarios are Phase 1 non-goals

Need to decide later:

- local-owner Web UI auth
- API bind/listen policy
- token model
- remote access model
- whether multi-user is ever needed
- whether roles/RBAC are needed

## Concrete Backup Implementation Design

Question:

What concrete backup/restore implementations should Nephos support after Phase 1?

Accepted Phase 1 direction:

- no concrete backup/restore implementation
- Nephos owns backup intent/policy/status
- Services own or provide data-aware implementations
- PVC snapshots are not universally sufficient for databases
- destroy requires destructive confirmation when persistent data exists

Need to decide later:

- first backup target
- database-native dump strategy
- object storage backup strategy
- PVC snapshot support
- filesystem/local storage backup strategy
- retention policy
- restore workflow
- backup status model
- backup-before-upgrade flow

## Upgrade Compatibility Design

Question:

How should Nephos validate upgrade compatibility after Phase 1?

Accepted Phase 1 direction:

- versions are pinned
- upgrades are explicit/manual
- no automatic latest
- Service upgrades with persistent data are risky by default
- rollback is best-effort, not guaranteed

Need to decide later:

- catalog compatibility metadata
- App/Service version constraints
- Service capability compatibility
- chart version compatibility
- preflight checks
- rollback metadata
- backup/checkpoint requirements

## Health And Status Check Implementation Details

Question:

How should Nephos implement concrete health/status checks after the Phase 1 minimum?

Accepted Phase 1 direction:

- Nephos-aware aggregate status
- Kubernetes readiness is an input, not the whole model
- lifecycle state is separate from health status
- removed/destroyed are lifecycle states
- backup status participates as `unsupported`
- status reasons/evidence are required

Need to decide later:

- exact status API shape
- status event/history model
- app-specific probe support
- Service-specific diagnostic support
- route reachability checks
- storage health checks
- backup status transitions
- how status affects exit codes in CLI
- how status renders in future Web UI

## Reference Scenario Exact Flow

Question:

What exact command spelling, status output, and manifest sketches should define the Paperless + PostgreSQL reference scenario?

Accepted direction:

- Paperless App
- PostgreSQL Service
- local filesystem catalog
- Nephos manifests
- Paperless requires only PostgreSQL in Phase 1 reference scenario
- capability binding
- PostgreSQL provisions an app-scoped database/user for Paperless
- Nephos materializes PostgreSQL binding outputs into Paperless App namespace
- Paperless binding Secret name follows `nephos-bind-<alias>`, for example `nephos-bind-database` when the alias is `database`
- default runtime namespaces are `app-paperless` and `svc-postgres` unless install-time instance names override them
- PostgreSQL binding fields are `host`, `port`, `database`, `username`, `password`, and `uri`
- basic ingress intent
- lifecycle install/start/stop/remove/destroy
- data preserved on stop/remove
- remove preserves app-scoped PostgreSQL resources and binding metadata
- destroy deletes app-scoped PostgreSQL resources created for Paperless after destructive confirmation
- destroy requires destructive confirmation when persistent data exists
- include Service dependency impact
- attempting to stop PostgreSQL while Paperless depends on it is blocked unless forced and shows an impact list
- use illustrative route examples such as `paperless.nephos.local` and `paperless.nephos.fcrozetta.app`

Need to decide:

- exact App manifest examples
- exact Service manifest examples
- exact commands
- expected status outputs
- exact CLI command spelling for root domain operations
- data preservation checks
