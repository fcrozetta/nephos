# Nephos Reconciliation

## Core Decision

API 0.0.1 uses an API-owned in-process background reconciler.

The reconciler reads Nephos desired state from SQLite and reconciles Nephos-owned resources into Kubernetes.

The reconciler is not a CLI-side kubectl mutation layer.

The boundary remains:

```text
intent -> API/database desired state -> reconciliation request -> reconciler -> Kubernetes runtime state
```

## API Mutation Contract

Mutating API calls that change desired state must:

- validate intent
- write desired-state changes
- create a reconciliation request
- commit those changes in one database transaction
- return after the transaction and request enqueue succeed

The API should not block on Kubernetes convergence before returning.

The response may expose pending reconciliation/status information.

## Reconciliation Requests

Reconciliation requests are persisted in SQLite.

In-memory-only queues are not the Phase 1 default.

Each request targets one resource target.

Accepted target categories:

- App instance
- Service instance
- binding
- platform domain configuration

Request states:

- `pending`
- `running`
- `succeeded`
- `failed`
- `blocked`

`pending` means the request has been created but not claimed.

`running` means the reconciler has claimed the request.

`succeeded` means the target has reconciled to the current desired state.

`failed` means the reconciler hit an execution/runtime error.

`blocked` means the target cannot reconcile until desired state or user input changes.

Examples of blocked requests:

- required capability/protocol has no eligible Service instance
- multiple eligible Service providers for the same capability/protocol require explicit selection
- required platform root domain configuration is missing
- required runtime mapping source is missing

Reconciliation request ids use:

```text
reconcile_<uuid4hex>
```

Reconciliation requests include durable action context.

Accepted request fields include:

- `target_generation`
- `action`
- `payload_json`
- `target_snapshot_json`

Use target snapshots when cleanup or retry cannot safely depend only on the current desired-state row.

Reconciliation requests may record the desired-state generation they target.

## Worker Model

API 0.0.1 starts with one serialized background worker.

This is acceptable for a single-user local-first platform.

Do not introduce distributed workers, leader election, or in-cluster controller complexity in API 0.0.1.

The reconciler should still be isolated behind module boundaries so it can later move to:

- a separate local daemon
- a worker process
- an in-cluster controller
- a scheduled reconciliation process

## Handler Requirements

Reconciliation handlers must be idempotent.

Handlers must be safe to retry.

Handlers reconcile Nephos-owned resources only.

Nephos-owned Kubernetes resources must be identifiable through accepted Nephos labels and metadata.

Handlers must not mutate Kubernetes resources Nephos does not own.

API 0.0.1 app-scoped provisioning uses internal backend-owned provisioning
handlers called by the reconciler during Binding reconciliation.

Provisioning handlers are Python adapter code, not public Service operation APIs,
CLI commands, manifest-declared scripts, Helm hooks, or user-authored Kubernetes
Jobs.

Binding reconciliation may ask an internal provisioning handler for output values,
then materialize the accepted `app-secret` Secret in the consuming App namespace.

Binding provider selection is protocol-aware. A Service is eligible only when it
provides the App requirement's `capability + protocol`.

Provisioning handler dispatch also uses `capability + protocol`, not capability
alone.

Secret values flow from handler to Kubernetes Secret materialization and must not
be exposed in API responses, status evidence, or redacted binding summaries.

SQLite binding output summaries store redacted metadata only, such as target,
Secret name, namespace, and output key names.

If a required handler is unavailable or cannot produce values, Binding
reconciliation becomes `blocked` with structured evidence.

The API 0.0.1 PostgreSQL app-scoped provisioning handler uses backend-owned
Kubernetes API calls. It reads or creates a Nephos-owned Service-side credential
Secret, reads the PostgreSQL administrator password from the Helm release Secret
using the API 0.0.1 chart convention, executes idempotent `psql` statements
inside the Nephos-owned PostgreSQL runtime pod, and returns the accepted
`host`, `port`, `database`, `username`, `password`, and `uri` output fields.

The PostgreSQL provisioning handler is the `sql/postgres` handler.

Alpha backbone handlers still to implement:

- `object-storage/s3` for SeaweedFS app-scoped bucket/access credentials.
- `oidc/oidc` for Zitadel per-App OIDC client material.
- `service-account/jwt` for Zitadel service account/JWT material.
- `sql/arcadedb`, `opencypher/bolt`, and `opencypher/n4j` for ArcadeDB.
- optional `gremlin/gremlin` and `mongo/mongo` for ArcadeDB when enabled.

Those pod, Secret, SQL, and chart-convention details are adapter internals, not
public manifest, API, or CLI contracts.

## Retry And Failure Semantics

Simple capped retry is the intended model.

Automatic retry may be deferred from API 0.0.1 if it adds too much implementation weight.

Failures do not roll back desired state.

When reconciliation fails, Nephos updates request state and status evidence while keeping desired state intact.

Blocked requests require desired-state changes, user input, or explicit manual reconciliation after the blocker is resolved.

Exact retry count, backoff, polling interval, and request claiming mechanics are implementation details still to define.

## Destroy Reconciliation

Destroy does not add a `destroying` lifecycle state.

The desired-state row remains present while teardown is pending.

Pending destroy is visible through reconciliation/action metadata and status.

After successful teardown of runtime objects and persistent data, the desired-state row is deleted.

Failed destroy keeps enough desired-state identity to report status and retry cleanup.

Do not infer destructive cleanup only from Kubernetes labels after deleting Nephos desired state.

## Manual Reconcile

Manual reconcile uses action subresources:

```text
POST /apps/{appInstance}/actions/reconcile
POST /services/{serviceInstance}/actions/reconcile
POST /bindings/{bindingId}/actions/reconcile
POST /platform/config/domains/actions/reconcile
```

Manual reconcile creates a reconciliation request and returns the normal mutation envelope.

It does not directly mutate Kubernetes inline.

## Status Updates

The reconciler writes latest status snapshots with reasons and evidence.

Status is separate from lifecycle.

Status should make reconciliation state visible to the API and CLI.

Status snapshots may record the observed desired-state generation.

Clients can compare observed generation against current desired-state generation to distinguish fresh status from stale status.

## Drift Handling

Phase 1 detects and reports drift for Nephos-owned resources.

Nephos may reconcile Nephos-owned resources when desired state is explicit or when manual reconciliation is requested.

Nephos should not continuously overwrite runtime drift in ways that hide operator changes without reporting them.

Nephos must not mutate resources it does not own.

## Pulumi Provider Runtime Invocation

The accepted forward runtime-provider direction is an internal Python Pulumi
provider package behind the reconciler.

Nephos owns meaning.

Pulumi performs labor.

The reconciler calls Pulumi-backed provider code through narrow Python
interfaces only.

API handlers and CLI clients do not call Pulumi directly.

Pulumi state is observed provider state, not canonical Nephos product state.

If Nephos desired state and Pulumi state disagree, Nephos desired state wins.

API 0.0.1 internal App and Service provider implementations are Python-only.

The expected internal package direction is:

```text
nephos_api.providers
```

Provider packages may manage runtime App deployment, runtime Service
deployment, generated Kubernetes resources, Helm releases through Pulumi
Kubernetes/Helm support, app-scoped Service resources, and redacted provider
status normalization.

API 0.0.1 runtime deployment dispatch uses:

```text
src/nephos_api/providers/
```

The default deployment path is:

```text
ProviderRuntimeDeployer
-> PulumiHelmProvider
-> Pulumi Automation API
-> kubernetes:helm.sh/v3:Release
```

Pulumi state uses a local file backend by default:

```text
.nephos/pulumi/state
```

Pulumi workspaces use:

```text
.nephos/pulumi/workspaces
```

Stack names match runtime names:

```text
app-<slug>
svc-<slug>
```

The host running `nephos-api` must have the Pulumi CLI available on `PATH`.
If the CLI is missing, reconciliation blocks with `pulumi_cli_missing`.

The Pulumi local file backend requires a configured secrets provider through
`PULUMI_CONFIG_PASSPHRASE` or `PULUMI_CONFIG_PASSPHRASE_FILE`.

If neither variable is set, reconciliation blocks with
`pulumi_passphrase_missing` before stack creation.

Direct Helm is secondary for Services.

Services need typed provider actions beyond generated config files:

- install runtime resources
- update runtime resources
- start and stop runtime workloads
- remove runtime deployment while preserving data
- destroy runtime deployment and Service-owned data after confirmation
- provision and deprovision app-scoped binding resources
- produce redacted status/evidence

For Services, Helm charts may be packaging inputs used by the Python Pulumi
provider, but the provider action contract is Nephos-owned Python code.

Provider packages must not define the public product model, lifecycle semantics,
dependency graph, source of truth, or secret exposure policy.

Release names, stack names, and namespaces must preserve accepted runtime
identity:

- `app-<slug>`
- `svc-<slug>`

`NEPHOS_API_KUBECONFIG` and `NEPHOS_API_KUBE_CONTEXT` remain bootstrap inputs
for runtime provider configuration.

Generated Pulumi programs, previews, apply results, Helm values, and provider
state are runtime artifacts.

They are not product API, catalog source of truth, committed examples, or
canonical Nephos state.

The previous direct Helm CLI adapter is superseded as the forward direction but
remains useful implementation history and may temporarily exist as a fallback
while Pulumi provider code lands.
