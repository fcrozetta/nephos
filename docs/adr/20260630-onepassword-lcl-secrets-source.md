# 1Password as LCL Secrets Source

- Status: accepted
- Date: 2026-06-30
- Tags: secrets, 1password, lcl, security, kubernetes, phase-1

Amends:

- `20260517-secrets-model.md`
- `20260517-phase-1-scope.md`

## Context and Problem Statement

The original Phase 1 secrets decision used Kubernetes Secrets as the only
concrete secrets mechanism and deferred external secret managers. That was the
right minimal control-plane shape before Nephos had a selected external secrets
backend.

For the current local Nephos work, Fernando has chosen 1Password as the
operator-owned source of truth. The `Nephos` 1Password service account is scoped
only to Nephos vaults, and the current work is limited to the local `lcl`
environment. LCL components may be destroyed and rebuilt from scratch.

The question is how Nephos should model 1Password without breaking the existing
Kubernetes runtime materialization model or giving agents/apps broad vault
access.

## Decision

Use 1Password as the operator-owned source of truth for Nephos LCL bootstrap and
runtime-support secrets.

Kubernetes Secrets remain the Phase 1 runtime materialization mechanism for
workloads. 1Password stores the durable source item; Nephos materializes only the
minimal selected fields into Kubernetes when a workload needs them.

Use one vault per Nephos environment:

| Environment | Vault | Current vault ID |
| --- | --- | --- |
| `lcl` | `nephos-lcl` | `4dna2bafdf6oluftatzyqzzgpi` |
| `dev` | `nephos-dev` | `rkr45cz6exnt6mh3sk6qrixyuq` |
| `prd` | `nephos-prd` | `utxh564oqvgm2yhqoskknrubq4` |

Rule of thumb:

- **Vault = environment boundary.**
- **Item = Service/App secret bundle.**
- **Fields = concrete credentials, tokens, connection strings, or files.**
- **Tags/folders = organization only, not security.**

For Phase 1 LCL, 1Password access is bootstrap/admin access through the `op` CLI
and the official `OP_SERVICE_ACCOUNT_TOKEN` environment variable. Nephos should
not expose `op`, service account tokens, Connect tokens, or broad vault access to
agents, Apps, or arbitrary package hooks.

Nephos manifests and desired state should store secret references or metadata,
not resolved secret values. Accepted reference forms are:

```text
op://<vault>/<item>/[section/]<field>
```

or structured metadata with the same meaning:

```yaml
secretRef:
  provider: onepassword
  env: lcl
  vault: nephos-lcl
  item: postgres-admin
  field: password
```

For LCL, `nephos-lcl` may be cleared and repopulated as part of rebuilds. This
does not imply the same policy for `dev` or `prd`.

## Initial item conventions

Use lowercase kebab-case item names. Prefer one item per Service/App secret
bundle.

Initial LCL item candidates:

| Item | Purpose | Notes |
| --- | --- | --- |
| `postgres-admin` | PostgreSQL Service administrator/bootstrap credentials | Service-internal/admin material; not app-scoped binding outputs. |
| `zitadel-bootstrap` | ZITADEL initial admin and bootstrap/provisioning material | Includes bootstrap admin credentials and later machine/provisioning material. |
| `seaweedfs-admin` | SeaweedFS/S3 administrator credentials | Service-internal/admin material. |
| `arcadedb-root` | ArcadeDB root/admin credentials | Service-internal/admin material. |
| `onepassword-connect-lcl` | Future LCL Connect credentials/token record | Placeholder convention; Connect deployment is not part of this decision slice. |

Common field names:

```text
username
password
host
port
database
uri
token
client_id
client_secret
credentials.json
```

Protocol-specific binding output fields remain governed by the binding/output
ADRs and implementation plans. 1Password item layout does not change the accepted
runtime Secret key contract for already-defined bindings such as
`sql/postgres`.

## Non-Goals

- Do not deploy 1Password Connect in this slice.
- Do not deploy the 1Password Kubernetes Operator in this slice.
- Do not make 1Password Environments beta part of Nephos Phase 1.
- Do not add canonical schema files under `schemas/`.
- Do not add canonical catalog examples under `examples/`.
- Do not implement secret rotation in this slice.
- Do not make `dev` or `prd` destructible just because `lcl` is destructible.
- Do not let Apps read directly from 1Password.
- Do not let arbitrary agents receive broad 1Password credentials.

## Consequences

The 2026-05-17 secrets ADR is narrowed rather than discarded: Kubernetes Secrets
are still the runtime substrate, but they are no longer the only Phase 1 secrets
mechanism. For LCL, 1Password is the upstream source of selected bootstrap and
runtime-support secrets.

Future Connect/Operator work should be modeled as a Nephos core Service that
provides a secrets capability, not as ad hoc CLI calls from Apps or agents.

Nephos state, API responses, status evidence, logs, and diagnostics must continue
to redact secret values. Storing 1Password item references is allowed; storing
resolved values is not.

## Follow-up Work

- Document the detailed LCL item and field conventions.
- Add a Nephos `onepassword` secrets provider abstraction before runtime code
  reads from 1Password.
- Add a `onepassword-connect` Service package when Connect/Operator runtime
  integration becomes in scope.
- Decide rotation behavior and backup semantics for 1Password-backed secrets.
- Decide when `dev` and `prd` should get dedicated service accounts or Connect
  servers/tokens.
