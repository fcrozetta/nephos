# A `kv` capability, and per-binding isolation without per-app databases

- Status: proposed
- Date: 2026-08-25
- Tags: provisioning, bindings, capabilities, valkey, redis, isolation, licensing

## Context and Problem Statement

Every capability provider Nephos has today hands each binding its own *container*
for data: postgres and mariadb create a database and a user, arcadedb a database,
seaweedfs a bucket and a scoped identity. `provision_binding` returns credentials
to a private namespace, and isolation follows from the container.

Valkey has no such container. Its numeric db indexes look like one and are not:
they are not an ACL boundary, and a binding user can `SELECT` any index (verified
on 8.1). So adding Valkey raises two questions the existing providers never had to
answer — what the capability is called when it is not a database, and what
isolation means when the store has no per-app partition.

## Decision Drivers

- Isolation must be something Redis actually enforces, not something the manifest
  merely describes.
- The binding output contract should stay recognisable to an app that already
  binds postgres or mariadb.
- Naming should extend ADR 20260824 rather than reopen it.
- The community registry asks for open-source-compatible licensing, which is what
  selected the engine in the first place.

## Decision Outcome

### Capability `kv`, protocol `redis`, engine `valkey`

`kv` names the interface, `redis` names the wire protocol — the same split as
`sql`/`postgres` and `sql`/`mysql`. `cache` was rejected: it names a *use case*,
and the same instance is equally a session store, a queue and a rate limiter. A
future memcached provider would be `kv`/`memcached` and slot in without renaming
anything.

**The protocol stays `redis` even though the product is Valkey**, and the
precedent is exact: mariadb declares `protocol: mysql` because it speaks the
MySQL wire protocol, not because it is MySQL. Valkey speaks RESP unchanged, so an
app declaring `kv`/`redis` binds either engine with an unmodified client library.
Naming the protocol `valkey` would assert a wire format that does not exist, and
would stop a Redis service and a Valkey service from being interchangeable
providers of the same requirement — which is the entire purpose of matching on
(capability, protocol). The binding `uri` keeps the `redis://` scheme for the same
reason: it is what client libraries parse.

Engine naming follows ADR 20260824: one bare-named engine per Service, named for
the provisioner. `kv` is unclaimed, so unlike mariadb there is no collision to
resolve — but the engine is still `valkey` rather than the free capability name.
Taking `kv` would read well today and recreate the `sql`/`mysql` asymmetry the
moment a second `kv` provider appears; naming the provisioner scales to N
providers with no further decision. That postgres holds `sql` is grandfathered,
and ADR 20260824 already notes it is really `sql-postgres` under a legacy name.

### Isolation is a per-binding ACL user scoped to a key prefix

Each binding gets `ACL SETUSER <user> reset on #<sha256> ~<prefix>* &<prefix>* +@all -@dangerous`,
with `prefix = nephos:<app>:<alias>:`, persisted with `ACL SAVE`.

Four parts, each of which fails silently if dropped. All four were verified
against Valkey 8.1 (and identically against Redis 8.2) rather than reasoned about:

- **`reset` first.** `ACL SETUSER` is additive. Re-provisioning after a prefix
  change without `reset` leaves the old pattern granted — correct on the first
  run, wrong on the second.
- **`-@dangerous` is the isolation, not hygiene.** Key patterns do not constrain
  `FLUSHALL`. Measured: a user with `~mine:*` and plain `+@all` was denied
  `GET other:binding:key` with `NOPERM` and then wiped that key with `FLUSHALL`.
  Without this token an app cannot read its neighbour's data but can destroy all
  of it. It also removes `CONFIG`, `ACL` and `SHUTDOWN`, so a binding cannot
  escalate its own grants.
- **The channel grant.** Valkey defaults `acl-pubsub-default` to `resetchannels`
  (confirmed on Valkey 8.1 and Redis 7.2/8.2), so a key-pattern-only user has no pub/sub at
  all.
- **`ACL SAVE`, checked as strictly as the grant.** Runtime ACL changes are
  in-memory. An unsaved `SETUSER` provisions cleanly, the app connects, and then
  every binding fails at once the next time the pod restarts. The mirror case
  matters too: an unsaved `DELUSER` is resurrected by a restart.

The cost is real and is pushed to the app: **Valkey enforces the key pattern but
never rewrites keys**, so an app that ignores the prefix gets `NOPERM` on its
first write, and no client library prefixes by default. That is why `keyPrefix`
is a binding output rather than an implementation detail.

`KEYS` and `INFO` fall inside Valkey's `@dangerous` category and are therefore
denied. `SCAN` covers the former. If a client library calls `INFO` on connect,
adding `+info` is a one-token relaxation.

### The credential reaches the exec payload as a hash, not a password

`ACL SETUSER` accepts `#<sha256-hex>` in place of `>plaintext`. Valkey stores that
same digest internally and authentication requires the preimage, so the exec
command array — which Kubernetes records verbatim in its audit log — carries a
verifier rather than a usable secret. The admin credential is not in the payload
at all: `redis-cli` reads `REDISCLI_AUTH` from the container environment.

This closes for Redis the gap issue #112 records for the SQL providers, where
per-binding passwords still reach argv inside `IDENTIFIED BY '...'`. It holds only
while passwords stay high-entropy: the hash is unsalted single-round SHA-256,
fine against `secrets.token_urlsafe(24)` and worthless if anyone later shortens it
or lets a caller supply it. Valkey also rejects any hash that is not exactly 64
lowercase hex characters — and `valkey-cli` exits 0 while rejecting it, which is
why output is parsed.

### `requirepass` is not used

**When `aclfile` is configured, Valkey silently ignores `requirepass`.** Measured
on Valkey 8.1, identically to Redis 8.2: an empty ACL file plus `--requirepass` produced
`user default on nopass ~* &* +@all` and answered an unauthenticated `PING` with
`PONG`. The obvious configuration ships a wide-open server. The `default` user is
therefore defined in the ACL file, seeded from the Service Secret.

Because binding users are saved into that same file, the seed rewrites only the
`user default` line rather than the file — which also makes rotating the Secret
take effect, where a create-if-absent seed would silently keep the old password.

### Readiness probes for `PONG`, not for an exit code

`valkey-cli ping` exits **0** even when the server answers `NOAUTH` (measured), so
a bare `["valkey-cli","ping"]` probe is vacuous in exactly the way
`mysqladmin ping` is. The probe matches the reply text.

## Considered and rejected

- **`cache` as the capability.** Names a use case, not an interface.
- **Isolation by db index.** Not an ACL boundary; a binding user can `SELECT`
  freely. It would have been isolation in the manifest and nowhere else.
- **A shared credential with no ACL user.** Cheapest, and gives no revocation
  path, no per-app audit trail, and no boundary at all.
- **`+@all` without `-@dangerous`.** Rejected on measurement, see above.
- **Passing the credential over the exec stdin channel.** Would also keep it out
  of argv, but no provisioner uses that channel today and `valkey-cli` needs EOF to
  exit, which the Kubernetes `WSClient` does not cleanly provide. The hash
  achieves the same result with the existing exec shape.

## Why Valkey rather than Redis or Dragonfly

The requirement was an OSS engine. That eliminated the original Redis pin on
licence grounds and made the choice a measured comparison rather than a
preference.

| Engine | Licence | OSI | Outcome |
|---|---|---|---|
| **Valkey 8.1** | BSD-3-Clause (Linux Foundation) | yes | **chosen** |
| Redis 7.2 | BSD-3-Clause | yes | last BSD Redis; superseded by Valkey's line |
| Redis 7.4 | RSALv2 / SSPL | **no** | fails the requirement |
| Redis 8.x | AGPLv3 | yes | OSI, but copyleft beyond the rest of the catalog |
| Dragonfly 1.35 | BSL 1.1 | **no** | fails the requirement, and see below |

Valkey was additionally verified to be a drop-in for the provisioning logic
already built: the exact command sequence, the `#<sha256>` password form, `reset`,
`-@dangerous`, `ACL SAVE`, `REDISCLI_AUTH`, uid 999, `/data` ownership and the
probe's exit-code behaviour all matched Redis 8.2 result-for-result.

Dragonfly was measured too, and would have forced the isolation model to change
rather than just the image, which is worth recording:

- **`#<sha256>` is rejected** (`ERR Unrecognized parameter #…`), so only
  `>plaintext` works. The per-binding password would land in the exec argv and
  therefore the Kubernetes audit log — a regression of the property this ADR
  relies on, and the one item with no workaround.
- **`reset` is unsupported** (`ERR Unrecognized parameter RESET`). `DELUSER` then
  `SETUSER` works but is two non-atomic commands, so a live app reconnecting
  mid-reconcile can fail. The additive hazard is real there: a second `SETUSER`
  without reset accumulated `~old:* ~new:*`.
- **Auth and ACL persistence appeared mutually exclusive** in the two
  configurations tested: `--requirepass` alone authenticates but `ACL SAVE` fails
  (`not configured to use an ACL file`), while adding `--aclfile` made `ACL SAVE`
  succeed and left unauthenticated `PING` answering `PONG`. Not exhaustively
  explored, but disqualifying on the licence alone.

For the record, Dragonfly *does* have `@dangerous` and 25 ACL categories, and
`-@dangerous` does protect a neighbour's keys there — an earlier reading that
suggested otherwise was a truncated `ACL CAT` in the test, not a Dragonfly defect.

## Relation to existing ADRs

- 20260824 (one bare-named engine per Service): **APPLIED**, not amended. `kv` is
  unclaimed, so the rule resolves with no collision.
- 20260721 (binding provisioning entitlements): **CONSISTENT**. The engine
  declares `recognized_entitlements = {"admin-credentials"}`, matching sql and
  mysql, and only an entitled binding causes the Service Secret to be read.
- 20260630 (binding output contracts): **EXTENDED**. `host`, `port`, `username`,
  `password`, `uri` and the entitled `adminUsername`/`adminPassword` keep their
  meanings. `keyPrefix` is new, and has to be: it is the one part of the isolation
  the platform cannot enforce on the app's behalf.
- 20260816 (seaweedfs S3 provisioning): **FOLLOWED**. `redis-cli`, like
  `weed shell`, exits 0 on command errors, so success is judged from output text
  through the same `assert_*_succeeded` shape.

## Follow-ups

- **`+info` on binding users**, if client libraries turn out to call it on
  connect. Left denied by default.
- **Valkey has no equivalent of the per-binding-password argv exposure** recorded
  in issue #112, so that issue stays scoped to postgres and mariadb.
- **Replication and backups** are unmodelled, as for the other data services.
  Persistence here is append-only-file on the volume.
