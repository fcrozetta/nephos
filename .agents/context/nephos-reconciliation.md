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

- required capability has no eligible Service instance
- multiple eligible Service providers require explicit selection
- required platform root domain configuration is missing
- required runtime mapping source is missing

Reconciliation request ids use:

```text
reconcile_<uuid4hex>
```

Reconciliation requests include durable action context.

Accepted request fields include:

- `action`
- `payload_json`
- target snapshot fields where needed

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
