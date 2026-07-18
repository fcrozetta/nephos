# Registry-declared, backend-executed binding provisioning engines

- Status: accepted
- Date: 2026-07-18
- Tags: provisioning, bindings, registry, capabilities, trust

## Context and Problem Statement

Binding provisioners (postgres, zitadel, and stubs for seaweedfs, arcadedb) are
hardcoded Python classes wired in a literal composite
(`CompositeBindingProvisioner([Postgres, Zitadel])` in `main.py`) plus a second
hardcoded injection for service-to-service dependencies. Adding a registry
service that needs binding provisioning requires editing control-plane code. That
breaks the registry-sourced extensibility model every other part of Nephos
follows.

The resolution is in the framing: services and apps are already "registry-sourced"
without shipping code. They ship **declarations** (YAML manifests + Helm charts)
that Nephos-owned code interprets. The control plane runs `cluster-admin`
(ADR 20260715), so executing registry-authored code in-process is remote code
execution at the platform's highest privilege. `spec.provisioning.mode` already
exists in the manifest but is never wired to dispatch.

## Decision

Binding provisioning is **registry-declared, backend-executed**.

- The service manifest selects a **capability-typed provisioning engine**
  (`sql`, `oidc`, `s3`, `graph-db`) and parameterizes it via typed inputs at the
  capability-abstraction level (credential references, logical parameters). Inputs
  must never carry raw runtime coordinates (pod names, Secret names, exec targets).
- The provisioner set is assembled **per binding from the installed service
  manifest**, not from a literal list. Selection is `service_slug -> manifest ->
  declared engine`, still validated against `(capability, protocol)`.
- The existing postgres/zitadel provisioners become the `sql`/`oidc` engine
  implementations behind a thin adapter. No engine logic is rewritten.
- Unchanged and backend-owned: the `BindingProvisioner` protocol, the
  `SecretResolvingBindingProvisioner` `op://` + `bao://` boundary, the
  per-capability output-key contract (ADR 20260630), redaction, and the
  blocked/failed reconcile semantics.

## Non-goals

- **In-process plugins loaded from the registry** — permanently rejected. Importing
  community git code into a cluster-admin control plane is RCE-as-a-feature; no
  in-process discipline mitigates it.
- **A sandboxed provisioning-Job escape hatch** for arbitrary registry-authored
  provisioning logic — considered and **dropped**. The capability-typed engine set
  covers the realistic capability set, and the Job path needs a full trust
  subsystem (image provenance, egress policy, scoped RBAC). If a genuinely novel
  capability ever requires arbitrary logic, it must land its own trust ADR before
  any implementation; it is out of scope here.
- **A free-form declarative recipe language** (SQL/HTTP/exec primitives) — rejected.
  It quietly re-becomes a code surface with a full validation and trust burden.
  Prefer a new typed engine over a general interpreter.

## Consequences

- A registry service that maps to an existing capability engine is provisioned
  with zero nephos-api edits (manifest-only).
- Adding a genuinely new capability still requires a backend engine PR. This is
  the accepted ceiling of the declarative model: it removes the hardcoded
  selection/wiring, not the need for backend engines. Provisioner selection
  becomes explicit and inspectable (the manifest engine field) instead of the
  blind try-each composite.
- Migration is a strangler: ship the engine selector with a back-compat fallback
  (engine absent -> today's `(capability, protocol)` predicate dispatch), route
  `sql -> postgres` and `oidc -> zitadel`, then delete the literal composite and
  the second hardcoded service-dependency injection once stable.
- Safe for community/remote registries without signing: only typed, validated
  declarations cross the trust boundary.

## Relation to existing ADRs

- 20260523 (internal provisioning handlers): AMEND. Handlers stay backend-owned
  Python; selection changes from a hardcoded capability predicate to a
  manifest-declared engine resolved through the installed manifest. Failure model
  and "secrets never in API/summary" preserved.
- 20260518 (service operation contract boundary): EXTEND. This answers its open
  question on how third-party service authors add supported operations safely, on
  the typed-declaration side it reserved (not manifest-declared scripts/hooks).
- 20260517 (catalog source and trust model): RESPECTED. Declarations only; no
  registry code executes.
- 20260630 (binding output contracts): UNCHANGED and reinforced. Output keys stay
  fixed and backend-validated; the manifest never authors them.
- 20260622 / 20260517 (capability providers): CONSISTENT. Dispatch stays keyed on
  `(capability, protocol)`; the engine set is the concrete form of "alternative
  providers for the same capability."
- 20260529 (Pulumi provider boundary): CONSISTENT. Engines stay Python-only and
  Nephos-owned.

## Open Questions

- The exact typed `inputs` schema per engine; it must stay at capability
  abstraction (credential refs, logical params), never runtime internals.
- Finishing the `s3` / `graph-db` engines (the seaweedfs / arcadedb stubs).
