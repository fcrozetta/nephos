# Explicit entitlements for elevated binding credentials

- Status: accepted
- Date: 2026-07-21
- Tags: provisioning, bindings, security, trust, capabilities

Technical Story: WS-D follow-up of ADR 20260718 (registry-declared binding
provisioning engines).

## Context and Problem Statement

A binding provisioner may return more than the app-scoped credential. The
postgres engine returns the Service's **admin** credential (`adminUsername` /
`adminPassword`) for some bindings so a consumer that must bootstrap its own
schema (e.g. Zitadel migrating its database) can do so.

Today that elevated grant is decided by a heuristic:

```python
def _is_service_dependency_context(context):
    return context.binding_id.startswith("service-")
```

Whether a binding receives the provider's admin password depends on whether its
`binding_id` string starts with `"service-"` (the prefix the deployer happens to
use for service->service dependency contexts). This is implicit privilege
inference by naming convention: not declared, not auditable, and fragile — any
future code path that mints a `service-`-prefixed id would leak admin
credentials, and the grant is invisible in the manifest. It is not currently
exploitable (no external input controls `binding_id`), but it is the wrong
authorization model.

How should a binding's entitlement to elevated provider credentials be
expressed?

## Decision Drivers

- Explicit over implicit: an elevated grant must be declared, not inferred.
- Default-deny: absence of a declaration yields the app-scoped credential only.
- Auditable: the grant is visible in the consumer manifest and reviewable.
- Consistent with ADR 20260718: capability-abstraction, engine-interpreted,
  "the registry/engine, not the schema, is the source of valid values."
- Minimal blast radius: preserve today's behavior for the one real consumer
  (Zitadel) without widening what apps can request.

## Decision Outcome

Chosen option: **an explicit, default-deny `entitlements` set on the consumer's
capability requirement, interpreted by the engine**, replacing the heuristic.

- `CapabilityRequirement` gains `entitlements: list[str] = []` (open set, like
  `engine: str` — the engine, not the schema, defines valid values). The first
  value is `admin-credentials`.
- `BindingProvisioningContext` gains `entitlements: frozenset[str] = frozenset()`.
  The reconciler and the deployer populate it from the consumer's requirement.
- The postgres engine returns the admin credential iff
  `"admin-credentials" in context.entitlements`, replacing
  `_is_service_dependency_context`. An engine that receives an entitlement it
  does not understand blocks loudly (mirrors the unknown-engine path).
- Scope: only the service->service dependency path grants entitlements today
  (that is the sole current consumer). App->service bindings stay default-deny;
  the field exists for them but no app declares it yet.

Provider-side policy (a provider approving/denying which consumers may hold an
entitlement) is a **non-goal** here: the core registry is curated, so a
consumer-declared, default-deny grant is sufficient. Untrusted-registry gating
is deferred to its own trust ADR.

### Migration (strangler, mirrors ADR 20260718)

`CapabilityRequirement` is `extra="forbid"`, so the field-accepting code must be
live before any manifest declares it, and the heuristic must stay until the
manifest declares the entitlement — or Zitadel loses its admin grant.

1. **Accept + OR** (code): add `entitlements`; the postgres engine grants admin
   if `"admin-credentials" in entitlements` **or** the legacy heuristic still
   matches. Deploy. No behavior change.
2. **Declare** (core-registry): add `entitlements: [admin-credentials]` to
   Zitadel's `sql` requirement. Merge + let the control plane refresh.
3. **Remove heuristic** (code): drop `_is_service_dependency_context`; rely only
   on the explicit entitlement. Deploy.

### Positive Consequences

- Elevated credential grants are explicit, declared, default-deny, auditable.
- The `binding_id` string stops carrying authorization meaning.
- Establishes an extensible entitlement vocabulary without a schema change per
  new grant (engine-interpreted, block-on-unknown).

### Negative Consequences

- Another three-step cross-repo migration with the deploy-ordering discipline of
  ADR 20260718 (accept field before declaring it; keep the net until declared).
- A new open string set is one more registry-authored surface an engine must
  validate.

## Considered Options

- **`entitlements: list[str]` on the requirement (chosen).** Open, engine
  interpreted, consistent with `engine: str`; extensible to future grants.
- **`admin: bool = False` on the requirement.** Simpler and adequate for the one
  grant, but binary, postgres-flavored, and re-opens the schema the moment a
  second elevated mode appears. Rejected for pattern-inconsistency with 20260718,
  though it is the smaller change.
- **Provider-side grant policy.** Correct for untrusted registries; overkill for
  a curated core registry and needs its own trust subsystem. Deferred.
- **Keep the heuristic.** Rejected: implicit, fragile, unauditable.

## Links

- Follows up [Registry-declared binding provisioning engines](20260718-registry-declared-binding-provisioning-engines.md) (WS-D).
- Consistent with [binding output contracts](20260630-alpha-backbone-binding-output-contracts.md): output keys stay backend-owned; this governs *which* keys a binding is entitled to, not their names.
