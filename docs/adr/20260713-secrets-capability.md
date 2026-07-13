# Provider-Agnostic Secrets Capability (`secrets://`)

- Status: accepted
- Date: 2026-07-13
- Tags: secrets, capability, openbao, provider, security, console, phase-2

## Context and Problem Statement

Nephos resolves secret references at deploy time only. Today install config
carries opaque `op://` (1Password CLI) or `bao://` (OpenBao KV) strings that a
`SchemeRoutingSecretResolver` reads and injects into per-service Kubernetes
Secrets. Two problems:

- Those schemes are **implementation-leaky**: a manifest that writes `bao://…`
  is coupled to OpenBao. If consumers name the provider, the Service abstraction
  earns nothing over just running a container.
- There is **no write/generate path**: Nephos can only read pre-existing values,
  so a new user must supply every service password out of band (e.g. from the
  operator's private 1Password vault). That blocks a shareable release.

The goal: the **same App + nephos.yml works with any secrets provider**, and a
new user provides **no service passwords at all** — only a Nephos admin account.

## Decision

### `secrets://` — a provider-agnostic logical reference

```
secrets://<scope>/<name>/<field>
  scope = svc/<slug> | app/<slug> | platform     (owner namespace)
  name  = logical secret name within the scope    (e.g. admin, master-key)
  field = key inside that secret                   (e.g. password, username)
```

The reference is a **logical coordinate Nephos owns**. It never encodes a
provider-native store path — that is what makes it portable across providers.
`op://` and `bao://` are frozen: kept resolving read-only for existing installs,
but no new refs are authored and they are documented as legacy.

### `secrets` capability + `SecretsProvider`

A `secrets` capability with a narrow value-store contract:

```python
class SecretsProvider(Protocol):
    def read_secret(self, path: str) -> dict[str, str] | None: ...
    def write_secret(self, path, fields, *, expected_version=None) -> None: ...  # CAS
    def capability_ready(self) -> bool: ...   # reachable + authed + writable
```

The **provider owns the value store**. Generation policy, idempotency, and the
no-lockout rule live in Nephos (a `SecretsMaterializer`), not the provider —
so backends are interchangeable. OpenBao and (later) 1Password are
implementations behind the capability.

### Resolution: read-or-generate, generation is opt-in

At deploy time a `secrets://` ref routes to the materializer:

1. `existing = provider.read_secret(path)`; if the field is present, **return it —
   never regenerate** (the no-lockout invariant).
2. Otherwise, **only if the field's manifest metadata declares a generation
   policy**, generate and CAS-write it. Default is `gen=none` (fail-closed): a
   ref for a fixed-identity value (a username, an operator-fixed key) is never
   silently randomized.

Generation policy is declared in **catalog manifest config-option metadata** as
a nested `generate` object, not in the ref string — keeping refs clean and
portable:

```yaml
- name: admin_password
  type: string
  generate:
    kind: password   # v1: password only
    length: 32
```

### Provider selection

A `secrets://` ref resolves through the **platform-default secrets provider**
(a platform setting), defaulting to the managed OpenBao instance (slug
`openbao`). The manifest carries no provider identity, so it stays portable; the
environment's default pointer decides the store. In v1 there is only one
provider (managed OpenBao), so the selection is implicit — no pointer table yet.

**Logical → provider path (locked).** The OpenBao KV v2 mapping is:

```
secrets://<scope>/<name>/<field>
  -> mount = <bao_kv_mount>   (default "secret")
     path  = nephos/<scope>/<name>
     field = <field>          (a key inside that KV secret)
```

Nephos-owned values live under the `nephos/` prefix so they never collide with
hand-written `bao://` secrets in the same mount. This convention is a lock-in
(renaming orphans stored values); it is fixed before a second provider lands.

### Bootstrap credential

Exactly one provider-bootstrap credential per provider, **outside** the
`secrets://` graph (no self-reference cycle):

- Managed OpenBao (default): the unseal key + root token, auto-generated on init
  and held in the `openbao-init` Kubernetes Secret. The operator supplies
  **nothing** (self-bootstrapping).
- (Later) 1Password / external OpenBao: an operator-supplied token, documented
  as setup input.

`capability_ready()` fails closed when the bootstrap credential is missing.

### First-run admin (the only human-provided credential)

The Nephos admin account is Nephos's own login, orthogonal to the secrets
capability, and never stored in a secrets provider:

- New `admin_accounts` SQLite table (hashed password). Not reconciled desired
  state (no `status_snapshots`/`reconciliation_requests` entry).
- Synchronous (non-202) `api/auth.py`: `GET /auth/state` → `{adminExists}`;
  `POST /admin/accounts` succeeds **only when zero admins exist** (account-
  takeover guard, since the API is unauthenticated); `POST /auth/login`.
- nephos-console gains a first-run `/setup` flow that creates the admin when none
  exists; the env password (`NEPHOS_CONSOLE_ADMIN_PASSWORD`) is removed. See the
  console ADR-0002.

## v1 scope (decided)

- Backed by the **managed OpenBao only**, self-bootstrapping. Add the OpenBao
  **write/generate** path (KV v2 CAS) that does not exist today.
- **Greenfield generate-if-absent**: a fresh install materializes zero-password
  secrets. This is safe because there is no pre-existing consumer state to lock
  out.
- First-run admin.

## Non-goals (deferred)

- **Adopt/import of existing consumer values.** Flipping an already-deployed
  service (e.g. zitadel's at-rest master key, postgres's PGDATA-baked password)
  to `secrets://` would generate a new value and lock it out. v1 does not migrate
  live installs; the operator destroys+recreates the LCL backbone under
  `secrets://`. A read-existing-then-seed adopt step is future work.
- **1Password provider** behind `secrets://` (proves interchangeability; carries
  a logical-path→item mapping rule and a no-CAS/last-writer-wins caveat to solve
  first).
- **Rotation** (the one operation that can lock out a live consumer; needs a
  dual-secret window design).
- **External/read-only-token OpenBao** write path, and multi-store providers.

## Consequences

- New users get a working control plane with **no operator-supplied service
  passwords**; the only credential is the first-run admin.
- Manifests become provider-portable; swapping the store does not touch App or
  Service manifests.
- The generate path is a new write surface (previously read-only); it must be
  CAS-guarded and read-back-safe.

## Follow-up / open questions

- Who seeds the platform-default provider pointer on a fresh install (CLI seed
  like the internal domain, or the console first-run) — deferred while there is
  only one provider.
- Whether `secrets://` needs a declared `secret` config-option type for
  install-time resolvability guarantees, or stays scheme-blind like today.
- Rotation design (dual-secret window) and the adopt/import step for migrating
  existing installs.
