# OpenBao as an In-Cluster Secret Backend

- Status: accepted
- Date: 2026-07-12
- Tags: secrets, openbao, bao, security, kubernetes, lcl, phase-2

## Context and Problem Statement

Nephos resolves secret references at deploy time. The accepted LCL source is
1Password via `op://` references (see
[1Password as LCL Secrets Source](20260630-onepassword-lcl-secrets-source.md)).

The onepassword-connect Service (an in-cluster 1Password Connect server that Apps
could query at runtime) was removed because it requires a 1Password Business or
Teams tier that is not available in this environment. Nephos still needs an
in-cluster secret backend that Apps and Services can be sourced from, and a
migration path off `op://` toward a Nephos-owned secret store.

## Decision

Add OpenBao as a Nephos-managed in-cluster secret backend, with a `bao://`
secret-reference scheme that coexists with `op://`.

### Reference scheme

`bao://<mount>/<path>/<field>` resolves a field from an OpenBao KV v2 store.
Resolution happens at deploy time, the same as `op://`: desired state stores only
references, never resolved values. A scheme-routing resolver dispatches `op://`
to the 1Password CLI resolver and `bao://` to the OpenBao resolver, so references
can migrate off 1Password incrementally rather than in one cut-over.

### Two runtime modes

- Dev mode (`bao server -dev`): in-memory, auto-unsealed, static root token.
  Insecure by construction. Only registered when `NEPHOS_API_ENV=lcl` and
  `NEPHOS_API_ALLOW_DEV_MODE_OPENBAO=1`. It exists to exercise the `bao://` path,
  not to hold real secrets.
- Persistent mode (`NEPHOS_API_OPENBAO_PERSISTENT=1`): a StatefulSet with a file
  storage backend on a PVC. It supersedes dev mode when enabled and is the
  "core service" path.

### Persistent lifecycle

Persistent OpenBao boots sealed and uninitialized. Its readiness probe treats
sealed/uninitialized as Ready so the rollout completes and post-deploy work can
run. A service self-lifecycle step then, via pod exec, idempotently:

- initializes the store if uninitialized,
- persists the unseal key and root token to a Nephos-owned Kubernetes Secret,
- unseals,
- ensures a KV v2 mount.

An unseal sidecar auto-unseals on pod restart using the managed key (mounted
optionally, absent on the first boot before the Secret exists), so a restarted
OpenBao returns to service without a manual reconcile.

### Token and key custody

The `bao://` resolver takes its token from a provider chain: the Nephos-managed
init Secret (read over the Kubernetes API) first, then a static dev token. So it
authenticates with the live init token, not a static one.

For LCL, the unseal key and root token live in a Nephos-owned Kubernetes Secret
in the OpenBao namespace. This is acceptable for LCL only.

### Single-instance constraints (Phase 2)

To keep the design simple while it proves out, Phase 2 assumes a single OpenBao
instance:

- It must be installed under the slug `openbao` (namespace `svc-openbao`); the
  token provider reads its token from that namespace.
- The init Secret name and keys are fixed constants shared by the lifecycle, the
  unseal sidecar, and the token provider, so they cannot diverge.

### Data-loss guards

- The lifecycle never re-initializes an already-initialized store, and refuses to
  proceed if the store is initialized but the keys Secret is missing (that would
  be unrecoverable data loss requiring manual recovery).
- PVC size and storage class are write-once: changing them after first deploy
  would force-replace the StatefulSet/PVC and destroy stored secrets.

## Public contract

New backend-local environment variables:

- `NEPHOS_API_ENV` (lcl | dev | prd; default prd, fail-closed)
- `NEPHOS_API_ALLOW_DEV_MODE_OPENBAO`
- `NEPHOS_API_OPENBAO_PERSISTENT`
- `NEPHOS_API_BAO_ADDR`
- `NEPHOS_API_BAO_TOKEN` (static fallback only)
- `NEPHOS_API_BAO_KV_MOUNT`

## Non-Goals

- Kubernetes auth method for Nephos (currently uses the managed root token).
- Multiple OpenBao instances or a configurable instance slug / Secret name.
- Production KMS auto-unseal and off-cluster key/PVC backup. In LCL the managed
  Secret plus the PVC are the sole source of truth after migration; losing the
  namespace loses keys and data together.
- Migrating postgres/zitadel to `bao://` in this change (only the reference
  arcadedb path is exercised).
- Moving the OpenBao catalog entry to core-registry (it is a community-registry
  entry today; the runtime provider lives in nephos-api).

## Consequences

- Nephos gains an in-cluster secret backend and a `bao://` scheme alongside
  `op://`, enabling an incremental migration off 1Password.
- The persistent core service is self-healing on restart in LCL, but its key
  custody is in-cluster only; production hardening is required before non-LCL use.

## Follow-up Work

Tracked in [open questions](../../.agents/context/nephos-open-questions.md):

- Kubernetes auth method instead of the managed root token.
- Configurable / multi-instance OpenBao (slug, Secret name, namespace).
- Migrate the backbone (postgres, zitadel) to `bao://` safely (seed the current
  value in place, then switch install config; catalog `service.yaml` is schema,
  not instance config).
- Promote the OpenBao catalog entry to core-registry once the provider stabilizes.
- Production key custody: KMS auto-unseal and off-cluster backup of keys and data.
