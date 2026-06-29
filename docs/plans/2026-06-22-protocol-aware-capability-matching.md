# Protocol-Aware Capability Matching Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Teach Nephos catalog, install, database state, and binding selection to match providers by `capability + protocol`, not broad database labels.

**Architecture:** Catalog entries declare the semantic access model as `capability` and wire/client compatibility as `protocol`. App install persists the resolved pair on bindings so later reconciliation does not need to reinterpret changed manifests. Existing `capability`-only manifests remain valid during migration by treating `protocol` as optional.

**Tech Stack:** Pydantic catalog models, SQLite migrations, repository helpers, FastAPI install path, pytest.

---

## Task 1: Add protocol fields to catalog models

**Objective:** Allow App requirements and Service provided capabilities to include `protocol`.

**Files:**
- Modify: `src/nephos_api/catalog.py`
- Test: `tests/test_catalog_loader.py`
- Test: `tests/test_catalog_api.py`

**Steps:**
1. Add `protocol: str | None = None` to `CapabilityRequirement` and `ProvidedCapability`.
2. Validate `protocol` with `_validate_catalog_identifier` when present.
3. Keep `protocol` optional for existing manifests.
4. Include `protocol` in `_app_summary()` requires entries and `_service_summary()` provides entries.
5. Add tests proving summaries expose protocol.
6. Run:
   ```bash
   uv run pytest tests/test_catalog_loader.py tests/test_catalog_api.py -q
   ```

## Task 2: Define alias defaulting for protocol-aware requirements

**Objective:** Prevent duplicate aliases when the same capability appears with different protocols.

**Files:**
- Modify: `src/nephos_api/catalog.py`
- Test: `tests/test_catalog_loader.py`

**Accepted rule:**
- If `as` is present, use it.
- If `protocol` is absent, default alias to `capability`.
- If `protocol` is present, default alias to `<capability>-<protocol>`.

Examples:

```yaml
requires:
  - capability: opencypher
    protocol: bolt
```

normalizes to alias `opencypher-bolt`.

```yaml
provides:
  - capability: opencypher
    protocol: n4j
```

normalizes to alias `opencypher-n4j`.

**Steps:**
1. Extract helper `_default_capability_alias(capability: str, protocol: str | None) -> str`.
2. Use it for App requirement aliases and Service provided aliases.
3. Ensure generated Secret name validation uses the normalized alias.
4. Add duplicate alias tests for two `opencypher` provisions with `bolt` and `n4j`.
5. Run targeted tests.

## Task 3: Persist protocol on bindings

**Objective:** Store the resolved protocol with every binding row.

**Files:**
- Create: `src/nephos_api/migrations/NNN_add_binding_protocol.sql` using the next lexical migration number.
- Modify: `src/nephos_api/repository.py`
- Modify: `src/nephos_api/domain.py` if `Binding` dataclass needs the field.
- Tests: `tests/test_db_migrations.py`, `tests/test_repository.py`

**Steps:**
1. Add nullable `protocol TEXT` to `bindings`.
2. Update repository selects to include `protocol`.
3. Update `create_binding(..., protocol: str | None)`.
4. Keep old rows valid with `NULL` protocol.
5. Include `protocol` in binding snapshots/responses where binding `capability` is already returned.
6. Run:
   ```bash
   uv run pytest tests/test_db_migrations.py tests/test_repository.py -q
   ```

## Task 4: Match providers by capability and protocol

**Objective:** Require provider selection to satisfy both fields when the App requirement includes protocol.

**Files:**
- Modify: `src/nephos_api/api/resources.py`
- Tests: `tests/test_install_api.py`, `tests/test_bindings_api.py`

**Steps:**
1. Pass `protocol = requirement.get("protocol")` through `_resolve_binding_providers`.
2. Change `_capability_provider_rows()` to `_matching_provider_rows(capability, protocol)`.
3. A Service provision matches if `provided.capability == capability` and either:
   - App requirement protocol is `None`, or
   - `provided.protocol == requirement.protocol`.
4. Include `protocol` in error `details` for ineligible/unavailable/selection-required errors when present.
5. Create binding with both `capability` and `protocol`.
6. Add tests:
   - `sql/postgres` selects PostgreSQL, not ArcadeDB `sql/arcadedb`.
   - `opencypher/bolt` selects ArcadeDB provider exposing that protocol.
   - selecting a Service with matching capability but wrong protocol returns `binding_provider_ineligible`.
7. Run targeted tests.

## Task 5: Update development reference catalog shape

**Objective:** Keep the current smoke green while moving PostgreSQL from `postgres` capability to `sql/postgres`.

**Files:**
- Modify: `src/nephos_api/dev_reference.py`
- Tests: `tests/test_dev_reference.py`, `tests/test_reconciler_runtime.py`

**Steps:**
1. Change reference App requirement to:
   ```yaml
   - capability: sql
     protocol: postgres
     as: database
   ```
2. Change reference PostgreSQL Service provision to:
   ```yaml
   - capability: sql
     protocol: postgres
     as: postgres
   ```
3. Keep provisioning outputs unchanged for now.
4. Run:
   ```bash
   uv run pytest tests/test_dev_reference.py tests/test_reconciler_runtime.py -q
   ```

## Task 6: Full verification

Run:

```bash
uv lock --check
uv run ruff check .
uv run pytest -q
git diff --check
```

Commit message:

```bash
git commit -m "feat: match service bindings by protocol"
```
