# Authenticated secret reveal for operator-owned credentials

- Status: accepted
- Date: 2026-07-26
- Tags: auth, secrets, api, console, security

Technical Story: an operator cannot retrieve a credential Nephos generated on
their behalf. Follows the retrieval open question recorded in
`.agents/context/nephos-open-questions.md` under the auth/user model.

## Context and Problem Statement

Nephos generates credentials the operator never sees. PostgreSQL's
`admin-password` declares a generation policy, so install requires no input and
nothing is stored in desired state: `config_json` is literally `{}`. The value is
materialized into the secrets provider (`secret/nephos/svc/postgres/admin-password`)
and injected into the runtime Secret. Nothing in the Nephos API or console can
show it.

That is the point of turnkey install, and it is also a hole: Nephos owns a
credential on the operator's behalf and offers them no way to read it back. The
only current paths are `kubectl get secret` and a direct OpenBao read, both of
which bypass Nephos entirely.

Redaction is a separate and lesser problem. Operator-supplied secrets (ArcadeDB
`root-password`) are stored verbatim in `config_json` and masked by
`_redacted_config`; the operator already knows those values. An endpoint that only
un-masks stored config would return nothing for the generated case, which is the
case that actually matters.

The blocker is that `nephos-api` has no request authentication. An in-cluster pod
with no credentials receives `200` from `/services`. Serving secrets from an
unauthenticated endpoint would take "can reach port 8099" and make it equivalent
to "can read every Service credential", where today that requires cluster-admin
RBAC to read Secrets across namespaces. That is privilege escalation, not merely
undoing redaction.

## Decision Drivers

- An operator must be able to read a credential Nephos generated for them,
  through Nephos.
- Do not widen unauthenticated access to secrets.
- Do not require settling the whole API authentication model first; that is a
  larger open question and this need should not block on it.
- Keep knowledge of where secrets live inside `nephos-api`. The console must not
  grow its own secret-store credentials.
- Revocable: a leaked credential must be cancellable without rotating the
  operator's password.

## Considered Options

- bearer token issued by `/auth/login`, gating the reveal endpoint
- re-authenticate per reveal (credentials in the reveal request body)
- console reads the secrets provider directly, gated by its own session
- no reveal path; document `kubectl` and the OpenBao read

## Decision Outcome

Chosen: **an opaque bearer token issued by `/auth/login`, gating a reveal endpoint
that resolves through the secrets provider.**

### 1. Token issuance and revocation

`POST /auth/login` gains `token` and `expiresAt` alongside its existing
`authenticated` and `subject` fields. Additive, so the current console login path
keeps working unchanged.

- **Opaque and hashed at rest.** A random token is returned once; only its hash is
  stored, in a new `admin_tokens` table (migration `0004`). This mirrors how
  `admin_accounts` already stores password hashes: a database read must not yield
  a usable credential.
- **12 hour lifetime**, matching the console's existing session cookie
  (`SESSION_COOKIE_OPTS.maxAge`). A shorter token would expire mid-session with no
  recovery, because the console mints its session from the subject alone and keeps
  no password to re-authenticate with.
- **Revocable.** `POST /auth/logout` deletes the row. Revocation is a row delete
  rather than a password rotation, which is the property a stateless signed token
  could not offer.
- Expired rows are rejected on use and deleted opportunistically.

### 2. Scope: this gates one endpoint, and does not authenticate the API

Only the reveal endpoint requires a token. Every other endpoint keeps its current
behavior. This is deliberate: gating the rest of the API is a breaking change to
every client and depends on the unresolved token/bind/remote-access questions.

**The API remains unauthenticated for everything else.** This ADR does not close
that open question, and must not be cited as having done so.

### 3. The reveal endpoint

```text
POST /services/{service_instance}/config/{option}/actions/reveal
Authorization: Bearer <token>
```

Resolution depends on how the option is defined, which is the crux:

- **Generated option** (declares a `generate` policy): rebuild the coordinate the
  deployer synthesizes, `secrets://svc/<slug>/<option>/value`, and read it through
  `SecretsMaterializer.resolve` (read-only; never generates). This is the path that
  serves the case with no stored value.
- **Operator-supplied option**: return the stored value from desired state, first
  resolving `secrets://`, `op://`, or `bao://` if the stored value is a reference
  rather than a literal.

Failure modes are explicit rather than empty: an unknown option, a non-sensitive
option, or an unconfigured secrets provider each return a distinct error rather
than `null`.

Response reports `source` (`secrets-provider` or `desired-state`) so the operator
can tell a generated credential from one they supplied.

### Positive Consequences

- An operator can read a credential Nephos generated for them, from the console.
- Secret-location knowledge stays in `nephos-api`; the console gains no
  secret-store credentials and no Kubernetes access.
- A leaked token is revocable without rotating the operator's password.
- The generated case works, which the redaction-only framing would have missed.

### Negative Consequences

- A token that can read every Service credential exists for up to 12 hours. Its
  blast radius is the whole secret set, because the endpoint is not scoped per
  service.
- The console stores that token in its session cookie. The cookie is `httpOnly`
  and signed, but `secure` is `false` for local HTTP (already true of the session
  itself), so on a plain-HTTP deployment it is sniffable on the local network.
- Reveal is an audit-relevant action and this ADR adds no audit trail. The status
  and evidence model is the obvious home; deliberately deferred rather than
  half-built.
- One authenticated endpoint alongside an otherwise open API is an inconsistency
  that will read as an oversight until the API auth question is settled.

## Pros and Cons of the Options

### Bearer token from `/auth/login` (chosen)

- Good, because it reuses the existing `admin_accounts` credential store and
  `/auth/login`, so no new credential concept is introduced.
- Good, because revocation is a row delete.
- Good, because it lays the groundwork for gating the rest of the API later.
- Bad, because it settles token lifetime and storage ahead of the broader auth
  decision, which may want different answers.
- Bad, because a leaked token reads every secret until it expires or is revoked.

### Re-authenticate per reveal

- Good, because nothing bearer-shaped is stored anywhere, so there is no token to
  leak.
- Good, because it requires no decision about lifetime or revocation.
- Bad, because the operator re-enters their password per reveal.
- Bad, because it sends the password on each reveal rather than once at login.

### Console reads the secrets provider directly

- Good, because it needs no `nephos-api` change.
- Bad, because the console gains broad secret-store credentials, widening the
  blast radius of the component most exposed to a browser.
- Bad, because it duplicates knowledge of where secrets live outside
  `nephos-api`, which the secrets model depends on being single-sourced.

### No reveal path

- Good, because `kubectl` and OpenBao reads are already correctly gated by
  cluster access.
- Bad, because Nephos generates a credential and then requires the operator to
  bypass Nephos to read it, which makes turnkey install a trap.

## Links

- Follows [Secrets Capability](./20260713-secrets-capability.md) for the
  `secrets://` coordinate and provider contract.
- Related to [OpenBao Secret Backend](./20260712-openbao-secret-backend.md).
- Depends on the auth/user model open question for the eventual API-wide gate;
  see `.agents/context/nephos-open-questions.md`.
