# One bare-named provisioning engine per Service

- Status: proposed
- Date: 2026-08-24
- Tags: provisioning, bindings, capabilities, naming, sql

## Context and Problem Statement

ADR 20260718 called the provisioning engines "capability-typed" and named them
after capabilities: `sql`, `oidc`, `opencypher`, `object-storage`. Read literally
that implies one engine per capability, and it is the rule stated inline in
`main._build_provisioning_engines`: "Engine name follows the capability name, as
sql / oidc / opencypher do."

Adding MariaDB as a `sql`/`mysql` provider looks like the case that breaks the
rule, because `sql` is already PostgreSQL's engine and
`EngineRoutingBindingProvisioner` dispatches on the engine **name only**
(`self._engines[name]`).

It is not the case that breaks the rule, because the rule is already not what
ADR 20260718's wording says. **ArcadeDB is a second provider of `sql` today.** Its
manifest declares `capability: sql, protocol: arcadedb` alongside `opencypher`
(over `bolt` and `n4j`), `gremlin` and `mongo`, and
`ArcadeDBAppScopedProvisioner._CORE_PROTOCOLS` contains `("sql", "arcadedb")`. Its
engine key is `opencypher`.

So the collision has a precedent and a resolution, and the question is only
whether MariaDB follows it.

## Decision Drivers

- Consistency with how the collision was already resolved, over inventing a
  second scheme for the same problem.
- The name must select an implementation unambiguously.
- Nothing may change for the PostgreSQL path or for any installed manifest.

## Considered Options

- Bare per-Service name: `mysql`
- Protocol-qualified name: `sql-mysql`
- One `sql` engine dispatching internally on `context.protocol`

## Decision Outcome

Chosen option: **`mysql`** — a bare, unqualified engine name, one per Service,
following `opencypher`.

This ADR does not introduce a convention; it records the one arcadedb already
established and corrects ADR 20260718's wording. The actual rule is:

- An engine name identifies a **provisioner**, not a capability. One Service, one
  engine, one bare lowercase name in a flat namespace.
- The name need not be a capability the Service provides, and need not be the only
  one it provides. `opencypher` serves arcadedb's `sql`, `gremlin` and `mongo`
  bindings too.
- **The `(capability, protocol)` narrowing belongs inside the engine**, not in its
  name — `_CORE_PROTOCOLS` in arcadedb, `_is_postgres_binding` in postgres,
  `_is_mariadb_binding` in mariadb. That predicate is what stops an engine
  answering for a binding it does not own.

### Positive Consequences

- The engine set stays a flat namespace of short names with no two naming styles
  in it: `sql`, `oidc`, `opencypher`, `object-storage`, `mysql`.
- Zero change to postgres, its manifest, or any installed row.
- The next provider of an already-claimed capability has a precedent to copy
  rather than a decision to re-litigate.

### Negative Consequences

- Uniqueness is by convention, not by construction. `mysql` is unique only because
  no other capability currently uses a protocol of that name; two capabilities
  sharing a protocol name would collide, and a collision in a dict literal is one
  engine silently shadowing the other rather than an error.
- Mitigation is cheap and belongs with whoever hits it first: the engine set is a
  single dict in one function, so a duplicate-key assertion at construction turns
  the silent shadow into a startup failure. Not added here — it is unrelated to
  MariaDB and would be the first such guard in the file.
- The engine name no longer tells a reader which capability is affected, so
  `provisioning_engine_unknown: 'mysql'` is slightly less self-explanatory than a
  qualified form would have been.

## Pros and Cons of the Options

### `mysql` (chosen)

- Good, because it is the shape arcadedb already uses for the same collision.
- Good, because it keeps one naming style across the whole engine set.
- Good, because it is the smallest diff and touches nothing that works.
- Bad, because uniqueness rests on convention rather than construction.

### `sql-qualified` name, e.g. `sql-mysql`

- Good, because uniqueness follows from the key being the full dispatch tuple.
- Good, because `catalog.py`'s `_default_capability_alias` already produces
  `{capability}-{protocol}` for a default binding alias, so the form exists.
- Bad, because **it contradicts the resolution already in the tree.** Arcade hit
  this exact collision on `sql` and did not qualify; adopting a different scheme
  for the second occurrence leaves two conventions for one problem and makes
  `opencypher` look like the anomaly.
- Bad, because it is asymmetric in practice: `sql` would have to stay
  PostgreSQL's un-migrated name, so the set reads `sql` beside `sql-mysql`.

### One `sql` engine dispatching internally on protocol

- Good, because the engine set stays literally one-per-capability.
- Bad, because it puts the platform's bootstrap database behind a new branch, and
  duplicates a decision `_is_postgres_binding` already makes, in a second place
  where the two can disagree.
- Bad, because it moves provisioner selection out of the inspectable manifest
  field and back into code — the "blind try-each composite" ADR 20260718 removed.

## Relation to existing ADRs

- 20260718 (registry-declared provisioning engines): **CLARIFY**, not amend. The
  dispatch mechanism, trust boundary and declaration-only contract are unchanged.
  Only the description of engine names is corrected: they are per-provisioner
  names, not capability types. The inline comment in
  `main._build_provisioning_engines` stating otherwise is updated with it.
- 20260721 (binding provisioning entitlements): **CONSISTENT**. `mysql` declares
  `recognized_entitlements = {"admin-credentials"}`, matching `sql`, so the
  router's default-deny check behaves identically for both.
- 20260630 (binding output contracts): **RESPECTED**. `mysql` emits the same key
  set as `sql` (`host`, `port`, `database`, `username`, `password`, `uri`, plus
  `adminUsername`/`adminPassword` only when entitled), so an app moves between the
  two providers by changing `protocol` alone.
- 20260727 (service admin credentials): **CONSISTENT**, and the same
  name-the-real-account reasoning applies one level down. MariaDB's superuser is
  `root`, so its config option is `root-password` mapping to `rootPassword`, and
  the runtime Secret key is `root-password` — following arcadedb, whose superuser
  is also `root`, rather than postgres' `admin-password`/`adminPassword`/
  `postgres-password`. Postgres' naming is not wrong for postgres: its superuser
  really is `postgres`. Copying it to MariaDB would have published a credential
  under a name that matches no account MariaDB has.

  Two consequences worth stating, because they are easy to miss:

  - The generated-secret coordinate is derived from the option name
    (`secrets://svc/<slug>/<option>/value`, see `api/resources.py`), so this fixes
    the vault path at `secrets://svc/mariadb/root-password/value`. Free to choose
    now; a rename after any install would orphan a generated secret.
  - The **binding output** keys stay `adminUsername`/`adminPassword`. Those are
    the cross-provider contract above, not a MariaDB name, and renaming them to
    `rootUsername`/`rootPassword` would break the property that an app switches
    provider by changing `protocol` alone. The provisioner marks that boundary
    explicitly where the two naming systems meet.

## Follow-ups

Recorded here rather than done, deliberately:

- **Deduplicate the Kubernetes ownership guards.** `_assert_active_owned_service_namespace`,
  `_assert_owned_credential_secret`, `_read_optional_secret`, `_read_required_secret`
  and `_decode_secret_key` now exist in three provisioners: `postgres.py`,
  `mariadb.py`, and (the namespace check) `zitadel.py`. These are the guards that
  refuse to touch an unowned or terminating namespace and an unowned Secret, so
  drift between copies is a security-relevant divergence, not cosmetic. They belong
  in `kubernetes_runtime.py` beside `binding_secret_labels` and `namespace_labels`.
  Not done in the MariaDB change because it edits the working postgres and zitadel
  paths, which is its own review.
- **Duplicate-engine-key assertion** in `_build_provisioning_engines`, per the
  negative consequence above.
- **Registry-side engine validation.** `catalog.py` accepts any string as
  `provisioning.engine`; a typo is only caught at provision time as
  `provisioning_engine_unknown`, on a binding that is then terminal.
