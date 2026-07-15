# Nephos control plane in-cluster (`nephos setup` / `up`)

- Status: accepted
- Date: 2026-07-15
- Tags: runtime-boundary, control-plane, cli, bootstrap, deploy

## Context and Problem Statement

Nephos deploys Apps and Services (and now the console) *into* a Kubernetes
cluster, but the control plane itself runs as a **host process**
(`nephos-api serve`): a Python process reaching the cluster via kubeconfig +
Pulumi, and reaching the managed OpenBao via a host `kubectl port-forward`.

That asymmetry has real costs: the host process gets reaped/restarted out of
band, the OpenBao port-forward is fragile (a dropped forward flips healthy apps
to `blocked`, see #54), and "how do I run Nephos" has no reproducible answer.

We want the control plane to run **in-cluster**, and a first-class way to stand
it up.

## Decision

### Run the control plane in-cluster

`nephos-api` ships as a container image (`ghcr.io/fcrozetta/nephos-api`) and runs
as a Deployment in a `nephos-system` namespace (`deploy/nephos-incluster.yaml`):

- **Auth**: the in-cluster ServiceAccount (`load_kubernetes_config` already falls
  back to in-cluster config when no kubeconfig/context is set).
- **RBAC**: broad (`cluster-admin`). The control plane creates namespaces,
  workloads, secrets, ingresses and drives Pulumi cluster-wide, so it is
  privileged by nature. Least-privilege is a deferred follow-up.
- **State**: a PVC holds the SQLite desired-state, the Pulumi state, and the
  cloned catalog registries.
- **Secrets**: reaches the managed OpenBao via in-cluster DNS
  (`svc-openbao-openbao.svc-openbao:8200`) — **no port-forward** (closes #54).

### Runtime boundary + CLI

The engine runs in-cluster; a **host-side CLI** bootstraps and drives it. Two
commands:

- **`nephos setup`** — the full, one-time bootstrap of an environment: create the
  cluster, configure local routing, deploy the control plane, and (greenfield)
  let it build the backbone. Heavy, run once per environment.
- **`nephos up <name>`** — bring up a named instance (its control plane). Names
  map to the PRD/DEV/LCL topology.

### Desired-state ownership

The in-cluster control plane owns **its own** SQLite desired-state on the PVC. It
is the single source of truth for what that environment should run; there is no
shared/host desired-state once it is in-cluster.

## Non-goals / open questions

- **Adopting an existing host-built cluster.** A fresh in-cluster control plane
  starts with an empty desired-state and does not know about a backbone deployed
  earlier by a host process. v1 is **greenfield**: `nephos setup` builds
  everything. Migrating an existing install means moving the desired-state DB onto
  the PVC or a `nephos setup` from scratch; a proper adopt step is future work.
- **The multi-instance model.** Exactly what `nephos up <name>` keys on
  (kube-context per instance, a config file listing instances, cluster name) is
  not yet settled — it will be pinned when the CLI lands, alongside the PRD/DEV/LCL
  boundaries (separate data roots, secrets, domains, destructive-action rules).
- **Least-privilege RBAC** instead of `cluster-admin`.
- **Bootstrap ordering** in greenfield `setup`: the control plane starts (no
  OpenBao needed to serve), deploys OpenBao (self-bootstrapping), then the rest
  (which may use generated secrets, now that OpenBao is up).

## Consequences

- Reproducible: a tagged image + a manifest, applied by `nephos setup`, instead of
  a host process someone remembers to run.
- Removes the OpenBao port-forward fragility (#54).
- The console's `api-url` moves from `host.k3d.internal:8099` to the in-cluster API
  Service.
- The control plane holds `cluster-admin` — an accepted, documented risk for now.
