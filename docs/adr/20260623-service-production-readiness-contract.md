# Service Production Readiness Contract

- Status: proposed
- Deciders: Fer, Hermes Agent
- Date: 2026-06-23
- Tags: services, production-readiness, status, secrets, backups, auth, zitadel, phase-1

Amends:

- `20260517-services-as-capability-providers.md`
- `20260517-health-and-status-model.md`
- `20260517-secrets-model.md`
- `20260517-storage-and-backup-semantics.md`
- `20260517-ingress-and-visibility-model.md`
- `20260622-alpha-backbone-catalog-and-service-providers.md`

## Context and Problem Statement

The alpha backbone now includes a working Nephos-managed Zitadel Service runtime with a bootstrap machine key. To use Zitadel as production-ready platform identity infrastructure, Nephos needs a repeatable production-readiness contract that separates runtime health from provisioning readiness, secret readiness, exposure readiness, backup readiness, and maintenance lifecycle.

The immediate implementation target is Zitadel, but Fer wants the direction to be generic for core Services rather than a one-off special case.

## Decision Drivers

- Production readiness must not depend on debug-only `cloudflared tunnel run nomad` or host port-forward paths.
- Services remain Nephos-owned capability providers; Apps consume capabilities through bindings.
- Nephos desired state remains canonical; Pulumi/Kubernetes provider state is observed runtime state.
- Secret values must remain redacted in API/status/logs.
- Phase 1 may use Kubernetes Secrets, but future external secret manager integration must remain possible.
- Phase 1 does not implement concrete backup/restore, but Services must be able to declare unsupported/deferred backup readiness honestly.
- Zitadel issuer/audience/domain behavior requires the provisioning path to preserve the canonical issuer hostname.

## Considered Options

1. Treat each Service's production readiness as bespoke implementation detail.
2. Define a generic readiness contract and implement Zitadel first.
3. Wait for all core Services before defining readiness.

## Decision Outcome

Chosen option: **define a generic readiness contract and implement Zitadel first**.

Service production readiness should be represented as structured, redacted status evidence that can cover these dimensions:

- `runtime`: workloads, pods, Services, PVCs, and Kubernetes-owned primitives are present and ready.
- `provisioning`: app-scoped binding provisioning can run through an approved internal/production path.
- `secrets`: required Service-owned and App-owned Secrets exist in approved storage and are redacted from summaries.
- `exposure`: configured public/private surfaces are reachable through approved production paths.
- `storage`: persistent storage exists and destroy/remove behavior is explicit.
- `backup`: backup/restore support is implemented, unsupported, or deferred with explicit status.
- `maintenance`: upgrade, restart, repair, key rotation, backup, and restore actions are either implemented or explicitly unsupported/deferred.

For the first Zitadel production-ready slice:

- Exposure should support **both public HTTPS and private access**.
- Management/provisioning should use the **same canonical issuer hostname with a separate internal/private network path**, not a separate Zitadel issuer identity.
- TLS termination remains **external to Nephos for now**.
- Kubernetes Secrets are acceptable in this slice; external secret manager support is deferred.
- Backup implementation is skipped for now; readiness must not claim supported backups.
- Embedded Postgres sidecar is acceptable for now, but the design should remain replaceable by the shared PostgreSQL Service later.

## Zitadel Management Endpoint Rule

Zitadel app provisioning must not use debug exposure paths as production dependencies.

The intended production rule is:

```text
canonical issuer hostname == hostname used for management/provisioning identity checks
network path for provisioning == private/internal route for that same hostname
```

In other words, Nephos should not create a second logical Zitadel issuer for management. If provider tooling cannot separate transport from issuer/audience, Nephos should provide or require an internal route/split-horizon resolution path for the same issuer hostname, or replace the provider with a client path that can preserve issuer/audience semantics correctly.

## Consequences

### Positive Consequences

- Production readiness becomes comparable across Services.
- Runtime health is no longer confused with provisioning readiness.
- Debug/public tunnel success is not treated as production capability.
- Future external secret manager and shared PostgreSQL migration paths remain open.
- Zitadel's issuer/audience constraints are treated as architecture, not a local workaround.

### Negative Consequences

- The status model grows before every Service has full readiness implementation.
- Zitadel production provisioning may require additional routing/DNS setup beyond the current debug flow.
- Backup readiness will initially report unsupported/deferred rather than complete.
- A future ADR may be needed for the exact external secret manager integration and backup/restore contracts.

## Non-Goals

- Do not implement a concrete backup/restore system in this decision.
- Do not make Nephos manage TLS certificates in this decision.
- Do not require external secret manager integration in this decision.
- Do not move Zitadel to the shared PostgreSQL Service in this decision.
- Do not define CLI command spelling for maintenance operations here.
- Do not expose secrets through any reveal/debug API.

## Follow-up Work

- Implement generic production-readiness evidence for Services.
- Implement Zitadel-specific readiness evidence first.
- Add tests proving redaction and separating runtime/provisioning/exposure/backup readiness.
- Define a production-safe Zitadel management/provisioning transport that preserves the canonical issuer hostname without depending on debug tunnel/host port-forward.
- Initial implementation adds `provisioning-transport` with `auto`, `issuer-endpoint`, and `port-forward` behavior: non-local hosts use the issuer endpoint; `.localhost` dev hosts use bounded port-forward.
- Zitadel runtime supports a Service-owned Ingress via `ingress-enabled` and `ingress-class-name` so the canonical issuer host can route through cluster ingress instead of the debug host port-forward.
- Keep backup support as `deferred`/`unsupported` status until a future backup ADR or implementation slice.

## Links

- Plan: `docs/plans/2026-06-23-zitadel-production-readiness.md`
