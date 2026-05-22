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

Do not add a backend local config file for API 0.0.1.

Do not store backend bootstrap configuration in the Nephos desired-state database.

Accepted bootstrap environment variables:

- `NEPHOS_API_DB_PATH`
- `NEPHOS_API_CATALOG_ROOTS`
- `NEPHOS_API_KUBECONFIG`
- `NEPHOS_API_KUBE_CONTEXT`

Use `NEPHOS_API_DB_PATH` for the SQLite database path.

If `NEPHOS_API_DB_PATH` is unset, default to:

```text
.nephos/state/nephos.db
```

The default path is relative to the backend process working directory. In normal repository development, that means the `nephos-api` repository root.

Use explicit SQL migration files under:

```text
migrations/
```

`uv run nephos-api db migrate` applies pending `*.sql` files in lexical filename order.

Use the migration filename stem as the `schema_migrations.version` value. Example:

```text
migrations/0000_initial.sql -> 0000_initial
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

Use one repo-shipped catalog root plus optional configured local filesystem roots.

The repo-shipped catalog root is:

```text
catalog/
```

Use `NEPHOS_API_CATALOG_ROOTS` as an optional path-list for additional local catalog roots.

Parse `NEPHOS_API_CATALOG_ROOTS` with the host platform path-list separator, such as `:` on macOS/Linux.

Configured catalog roots are backend-local configuration for API 0.0.1, not platform desired state.

Kubernetes target selection is refined by [K3s Dev Integration Mechanics](20260522-k3s-dev-integration-mechanics.md).

API 0.0.1 supports optional Kubernetes target overrides:

```text
NEPHOS_API_KUBECONFIG
NEPHOS_API_KUBE_CONTEXT
```

If unset, backend runtime and K3s integration tests use normal Kubernetes client configuration resolution.

Use these pytest markers:

- `unit`
- `integration`
- `k3s`

Tests marked `k3s` require a real K3s cluster.

K3s tests should also be marked `integration`.

The default backend test command should exclude K3s tests:

```bash
uv run pytest -m "not k3s"
```

Run K3s integration tests explicitly:

```bash
uv run pytest -m k3s
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

### Pytest `unit`, `integration`, and `k3s` markers

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

Catalog loading must always include the repo `catalog/` root and may include additional roots from `NEPHOS_API_CATALOG_ROOTS`.

Catalog source identifier behavior is refined by [Catalog Source Identity and Errors](20260522-catalog-source-identity-and-errors.md).

Backend tests must use the accepted markers and keep K3s tests out of the default fast test command.

K3s test execution and Kubernetes target selection are refined by [K3s Dev Integration Mechanics](20260522-k3s-dev-integration-mechanics.md).

Do not add Makefile or task-runner wrapper contracts for API 0.0.1 unless a later decision changes this.

## Open Questions

- exact generated K3s test namespace name format
- stricter allowed-context/server safety checks beyond opt-in and API reachability
- future K3s CI job shape, if K3s integration is added to CI
- Kubernetes client fixture strategy
- coverage expectations
