# Pulumi Provider Boundary

- Status: accepted
- Date: 2026-05-29
- Tags: pulumi, providers, runtime, reconciliation, phase-1

## Context and Problem Statement

Nephos needs a runtime execution layer that can manage Apps, Services,
capability bindings, lifecycle semantics, ingress, and future external
infrastructure without turning Nephos into a weak wrapper around Kubernetes,
Helm, Terraform/OpenTofu, Ansible, or Pulumi.

Previous decisions made Nephos API and SQLite the source of truth for desired
platform state. They also accepted Helm-primary runtime packaging underneath
Nephos manifests and, for API 0.0.1, a backend-owned Helm CLI adapter.

The accepted direction is now to use Pulumi under the hood for provider labor.
Because both Pulumi and Nephos use Python, API 0.0.1 should also constrain
internal App and Service provider packages to Python. Additional provider
implementation languages may be considered later, but they are not part of
API 0.0.1.

## Decision

Nephos owns meaning. Pulumi performs labor.

Nephos remains the canonical product and desired-state layer:

- Apps
- Services
- capabilities
- bindings
- lifecycle state
- dependency impact
- platform domains
- backup and data lifecycle intent
- latest Nephos-aware status
- reconciliation requests

Pulumi is an internal provider execution backend, not the source of truth.

Pulumi state is provider-observed execution state. It must not replace SQLite,
catalog manifests, Nephos relationships, lifecycle state, or binding metadata.

API handlers and CLI clients must not invoke Pulumi directly.

Pulumi runs behind the reconciler through narrow Python provider interfaces.

API 0.0.1 App and Service provider implementations are Python-only. In
practice, that means Nephos-owned provider code lives in internal Python
packages and may use Pulumi Automation API and Pulumi providers to make runtime
resources real.

The first internal package direction is:

```text
nephos_api.providers
  - runtime App deployment providers
  - runtime Service deployment providers
  - app-scoped binding/provisioning providers
  - provider result/status normalization
```

The exact module layout is implementation detail, but the boundary is not:
provider packages receive Nephos desired-state inputs and return redacted
outputs/status. They do not define the product model.

## Provider Roles

Pulumi providers may manage:

- Kubernetes resources
- Helm releases through Pulumi Kubernetes/Helm support
- App runtime resources
- Service runtime resources
- typed Service provider actions
- generated App ingress resources when useful
- Service-side resources needed for bindings
- future DNS, Cloudflare, tunnel, object storage, or external infrastructure

Pulumi providers must not own:

- public API resource shape
- lifecycle verb semantics
- App/Service/capability/binding identity
- dependency graph truth
- destructive confirmation policy
- backup/data lifecycle semantics
- secret exposure policy

## State Ownership Rule

If Nephos desired state and Pulumi state disagree, Nephos desired state wins.

Pulumi refresh/preview/apply output is evidence for reconciliation and status,
not canonical platform state.

Nephos stores secret references and redacted summaries, not raw Pulumi state
dumps or secret values.

Provider outputs must be redacted before writing logs, evidence, status, or
database summaries.

## Lifecycle Rule

Nephos lifecycle verbs remain product semantics:

- install
- start
- stop
- remove
- destroy
- reconcile

They must not collapse into Pulumi create/update/destroy semantics.

For example, App stop still means scale runtime workloads to zero while
preserving desired state, bindings, config, secrets, data, route intent, and
metadata. It is not a Pulumi destroy.

## Service Provider Action Rule

Direct Helm is secondary for Services.

Services need more than config-file deployment. A Service provider must be able
to expose typed internal actions such as:

- install runtime resources
- update runtime resources
- start runtime workloads
- stop runtime workloads
- remove runtime deployment while preserving data
- destroy runtime deployment and Service-owned data after confirmation
- provision app-scoped binding resources
- deprovision app-scoped binding resources
- produce redacted status/evidence

Helm charts may still be useful as a packaging artifact inside a Service
provider, but they do not define the Service behavior model.

For Services, generated Helm values and chart installation are implementation
details underneath the Python Pulumi provider. They are not sufficient as the
provider contract.

The API 0.0.1 Service provider path is therefore:

```text
Nephos Service desired state
-> reconciliation request
-> internal Python Service provider
-> Pulumi program/provider actions
-> optional Helm chart/Kubernetes resources
```

This keeps Service behavior in Nephos-owned provider code rather than scattering
it across chart values, hooks, ad hoc scripts, or catalog YAML.

## Consequences

The direct Helm CLI adapter accepted for API 0.0.1 becomes a transitional
implementation detail and is superseded by the Pulumi provider direction.

Helm chart identity may remain in Nephos manifests where Helm packaging gives
leverage, but Helm execution should happen through the internal provider layer
instead of becoming API, CLI, or catalog source of truth.

For Services specifically, Helm is secondary to the Python Pulumi Service
provider because Service behavior includes lifecycle and binding actions beyond
chart configuration.

Provider operations need explicit lock scopes before concurrency expands beyond
the serialized API 0.0.1 worker.

Likely lock scopes:

- cluster
- namespace
- App instance
- Service instance
- binding

The provider boundary should be thin and concrete. Avoid fake-universal
provider abstractions that hide important App, Service, or capability-specific
behavior.

## API 0.0.1 Implementation Defaults

The initial provider package lives under:

```text
src/nephos_api/providers/
```

API 0.0.1 dispatches App and Service runtime deployment through a
`ProviderRuntimeDeployer`.

The default runtime provider is a Pulumi-backed Helm provider. It uses Pulumi
Automation API with a local file backend.

Default Pulumi local state location:

```text
.nephos/pulumi/state
```

Default Pulumi local workspace root:

```text
.nephos/pulumi/workspaces
```

Each runtime target gets its own workspace under the workspace root.

Stack names use accepted runtime names:

```text
app-<slug>
svc-<slug>
```

The Pulumi Helm provider creates `kubernetes:helm.sh/v3:Release` resources from
Nephos manifest chart identity and Nephos-generated values.

The Pulumi CLI must be installed on the host running `nephos-api`. If it is
missing, runtime reconciliation blocks with reason:

```text
pulumi_cli_missing
```

The Pulumi local file backend also requires a configured secrets provider.
The host process must provide one of:

```text
PULUMI_CONFIG_PASSPHRASE
PULUMI_CONFIG_PASSPHRASE_FILE
```

If neither variable is set, runtime reconciliation blocks before stack
creation with reason:

```text
pulumi_passphrase_missing
```

The provider passes the selected passphrase environment into the Pulumi local
workspace. This is host bootstrap configuration for Pulumi state encryption,
not Nephos desired state and not database-stored platform config.

## Non-Goals

- Do not make Pulumi stack state the Nephos source of truth.
- Do not expose Pulumi programs as user-authored catalog semantics.
- Do not make App lifecycle hot paths depend on arbitrary generated Pulumi code.
- Do not model Services as Helm charts plus config files.
- Do not support multi-language Pulumi provider packages in API 0.0.1.
- Do not add Terraform/OpenTofu or Ansible to the API 0.0.1 hot path.
- Do not expose a general user-facing Service operation API in API 0.0.1.

## Supersedes

This ADR supersedes the API 0.0.1 Helm CLI invocation decision as the forward
runtime-provider direction:

- `20260523-api-0-0-1-helm-invocation-mechanics.md`

The earlier ADR remains useful as implementation history for the direct Helm
adapter that proved the first runtime path.

## Open Questions

- provider operation lock table shape
- exact redacted Pulumi preview/apply evidence fields
