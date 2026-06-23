# Zitadel Service Production Readiness Plan

> **For Hermes:** Do not implement architecture-changing code from this plan until the blocking decisions are answered by Fer or explicitly deferred. Use systematic debugging/TDD for each implementation slice.

**Goal:** Make the Nephos `zitadel` Service ready for production use as a shared identity Service for Apps, including reliable runtime, provisioning, secrets, backup/restore, health, and operational lifecycle.

**Architecture:** Zitadel remains a Nephos Service that provides `oidc/oidc` and `service-account/jwt`. Nephos desired state stays canonical; provider implementations perform runtime/provisioning labor. Production readiness must not depend on debug-only host port-forwards or `cloudflared tunnel run nomad`.

**Tech Stack:** Python/FastAPI Nephos API, SQLite desired state, Kubernetes runtime, Pulumi provider labor, ZITADEL v2.58, Kubernetes Secrets/PVCs unless Fer chooses a different production secret/storage model.

---

## Non-goals

- Do not make Zitadel the Nephos control-plane login unless separately decided.
- Do not model Chiron or any specific dogfood App in this slice.
- Do not depend on debug Cloudflare/host port-forward for production provisioning.
- Do not add canonical schemas under `schemas/` or canonical examples under `examples/` without approval.
- Do not expose raw passwords, client secrets, machine keys, JWT private keys, Pulumi stack outputs, or connection strings in API/status/log summaries.
- Do not silently choose production topology decisions that affect runtime boundaries, TLS, secrets, backup, or public API contracts.

## Current verified facts

- Main `zitadel` Service was recreated through Nephos.
- Main pod is healthy with both containers ready.
- Main Service now has the Nephos bootstrap machine key present.
- Local and public debug health endpoints returned `200 ok` after restart.
- Repository was clean after reverting experimental provider-transport edits.
- Fresh local/dev-style smoke instances previously proved `oidc/oidc` and `service-account/jwt` creation can work when the provider transport/domain constraints are satisfied.
- The current production blocker is management/provisioning transport for a real public-domain issuer without relying on debug exposure.

## Current production gaps

1. **Management/provisioning transport**
   - Current internal port-forward path is safe operationally but the Pulumiverse provider/ZITADEL domain validation makes public-domain issuer handling tricky.
   - Debug/public Cloudflare route is not a production provisioning path.
   - Need a chosen design for separate management endpoint vs same issuer endpoint.

2. **Issuer/exposure/TLS model**
   - Production issuer domain and TLS termination ownership are undecided.
   - Current debug setup uses external Cloudflare/manual host port-forward, which is explicitly not production architecture.

3. **Secrets model**
   - Current alpha catalog carries local defaults for admin/database/master/bootstrap config.
   - Production needs generated/supplied secret material, redacted API responses, and no committed/default real secrets.
   - Need decision on Kubernetes Secrets vs future external secret manager for this slice.

4. **Persistence and backup/restore**
   - Current runtime is a StatefulSet with PVCs and an embedded Postgres sidecar.
   - Production readiness needs declared backup/restore behavior and verification.
   - Need decision on volume snapshots, logical Postgres backup, both, or declaration-only for this slice.

5. **Database topology**
   - Current Zitadel runtime owns a Postgres sidecar.
   - Need decision whether this is acceptable for first production-ready Nephos or whether Zitadel must bind to the shared PostgreSQL Service.

6. **Operational status/evidence**
   - Production readiness should report runtime health, bootstrap key presence, route exposure, storage readiness, and provisioning readiness separately.
   - Status evidence must stay structured and redacted.

7. **Upgrade/maintenance lifecycle**
   - Production readiness should define how image upgrades, config changes, key rotation, restart, backup, restore, and repair are invoked or at least represented.

## Fer decisions captured on 2026-06-23

1. **Production exposure:** support both public HTTPS and private access.
2. **Management endpoint:** Hermes recommendation is same canonical issuer hostname with a separate internal network path, not a separate Zitadel issuer identity. Production should avoid debug tunnels while preserving the Host/audience ZITADEL expects. This likely means split-horizon/private routing for the same issuer host, or a direct client path that can preserve issuer/audience separately from transport if the provider cannot.
3. **TLS ownership:** for now, TLS termination remains external to Nephos.
4. **Secrets:** external secret manager later; Kubernetes Secrets are acceptable for this slice.
5. **Backups:** skip backup implementation for now; record hooks/status as future work only.
6. **Database topology:** embedded Postgres sidecar is acceptable for now, but should be designed so it can move to the shared PostgreSQL Service later.
7. **Scope:** establish a generic production-readiness contract for core Services, and implement Zitadel first.

## Proposed implementation slices after decisions

### Slice 1: Production-readiness contract and status model

**Objective:** Add a concrete internal checklist/status shape for Service readiness without adding a public schema prematurely.

**Likely files:**
- `src/nephos_api/reconciler.py`
- `src/nephos_api/providers/base.py`
- `src/nephos_api/providers/kubernetes.py`
- `src/nephos_api/api/resources.py`
- focused status/reconciler tests

**Validation:**
- status reports runtime health, provisioning readiness, route readiness, storage readiness, and backup readiness as separate redacted evidence.

### Slice 2: Production secret generation and storage

**Objective:** Replace production-relevant static local defaults with generated/supplied secret material and strict redaction.

**Likely files:**
- `src/nephos_api/dev_backbone.py`
- `src/nephos_api/providers/kubernetes.py`
- `src/nephos_api/api/resources.py`
- `tests/test_dev_backbone.py`
- `tests/test_pulumi_kubernetes_provider.py`
- `tests/test_install_api.py`

**Validation:**
- install without explicit secrets generates/stores Kubernetes Secrets when accepted.
- API snapshots redact all sensitive fields.
- no real generated secret is written to catalog manifests, plans, logs, or status.

### Slice 3: Production management transport

**Objective:** Provide a reliable provisioning path that is not the debug tunnel/port-forward and works with Zitadel issuer/audience rules.

**Possible designs, pending Fer decision:**
- internal management hostname/Ingress that ZITADEL accepts;
- Service-local management endpoint with matching ExternalDomain policy;
- direct ZITADEL API client replacing Pulumiverse provider if provider cannot separate issuer and transport;
- accepted public endpoint with Nephos-managed TLS/Ingress.

**Likely files:**
- `src/nephos_api/provisioners/zitadel.py`
- `tests/test_alpha_backbone_provisioning.py`
- optional new direct client tests if Pulumi provider is replaced.

**Validation:**
- live smoke provisions and destroys both `oidc/oidc` and `service-account/jwt` against the main `zitadel` Service without debug tunnel/host port-forward dependency.
- `provisioning-transport=auto` uses the issuer endpoint for non-local hosts and bounded port-forward for `.localhost` dev hosts.
- invalid `provisioning-transport` values fail closed.

### Slice 4: Backup/restore hooks

**Objective:** Add the chosen backup/restore contract for Zitadel runtime data.

**Likely files:**
- provider/runtime implementation files depending on selected method
- docs/ADR or open questions if public lifecycle/API contract changes
- tests for backup plan/status if implemented in API 0.0.1

**Validation:**
- backup can be triggered or at minimum readiness reports exact supported method and missing prerequisites.
- restore path is documented and tested if in scope.

### Slice 5: Production smoke command

**Objective:** Provide one repeatable production-readiness smoke that checks runtime, bootstrap identity, provisioning, cleanup, and redaction.

**Likely files:**
- `src/nephos_api/dev_backbone.py` or a new dev/prod-smoke helper
- tests for non-live behavior and blockers

**Validation:**

```bash
uv lock --check
uv run ruff check .
uv run pytest -q
git diff --check
```

Live verification command to define after decisions; must not require debug Cloudflare/host port-forward.

## Risks

- Treating debug tunnel success as production readiness.
- Encoding a public manifest/API contract before schema/ADR approval.
- Making secrets durable in the wrong layer.
- Creating a backup story that only backs up PVCs but not ZITADEL logical consistency, or vice versa.
- Replacing the Pulumiverse provider too early without proving its limitation is fundamental.
- Over-scoping this into all core Services before Zitadel is stable.

## Rollback notes

- Keep production-readiness planning and implementation in separate commits.
- If provider transport changes fail, preserve runtime/bootstrap-key work and revert only provisioning transport changes.
- If secrets/backups require a different platform-wide decision, keep them in open questions/draft ADR and do not partially implement public contracts.

## Architecture documentation impact

Before implementation, Fer should approve which docs to change:

- `.agents/context/nephos-open-questions.md` — to record unresolved production decisions if not answered immediately.
- `docs/adr/` — likely needed if production readiness changes runtime boundaries, auth/security model, backup/data lifecycle semantics, public API/CLI contract, or Service catalog behavior.
- Existing plan files/`PLANS.md` — safe to update as planning metadata.

No architecture context or ADR updates are made by this plan.
