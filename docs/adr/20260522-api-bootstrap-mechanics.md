# API Bootstrap Mechanics

- Status: accepted
- Date: 2026-05-22
- Tags: api, bootstrap, sqlite, migrations, catalog, testing, phase-1

## Context and Problem Statement

API 0.0.1 starts with the migration and database layer.

The backend package and command shape is accepted, but implementation still needs the initial bootstrap mechanics for:

- SQLite database location
- backend-local configuration source
- migration runner behavior
- SQLite busy handling
- catalog root configuration
- pytest markers
- Makefile/task wrapper policy

These mechanics must stay backend-local to `nephos-api` and must not become `nephos-cli` product UX.

## Decision

Use environment variables as the API 0.0.1 backend bootstrap configuration source.

Do not add a structured backend local config file for API 0.0.1.

For local development and manual testing, `nephos-api` may read a `.env` file
from the backend process working directory and use it only to populate missing
process environment variables. Real environment variables take precedence over
`.env` values.

The `.env` file is an environment injection convenience, not a Nephos desired
state source, not platform configuration, and not a product config file.

Do not store backend bootstrap configuration in the Nephos desired-state database.

Accepted bootstrap environment variables:

- `NEPHOS_API_DB_PATH`
- `NEPHOS_API_CORE_REGISTRY_URL`
- `NEPHOS_API_CORE_REGISTRY_PATH`
- `NEPHOS_API_CATALOG_ROOTS`
- `NEPHOS_API_KUBECONFIG`
- `NEPHOS_API_KUBE_CONTEXT`
- `NEPHOS_API_INTERNAL_DOMAIN`
- `NEPHOS_API_INGRESS_CLASS`
- `NEPHOS_API_RUN_KUBERNETES_TESTS`
- `PULUMI_CONFIG_PASSPHRASE`
- `PULUMI_CONFIG_PASSPHRASE_FILE`

Use `NEPHOS_API_DB_PATH` for the SQLite database path.

If `NEPHOS_API_DB_PATH` is unset, default to:

```text
.nephos/state/nephos.db
```

The default path is relative to the backend process working directory. In normal repository development, that means the `nephos-api` repository root.

Use explicit SQL migration files under:

```text
src/nephos_api/migrations/
```

`uv run nephos-api db migrate` applies pending `*.sql` files in lexical filename order.

`uv run nephos-api init` is the expected user-facing backend bootstrap command
for API 0.0.1 development. It loads backend bootstrap environment, applies
pending migrations, creates the local desired-state database if needed, and
ensures one default internal ingress root domain. If no internal domain is
provided by `NEPHOS_API_INTERNAL_DOMAIN` or `--internal-domain`, the fallback is:

```text
nephos.local
```

The backend-local option is:

```bash
uv run nephos-api init --internal-domain <dns-suffix>
```

The initialized domain uses the internal platform-domain name `internal` and is
stored as Nephos desired state. It must not be stored only in `.env`.

`init` must not install Apps, install Services, mutate the selected Kubernetes
cluster, or create runtime reconciliation requests.

Use the migration filename stem as the `schema_migrations.version` value. Example:

```text
src/nephos_api/migrations/0000_initial.sql -> 0000_initial
```

Record a migration version only after that migration succeeds.

Run each migration in an explicit transaction where SQLite allows it.

The migration runner fails rather than attempting automatic repair when migration state is dirty or inconsistent, such as when applied versions do not match local migration files or when a migration fails partway through.

Do not implement rollback or downgrade commands for API 0.0.1.

SQLite connections should use:

```sql
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
```

Keep SQLite transactions short and explicit.

Do not add app-level write retry logic for API 0.0.1.

Use one managed first-party registry as the initial catalog dependency set.
Nephos clones that registry locally during `init`/`serve` when the checkout is
missing.

When the managed checkout already exists, Nephos refreshes it during
`init`/`serve` with a fast-forward-only `git pull` rather than treating any
existing path as valid. This keeps managed catalog manifests current instead of
silently running against a stale checkout.

Nephos refuses to refresh and fails startup when a managed checkout is not a
clean, fast-forwardable checkout of the configured registry. It rejects the
checkout when it:

- has an `origin` remote URL that does not match the configured `registry.url`,
- has uncommitted working-tree changes,
- has local commits ahead of its upstream, or
- has diverged such that a fast-forward is not possible.

The remote-URL check runs first. `git pull --ff-only` and the ahead check both
follow the checkout's own upstream, so a drifted `origin` would let Nephos
refresh from a foreign remote while reporting success for the configured
registry; validating `origin` against the configured URL first is what makes the
remaining guards meaningful. On mismatch Nephos fails fast rather than auto
re-pointing or re-cloning; operators repair the checkout or use the
`NEPHOS_API_CATALOG_ROOTS` escape hatch themselves.

Operators who need local catalog edits must use the `NEPHOS_API_CATALOG_ROOTS`
escape hatch, which replaces the managed dependency set and skips managed
registry synchronization. Managed checkouts are not an editing surface.

The default managed registry URL is:

```text
https://git.fcrozetta.app/nephos/core-registry.git
```

The default managed registry checkout path is:

```text
.nephos/registries/core-registry
```

Use `NEPHOS_API_CORE_REGISTRY_URL` and `NEPHOS_API_CORE_REGISTRY_PATH` only as
backend-local development/test overrides for that managed registry.

Use `NEPHOS_API_CATALOG_ROOTS` as a path-list escape hatch for local catalog
experiments. When set, it replaces the managed core-registry dependency set.

Parse `NEPHOS_API_CATALOG_ROOTS` with the host platform path-list separator, such as `:` on macOS/Linux.

Configured catalog roots and managed registry overrides are backend-local
configuration for API 0.0.1, not platform desired state.

Kubernetes target selection is refined by [Kubernetes Runtime Target and Local Ingress DNS](20260601-kubernetes-runtime-target-and-local-ingress-dns.md).

API 0.0.1 supports optional Kubernetes target overrides:

```text
NEPHOS_API_KUBECONFIG
NEPHOS_API_KUBE_CONTEXT
```

If unset, backend runtime and Kubernetes integration tests use normal Kubernetes client configuration resolution.

Use these pytest markers:

- `unit`
- `integration`
- `kubernetes`

Tests marked `kubernetes` require a real selected Kubernetes cluster.

Kubernetes tests should also be marked `integration`.

The default backend test command should exclude Kubernetes runtime tests:

```bash
uv run pytest -m "not kubernetes"
```

Run Kubernetes integration tests explicitly:

```bash
uv run pytest -m kubernetes
```

Defer Makefile or task-runner wrappers.

Raw `uv run nephos-api ...`, `uv run pytest ...`, and `uv run ruff ...` commands are the accepted local command surface until implementation proves wrappers are useful.

## Considered Options

### Environment variables only

- Good, because API 0.0.1 stays simple.
- Good, because backend bootstrap config does not pollute desired state.
- Bad, because more structured local config may become useful later.

### Environment variables plus backend config file

- Good, because repeated local configuration can be easier.
- Bad, because it adds another config surface before API 0.0.1 needs it.

### DB-stored backend bootstrap config

- Good, because it would make config inspectable through the API.
- Bad, because the database path and catalog roots are needed before desired-state storage is available.

### Default `.nephos/state/nephos.db`

- Good, because local development state stays contained.
- Good, because the default path does not clutter the repository root.
- Bad, because users must know where local state lives when resetting manually.

### Default `./nephos.db`

- Good, because it is obvious.
- Bad, because it clutters the repository root and is easier to commit accidentally.

### Lexical SQL migration runner

- Good, because it is explicit and easy to inspect.
- Good, because it avoids ORM migration framework weight.
- Bad, because rollback and repair remain manual.

### Only support `0000_initial.sql`

- Good, because it is enough before the first usable version.
- Bad, because it creates immediate rewrite work once the second migration appears.

### SQLite busy timeout without app-level retry

- Good, because it handles common single-process contention without hiding concurrency problems.
- Good, because API 0.0.1 already assumes one API process and one serialized reconciler.
- Bad, because future multi-process or heavier write load will need a stronger policy.

### Catalog roots through `NEPHOS_API_CATALOG_ROOTS`

- Good, because local catalog iteration is possible without platform config.
- Good, because multiple roots can be tested early.
- Bad, because source identifier behavior needed a separate decision.

### Pytest `unit`, `integration`, and `kubernetes` markers

- Good, because Kubernetes-dependent tests are explicit.
- Good, because fast tests stay runnable without a cluster.
- Bad, because test authors must keep marker discipline.

### Defer Makefile/task wrappers

- Good, because accepted raw commands exist and wrappers can be added after real repetition appears.
- Bad, because commands are longer until wrappers exist.

## Consequences

Implementation must provide environment-based bootstrap config for the accepted variables.

Implementation must create or use `.nephos/state/nephos.db` by default when no DB path is provided.

Migration implementation must apply SQL files in lexical order and record successful versions in `schema_migrations`.

SQLite setup must enable foreign keys, WAL mode, and a 5000 ms busy timeout.

Catalog loading defaults to the managed core-registry checkout as source
`default`. `NEPHOS_API_CATALOG_ROOTS` is an escape hatch that replaces that
managed dependency set when configured.

Bootstrap must refresh existing managed checkouts fast-forward-only and fail
startup on dirty, ahead, or divergent managed checkouts rather than running
against a stale or locally modified catalog.

Catalog source identifier behavior is refined by [Catalog Source Identity and Errors](20260522-catalog-source-identity-and-errors.md).

Backend tests must use the accepted markers and keep Kubernetes runtime tests out of the default fast test command.

Kubernetes runtime test execution and Kubernetes target selection are refined by [Kubernetes Runtime Target and Local Ingress DNS](20260601-kubernetes-runtime-target-and-local-ingress-dns.md).

Do not add Makefile or task-runner wrapper contracts for API 0.0.1 unless a later decision changes this.

## Open Questions

- exact generated Kubernetes test namespace name format
- stricter allowed-context/server safety checks beyond opt-in and API reachability
- future Kubernetes runtime CI job shape, if Kubernetes integration is added to CI
- Kubernetes client fixture strategy
- coverage expectations
