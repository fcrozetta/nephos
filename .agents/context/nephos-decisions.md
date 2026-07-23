# Nephos Decisions

## D001: Nephos is a platform control plane

Nephos is a platform control plane for composable self-hosted infrastructure.

It should not be modeled as a generic container manager.

## D002: Kubernetes context is the runtime target

API 0.0.1 targets the selected Kubernetes kubeconfig/context.

Docker Desktop, kind, kubeadm, K3s, and other compatible Kubernetes clusters
are possible selected targets.

K3s is a compatible local cluster option, not the assumed runtime type.

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

## D013: Helm runtime packaging

Helm charts are a Phase 1 runtime packaging mechanism underneath Nephos manifests.

Direct Helm is secondary for Services because Services need typed provider
actions beyond generated config files.

For Services, the internal Python Pulumi provider owns lifecycle, binding,
status, and future maintenance actions. Helm charts may be used underneath that
provider where they give leverage.

Raw Kubernetes manifests are an allowed fallback when no credible chart exists, a chart is too leaky or unstable, the workload is simple, Nephos deploys its own support components, or a curated Nephos-native deployment is clearer.

## D014: Local filesystem catalog first

Phase 1 catalogs start as local filesystem catalogs.

Git repositories, OCI registries, remote indexes, signed catalogs, and private remote catalogs are deferred.

## D015: Service operation terminology

Service operation is the canonical term for typed backend/API-owned Service management actions.

Service management action may be used descriptively, but should not be the preferred architecture term.

Service operations are reserved but bounded in Phase 1.

Phase 1 may use internal typed Service handlers for minimal accepted provisioning work.

Phase 1 does not expose a general user-facing Service operation API or CLI UX.

Do not model Service operations as arbitrary shell commands, Helm hooks, Kubernetes jobs, or user-provided scripts exposed as product semantics.

The detailed Service operation schema and command contract remain deferred.

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

For API 0.0.1, `destroyed` is terminal history or absent after deletion, not a normal active desired-state lifecycle value.

Health status levels are `unknown`, `pending`, `healthy`, `degraded`, `blocked`, `stopped`, and `not_applicable`.

## D031: Status requires reasons and evidence

Every status must include reasons and/or evidence.

Do not expose opaque green/red status without explaining why.

## D032: Phase 1 status is minimal but platform-aware

Phase 1 status includes desired lifecycle state, reconciliation state, Kubernetes object existence/readiness, binding resolution, dependency availability, route known/unknown, backup status as `unsupported`, and Service dependent impact.

## D033: Phase 1 targets a selected single-node Kubernetes cluster

Phase 1 targets a selected single-node Kubernetes cluster as the real runtime
backend.

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

Traefik may be the Phase 1 default ingress controller, but not because Nephos
assumes K3s.

Traefik does not provide local DNS resolution. It routes HTTP after the App
hostname already resolves to the selected cluster ingress endpoint.

Nephos owns route and visibility intent.

Kubernetes owns concrete Ingress resources.

Phase 1 implements local visibility and reserves private, public, and tailnet visibility for later.

Phase 1 supports multiple configured ingress root domains with one default/canonical domain.

At least one root domain is required for generated route hosts.

Ingress root domains are platform desired state in the Nephos API/database.

They are managed through Nephos API/CLI platform configuration operations.

They are not App manifest fields.

Nephos generates host rules for each configured root domain.

Root domains are aliases for the same route intent, not separate Apps or separate routes.

Default route host pattern is `<app-instance>.<root-domain>`.

Non-default route host pattern is `<route>.<app-instance>.<root-domain>`.

Path-based App routing is out of scope for Phase 1.

Phase 1 Nephos-managed ingress is HTTP-only.

If generated hostnames collide, Nephos fails and requires an explicit route, App instance, or domain policy change.

Services do not expose admin routes through Nephos ingress in Phase 1.

Root domain config uses `name`, `domain`, and `default`.

The domain value is a DNS suffix.

Reject URLs, paths, wildcards, schemes, and ports.

Nephos setup creates initial platform configuration before Apps are installed, including at least one ingress root domain and exactly one default/canonical root domain.

For local browser testing without `/etc/hosts`, the initial root domain should
be a resolvable suffix such as `nephos.localhost`.

Generated Kubernetes Ingress resources set `ingressClassName` from
`NEPHOS_API_INGRESS_CLASS`, or auto-detect a single/default cluster
`IngressClass`.

Setup UX and command implementation belong in the separate `nephos-cli` repository after Nephos API `0.0.1` is implemented.

Root domain operations are add, list, remove, and set default.

App status shows canonical URL from the default root domain plus aliases from non-default root domains.

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

Use a real selected Kubernetes cluster for Kubernetes integration tests.

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

The exact CLI command spelling for root domain operations remains open.

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

Phase 1 keeps Helm chart identity available underneath Nephos manifests.

Direct Helm is secondary for Services.

Helm runtime references should carry pinned chart identity such as repository, chart name, and chart version.

Raw Kubernetes manifest references remain an allowed fallback.

Raw Helm values and Kubernetes object specs must not become the primary Nephos manifest schema.

## D068A: Pulumi is the accepted forward provider execution backend

Nephos owns meaning.

Pulumi performs labor.

Nephos API/SQLite desired state remains canonical.

Pulumi state is provider-observed execution state and must not replace Nephos
desired state, lifecycle state, relationships, dependency impact, or binding
truth.

API handlers and CLI clients must not call Pulumi directly.

Pulumi runs behind the reconciler through internal Python provider packages.

API 0.0.1 App and Service provider packages are Python-only.

The expected internal package direction is `nephos_api.providers`.

Additional provider implementation languages are deferred.

For Services, Pulumi-backed Python providers must expose typed internal actions
beyond chart config files. Helm may be an implementation tool underneath the
Service provider, but it is not the Service provider contract.

## D068B: API 0.0.1 provider implementation defaults

The API 0.0.1 provider package lives under:

```text
src/nephos_api/providers/
```

The default runtime deployment provider is `PulumiHelmProvider` behind
`ProviderRuntimeDeployer`.

Pulumi Automation API uses a local file backend by default.

Default state location:

```text
.nephos/pulumi/state
```

Default workspace root:

```text
.nephos/pulumi/workspaces
```

Stack names match accepted runtime names:

```text
app-<slug>
svc-<slug>
```

The Pulumi CLI must be available on `PATH` for runtime convergence.

If it is missing, Nephos records a blocked reconciliation with reason
`pulumi_cli_missing`.

The Pulumi local file backend requires `PULUMI_CONFIG_PASSPHRASE` or
`PULUMI_CONFIG_PASSPHRASE_FILE`.

If neither is configured, Nephos records a blocked reconciliation with reason
`pulumi_passphrase_missing`.

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

Use `spec.runtime.type`, `spec.runtime.chart.repository`, `spec.runtime.chart.name`, `spec.runtime.chart.version`, and reserved `spec.runtime.values.mappings[]` for Helm runtime references.

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

## D113: Ingress root domains are platform desired state

Ingress root domains are platform desired state in the Nephos API/database.

They are not App manifest fields, startup-only environment variables, or local config files that bypass the canonical desired-state model.

Nephos API and CLI manage ingress root domains through platform configuration operations.

## D114: Root domain config uses name domain default

Ingress root domain config uses this semantic shape:

```yaml
rootDomains:
  - name: local
    domain: nephos.local
    default: true
  - name: cloudflare
    domain: nephos.fcrozetta.app
```

`name` is a Nephos machine identifier.

`domain` is a DNS suffix.

Exactly one root domain has `default: true`.

At least one root domain is required before route reconciliation can generate hosts.

## D115: Root domain values are DNS suffixes only

Store only DNS suffixes such as `nephos.local`.

Reject full URLs, paths, wildcards, schemes, and ports.

Wildcard behavior belongs in DNS, tunnel, or external routing configuration, not in Nephos root domain state.

## D116: Root domain operations are typed platform config operations

Phase 1 needs platform configuration operations for add, list, remove, and set default.

The accepted HTTP API path is `/platform/config/domains`.

The exact CLI command spelling remains open.

Removing a root domain removes that domain's generated host aliases from reconciled ingress after explicit confirmation when existing routes use it.

## D117: Setup creates initial platform ingress config

Nephos setup must create initial platform configuration before Apps are installed.

That setup includes at least one ingress root domain and exactly one default/canonical root domain.

For API 0.0.1 backend-local development, `uv run nephos-api init` creates the
initial internal root domain. If no domain is passed, the default is
`nephos.local` with platform-domain name `internal`.

User-facing setup UX belongs in the separate `nephos-cli` repository after
Nephos API `0.0.1` is implemented.

Do not rely on App installation to discover or create ingress root domain configuration.

Do not silently invent hostnames during App install.

## D118: App status shows canonical URL and aliases

App status shows the canonical URL generated from the default root domain and aliases generated from non-default root domains.

Because Phase 1 Nephos-managed ingress is HTTP-only, Nephos-generated URLs use `http://`.

## D119: Backend may start with incomplete platform config

The backend may start with an empty database.

When required platform configuration is missing, the backend reports platform configuration as incomplete until setup creates the required desired state.

## D120: Setup command design is deferred to nephos-cli

Setup UX and command implementation belong in the separate `nephos-cli` repository.

Nephos setup command design is deferred until after Nephos API `0.0.1` is implemented.

Open CLI-phase questions:

- exact setup command spelling
- whether setup is interactive, flag-driven, or both
- exact root domain command group spelling
- setup idempotency behavior
- App install behavior when setup is missing
- exact API paths used by broader CLI setup operations beyond root domain config

## D121: Service operations are reserved but bounded

Service operations are typed backend/API-owned Service management actions.

They are not arbitrary shell commands, Helm hooks, Kubernetes jobs, or user-provided scripts exposed as product semantics.

Phase 1 may use internal typed Service handlers for minimal accepted provisioning work.

Phase 1 does not expose a general user-facing Service operation API or CLI UX.

`spec.operations[]` remains reserved in Service manifests and defaults to an empty list.

Canonical Service operation schemas and examples require later explicit approval.

Future user-facing or risky Service operations must be dependency-aware and status/audit visible.

Destructive or risky Service operations must require explicit confirmation.

## D122: API 0.0.1 uses a REST-ish resource model

API 0.0.1 uses REST-ish resources rather than a command/action API or CLI-shaped HTTP paths.

Lifecycle operations are actions on resources, not raw Kubernetes commands.

## D123: Installed Apps and Services are instance resources

Installed Apps are represented internally as `AppInstance` records.

Installed Services are represented internally as `ServiceInstance` records.

The public API may expose installed App instances under `/apps` and installed Service instances under `/services`.

Catalog App and Service manifests are separate from installed instances.

## D124: Bindings are first-class API/database resources

Bindings connect App instance requirement aliases to Service instance capabilities.

Bindings are not embedded only inside App desired state and are not inferred from Kubernetes Secret metadata.

## D125: Root domain API path is /platform/config/domains

Ingress root domains are platform configuration resources in the API/database.

The accepted Phase 1 API path is:

```text
/platform/config/domains
```

These resources represent Nephos ingress root domains, not generic DNS management.

## D126: API lifecycle and status are separate

Lifecycle state is desired state.

API 0.0.1 active lifecycle states are `running`, `stopped`, and `removed`.

`destroyed` is terminal history or absent after deletion, not a normal active desired-state lifecycle value.

Status is separate from lifecycle state.

API 0.0.1 should persist the latest status snapshot with reason and evidence fields.

## D127: API mutations enqueue reconciliation

Mutating API calls update desired state and create a persisted reconciliation request.

A manual reconcile endpoint is allowed for debugging.

The API must not bypass desired state and reconciliation by directly mutating Kubernetes inline as the primary effect of a command.

## D128: API 0.0.1 scope is the reference flow

API 0.0.1 defines only resources needed for the Paperless plus PostgreSQL reference flow.

Future backups, upgrades, auth/RBAC, resource profiles, remote catalogs, and generalized Service operation APIs are deferred.

## D129: API 0.0.1 uses plain SQL data access

Use plain SQL through a small repository/data-access layer.

Do not introduce a full ORM for API 0.0.1.

## D130: Initial database schema starts at migrations/0000_initial.sql

Use explicit SQL migration files.

Before the first usable version, local development may destroy and recreate the SQLite database.

The initial schema should live in `migrations/0000_initial.sql`.

Forward-compatible migration discipline starts after the first usable version is established.

## D131: API 0.0.1 table families are normalized

API 0.0.1 should use separate normalized table families:

- `app_instances`
- `service_instances`
- `bindings`
- `platform_domains`
- `status_snapshots`
- `reconciliation_requests`
- `schema_migrations`

Exact columns, indexes, constraints, and foreign-key behavior remain implementation details.

## D132: Desired state stores normalized fields plus JSON snapshots

Use normalized columns for core identity, relationship, lifecycle, and lookup fields.

Use SQLite JSON text columns for snapshots and flexible payloads where useful.

JSON payloads must be validated at the API/domain boundary.

Do not use unvalidated JSON blobs as the main domain model.

## D133: Installed records store catalog identity and digest

Installed App and Service records store catalog identity and version information.

This should include catalog kind, catalog name, catalog version when available, catalog source id, catalog source path snapshot, and SHA-256 manifest digest.

Do not store a full manifest snapshot by default.

Store a full manifest snapshot only if implementation proves it is necessary for a concrete behavior such as stable replay, import/export, or debugging.

Do not recompute installed desired state only from current catalog files.

## D134: Status persistence stores latest snapshots

Persist the latest status snapshot per resource.

Status must include reasons and evidence.

Status event/history storage is deferred.

## D135: Reconciliation requests are persisted

Persist reconciliation requests in SQLite.

In-memory-only reconciliation queues are not the Phase 1 default.

Persisted reconciliation requests make the API mutation/reconciler boundary visible and retryable.

## D136: API mutations are transaction-bound

API mutations that change desired state must write desired-state changes and the reconciliation request in one database transaction.

Do not write desired state and enqueue reconciliation as separate best-effort steps.

## D137: Destroy removes active desired-state rows after teardown

Destroy removes active desired-state rows after successful teardown.

API 0.0.1 does not require an audit/history table for destroyed resources.

`destroyed` may appear later as terminal history if an audit/history model is accepted.

## D138: API 0.0.1 catalog roots are local filesystem roots

API 0.0.1 supports one repo-shipped catalog root and optional configured local filesystem catalog roots.

The repo-shipped catalog root is:

```text
catalog/
```

Additional local catalog roots are configured with `NEPHOS_API_CATALOG_ROOTS`.

`NEPHOS_API_CATALOG_ROOTS` is parsed as a platform path-list.

Custom catalog roots are backend local configuration for API 0.0.1.

Do not store custom catalog roots as platform desired state in SQLite for API 0.0.1.

Catalog source management can move into platform configuration later by explicit decision.

## D139: API 0.0.1 loads catalog manifests on demand

The API reads and validates catalog manifests on demand.

Do not import all catalog entries into SQLite before use.

Do not require a startup catalog index in API 0.0.1.

## D140: Catalog directory slug must match metadata.name

The directory slug and manifest `metadata.name` must match.

Do not silently normalize mismatches.

## D141: Duplicate catalog entries require explicit source selection

Duplicate catalog entries with the same kind and name across configured roots are an error unless the caller explicitly selects a source.

Do not let later roots silently override earlier roots.

## D142: Manifest validation starts with typed Python domain models

Validate manifests with typed Python/Pydantic domain models in API code first.

Do not add canonical JSON Schema files under `schemas/` until Fer approves the concrete validation schema.

Reject unknown manifest fields once canonical validation models exist.

## D143: Install selects catalog kind and name

Install by catalog kind and name, plus optional explicit source when needed.

Do not make arbitrary install-from-path the main API or UX flow.

## D144: Installed catalog metadata stores digest by default

At install time, store catalog kind, catalog name, catalog version when available, catalog source id, catalog source path snapshot, and SHA-256 digest of the manifest file content.

Do not store a full manifest snapshot by default.

Store a full manifest snapshot only if implementation proves it is necessary for concrete behavior such as stable replay, import/export, or debugging.

## D145: Draft manifests remain non-canonical

Temporary draft manifests stay under `.agents/drafts/manifests/`.

Drafts remain non-canonical until API validation models exist and Fer approves promotion.

Do not treat drafts as implementation contracts.

## D146: Catalog metadata.version remains optional

`metadata.version` remains optional for catalog entries.

Installed records store version if present and always store manifest digest.

## D147: Reconciliation runs as an API-owned background worker

API 0.0.1 uses an API-owned in-process background reconciler.

The reconciler reads desired state from SQLite and reconciles Nephos-owned resources into Kubernetes.

## D148: Mutating API calls return after enqueue

Mutating API calls write desired-state changes and a reconciliation request in one database transaction.

The API returns after the transaction commits.

The API should not wait for Kubernetes convergence before returning.

## D149: Reconciliation requests target one resource

Each reconciliation request targets one App instance, Service instance, binding, or platform domain configuration target.

## D150: Reconciliation request states are accepted

Accepted reconciliation request states are:

- `pending`
- `running`
- `succeeded`
- `failed`
- `blocked`

## D151: Reconciliation handlers are idempotent

Reconciliation handlers must be idempotent and safe to retry.

Handlers reconcile Nephos-owned resources only.

Nephos must not mutate Kubernetes resources it does not own.

## D152: Initial reconciliation concurrency is serialized

The first reconciliation worker is a single serialized worker.

This is acceptable for a single-user local-first platform, including beyond API 0.0.1 until real usage proves queue concurrency is needed.

## D153: Reconciliation retry is simple and capped

Simple capped retry is the intended model.

Automatic retry may be deferred from API 0.0.1 if it adds too much implementation weight.

Blocked requests require desired-state changes, user input, or explicit manual reconciliation after the blocker is resolved.

## D154: Reconciler writes latest status snapshots

The reconciler writes latest status snapshots with reasons and evidence.

Status is separate from lifecycle.

Reconciliation state should be visible through API and CLI status.

## D155: Reconciliation failure keeps desired state intact

Failures do not roll back desired state.

When reconciliation fails, Nephos updates request state and status evidence while preserving the desired-state record.

## D156: Phase 1 drift handling is detect and report

Phase 1 detects and reports drift for Nephos-owned resources.

Nephos may reconcile Nephos-owned resources when desired state is explicit or when manual reconciliation is requested.

Nephos should not continuously overwrite runtime drift in ways that hide operator changes without reporting them.

## D157: Install mutation creates installed resources

API install mutation happens through:

```text
POST /apps
POST /services
```

The request body carries catalog reference, optional explicit source, instance name, config, and binding/provider choices.

Do not put install mutation under catalog endpoints as the primary API shape.

Do not make arbitrary YAML path install the primary API shape.

## D158: Lifecycle actions are POST action subresources

Lifecycle actions use:

```text
POST /apps/{appInstance}/actions/{action}
POST /services/{serviceInstance}/actions/{action}
```

Accepted action names are `start`, `stop`, `remove`, and `destroy`.

## D159: Destroy is a confirmed POST action

Keep `destroy` as `POST .../actions/destroy`, not `DELETE`.

Destroy requires explicit confirmation in the request body.

Destroy is destructive platform intent reconciled into runtime/data deletion, not plain API row deletion.

## D160: Dependency-blocked Service lifecycle returns conflict

Stopping, removing, or destroying a Service instance with dependents returns `409 Conflict` with an impact list unless the request explicitly carries `force: true`.

The impact list should include dependent Apps and binding relationships.

## D161: Mutating API responses prefer 202 Accepted

Mutating API calls that create desired-state changes should prefer `202 Accepted`.

Mutation responses use `{ resource, reconciliation, status? }`.

`status` is optional.

The `reconciliation` object must include request id and state.

## D162: Lifecycle actions are idempotent

Repeated lifecycle requests to the same desired state should be idempotent.

When possible, Nephos should avoid duplicate reconciliation work and return the current resource plus no-op or existing pending reconciliation information.

It is acceptable to enqueue reconciliation when needed to verify or converge runtime state.

## D163: Public API paths use installed instance slugs

Public resource paths use installed instance slugs.

Examples:

```text
/apps/paperless
/services/postgres
```

Opaque UUIDs are not the primary public path identifiers in API 0.0.1.

## D164: Install bodies use catalogRef

Install bodies use a `catalogRef` object with `kind`, `name`, and optional `source`.

App installs use `catalogRef`, optional `instanceName`, optional `config`, and optional `bindings`.

Explicit App binding provider selection uses `bindings.<alias>.serviceInstance`.

`alias` is the App requirement alias after defaulting.

`serviceInstance` is the installed Service instance slug.

Service installs use `catalogRef`, optional `instanceName`, and optional `config`.

`catalogRef.source` is required only when needed to disambiguate duplicate catalog entries.

## D165: Lifecycle action bodies share force and confirm

Lifecycle action bodies use common optional fields:

- `force`
- `confirm`

`force` defaults to `false`.

`confirm` is required only for `destroy`.

## D166: Mutation responses use resource/reconciliation/status envelope

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

## D167: Nephos-owned domain errors use a simple envelope

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

## D168: Dependency impact payload is structured

Dependency-blocked lifecycle errors use `409 Conflict`.

Impact details include:

- required force flag
- dependent App instance
- binding id
- binding alias
- capability

## D169: Framework validation errors may remain framework-shaped for 0.0.1

FastAPI/Pydantic framework validation errors may remain in their default framework shape for API 0.0.1.

Do not treat framework validation error shape as stable Nephos product API.

## D170: Database relationships use internal ids and public resources use slugs

Use internal stable text ids for database relationships.

Use unique public slugs for user-addressable resources such as installed App instances and Service instances.

Public API paths continue to use installed instance slugs, not internal ids.

## D171: Core domain tables carry timestamps

Core domain tables should include `id`, `created_at`, and `updated_at`.

User-addressable domain tables should additionally include a unique `slug`.

`schema_migrations` uses migration metadata fields recorded in D177.

## D172: State enums use SQLite CHECK constraints

Use SQLite `CHECK` constraints for accepted enum-like state fields.

At minimum, enforce accepted lifecycle states, reconciliation request states, and status levels.

## D173: SQLite foreign keys are enabled and lifecycle deletes are explicit

Enable SQLite foreign keys.

Use restrictive relationships by default.

Do not rely on broad `ON DELETE CASCADE` to implement Nephos lifecycle semantics.

Deletes for `remove` and `destroy` must happen through explicit domain transactions that preserve accepted lifecycle and data-deletion rules.

## D174: JSON text columns are validated snapshots and payloads only

Use SQLite JSON text columns only for validated snapshots and flexible payloads.

Do not hide authoritative relationships, lifecycle state, dependency tracking, or public identity in generic JSON blobs.

## D175: Reconciliation request columns stay bounded for API 0.0.1

For API 0.0.1, `reconciliation_requests` uses bounded accepted fields:

- `id`
- `target_type`
- `target_id`
- `target_generation`
- `action`
- `payload_json`
- `target_snapshot_json`
- `state`
- `error`
- `created_at`
- `updated_at`

Attempt counters, claimed timestamps, requested-by metadata, explicit backoff columns, and richer worker lease fields are deferred unless implementation proves they are needed before API 0.0.1 is usable.

## D176: Status snapshots are keyed by resource target

Persist latest status snapshots as one row per resource target.

Use a unique key over `resource_type` and `resource_id`.

Do not store latest status JSON directly on each resource row as the primary model.

Status event history remains deferred.

## D177: Schema migrations track version and applied_at

Track applied migrations with:

```sql
schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT)
```

`schema_migrations` should exist in the initial schema.

## D178: Internal ids use typed UUID4 hex prefixes

Use typed internal text ids with resource prefixes and UUID4 hex suffixes.

Initial prefixes:

- App instance: `appinst_<uuid4hex>`
- Service instance: `svcinst_<uuid4hex>`
- binding: `binding_<uuid4hex>`
- platform domain: `domain_<uuid4hex>`
- reconciliation request: `reconcile_<uuid4hex>`
- status snapshot: `status_<uuid4hex>`

## D179: Timestamps are app-generated UTC ISO strings

Use app-generated UTC ISO timestamp strings with `Z`.

Initial representation:

```text
YYYY-MM-DDTHH:MM:SSZ
```

Database columns use snake case such as `created_at`.

API payloads use camel case such as `createdAt`.

## D180: Read payloads are domain snapshots with ids and slugs

Read resource payloads are domain snapshots, not raw database rows.

Installed App and Service snapshots include `id`, `slug`, `kind`, `lifecycle`, catalog identity, config summary, relationship summaries, `createdAt`, `updatedAt`, and optional latest `status`.

Internal ids may appear in read payloads.

Installed App and Service public paths still use slugs.

## D181: Status payloads are structured

Accepted status payload fields are:

- `level`
- `lifecycle`
- `reconciliation`
- `reason`
- `message`
- `evidence`
- `observedAt`

`evidence` is an array of structured facts, not an unbounded raw Kubernetes dump.

Secret values must remain redacted.

## D182: Manual reconcile uses action subresources

Accepted Phase 1 manual reconcile endpoints are:

```text
POST /apps/{appInstance}/actions/reconcile
POST /services/{serviceInstance}/actions/reconcile
POST /bindings/{bindingId}/actions/reconcile
POST /platform/config/domains/actions/reconcile
```

Manual reconcile creates a reconciliation request and returns the normal mutation envelope.

It must not directly mutate Kubernetes inline.

## D183: Catalog read endpoints are read-only resources

Accepted Phase 1 catalog read endpoints are:

```text
GET /catalog/apps
GET /catalog/apps/{name}
GET /catalog/services
GET /catalog/services/{name}
```

Catalog detail endpoints accept optional `source` selection where duplicate catalog entries require disambiguation.

Catalog endpoints are read-only in API 0.0.1.

Install mutation remains owned by `POST /apps` and `POST /services`.

## D184: App read payloads expose bindings and routes

Installed App read payloads use the accepted common snapshot fields and include top-level:

- `catalogRef`
- `config`
- `bindings`
- `routes`
- `status`

Do not hide App relationships under one generic relationship blob as the primary shape.

## D185: Service read payloads expose provides and dependents

Installed Service read payloads use the accepted common snapshot fields and include top-level:

- `catalogRef`
- `config`
- `provides`
- `dependents`
- `status`

Service `dependents` are included directly so Service impact is visible without requiring a separate endpoint for API 0.0.1.

## D186: Binding read payloads are exposed directly

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

Binding output and Secret summaries must not expose secret values.

## D187: Status evidence entries are structured

Status evidence entries use:

- `source`
- `subject`
- `reason`
- `message`
- `observedAt`
- optional redacted `data`

Evidence `data` is for small structured facts only.

Do not expose raw Kubernetes objects, full Helm output, Secret values, or unbounded runtime dumps through evidence.

## D188: Catalog responses use normalized summaries

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

Do not return raw manifest blobs by default.

Raw or full validated manifest output, if needed later, requires an explicit response field or endpoint decision.

## D189: Installed slugs are immutable in API 0.0.1

API 0.0.1 has no rename API.

Installed App and Service slugs are immutable in API 0.0.1.

Future rename, alias, or display metadata update behavior requires a separate decision.

## D190: App binding entries expose binding identity and status

App `bindings` entries use:

- `id`
- `alias`
- `capability`
- `serviceInstance`
- `status`

## D191: App route entries expose route identity and generated URLs

App `routes` entries use:

- `name`
- `visibility`
- `target`
- `canonicalUrl`
- `aliases`
- `status`

## D192: Service provides entries expose capability metadata and output targets

Service `provides` entries use:

- `capability`
- optional `alias`
- optional `version`
- `bindingOutputTargets`

## D193: Service dependent entries expose App and binding impact

Service `dependents` entries use:

- `appInstance`
- `bindingId`
- `bindingAlias`
- `capability`
- `lifecycle`
- `status`

## D194: Binding output summaries are redacted Secret summaries

Binding redacted output or Secret summaries use:

- `target`
- `secretName`
- `namespace`
- `keys`
- `redacted`

`redacted` must be `true` when Secret-related output exists in the summary.

Do not expose Secret values.

## D195: Catalog summaries expose requires routes and provides

App catalog summaries include:

- `requires`
- `routes`

Service catalog summaries include:

- `provides`

Do not return raw manifest blobs by default.

## D196: Nested response status summaries are compact

Nested response entry `status` fields use:

- `level`
- `reason`
- `message`
- `observedAt`

Do not embed full status evidence objects into every nested relationship entry by default.

## D197: App route targets are semantic

App route `target` entries use:

- `port`

The route target matches manifest intent.

Do not expose raw Kubernetes ingress backend shape as the default route target response.

## D198: App catalog requirement summaries use capability alias fields

App catalog `requires` entries use:

- `capability`
- `alias`
- optional `provider`

If the manifest omits the binding alias, `alias` is defaulted from the capability.

## D199: App catalog route summaries use name visibility target

App catalog `routes` entries use:

- `name`
- `visibility`
- `target`

## D200: Service catalog provides summaries include output targets

Service catalog `provides` entries use:

- `capability`
- optional `alias`
- optional `version`
- `bindingOutputTargets`

## D201: Validation error normalization is deferred

FastAPI/Pydantic framework validation errors may remain framework-shaped for API 0.0.1.

Framework validation error shapes are not stable Nephos product API.

Nephos-owned domain errors still use the accepted domain error envelope.

## D202: Destroy keeps desired state until teardown succeeds

Destroy keeps the desired-state row present while teardown is pending.

Do not add `destroying` as a lifecycle state.

The in-progress destroy state is represented by reconciliation/action metadata and, where useful, a delete-request timestamp such as `delete_requested_at`.

After successful teardown, the desired-state row is deleted.

## D203: Reconciliation requests include durable action context

Reconciliation requests include:

- `target_generation`
- `action`
- `payload_json`
- `target_snapshot_json`

Use target snapshots when cleanup or retry cannot safely depend only on the current desired-state row.

## D204: Desired-state rows track generation

Desired-state domain rows include an integer `generation`.

Increment `generation` on desired-state mutation.

Reconciliation and status records may record target or observed generation so stale status can be distinguished from current status.

## D205: API 0.0.1 SQLite writes are single-process and WAL-backed

API 0.0.1 uses:

- one API process
- one serialized reconciler
- short explicit transactions
- `PRAGMA foreign_keys=ON`
- `PRAGMA journal_mode=WAL`
- `PRAGMA busy_timeout=5000`

## D206: Initial migration contains the API 0.0.1 schema

The initial schema lives in:

```text
migrations/0000_initial.sql
```

The initial migration should contain all API 0.0.1 tables and accepted constraints.

Do not create schema imperatively in Python.

## D207: App and Service tables use explicit domain columns

`app_instances` and `service_instances` use explicit columns for:

- `id`
- `slug`
- catalog identity, version, source, and digest
- `lifecycle`
- `generation`
- `config_json`
- `delete_requested_at`
- `created_at`
- `updated_at`

Do not store installed App or Service identity primarily in JSON blobs.

## D208: Binding rows use explicit relationship columns

`bindings` uses:

- `id`
- `app_instance_id`
- `service_instance_id`
- `alias`
- `capability`
- `generation`
- `output_summary_json`
- `created_at`
- `updated_at`

Binding relationships are not generic JSON metadata.

## D209: Platform domains are one row per root domain

`platform_domains` uses:

- `id`
- `name`
- `domain`
- `is_default`
- `generation`
- `created_at`
- `updated_at`

Do not store Phase 1 root domains as an env-only config or one opaque platform config JSON blob.

## D210: Status snapshots use target columns and evidence JSON

`status_snapshots` uses:

- `id`
- `resource_type`
- `resource_id`
- `level`
- `lifecycle`
- `reconciliation`
- `reason`
- `message`
- `evidence_json`
- `observed_generation`
- `observed_at`
- `created_at`
- `updated_at`

Latest status remains one row per resource target.

## D211: Reconciliation requests use target generation and snapshots

`reconciliation_requests` uses:

- `id`
- `target_type`
- `target_id`
- `target_generation`
- `action`
- `payload_json`
- `target_snapshot_json`
- `state`
- `error`
- `created_at`
- `updated_at`

## D212: Initial indexes enforce accepted product rules

Accepted API 0.0.1 indexes and uniqueness rules include:

- unique App instance slugs
- unique Service instance slugs
- unique binding alias per App instance
- one default platform domain
- unique latest status snapshot per `resource_type` and `resource_id`
- reconciliation queue index by `state` and `created_at`

## D213: Repository names are nephos-api and nephos-cli

When distinguishing repositories, this backend/API repository is `nephos-api`.

The separate user-facing CLI repository is `nephos-cli`.

When documentation says `nephos <command>`, it refers to the user-facing command implemented by `nephos-cli`.

Backend-local development/ops commands in `nephos-api` must not use the `nephos <command>` spelling.

## D214: SQLite column types and nullability are conservative

Use:

- `TEXT` for ids, slugs, enum values, timestamps, JSON payloads, and digests
- `INTEGER` for `generation`
- `INTEGER` for booleans such as `is_default`

Use `NOT NULL` on required identity, state, generation, and timestamp columns.

Nullable columns are allowed only for optional fields such as `catalog_version`, `delete_requested_at`, optional messages/reasons/errors, and optional JSON payloads.

## D215: SQLite CHECK constraints enforce accepted states

Use SQLite `CHECK` constraints for:

- lifecycle state
- reconciliation request state
- status level
- `is_default IN (0, 1)`
- `generation >= 1`

## D216: Polymorphic targets use type and id fields

Status snapshots use `resource_type` and `resource_id`.

Reconciliation requests use `target_type` and `target_id`.

Use CHECK constraints for allowed target/resource types.

Validate target existence in repository/domain code.

Do not create separate status or reconciliation tables per target type in API 0.0.1.

## D217: JSON payloads are validated in Python domain models

JSON columns should default to `'{}'` or `'[]'` where the response/domain shape is always present.

Validate JSON payloads in Python/domain models, not through SQLite JSON functions.

## D218: Migration and reset commands are backend-local nephos-api commands

Initialization, migration, and reset commands are backend-local `nephos-api` development/ops commands.

They are not product CLI commands.

Accepted backend-local command spelling:

```bash
uv run nephos-api init
uv run nephos-api db migrate
uv run nephos-api db reset --force
```

`uv run nephos-api init` loads backend bootstrap environment and applies
database migrations. It also ensures one default internal platform domain. If
no internal domain is passed, it uses `nephos.local`.

It must not install Apps, install Services, mutate the selected Kubernetes
cluster, or create runtime reconciliation requests.

Do not document or implement backend-local init/migration/reset commands as `nephos <command>`.

## D219: Backend package layout is src/nephos_api

The backend/API Python package layout is:

```text
src/nephos_api/
```

Fer preferred the shorter `src/nephos/` shape but accepted `src/nephos_api/` to preserve the repository and command boundary with `nephos-cli`.

## D220: Backend-local console command is nephos-api

The backend/API repository exposes a backend-local console command named:

```text
nephos-api
```

The user-facing `nephos` product command remains owned by the separate `nephos-cli` repository.

## D221: Backend startup command is nephos-api serve

The accepted local backend startup command is:

```bash
uv run nephos-api serve
```

This starts the local `nephos-api` process for development.

## D222: FastAPI entrypoint is nephos_api.main:app

The FastAPI app entrypoint is:

```text
nephos_api.main:app
```

## D223: API 0.0.1 implementation starts with the database layer

API 0.0.1 implementation order is:

1. migration and database layer
2. API skeleton
3. catalog loader
4. reconciler

## D224: API bootstrap config uses env vars, with `.env` loading for local dev

API 0.0.1 backend bootstrap configuration uses environment variables.

`nephos-api` may read `.env` from the backend process working directory and
use it only to populate missing process environment variables.

Real environment variables take precedence over `.env` values.

Do not add a structured backend local config file for API 0.0.1.

Do not store backend bootstrap configuration in the Nephos desired-state database.

Accepted bootstrap environment variables:

- `NEPHOS_API_DB_PATH`
- `NEPHOS_API_CATALOG_ROOTS`
- `NEPHOS_API_KUBECONFIG`
- `NEPHOS_API_KUBE_CONTEXT`
- `NEPHOS_API_INTERNAL_DOMAIN`
- `NEPHOS_API_INGRESS_CLASS`
- `NEPHOS_API_RUN_KUBERNETES_TESTS`
- `PULUMI_CONFIG_PASSPHRASE`
- `PULUMI_CONFIG_PASSPHRASE_FILE`

## D225: SQLite DB path uses NEPHOS_API_DB_PATH

`NEPHOS_API_DB_PATH` sets the SQLite database path.

If unset, default to:

```text
.nephos/state/nephos.db
```

The default path is relative to the backend process working directory.

## D226: Migration runner applies SQL files lexically

`uv run nephos-api db migrate` applies pending `*.sql` files from `migrations/` in lexical filename order.

Use the migration filename stem as the `schema_migrations.version` value.

Example:

```text
migrations/0000_initial.sql -> 0000_initial
```

Record a migration version only after the migration succeeds.

Run each migration in an explicit transaction where SQLite allows it.

Dirty or inconsistent migration state fails rather than attempting automatic repair.

Rollback and downgrade commands are not part of API 0.0.1.

## D227: SQLite uses 5000 ms busy timeout and no app-level write retry

SQLite connections should use:

```sql
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
```

Keep transactions short and explicit.

Do not add app-level SQLite write retry logic for API 0.0.1.

## D228: Additional catalog roots use NEPHOS_API_CATALOG_ROOTS

The repo-shipped catalog root is:

```text
catalog/
```

Additional local catalog roots are configured with:

```text
NEPHOS_API_CATALOG_ROOTS
```

`NEPHOS_API_CATALOG_ROOTS` is parsed as a platform path-list.

Configured catalog roots are backend-local configuration for API 0.0.1, not platform desired state.

## D229: Backend pytest markers are unit integration kubernetes

Use these pytest markers:

- `unit`
- `integration`
- `kubernetes`

Tests marked `kubernetes` require a real selected Kubernetes cluster and should
also be marked `integration`.

Default backend test command:

```bash
uv run pytest -m "not kubernetes"
```

Explicit Kubernetes runtime integration test command:

```bash
uv run pytest -m kubernetes
```

## D230: Makefile and task-runner wrappers are deferred

Makefile and task-runner wrappers are deferred.

Raw `uv run nephos-api ...`, `uv run pytest ...`, and `uv run ruff ...` commands are the accepted local command surface until implementation proves wrappers are useful.

## D231: API 0.0.1 catalog source ids are default and local-N

The repo-shipped catalog root uses source id:

```text
default
```

Additional roots from `NEPHOS_API_CATALOG_ROOTS` use source ids in configured order:

```text
local-1
local-2
local-3
```

Source ids are stable only for the current backend configuration and root order.

Catalog responses expose source ids through `source`.

Catalog responses do not expose raw filesystem paths by default.

`sourcePath` is reserved for future backend/debug/detail contexts.

## D232: Catalog source selection uses source ids

Explicit source selection uses source ids in:

- `catalogRef.source`
- catalog detail `?source=`

Do not use raw filesystem paths as catalog source identifiers in API 0.0.1.

## D233: Ambiguous catalog entries return catalog_entry_ambiguous

If a catalog kind/name exists in more than one configured source and the caller does not provide `source`, return HTTP `409 Conflict`.

Use Nephos-owned domain error code:

```text
catalog_entry_ambiguous
```

Error details include `kind`, `name`, and `sources[]` as source ids.

Do not silently pick the first matching catalog root.

## D234: Missing catalog source ids return catalog_source_not_found

If a caller provides a source id that does not exist in the current backend configuration, return HTTP `404 Not Found`.

Use Nephos-owned domain error code:

```text
catalog_source_not_found
```

Error details include the requested `source`.

## D235: Installed records store source id and source path

Persisted installed App and Service records store both:

- catalog source id
- catalog source path snapshot

The API 0.0.1 database columns are:

- `catalog_source_id`
- `catalog_source_path`

## D236: Nephos API tests do not manage cluster lifecycle

`nephos-api` tests do not install, start, stop, reset, or destroy the selected
Kubernetes cluster.

Kubernetes integration tests require a pre-existing reachable Kubernetes
cluster selected through kubeconfig/context.

## D237: Kubernetes target selection uses standard config with env overrides

Backend runtime and Kubernetes integration tests use normal Kubernetes client configuration resolution by default.

API 0.0.1 supports optional overrides:

- `NEPHOS_API_KUBECONFIG`
- `NEPHOS_API_KUBE_CONTEXT`

If those variables are unset, the backend and tests use the standard active kubeconfig/context resolution.

## D238: Kubernetes runtime tests require explicit opt-in and preflight

Kubernetes runtime integration tests require:

- `NEPHOS_API_RUN_KUBERNETES_TESTS=1`
- Kubernetes API reachability

The initial safety guard is explicit opt-in plus API reachability.

Stricter allowed-context/server checks may be added later.

## D239: Default CI excludes Kubernetes runtime integration tests

Default CI runs unit and non-Kubernetes-runtime tests only.

Kubernetes runtime integration tests are local/manual until a later CI decision
defines a runtime job.

## D240: Kubernetes runtime integration tests use generated labeled namespaces

Kubernetes runtime integration tests use generated test namespaces.

Generated test namespaces and test-owned resources must use:

```text
app.kubernetes.io/managed-by: nephos
```

Test cleanup may delete only generated test namespaces/resources that it created and labeled.

## D241: Backend runtime uses the same Kubernetes target resolution as tests

The runtime backend uses the same kubeconfig/context resolution as Kubernetes integration tests.

`NEPHOS_API_KUBECONFIG` and `NEPHOS_API_KUBE_CONTEXT` apply to both.

## D242: Cluster lifecycle remains outside nephos-api

Cluster setup and lifecycle are user-managed or `nephos-cli`-managed for now.

`nephos-api` reconciles into Kubernetes, but it must not start the selected
cluster itself.

## D243: Capability providers install lazily, on demand

`nephos setup` installs only the backbone (OpenBao + console); it does not
install capability providers. When an App/Service is installed and a capability
requirement is unmet, the provider is installed on demand:

- Resolution searches the registered registries in precedence order
  core -> mythos -> community (skipping any not registered).
- Ambiguity (more than one eligible provider) is resolved by an explicit user
  pick, not silent auto-selection.
- A lazily-installed provider persists like a normally-installed service; it is
  not torn down when its consumer is removed.
- Single-user assumption for now; no cross-request race handling.

At install the console shows a modal listing what is missing and what will be
installed, with Install dependencies / Cancel (cancel aborts the original
install too). Reverses the earlier "install providers from setup" intent (see
the ADR 20260715 addendum). Tracked in #79.

## D244: Dependency preflight is a read-only plan endpoint

`GET /catalog/apps/{name}/plan` returns a read-only dependency plan the console
renders before install. Per capability requirement it reports one of four states:

- satisfied: exactly one eligible installed provider (auto-binds).
- needs_selection: more than one eligible installed provider (user picks).
- installable: no installed provider, but >= 1 catalog provider could be
  installed; candidates in core -> mythos -> community order as {name, source}.
- unresolvable: no installed provider and no catalog candidate.

Plan shape: {app:{name,source}, requirements:[{alias, capability, protocol?,
state, installedProviders:[slug], candidates:[{name,source}]}], satisfiable}.
Match is (capability, protocol) equality honoring an optional requirement.provider
pin; eligibility reuses the install path's running-provider rule. The mutating
commit (install chosen providers, then the app) is separate.

## D245: App install can install dependency providers (install directive)

`POST /apps` may carry, per requirement alias, an install directive instead of an
existing-instance selection. `BindingSelection` is a union: exactly one of

- `serviceInstance: <slug>` -- bind an already-installed running instance, or
- `install: {name, source, instanceName?}` -- install that catalog provider
  Service turnkey (config={}) and bind to it.

The provider(s), App, and bindings are created in one atomic transaction. A
requirement with no installed provider and no install directive still fails
closed -- nothing auto-installs without an explicit directive. Fail-fast
validation before the transaction: the chosen provider must provide the
requirement's capability (dependency_provider_incapable) and match a
requirement.provider pin (dependency_provider_pin_mismatch); it installs turnkey
only (config={}); a slug clash -- an existing instance, or the same instance name
from two different providers in one request -- returns
dependency_instance_conflict. Multiple aliases may install the same provider
(same name/source/slug): it is created once and all those aliases bind to it.
Implements #79 (commit half).
