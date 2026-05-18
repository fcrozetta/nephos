# Nephos Decisions

## D001: Nephos is a platform control plane

Nephos is a platform control plane for composable self-hosted infrastructure.

It should not be modeled as a generic container manager.

## D002: K3s is the default runtime backend

K3s is the primary runtime backend.

Other Kubernetes backends may be supported later through cluster adapters.

## D003: Kubernetes is the runtime API boundary

Nephos can be backend-agnostic mostly above the Kubernetes API layer.

Below that layer, cluster lifecycle is backend-specific.

## D004: Apps and Services are top-level concepts

Nephos has two primary installable concepts:

- Apps
- Services

Apps are user-facing workloads.

Services are shared platform infrastructure/capabilities.

## D005: Services expose capabilities

Services expose typed capabilities.

Apps consume capabilities through bindings.

## D006: Nephos API/database is canonical desired state

The Nephos API and database are the source of truth for desired platform state.

SQLite is the Phase 1 database.

YAML is import/export only.

Kubernetes is runtime state.

Kubernetes CRDs and GitOps-as-source-of-truth are deferred.

## D007: Backend and CLI live in separate repositories

The `nephos` repository owns the backend/control plane.

The CLI lives in `../nephos-cli` and `https://github.com/fcrozetta/nephos-cli`.

Do not implement CLI code in this repository without an explicit decision changing that boundary.

## D008: Phase 1 backend stack

The backend stack is Python, FastAPI, SQLite, simple explicit SQL migrations, and the official Python Kubernetes client.

## D009: Phase 1 CLI stack

The CLI stack is Python and Typer, implemented in the separate `nephos-cli` repository.

The CLI talks to the Nephos API/local controller.

The CLI must not become an unstructured direct Kubernetes mutation layer.

## D010: Phase 1 reconciler shape

Use an API-owned in-process reconciler for Phase 1.

Keep module boundaries clear enough to later extract the reconciler into a daemon, worker, scheduled process, or in-cluster controller.

Phase 1 drift handling should detect and report drift and reconcile only Nephos-owned resources when desired state is explicit.

## D011: Nephos manifests are the package boundary

Installable Apps and Services are defined by Nephos manifests.

Nephos manifests own platform semantics.

Helm charts and raw Kubernetes manifests are runtime deployment implementation details underneath the Nephos manifest layer.

## D012: App and Service manifests are separate

Apps and Services use separate manifest formats because they have different roles and authors.

App authors should not need to understand Service internals.

Service authors need to model capability exposure, provisioning behavior, and Service operations.

## D013: Helm-primary runtime packaging

Helm charts are the primary Phase 1 runtime deployment mechanism underneath Nephos manifests.

Raw Kubernetes manifests are an allowed fallback when no credible chart exists, a chart is too leaky or unstable, the workload is simple, Nephos deploys its own support components, or a curated Nephos-native deployment is clearer.

## D014: Local filesystem catalog first

Phase 1 catalogs start as local filesystem catalogs.

Git repositories, OCI registries, remote indexes, signed catalogs, and private remote catalogs are deferred.

## D015: Service operation terminology

Service operation is the canonical term for typed backend/API-owned Service management actions.

Service management action may be used descriptively, but should not be the preferred architecture term.

Service operations are optional in Phase 1, and their detailed contract still needs design.

## D016: Installed Services are Service instances

Service instance is the canonical term for an installed concrete Service.

A Service manifest defines an installable Service shape.

A Service instance is the installed platform/runtime instance.

## D017: Services are shared by default

Services are shared by default.

Where a Service supports app-scoped resources inside one runtime instance, Nephos should use one shared Service instance by default.

PostgreSQL should generally use one shared Service instance with separate databases/users per App by default.

## D018: Dedicated Service instances are reserved

Apps may request isolation from a Service provider.

An isolation request creates a dedicated Service instance when required or requested.

Dedicated Service instances are still first-class Services and may be explicitly bound by other Apps.

Phase 1 reserves the concept but implements shared/global Service instances first.

## D019: Bindings track dependents

Bindings are the source of dependent tracking between Apps and Service instances.

Do not maintain ad hoc dependent lists as authoritative state.

## D020: Service provider selection rules

Multiple Service instances may expose the same capability.

If exactly one eligible Service instance exposes a required capability, Nephos may auto-bind by default.

If multiple eligible Service instances expose a required capability and no default provider is configured, Nephos must require explicit selection.

Nephos may support a user-configurable default provider per capability.

## D021: Service lifecycle with dependents requires force

Stopping, removing, or destroying a Service instance with dependents must require explicit force and show an impact list.

Shared Service instances are long-lived infrastructure by default.

## D022: No Phase 1 resource policy system

Phase 1 does not implement a Nephos resource policy system.

Running Apps and Services use replicas `1`.

Stopped or disabled Apps and Services use replicas `0`.

Resource profiles are reserved for future design but not defined.

Raw Kubernetes CPU/memory knobs are not primary UX.

## D023: No Phase 1 HA or autoscaling

Phase 1 does not support HA, autoscaling, affinity, anti-affinity, quotas, or scheduling policy.

## D024: Phase 1 auth is single-owner local-first

Phase 1 is single-owner and local-first.

The CLI is a trusted local client.

No login, multi-user model, roles, or RBAC are required in Phase 1.

The Web UI is deferred.

Friend, cloud, hosted, and multi-user scenarios are out of scope for Phase 1 but not forbidden forever.

## D025: Versions are pinned and upgrades are manual

App, Service, catalog, Helm chart, runtime deployment reference, and Nephos versions are pinned.

Upgrades are explicit and manual.

No automatic latest behavior is allowed by default.

## D026: Service upgrades with persistent data are risky by default

Services are higher-risk upgrade targets than Apps because they commonly own persistent infrastructure state.

Risky Service upgrades should require backup/checkpoint confirmation once the Service declares backup support.

Until backup support exists, Nephos must warn that no supported backup exists.

Rollback is best-effort in Phase 1, not guaranteed.

## D027: Nephos owns backup intent but not universal implementation

Nephos owns backup intent, policy, and status.

Services own or provide data-aware backup/restore implementation where data semantics matter.

Phase 1 does not implement concrete backup/restore and must not promise universal backup guarantees.

## D028: Destroy is the data-deleting lifecycle operation

Stop preserves persistent data.

Remove removes runtime objects while preserving persistent data by default.

Destroy deletes runtime objects and persistent data.

Destroy must require destructive confirmation when persistent data exists.

There is no separate purge lifecycle operation.

## D029: Health status is Nephos-aware

Nephos health/status aggregates Kubernetes runtime signals and Nephos platform signals.

Kubernetes readiness is an input, not the full status model.

## D030: Lifecycle state is separate from health status

Removed and destroyed are lifecycle states, not health statuses.

Health status levels are `unknown`, `pending`, `healthy`, `degraded`, `blocked`, `stopped`, and `not_applicable`.

## D031: Status requires reasons and evidence

Every status must include reasons and/or evidence.

Do not expose opaque green/red status without explaining why.

## D032: Phase 1 status is minimal but platform-aware

Phase 1 status includes desired lifecycle state, reconciliation state, Kubernetes object existence/readiness, binding resolution, dependency availability, route known/unknown, backup status as `unsupported`, and Service dependent impact.

## D033: Phase 1 targets single-node K3s

Phase 1 targets single-node K3s as the default real runtime backend.

Cluster lifecycle support is minimal in Phase 1.

## D034: Phase 1 App and Service lifecycle commands

Phase 1 includes App and Service install, start, stop, remove, and destroy.

The disable lifecycle operation is deferred.

## D035: Phase 1 uses local filesystem catalog from day one

Phase 1 should load a local filesystem catalog from day one.

The repo may ship a tiny reference catalog, but App behavior must not be hardcoded in backend logic.

## D036: No service mesh in Phase 1

Multi-component Apps communicate through normal Kubernetes Services/networking.

No service mesh is required or included in Phase 1.

## D037: Paperless and PostgreSQL reference scenario

The canonical Phase 1 reference scenario is Paperless App plus PostgreSQL Service.

## D038: One namespace per App or Service instance

Nephos uses separate Kubernetes namespaces for App instances and Service instances.

Use `app-<slug>` for App instances, `svc-<slug>` for Service instances, and `nephos-system` for Nephos control-plane/runtime support components.

Remove preserves namespaces.

Destroy deletes namespaces by default after destructive confirmation when persistent data exists.

## D039: No default-deny NetworkPolicy in Phase 1

Phase 1 does not apply default-deny NetworkPolicy.

Network policy is reserved for later design.

## D040: Traefik local ingress in Phase 1

Traefik is the Phase 1 default ingress controller because K3s includes it.

Nephos owns route and visibility intent.

Kubernetes owns concrete Ingress resources.

Phase 1 implements local visibility and reserves private, public, and tailnet visibility for later.

Phase 1 supports multiple configured ingress root domains with one default/canonical domain.

At least one root domain is required for generated route hosts.

Nephos generates host rules for each configured root domain.

Root domains are aliases for the same route intent, not separate Apps or separate routes.

Default route host pattern is `<app-instance>.<root-domain>`.

Non-default route host pattern is `<route>.<app-instance>.<root-domain>`.

Path-based App routing is out of scope for Phase 1.

Phase 1 Nephos-managed ingress is HTTP-only.

If generated hostnames collide, Nephos fails and requires an explicit route, App instance, or domain policy change.

Services do not expose admin routes through Nephos ingress in Phase 1.

## D041: Manual tunnel compatibility without tunnel automation

Cloudflare Tunnel, Tailscale, DNS automation, and TLS automation are deferred.

Nephos-generated local ingress must be compatible with a manually configured Cloudflare Tunnel, but Nephos does not manage Cloudflare credentials, tunnel lifecycle, or DNS records in Phase 1.

## D042: Stopped Apps keep route intent

Stopping an App keeps route intent and may keep runtime ingress objects.

Status must report the App as stopped or unavailable.

Removing or destroying an App removes runtime ingress objects.

## D043: Kubernetes Secrets are Phase 1 secret storage

Phase 1 uses Kubernetes Secrets.

External secret managers are deferred.

Nephos owns secret policy, labels, injection, preservation, deletion, and redaction semantics.

## D044: Binding credentials are materialized into App namespaces

Service-internal and Service-admin secrets live in Service instance namespaces.

App binding credentials are materialized into App namespaces.

Apps should not read Service namespace Secrets directly.

Bindings determine which App may receive which Service credentials.

## D045: Secret values are redacted by default

Secret values must be redacted in API responses, CLI output, status output, logs, and diagnostics by default.

Stop and remove preserve Secrets.

Destroy deletes Secrets for the destroyed entity after destructive confirmation when persistent data or credentials are involved.

## D046: Phase 1 catalog sources are local filesystem paths

Phase 1 supports repo-shipped reference catalog entries and user-configured local filesystem catalog paths.

The backend must not hardcode App or Service behavior.

Reference scenarios should exercise the catalog and manifest path.

## D047: User-created local catalog entries are allowed

User-created local catalog entries are allowed in Phase 1.

Until the concrete validation schema is accepted, local user-created entries do not carry a schema stability promise.

## D048: Local catalog files are trusted local-owner input

Phase 1 treats local catalog files as trusted local-owner input.

Remote catalog trust, signing, verification, private catalog credentials, and package sandboxing guarantees are deferred.

## D049: Catalog metadata lives in manifests for Phase 1

For Phase 1, App and Service manifests carry minimal catalog metadata.

A separate catalog index is deferred.

Catalog metadata must not become a second source of truth for package semantics.

## D050: Backend local development uses uv

Use `uv` as the canonical Python workflow for backend development in this repository.

## D051: Backend tests use pytest and ruff

Use `pytest` for backend tests.

Use `ruff` for backend linting/formatting checks.

Use mocks or fakes for unit tests.

Use real K3s for Kubernetes integration tests.

## D052: Phase 1 backend distribution is local process plus container image

Phase 1 backend distribution consists of a local development process and a backend container image for runtime packaging.

Full installer packaging is deferred.

## D053: CLI workflow belongs to the CLI repository

The separate `nephos-cli` repository owns CLI implementation, linting, testing, packaging, and release workflow.

Do not add CLI implementation code to this repository without an explicit boundary change.

## D054: Phase 1 has version awareness without strict blocking

The backend should expose a version endpoint.

The CLI should report CLI and backend versions and may warn when backend version is unknown, older, or newer than expected.

The CLI should not block state-mutating commands solely because of version mismatch in Phase 1.

Strict CLI/backend compatibility blocking is deferred.

## D055: ADRs are required for architecture-significant changes

Create or update ADRs for changes affecting architecture structure, lifecycle semantics, source of truth, manifest/schema shape, runtime boundaries, auth/security, backup/data lifecycle semantics, public API/CLI contract, catalog behavior, or Phase 1 scope.

Minor implementation details inside accepted architecture do not require a new ADR.

## D056: ADR statuses have explicit meanings

Use `draft`, `proposed`, `accepted`, `rejected`, `deprecated`, and `superseded`.

`accepted` means Fer confirmed the decision.

Accepted ADRs are durable.

Material changes to accepted decisions should normally use a new superseding/amending ADR.

## D057: Agents must not implement through architectural ambiguity

If architecture is unclear, agents must ask Fer or record an open question before implementing.

Low-level implementation details may be chosen pragmatically when consistent with accepted ADRs and context.

## D058: Canonical schemas and examples require Fer approval

Do not add canonical schema files under `schemas/` until Fer approves the concrete validation schema.

Do not add canonical examples under `examples/` until manifest validation plus command/status shape are stable enough and Fer approves promotion.

Temporary draft manifests are allowed while designing schemas, but they must live under `.agents/drafts/manifests/`, be clearly marked non-canonical, and not be treated as source of truth.

## D059: Architecture-changing work updates documentation in the same change

Any PR, commit, or agent change that alters architecture or public contracts must update ADRs, context, or open questions in the same change.

## D060: Keep architecture decision batches separate when feasible

Keep architecture decision batches in separate commits when feasible.

## D061: Draft manifest workspace is .agents/drafts/manifests

Temporary draft manifest sketches may live under `.agents/drafts/manifests/`.

Draft manifests are non-canonical, must not live under `schemas/` or `examples/`, and must not be treated as source of truth.

## D062: Paperless plus PostgreSQL is the canonical reference scenario flow

The canonical Phase 1 reference scenario installs PostgreSQL Service, installs Paperless App, binds Paperless to the `postgres` capability, exposes Paperless through local route intent, exercises stop/start data preservation, removes Paperless preserving data, and destroys Paperless with destructive confirmation.

Paperless requires only PostgreSQL in the Phase 1 reference scenario.

## D063: Reference scenario includes Service dependency impact

The reference scenario must include attempting to stop PostgreSQL while Paperless depends on it.

Nephos should block the Service stop unless forced and show an impact list.

## D064: Reference scenario route is illustrative

Use illustrative generated hosts such as `paperless.nephos.local` and `paperless.nephos.fcrozetta.app`.

The exact ingress root domain configuration storage/API shape remains open.

## D065: Nephos manifests use YAML

Nephos manifests are YAML documents.

## D066: Nephos manifests use a Kubernetes-like envelope

Nephos manifests use `apiVersion`, `kind`, `metadata`, and `spec`.

The envelope is for Nephos manifest structure and versioning.

It does not mean Nephos manifests are Kubernetes CRDs.

## D067: App and Service are accepted manifest kinds

Accepted manifest kinds are `App` and `Service`.

Apps and Services remain separate because they have different roles and authors.

## D068: Runtime references remain below Nephos manifests

Phase 1 remains Helm-primary underneath Nephos manifests.

Helm runtime references should carry pinned chart identity such as repository, chart name, and chart version.

Raw Kubernetes manifest references remain an allowed fallback.

Raw Helm values and Kubernetes object specs must not become the primary Nephos manifest schema.

## D069: Binding schema remains minimal at manifest level

App manifests declare required capabilities.

Service manifests declare exposed capabilities.

Nephos resolves and creates bindings outside the manifest.

Later accepted binding output details are recorded in D076-D082.

## D070: Manifest apiVersion is nephos.pro/v1alpha1

Use `apiVersion: nephos.pro/v1alpha1` for Nephos manifests.

This is a manifest schema/version lane, not a Nephos product version, App version, Service version, catalog version, or runtime package version.

## D071: Catalog entries use directory-per-entry layout

Use `catalog/apps/<app-slug>/app.yaml` for App catalog entries.

Use `catalog/services/<service-slug>/service.yaml` for Service catalog entries.

Catalog entries are available Apps and Services.

Installed App and Service instances live in Nephos desired state, not catalog files.

## D072: Routes declare identity and visibility, not full hostnames

App manifests use `spec.routes[]` with route `name`, `visibility`, and `target`.

Nephos derives hostnames from App instance name, route name, visibility, and configured domain policy.

Phase 1 hostname generation uses `<app-instance>.<root-domain>` for default routes and `<route>.<app-instance>.<root-domain>` for non-default routes.

Do not put full hostnames in App manifests as the primary route model.

## D073: Initial App manifest field conventions

App manifests use `metadata.name`, optional `metadata.displayName`, optional `metadata.description`, optional `metadata.version`, `spec.requires[]`, `spec.routes[]`, `spec.config.options[]`, and `spec.runtime`.

`spec.requires[]` entries support `capability`, optional `as`, and optional `provider`.

## D074: Initial Service manifest field conventions

Service manifests use `metadata.name`, optional `metadata.displayName`, optional `metadata.description`, optional `metadata.version`, `spec.provides[]`, `spec.bindings.outputs[]`, `spec.provisioning.mode`, `spec.runtime`, and `spec.operations[]`.

`spec.provides[]` entries support `capability`, optional `as`, and optional `version`.

`spec.bindings.outputs[]` starts with `target: app-secret`.

For Phase 1, `app-secret` is the only accepted binding output target.

## D075: Runtime field convention is spec.runtime

Use `spec.runtime.type`, `spec.runtime.chart.repository`, `spec.runtime.chart.name`, `spec.runtime.chart.version`, and reserved `spec.runtime.values.mappings[]` for Helm-primary runtime references.

`values.mappings` is reserved for Nephos-owned mapping from Nephos semantics into Helm values.

Do not expose raw Helm values as the primary user schema.

Raw Kubernetes manifest runtime reference shape is deferred until first needed.

## D076: Phase 1 binding output target is app-secret

Phase 1 supports `app-secret` as the only binding output target.

`app-secret` means Nephos materializes binding credentials into the consuming App namespace as a Kubernetes Secret.

Future binding output targets are deferred.

## D077: PostgreSQL binding output fields

PostgreSQL bindings use these logical output fields:

- `host`
- `port`
- `database`
- `username`
- `password`
- `uri`

Later accepted key serialization details are recorded in D086.

## D078: Nephos chooses deterministic binding Secret names

Service manifests declare logical binding outputs.

They do not hardcode final consuming Secret names.

Nephos chooses deterministic Secret names from binding alias.

The Phase 1 name format is recorded in D103.

## D079: App binding aliases are symbolic

App manifests use symbolic binding aliases such as `as: database`.

Nephos maps binding outputs into runtime deployment values through the reserved `spec.runtime.values.mappings[]` lane.

Do not make Apps depend on Service namespace Secrets or raw Kubernetes Secret templates.

## D080: Phase 1 provisioning modes are app-scoped-resource and none

Phase 1 recognizes two provisioning modes:

- `app-scoped-resource`
- `none`

`app-scoped-resource` means the Service creates a resource for the consuming App inside the Service instance.

`none` means no Service-side resource is created for the binding.

## D081: Provisioning is a typed backend-owned contract

Provisioning is a typed Nephos backend/API-owned contract.

Do not model provisioning as arbitrary user-facing shell scripts.

Do not make Helm hooks the product-level provisioning contract.

The concrete execution mechanism remains open.

## D082: Remove preserves provisioned resources and destroy deletes them

Removing an App preserves provisioned Service-side resources created for that App.

Destroying an App deletes provisioned Service-side resources created for that App after destructive confirmation.

Binding materialized Secrets follow the accepted secret lifecycle.

## D083: Phase 1 installable catalog entries require runtime identity fields

Phase 1 installable App and Service catalog entries require:

- `apiVersion`
- `kind`
- `metadata.name`
- `spec.runtime`

This applies to catalog entries that Nephos deploys.

Future imported, external, or pre-existing Services may need a different runtime shape, but that requires a later explicit decision.

## D084: App requirements, routes, and config options default empty

For Phase 1 App manifests:

- `spec.requires[]` is optional and defaults to an empty list.
- `spec.routes[]` is optional and defaults to an empty list.
- `spec.config.options[]` is optional and defaults to an empty list.

This keeps standalone, worker, internal, and no-route Apps valid.

## D085: Service provides and provisioning mode are explicit

For Phase 1 Service manifests:

- `spec.provides[]` is required and must be non-empty.
- `spec.provisioning.mode` is required and must be either `none` or `app-scoped-resource`.
- `spec.operations[]` is optional and defaults to an empty list.

For the Phase 1 PostgreSQL Service, `spec.bindings.outputs[]` must include an `app-secret` output.

The broader required/default behavior for Services that expose capabilities without binding outputs remains open.

## D086: PostgreSQL output fields are capability-defined

PostgreSQL binding output fields are defined by the `postgres` capability contract.

Do not add a manifest `fields:` syntax for PostgreSQL outputs in Phase 1.

For PostgreSQL `app-secret` outputs, use these exact lowercase Kubernetes Secret keys:

- `host`
- `port`
- `database`
- `username`
- `password`
- `uri`

## D087: Canonical examples wait for validation and command/status shape

Keep manifest sketches under `.agents/drafts/manifests/` for now.

Do not add canonical examples under `examples/` until manifest validation plus command/status shape are stable enough that examples will not immediately rot.

## D088: Phase 1 App config option types are minimal

Phase 1 App config option types are:

- `string`
- `integer`
- `boolean`
- `enum`

The `secret` App config option type is deferred.

App config must not become a second credential path beside bindings and generated Service credentials.

Arbitrary object and array config option values are not supported in Phase 1.

## D089: Unknown manifest fields are rejected once schemas exist

Once canonical schemas exist, unknown manifest fields are rejected.

Do not silently ignore unknown fields in canonical manifests.

Before schemas exist, draft manifests remain non-canonical and must not be treated as validation contracts.

## D090: Raw Kubernetes manifest fallback shape is deferred

Raw Kubernetes manifests remain an accepted fallback runtime mechanism.

The exact raw manifest fallback field shape is deferred until Nephos needs a raw-manifest package.

Do not add raw manifest schema fields now.

## D091: Config option object shape

Phase 1 config options support:

- `name`
- `type`
- `label`
- `description`
- `default`
- `required`

Required config option fields:

- `name`
- `type`

Optional config option fields:

- `label`
- `description`
- `default`
- `required`

`name` is the stable machine key.

Use `label` for display text.

`required` defaults to `false`.

## D092: Enum config options use value and label objects

Enum config options use object values with:

- `value`
- `label`

`value` is the stored value.

`label` is display text.

## D093: Config validation bounds are deferred

Do not add validation bounds such as `min`, `max`, `regex`, or length constraints in Phase 1.

Config option `default` values should still match the declared config option type.

## D094: Config options do not carry runtime mapping paths

Config options are semantic inputs.

Do not put Helm value paths, environment variables, or Kubernetes field paths directly in config option objects.

Mapping config options into runtime deployment values happens through `spec.runtime.values.mappings[]`.

Accepted Phase 1 mapping shape is recorded in D095-D099.

## D095: Phase 1 runtime mapping source kinds are config and binding

Phase 1 runtime value mappings support only these source kinds:

- `config`
- `binding`

Route and storage mapping source kinds are deferred.

Do not add a generic expression language.

## D096: Runtime mappings use explicit from and to objects

Config mappings use:

```yaml
from:
  kind: config
  name: paperless_ocr_language
to:
  helmValue: paperless.ocr.language
```

Binding mappings use:

```yaml
from:
  kind: binding
  name: database
  field: uri
to:
  helmValue: env.DATABASE_URL
```

For binding sources, `name` references the App binding alias.

For binding sources, `field` references a binding output field such as `uri`.

The binding mapping source shape may be revisited after a fuller Nephos manifest is evaluated.

## D097: Runtime mapping targets use helmValue dot paths

The `helmValue` target is a dot path in Phase 1.

Do not use raw nested Helm value fragments as mapping targets in Phase 1.

Target path escaping for literal dots in Helm value keys is deferred until needed.

## D098: Runtime mappings have no transforms in Phase 1

Do not support mapping transforms in Phase 1.

Binding fields should expose useful outputs such as `uri` instead of requiring template strings or format transforms.

## D099: Missing mapping sources block reconciliation

If a mapping source is missing, reconciliation fails with `blocked` status and a reason.

Do not silently skip missing mapping sources.

## D100: Runtime mappings live only under spec.runtime.values.mappings

Mappings live only under `spec.runtime.values.mappings[]`.

Do not define runtime mappings inline on config options or binding declarations.

## D101: Binding aliases default to capability

If `as` is omitted from an App requirement, the binding alias defaults to the requirement `capability`.

Example:

```yaml
spec:
  requires:
    - capability: postgres
```

The alias defaults to `postgres`.

## D102: Binding aliases are unique per App

Binding aliases must be unique within one App manifest and one installed App instance after defaulting.

If an App needs more than one binding for the same capability, it must set explicit aliases.

## D103: Binding Secret names use nephos-bind alias

For Phase 1 `app-secret` outputs, Nephos creates the Secret in the consuming App namespace with this name:

```text
nephos-bind-<alias>
```

The alias must follow the accepted Nephos machine identifier rule.

If `nephos-bind-<alias>` would exceed Kubernetes Secret name limits, Nephos rejects the alias and requires a shorter explicit alias.

## D104: Rebinding keeps the App Secret name stable

Rebinding an alias to a different Service instance updates the same Secret name with new contents after explicit reconciliation or confirmation.

Rebinding does not create a new Secret name by default.

## D105: Binding Secrets carry relationship metadata

Binding Secrets must include:

```yaml
app.kubernetes.io/managed-by: nephos
nephos.pro/app-instance: <app-instance>
nephos.pro/service-instance: <service-instance>
nephos.pro/capability: <capability>
nephos.pro/binding-alias: <alias>
```

## D106: Secret naming slug rules follow shared Nephos name rules

Do not define a separate binding-Secret-only slugging system in Phase 1.

Binding Secret alias slug normalization follows the same Nephos machine identifier rules used for App, Service, namespace, route, and catalog slugs.

## D107: Machine identifiers use strict DNS-label style

Manifest `metadata.name`, binding aliases, route names, installed App instance slugs, installed Service instance slugs, and catalog entry slugs must match:

```text
^[a-z0-9]([-a-z0-9]*[a-z0-9])?$
```

Nephos rejects invalid machine identifiers.

Do not silently normalize, lowercase, truncate, suffix, or randomize machine identifiers.

## D108: Instance names default from catalog metadata name

By default, an installed instance name equals the catalog manifest `metadata.name`.

Users may provide an explicit instance name at install time.

App instance names are unique within the App instance scope.

Service instance names are unique within the Service instance scope.

## D109: Name collisions fail explicitly

If a name, alias, route, provider, or instance selection collides or is ambiguous, Nephos fails and requires explicit user input.

Nephos does not silently add suffixes such as `-2`.

Nephos does not generate random suffixes for platform-visible names in Phase 1.

## D110: Generated Kubernetes names must fit resource limits

Generated Kubernetes object names must fit Kubernetes name limits.

Prefixes count toward the final Kubernetes name length.

Known Phase 1 derived names include:

- `app-<slug>`
- `svc-<slug>`
- `nephos-bind-<alias>`

If a final generated name would exceed the Kubernetes limit for that resource, Nephos rejects the input and asks for a shorter explicit name or alias.

## D111: Runtime metadata uses app.kubernetes.io and nephos.pro keys

Nephos-managed Kubernetes resources should use:

```yaml
app.kubernetes.io/managed-by: nephos
```

Nephos-owned relationship metadata uses keys under `nephos.pro/*`.

Accepted Phase 1 keys:

- `nephos.pro/app-instance`
- `nephos.pro/service-instance`
- `nephos.pro/capability`
- `nephos.pro/binding-alias`

Binding Secrets must carry all four relationship keys plus `app.kubernetes.io/managed-by: nephos`.

## D112: Nephos does not use ownerReferences for platform relationships

Nephos does not use Kubernetes `ownerReferences` to represent Nephos platform relationships in Phase 1.

Nephos desired state in the API/database is the source of truth.

Kubernetes labels and annotations exist for inspection, drift detection, and cleanup.

Do not model App-Service bindings, Service dependents, lifecycle ownership, or desired-state ownership through Kubernetes owner references.

Helm charts or Kubernetes controllers may create their own internal owner references as runtime implementation details, but Nephos must not rely on those references as the platform relationship model.
