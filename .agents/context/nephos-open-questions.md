# Nephos Open Questions

## Alpha Backbone Binding Output Details

Question:

What exact binding output fields, Secret key names, status evidence, and Service
surface route fields should the non-PostgreSQL alpha backbone Services use?

Accepted direction:

- alpha backbone Service order is PostgreSQL, Zitadel, SeaweedFS, ArcadeDB, then the first dogfood App
- Pulumi is the runtime path
- Aspire is out of scope
- Helm may be used underneath Pulumi-backed Service providers when it is the easiest Service install path
- Helm charts do not define Nephos Service behavior
- binding provider matching is `capability + protocol`
- PostgreSQL provides `sql/postgres`
- ArcadeDB provides `sql/arcadedb`, `opencypher/bolt`, `opencypher/n4j`, optional `gremlin/gremlin`, and optional `mongo/mongo` when enabled
- SeaweedFS provides `object-storage/s3`
- Zitadel provides `oidc/oidc` and `service-account/jwt`
- Zitadel login/admin UI are Service surfaces/routes, not a separate App

Need to decide:

- exact OIDC client binding output fields and Secret key names
- exact Zitadel service-account/JWT binding output fields and Secret key names
- exact SeaweedFS S3 binding output fields and Secret key names
- exact ArcadeDB binding output fields and Secret key names per protocol
- default enablement policy for optional ArcadeDB `gremlin/gremlin` and `mongo/mongo`
- Service-surface route shape for Zitadel login/admin UI
- whether generic Service surfaces need a shared response shape before the first implementation

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

- Traefik may be the Phase 1 default ingress controller
- Traefik does not provide local DNS resolution
- local browser testing without `/etc/hosts` needs a resolvable suffix such as `nephos.localhost`
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
- installed records store catalog identity, version when available, catalog source id, catalog source path snapshot, and manifest digest information
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
- App snapshots include top-level `catalogRef`, `config`, `bindings`, `routes`, and `status`
- App `bindings` entries use `id`, `alias`, `capability`, `serviceInstance`, and `status`
- nested response entry `status` fields use compact objects with `level`, `reason`, `message`, and `observedAt`
- App `routes` entries use `name`, `visibility`, `target`, `canonicalUrl`, `aliases`, and `status`
- App route `target` uses semantic `{ port }`
- Service snapshots include top-level `catalogRef`, `config`, `provides`, `dependents`, and `status`
- Service `provides` entries use `capability`, optional `alias`, optional `version`, and `bindingOutputTargets`
- Service `dependents` entries use `appInstance`, `bindingId`, `bindingAlias`, `capability`, `lifecycle`, and `status`
- Binding snapshots include `id`, `alias`, `capability`, `appInstance`, `serviceInstance`, redacted output or Secret summary, `status`, `createdAt`, and `updatedAt`
- Binding redacted output or Secret summaries use `target`, `secretName`, `namespace`, `keys`, and `redacted: true`
- status payloads include `level`, `lifecycle`, `reconciliation`, `reason`, `message`, `evidence`, and `observedAt`
- status evidence is structured and must not be an unbounded raw Kubernetes dump
- status evidence entries include `source`, `subject`, `reason`, `message`, `observedAt`, and optional redacted `data`
- catalog read endpoints are `GET /catalog/apps`, `GET /catalog/apps/{name}`, `GET /catalog/services`, and `GET /catalog/services/{name}`
- catalog responses return normalized summaries with `kind`, `name`, `displayName`, `description`, `version`, `source`, `manifestDigest`, capability summary, and route summary
- App catalog summaries include `requires` and `routes`
- App catalog `requires` entries use `capability`, `alias`, and optional `provider`
- App catalog `routes` entries use `name`, `visibility`, and `target`
- Service catalog summaries include `provides`
- Service catalog `provides` entries use `capability`, optional `alias`, optional `version`, and `bindingOutputTargets`
- catalog responses do not return raw manifest blobs by default
- validation error normalization is deferred until after API 0.0.1
- API 0.0.1 has no rename API
- installed App and Service slugs are immutable in API 0.0.1
- API 0.0.1 defines only resources needed for the Paperless plus PostgreSQL reference flow

Need to decide:

- none for API 0.0.1 response field shape

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
- App snapshots include top-level `bindings` and `routes`
- App binding and route nested entry fields are accepted
- Service snapshots include top-level `provides` and `dependents`
- Service provides and dependent nested entry fields are accepted
- Binding snapshots are exposed directly with redacted output or Secret summary
- Binding output or Secret summary fields are accepted and always redacted
- nested response entry `status` fields use compact objects with `level`, `reason`, `message`, and `observedAt`
- App route `target` uses semantic `{ port }`
- catalog nested summary fields are accepted
- status payloads use the accepted structured status shape
- API 0.0.1 has no rename API and installed slugs are immutable
- repeated lifecycle requests to the same desired state should be idempotent
- Nephos should avoid duplicate reconciliation work when possible, but may enqueue reconciliation when needed to verify or converge runtime state

Need to decide:

- none for API 0.0.1 lifecycle response shape

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
- App, Service, and Binding response field groups are accepted
- nested App, Service, Binding, and catalog summary fields are accepted
- status payloads use the accepted structured status shape
- status evidence entries use `source`, `subject`, `reason`, `message`, `observedAt`, and optional redacted `data`
- reconciliation request ids use `reconcile_<uuid4hex>`
- Nephos-owned domain errors use `{ error: { code, message, details? } }`
- dependency-blocked lifecycle errors use `409 Conflict`
- dependency impact details include `requiresForce`, dependent App instance, binding id, binding alias, and capability
- FastAPI/Pydantic framework validation errors may remain in their default framework shape for API 0.0.1
- default framework validation error shape is not stable Nephos product API
- validation error normalization is deferred until after API 0.0.1
- nested response entry `status` fields use compact objects with `level`, `reason`, `message`, and `observedAt`
- App route `target` uses semantic `{ port }`
- catalog nested summary fields are accepted

Need to decide:

- none for API 0.0.1 payload and response shape

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
- initial migration contains all API 0.0.1 tables and accepted constraints
- do not create schema imperatively in Python
- forward-compatible migration discipline starts after the first usable version is established
- API 0.0.1 table families are `app_instances`, `service_instances`, `bindings`, `platform_domains`, `status_snapshots`, `reconciliation_requests`, and `schema_migrations`
- `app_instances` and `service_instances` use explicit catalog identity, lifecycle, generation, config, pending destroy, and timestamp columns
- `bindings` use explicit App/Service relationship, alias, capability, generation, output summary, and timestamp columns
- `platform_domains` use one row per root domain with `name`, `domain`, `is_default`, generation, and timestamps
- `status_snapshots` use target identity, status fields, `evidence_json`, `observed_generation`, `observed_at`, and timestamps
- `reconciliation_requests` use target identity, `target_generation`, `action`, `payload_json`, `target_snapshot_json`, state/error, and timestamps
- accepted indexes and uniqueness rules include unique App slugs, unique Service slugs, unique binding alias per App, one default platform domain, one latest status row per target, and reconciliation queue lookup by `state` and `created_at`
- use normalized columns for core identity, relationship, lifecycle, and lookup fields
- use SQLite JSON text columns for snapshots and flexible payloads where useful
- validate JSON payloads at the API/domain boundary
- installed records store catalog identity and version information
- installed records should include catalog kind, catalog name, catalog version when available, catalog source id, catalog source path snapshot, and SHA-256 manifest digest
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
- desired-state domain rows include integer `generation`
- increment `generation` on desired-state mutation
- timestamps use app-generated UTC ISO strings with `Z`
- user-addressable domain tables additionally include unique `slug`
- enum-like state fields should use SQLite `CHECK` constraints
- SQLite foreign keys are enabled
- SQLite uses WAL mode for API 0.0.1
- relationships are restrictive by default
- broad `ON DELETE CASCADE` is not used to implement Nephos lifecycle semantics
- destructive lifecycle deletes happen through explicit domain transactions
- JSON text columns are only for validated snapshots and flexible payloads
- authoritative relationships, lifecycle state, dependency tracking, and public identity are not hidden in generic JSON blobs
- `reconciliation_requests` include `id`, `target_type`, `target_id`, `target_generation`, `action`, `payload_json`, `target_snapshot_json`, `state`, `error`, `created_at`, and `updated_at`
- target snapshots are used when cleanup or retry cannot safely depend only on the current desired-state row
- attempt counters, claimed timestamps, requested-by metadata, explicit backoff columns, and richer worker lease fields are deferred unless implementation proves they are needed before API 0.0.1 is usable
- `status_snapshots` stores one latest row per `resource_type` and `resource_id`
- `schema_migrations` uses `version TEXT PRIMARY KEY` and `applied_at TEXT`
- backend-local init command is `uv run nephos-api init`
- init ensures one default internal platform domain, defaulting to `nephos.local`
- backend-local migration command is `uv run nephos-api db migrate`
- backend-local reset command is `uv run nephos-api db reset --force`
- backend bootstrap config uses environment variables for API 0.0.1, with `.env` loading allowed for local development and manual testing
- `NEPHOS_API_DB_PATH` sets the SQLite database path
- default SQLite path is `.nephos/state/nephos.db`
- migration runner applies pending `*.sql` files in lexical filename order
- migration version is the filename stem, such as `0000_initial`
- migration runner records versions only after successful execution
- dirty or inconsistent migration state fails instead of automatic repair
- rollback and downgrade commands are out of API 0.0.1
- SQLite connections use `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, and `PRAGMA busy_timeout=5000`
- no app-level SQLite write retry logic in API 0.0.1
- API mutations that change desired state write desired-state changes and reconciliation request in one database transaction
- destroy keeps the desired-state row present while teardown is pending
- do not add `destroying` as a lifecycle state
- after successful teardown, destroy removes active desired-state rows
- API 0.0.1 does not require an audit/history table for destroyed resources

Need to decide:

- exact DB JSON payload fields beyond accepted API snapshot/status shape
- exact target snapshot JSON fields
- exact request claiming behavior, if/when queue leasing becomes necessary
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
- API 0.0.1 reconciliation requests include durable action context with `target_generation`, `action`, `payload_json`, and `target_snapshot_json`
- attempt counters, claimed timestamps, requested-by metadata, explicit backoff columns, and richer worker lease fields are deferred unless implementation proves they are needed before API 0.0.1 is usable
- handlers must be idempotent and safe to retry
- one serialized background worker is the initial model
- API 0.0.1 uses one API process and one serialized reconciler with short explicit SQLite transactions
- serialized queueing is acceptable for the single-user local-first model beyond API 0.0.1 until real usage proves concurrency is needed
- simple capped retry is intended
- automatic retry may be deferred from API 0.0.1 if it adds too much implementation weight
- the reconciler writes latest status snapshots with reasons and evidence
- reconciliation and status records may record target or observed desired-state generation
- failures do not roll back desired state
- destroy keeps the desired-state row present while teardown is pending and deletes it only after successful teardown
- drift is detected and reported for Nephos-owned resources
- Nephos reconciles drift only when desired state is explicit or manual reconciliation is requested
- manual reconcile uses action subresources for App, Service, binding, and platform domain configuration targets
- Nephos does not mutate resources it does not own

Need to decide:

- exact target snapshot JSON fields
- exact request claiming behavior in SQLite, if/when queue leasing becomes necessary
- exact polling/wakeup mechanism
- exact retry count and backoff behavior
- whether automatic retry lands in API 0.0.1 or immediately after
- exact status evidence `data` payloads for reconciliation evidence

## Secrets Details

Question:

What exact secret naming, labeling, rotation, backup, and 1Password-backed source-of-truth behavior should Nephos use?

Accepted direction:

- Kubernetes Secrets remain the Phase 1 runtime materialization mechanism
- 1Password is the accepted operator-owned source of truth for LCL bootstrap and runtime-support secrets
- `nephos-lcl`, `nephos-dev`, and `nephos-prd` are separate environment vaults
- only LCL is currently disposable/repopulate-safe
- vaults are environment boundaries
- items are Service/App secret bundles
- fields are concrete credentials, tokens, connection strings, or files
- tags/folders are organization only and not security boundaries
- service account/CLI bootstrap uses the official `OP_SERVICE_ACCOUNT_TOKEN` variable
- Nephos desired state may store 1Password references such as `op://nephos-lcl/postgres-admin/password` or equivalent structured metadata
- Nephos desired state, status, logs, and diagnostics must not store or expose resolved secret values
- Apps do not read directly from 1Password in Phase 1
- future 1Password Connect/Kubernetes Operator integration should be modeled as a Nephos core Service/capability provider
- Service-internal/admin secrets live in Service namespaces when materialized into Kubernetes
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

- rotation behavior for 1Password-backed and Kubernetes-materialized secrets
- whether/how 1Password-backed secrets are represented in Nephos backup status
- future explicit reveal/debug command behavior
- exact future `onepassword-connect` Service manifest and provider shape
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
- Helm chart runtime packaging references underneath Nephos manifests
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
- repo-shipped catalog root is `catalog/`
- custom catalog roots are backend local configuration for API 0.0.1
- additional local catalog roots are configured with `NEPHOS_API_CATALOG_ROOTS`
- `NEPHOS_API_CATALOG_ROOTS` is parsed as a platform path-list
- repo-shipped catalog root source id is `default`
- configured local roots use source ids `local-1`, `local-2`, `local-3` in configured order
- source ids are stable only for the current backend configuration and root order
- catalog responses expose source ids through `source`
- catalog responses do not expose raw filesystem paths by default
- `sourcePath` is reserved for future backend/debug/detail contexts
- custom catalog roots are not platform desired state in SQLite for API 0.0.1
- catalog source management can move into platform configuration later by explicit decision
- API reads and validates catalog manifests on demand
- do not import all catalog entries into SQLite before use
- do not require a startup catalog index
- directory slug and manifest `metadata.name` must match
- do not silently normalize slug/name mismatches
- duplicate catalog entries with the same kind and name across configured roots are an error unless the caller explicitly selects a source
- `catalogRef.source` and catalog detail `?source=` use source ids
- ambiguous duplicate catalog entries return `409 Conflict` with code `catalog_entry_ambiguous`
- `catalog_entry_ambiguous` details include `kind`, `name`, and `sources[]`
- unknown source ids return `404 Not Found` with code `catalog_source_not_found`
- do not let later roots silently override earlier roots
- validate manifests with typed Python/Pydantic domain models in API code first
- do not add canonical JSON Schema files under `schemas/` until Fer approves the concrete validation schema
- reject unknown manifest fields once canonical validation models exist
- install by catalog kind and name, plus optional explicit source when needed
- do not make arbitrary install-from-path the main API or UX flow
- store catalog kind, catalog name, catalog version when available, catalog source id, catalog source path snapshot, and SHA-256 manifest digest at install time
- do not store a full manifest snapshot by default
- store a full manifest snapshot only if implementation proves it is necessary for concrete behavior such as stable replay, import/export, or debugging
- temporary draft manifests stay under `.agents/drafts/manifests/` and remain non-canonical until API validation models exist and Fer approves promotion
- `metadata.version` remains optional for catalog entries
- installed records store version if present and always store the manifest digest
- catalog responses return normalized summaries with `kind`, `name`, `displayName`, `description`, `version`, `source`, `manifestDigest`, capability summary, and route summary
- App catalog summaries include `requires` and `routes`
- App catalog `requires` entries use `capability`, `alias`, and optional `provider`
- App catalog `routes` entries use `name`, `visibility`, and `target`
- Service catalog summaries include `provides`
- Service catalog `provides` entries use `capability`, optional `alias`, optional `version`, and `bindingOutputTargets`
- catalog responses do not return raw manifest blobs by default

Need to decide:

- exact Pydantic/domain validation model names
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

- backend/control plane lives in `nephos-api`
- CLI lives in `../nephos-cli`
- backend Python package layout is `src/nephos_api/`
- backend-local console command is `nephos-api`
- FastAPI app entrypoint is `nephos_api.main:app`
- backend Phase 1 distribution is local development process plus backend container image
- full installer packaging is deferred
- CLI workflow belongs to the separate CLI repository
- Phase 1 has backend/CLI version awareness without strict compatibility blocking

Need to decide:

- backend container image strategy
- CLI installation path
- release process across the two repositories
- future strict compatibility matrix

## Local Development Workflow Details

Question:

What are the exact local development commands and conventions for Nephos?

Accepted direction:

- `uv` is the canonical backend Python workflow
- backend-local init command is `uv run nephos-api init`
- init ensures one default internal platform domain, defaulting to `nephos.local`
- backend-local migration command is `uv run nephos-api db migrate`
- backend-local reset command is `uv run nephos-api db reset --force`
- backend-local serve command is `uv run nephos-api serve`
- API 0.0.1 implementation starts with migration/database layer, then API skeleton, then catalog loader, then reconciler
- backend bootstrap configuration uses environment variables
- `.env` may populate missing local process environment variables for development and manual testing
- real environment variables override `.env`
- no structured backend local config file for API 0.0.1
- no DB-stored backend bootstrap config for API 0.0.1
- Kubernetes target selection uses normal Kubernetes client configuration resolution by default
- optional `NEPHOS_API_KUBECONFIG`
- optional `NEPHOS_API_KUBE_CONTEXT`
- Makefile and task-runner wrappers are deferred
- CLI points at local backend/API during development
- cluster setup and lifecycle are user-managed or `nephos-cli`-managed for now
- `nephos-api` must not install, start, stop, reset, or destroy the selected Kubernetes cluster

Need to decide:

- how `../nephos-cli` points to a local backend
- exact `nephos-cli` cluster setup/reset workflow

## Testing Details

Question:

What exact test commands, tags, and CI boundaries should Nephos use?

Accepted direction:

- `pytest` for backend tests
- `ruff` for backend linting/formatting checks
- mocks/fakes for unit tests
- real Kubernetes cluster for Kubernetes integration tests
- pytest markers are `unit`, `integration`, and `kubernetes`
- tests marked `kubernetes` require a real selected Kubernetes cluster and should also be marked `integration`
- Kubernetes integration tests require a pre-existing reachable Kubernetes cluster
- Kubernetes integration tests require `NEPHOS_API_RUN_KUBERNETES_TESTS=1`
- Kubernetes preflight verifies explicit opt-in and Kubernetes API reachability
- default CI runs unit and non-Kubernetes-runtime tests only
- Kubernetes integration tests are local/manual until a later CI decision
- Kubernetes integration tests use generated test namespaces
- generated test namespaces and test-owned resources use `app.kubernetes.io/managed-by: nephos`
- test cleanup may delete only generated test namespaces/resources that it created and labeled
- default backend test command is `uv run pytest -m "not kubernetes"`
- explicit Kubernetes integration test command is `uv run pytest -m kubernetes`
- CLI tests live in the separate CLI repository

Need to decide:

- exact generated Kubernetes test namespace name format
- stricter allowed-context/server safety checks beyond opt-in and API reachability
- future Kubernetes runtime CI job shape, if Kubernetes integration is added to CI
- exact Kubernetes client fixture implementation
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
