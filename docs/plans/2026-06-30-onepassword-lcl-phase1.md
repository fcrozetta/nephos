# 1Password LCL Phase 1 Conventions

## Goal

Define the first concrete Nephos LCL 1Password conventions so Nephos can safely
use `nephos-lcl` as the operator-owned source of truth for bootstrap and
runtime-support secrets while continuing to materialize workload secrets as
Kubernetes Secrets.

## Non-goals

- Do not deploy 1Password Connect yet.
- Do not deploy the 1Password Kubernetes Operator yet.
- Do not implement runtime reads from 1Password in Nephos code yet.
- Do not create canonical schema files under `schemas/`.
- Do not create canonical manifest examples under `examples/`.
- Do not design production rotation/backup semantics yet.
- Do not change `dev` or `prd` safety policy; only LCL is disposable.

## Current understanding

- Current environment in scope: `lcl`.
- Current service account: `Nephos`.
- The service account can see only Nephos vaults.
- `nephos-lcl` may be cleared and repopulated during local rebuilds.
- 1Password is the operator source of truth for LCL bootstrap/runtime-support
  secrets.
- Kubernetes Secrets remain the runtime materialization mechanism for workloads.
- Nephos desired state stores references/metadata, not secret values.

Environment vaults:

| env | vault | vault ID |
| --- | --- | --- |
| `lcl` | `nephos-lcl` | `4dna2bafdf6oluftatzyqzzgpi` |
| `dev` | `nephos-dev` | `rkr45cz6exnt6mh3sk6qrixyuq` |
| `prd` | `nephos-prd` | `utxh564oqvgm2yhqoskknrubq4` |

## Files likely to change

- `PLANS.md`
- `docs/adr/20260630-onepassword-lcl-secrets-source.md`
- `docs/plans/2026-06-30-onepassword-lcl-phase1.md`
- `docs/maintainers.md`
- `.agents/context/nephos-phase1.md`
- `.agents/context/nephos-open-questions.md`

Implementation files are intentionally out of scope for this first convention
slice.

## Rule of thumb

- **Vault = environment boundary.**
- **Item = Service/App secret bundle.**
- **Fields = concrete credentials, tokens, connection strings, or files.**
- **Tags/folders = organization only, not security.**

## Item naming

Use lowercase kebab-case item names. Prefer one item per Service/App secret
bundle.

Item names should be stable across environments. The environment comes from the
vault, not the item name.

Good:

```text
nephos-lcl/postgres-admin
nephos-dev/postgres-admin
nephos-prd/postgres-admin
```

Avoid:

```text
nephos-lcl/postgres-admin-lcl
nephos-dev/dev-postgres-admin
```

## Initial LCL item catalog

| Item | Purpose | Initial fields |
| --- | --- | --- |
| `postgres-admin` | PostgreSQL Service administrator/bootstrap credentials | `username`, `password`, `host`, `port`, `database`, `uri` |
| `zitadel-bootstrap` | ZITADEL bootstrap admin/provisioning material | `admin_username`, `admin_password`, later `machine_key.json` or `credentials.json` |
| `seaweedfs-admin` | SeaweedFS/S3 administrator credentials | `access_key`, `secret_key`, `endpoint`, `console_username`, `console_password` |
| `arcadedb-root` | ArcadeDB root/admin credentials | `username`, `password`, `host`, `port`, `http_url`, protocol-specific URI fields as needed |
| `onepassword-connect-lcl` | Future Connect credentials/token record | `credentials.json`, `token`, `host` once Connect is in scope |

These items represent Service-internal/admin material. App-scoped binding outputs
are still governed by binding/provider logic and materialized into App namespace
Kubernetes Secrets.

## Initial LCL references

The initial `nephos-lcl` starter items were populated with generated local
bootstrap/admin credentials. Do not commit or log resolved values. Use references
or structured metadata only.

| Purpose | Reference |
| --- | --- |
| PostgreSQL admin password | `op://nephos-lcl/postgres-admin/password` |
| PostgreSQL admin username | `op://nephos-lcl/postgres-admin/username` |
| ZITADEL admin username | `op://nephos-lcl/zitadel-bootstrap/admin_username` |
| ZITADEL admin password | `op://nephos-lcl/zitadel-bootstrap/admin_password` |
| ZITADEL master key | `op://nephos-lcl/zitadel-bootstrap/master_key` |
| ZITADEL external host | `op://nephos-lcl/zitadel-bootstrap/external_host` |
| SeaweedFS S3 access key | `op://nephos-lcl/seaweedfs-admin/access_key` |
| SeaweedFS S3 secret key | `op://nephos-lcl/seaweedfs-admin/secret_key` |
| SeaweedFS console password | `op://nephos-lcl/seaweedfs-admin/console_password` |
| ArcadeDB root username | `op://nephos-lcl/arcadedb-root/username` |
| ArcadeDB root password | `op://nephos-lcl/arcadedb-root/password` |
| Future Connect credentials file | `op://nephos-lcl/onepassword-connect-lcl/credentials.json` |
| Future Connect token | `op://nephos-lcl/onepassword-connect-lcl/token` |

`onepassword-connect-lcl` is intentionally a placeholder until Connect deployment
is in scope.

## Common field conventions

Prefer these field names where they fit:

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
endpoint
credentials.json
```

Use snake_case for multi-word scalar fields because these fields often become
Secret keys or API metadata keys.

Use `.json` suffixes for fields that hold complete JSON file payloads:

```text
credentials.json
machine_key.json
```

## Reference conventions

Human-readable reference form:

```text
op://nephos-lcl/postgres-admin/password
```

Structured Nephos metadata form:

```yaml
secretRef:
  provider: onepassword
  env: lcl
  vault: nephos-lcl
  item: postgres-admin
  field: password
```

Use IDs in generated machine state when stable lookup matters, but keep names in
operator-facing docs and examples.

## Proposed steps

1. Record the accepted LCL source-of-truth decision in an ADR. **Done.**
2. Record the Phase 1 item, field, and reference conventions in this plan. **Done.**
3. Populate the initial `nephos-lcl` starter items with generated local
   bootstrap/admin credentials. **Done.**
4. Add a runtime secret reference resolver for `op://...` config values. **Done.**
5. Wire the resolver into the provider and Helm deployer config-mapping path so
   runtime providers receive resolved values while desired state keeps refs.
   **Done.**
6. Make the alpha backbone smoke config use `nephos-lcl` references for
   PostgreSQL and ZITADEL bootstrap secrets. **Done.**
7. Later, when Connect/Operator is in scope, add a `onepassword-connect` Service
   and materialization provider.

## Implemented code path

Runtime config mapping now resolves `op://...` string values at deploy time:

- `src/nephos_api/secret_refs.py`
  - `OnePasswordCliSecretResolver` resolves refs through `op read`.
  - `StaticSecretResolver` supports focused tests.
  - resolver errors use `RuntimeBlockedError` without including command stderr or
    resolved values.
- `src/nephos_api/providers/deployer.py`
  - resolves config-mapped `op://...` values before calling provider runtimes.
- `src/nephos_api/helm_runtime.py`
  - resolves config-mapped `op://...` values before writing Helm values files.
- `src/nephos_api/main.py`
  - default provider deployer uses `OnePasswordCliSecretResolver`.
- `src/nephos_api/dev_backbone.py`
  - alpha backbone LCL configs now use `op://nephos-lcl/...` references for
    PostgreSQL admin password, ZITADEL admin password, and ZITADEL master key.
  - smoke waits for both binding Secrets before declaring success and retries the
    transient ZITADEL bootstrap-machine-key read while the pod finishes writing
    it.
- `src/nephos_api/provisioners/zitadel.py`
  - internal port-forward provisioning connects through the forwarded local port
    while preserving the configured external ZITADEL domain for provider origin
    checks.

Desired state still stores only references. Runtime providers receive real values
only at deployment/materialization time.

Live verification passed on Docker Desktop with a temporary Pulumi passphrase:

```text
uv run nephos-api dev backbone-smoke --timeout-seconds 180
# Alpha backbone smoke passed
```

## Risks

- Confusing 1Password source-of-truth with runtime delivery. Kubernetes still
  owns workload Secret resources in Phase 1.
- Treating tags/folders as access control. Vaults are the environment boundary.
- Accidentally making PRD disposable because LCL is disposable.
- Storing resolved secrets in Nephos desired state, status, logs, or Pulumi
  evidence.
- Creating item conventions that conflict with binding output schemas.

## Validation commands

```bash
git diff --check
uv run ruff check .
uv run pytest -q
```

For this documentation-only slice, `git diff --check` is the minimum required
verification. Run the full baseline before combining this with code changes.

## Rollback notes

- Revert this plan and the ADR/context edits if 1Password stops being the chosen
  LCL source of truth.
- Do not delete 1Password vaults/items as part of repository rollback; external
  secrets are operator-owned state.

## Open questions

- Exact rotation behavior for 1Password-backed secrets.
- Whether/how Nephos backup status should describe external 1Password-backed
  secrets.
- Exact future `onepassword-connect` Service manifest and provider shape.
- When `dev` and `prd` should get dedicated service accounts, Connect servers,
  or narrower tokens.
