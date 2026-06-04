# K3s Dev Integration Mechanics

- Status: superseded
- Date: 2026-05-22
- Tags: k3s, kubernetes, testing, development, phase-1

Superseded for API 0.0.1 runtime target naming and integration test naming by
[Kubernetes Runtime Target and Local Ingress DNS](./20260601-kubernetes-runtime-target-and-local-ingress-dns.md).
The retained decision is that `nephos-api` tests do not manage cluster
lifecycle and require explicit opt-in before mutating a selected Kubernetes
cluster.

## Context and Problem Statement

Nephos targets K3s as the Phase 1 default/reference runtime backend.

Earlier decisions accepted real Kubernetes integration tests, pytest markers
named `k3s`, and a default backend test command that excludes those tests.

The missing decisions were:

- whether `nephos-api` tests create or manage K3s
- how the backend selects the Kubernetes target
- how K3s integration tests avoid accidental execution against the wrong cluster
- whether K3s tests run in default CI
- how test resources are isolated and cleaned up
- whether backend runtime cluster lifecycle is owned by `nephos-api` or `nephos-cli`

These mechanics must preserve the boundary:

```text
intent -> desired state -> reconcile into Kubernetes
```

They must also keep `nephos-api` from becoming a raw cluster lifecycle manager.

## Decision

`nephos-api` tests do not install, start, stop, reset, or destroy K3s or any
other Kubernetes cluster.

K3s-marked integration tests require a pre-existing reachable Kubernetes
cluster selected through kubeconfig/context.

Kubernetes target selection uses the normal Kubernetes client configuration resolution by default.

API 0.0.1 supports these optional backend environment overrides:

```text
NEPHOS_API_KUBECONFIG
NEPHOS_API_KUBE_CONTEXT
```

If those variables are unset, the backend and tests use the standard kubeconfig/context resolution provided by the Kubernetes client.

Tests marked `k3s` require:

- `NEPHOS_API_RUN_K3S_TESTS=1`
- a reachable Kubernetes API server

The initial safety guard is explicit opt-in plus API reachability.

Stricter context/server/namespace allow-listing may be added later, but the first implementation must not run K3s tests implicitly.

Default CI runs unit and non-K3s tests only.

K3s integration tests are local/manual until a later CI decision defines a
real Kubernetes runtime job.

K3s integration tests use generated test namespaces.

Generated test namespaces and test-owned resources must be labeled:

```text
app.kubernetes.io/managed-by: nephos
```

Test cleanup may delete only generated test namespaces/resources that it created and labeled.

The runtime backend uses the same kubeconfig/context resolution as K3s integration tests.

Cluster setup and lifecycle remain user-managed or `nephos-cli`-managed for now.

`nephos-api` must not start K3s, k3d, kind, kubeadm, or any other cluster
itself.

## Considered Options

### Green: pre-existing Kubernetes cluster, explicit opt-in tests

- Good, because `nephos-api` tests stay focused on backend behavior.
- Good, because cluster lifecycle remains separate from API/reconciler logic.
- Good, because accidental mutation risk is reduced by explicit opt-in.
- Bad, because developers must prepare a compatible Kubernetes cluster before running integration tests.

### Amber: test harness starts and resets K3s or another cluster

- Good, because test setup can be more repeatable.
- Bad, because `nephos-api` would start owning cluster lifecycle before the CLI/setup contract exists.
- Bad, because local machine differences make the harness heavier and more fragile.

### Red: run K3s tests against whatever kubeconfig is active

- Good, because it is easy to implement.
- Bad, because it can mutate the wrong cluster.
- Bad, because Kubernetes-dependent tests would become unsafe and surprising.

### Green: normal kubeconfig resolution plus explicit env overrides

- Good, because it matches standard Kubernetes client behavior.
- Good, because local developers can override config without adding another backend config file.
- Bad, because users still need to know which context is active.

### Red: hardcoded K3s kubeconfig path

- Good, because it is simple on one machine.
- Bad, because it breaks common local setups and adjacent CLI workflows.

### Green: default CI excludes K3s integration

- Good, because CI remains lightweight while API 0.0.1 is being shaped.
- Good, because K3s CI setup can be designed deliberately later.
- Bad, because runtime reconciliation coverage depends on local/manual runs for now.

### Amber: CI runs K3s integration from day one

- Good, because runtime regressions are caught earlier.
- Bad, because it adds infrastructure weight before the first implementation is stable.

## Consequences

Implementation must not add backend test code that installs, starts, stops, resets, or destroys K3s.

Implementation must provide Kubernetes target resolution for backend runtime and K3s tests using:

- normal Kubernetes client config resolution
- optional `NEPHOS_API_KUBECONFIG`
- optional `NEPHOS_API_KUBE_CONTEXT`

K3s tests must fail or skip before mutation unless `NEPHOS_API_RUN_K3S_TESTS=1` is set and the Kubernetes API is reachable.

The default backend test command remains:

```bash
uv run pytest -m "not k3s"
```

The explicit K3s integration command remains:

```bash
uv run pytest -m k3s
```

Default CI must not run K3s tests until a later decision accepts a Kubernetes
runtime CI job.

K3s integration tests must use generated namespaces and ownership labels so cleanup is bounded.

`nephos-api` can reconcile into Kubernetes, but it does not own cluster setup
or cluster lifecycle.

## Open Questions

- exact generated test namespace name format
- exact stricter allowed-context/server safety check beyond opt-in and reachability
- future Kubernetes runtime CI job shape, if K3s integration is added to CI
- exact Kubernetes client fixture implementation
- exact `nephos-cli` local backend and cluster setup workflow
