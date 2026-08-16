# Service readiness must be measured, or say that it is not

- Status: proposed
- Deciders: Fer
- Date: 2026-08-17
- Tags: services, production-readiness, status, evidence, phase-1

Supersedes (on acceptance):

- `20260623-service-production-readiness-contract.md`

Technical Story: surfaced while hardening the SeaweedFS Service (ADR 20260816).
The Service reported four readiness dimensions the whole time its filer was
serving every S3 credential to any pod in the cluster. Nothing in the contract
was capable of noticing, and nothing in the contract was lying either — which is
the problem.

## Context and Problem Statement

ADR 20260623 chose, explicitly, to "define a generic readiness contract" over
"treat each Service's production readiness as bespoke implementation detail". It
named seven dimensions: `runtime`, `provisioning`, `secrets`, `exposure`,
`storage`, `backup`, `maintenance`.

The implementation went the other way, and the gap is now load-bearing rather
than cosmetic:

- `_service_production_readiness_evidence(slug)` emits four checks for every
  Service. Three of them — `secrets`, `backup`, `maintenance` — are string
  literals with no evaluation behind them. They are *policy statements*, and they
  are correct as policy statements, but they are rendered in the same shape as a
  check that observed something.
- The fourth, `runtime`, is emitted only inside
  `if target_type == "service_instance" and reason == "runtime_deployed"`. It
  restates the condition it is emitted under. It cannot ever say "not ready"; a
  Service whose runtime is not deployed simply produces no readiness evidence at
  all.
- The reconciler then branches on `if slug == "zitadel"` and appends four more
  checks. That is precisely the bespoke-per-Service option the ADR rejected,
  reintroduced in the layer that was supposed to prevent it.
- `storage` is one of the seven named dimensions and is implemented nowhere. It
  is not reported as unknown; it is absent.

The consequence is a report where **absence is indistinguishable from
non-evaluation**, and where a reader cannot tell a measurement from a policy.
"Four dimensions look fine" and "four dimensions were never checked" render
identically. That is worse than reporting nothing, because a status payload
invites the reader to treat it as evidence.

The SeaweedFS case makes it concrete. Between ADR 20260816 landing and its
security follow-up, the Service was genuinely `runtime_deployed`, so the report
was accurate on the one dimension it measured — while `exposure` (an
unauthenticated filer reachable cluster-wide) and `storage` (a PVC with no
declared destroy semantics) were exactly the dimensions the contract named and
did not implement.

## Decision Drivers

- A readiness payload must not be able to imply a property nobody checked.
- Policy deferrals are legitimate and must remain expressible — `backup` really
  is deferred, and saying so is the honest answer, not a gap.
- The distinction that matters to a reader is not pass/fail, it is **on what
  basis**: observed, declared, or unknown.
- Per-Service knowledge must not live in the reconciler. It was rejected once
  already and came back.
- Nothing here should require implementing backup, TLS, or an external secret
  manager to become true.

## Considered Options

- Keep the dimension list, add a basis to every check, and forbid slug branching.
- Implement all seven dimensions as measurements before reporting any of them.
- Drop the readiness payload until there is something real to report.

## Decision Outcome

Chosen option: **keep the dimensions, make the basis explicit, and move
per-Service knowledge out of the reconciler.**

**1. Every check declares its basis.** A check carries `basis` with one of:

- `measured` — derived from state observed during this reconciliation pass. A
  `measured` check may report a bad outcome; that is the point of it.
- `declared` — true by standing platform decision, not observation. `backup:
  deferred` and `secrets: kubernetes-secrets` are `declared`.
- `undetermined` — the dimension applies to this Service and nothing evaluated
  it. This is the default for any dimension not otherwise produced.

A consumer rendering readiness must not present `declared` or `undetermined` as
though it were `measured`. `undetermined` must never render as healthy.

**2. Readiness evidence is emitted on every reconciliation outcome**, not only on
`runtime_deployed`. A Service that failed to deploy has a readiness story —
`runtime` measured as not ready — and today it produces silence.

**3. `runtime` must be `measured`.** It is the one dimension Nephos already
observes, and restating the gate it was emitted under does not count.

**4. No branching on slug in the reconciler.** Dimensions beyond the generic set
are contributed by the Service's provider or declared in its manifest. The
Zitadel-specific `exposure`, `tls`, `database-topology` and `provisioning` checks
move to that mechanism; this ADR does not fix which of the two, because that is
an implementation choice the first slice should make with the code in front of
it.

**5. Every named dimension appears for every Service**, with `undetermined` where
nothing evaluated it. `storage` stops being invisible by omission.

**6. The payload carries a new `contractVersion`**, so a consumer can tell the
two shapes apart rather than inferring from which keys are present.

Inherited unchanged from 20260623: TLS termination stays external to Nephos,
Kubernetes Secrets remain acceptable for Phase 1, and backup implementation
remains out of scope. This ADR changes how readiness is *reported*, not what is
implemented behind it.

### Positive Consequences

- A readiness payload becomes falsifiable. A dimension can report a problem
  instead of vanishing.
- The honest deferrals stay honest and become legible as deferrals rather than
  passes.
- The bespoke-per-Service option stays rejected in practice, not just on paper.
- Adding a Service stops requiring an edit to the reconciler.

### Negative Consequences

- Existing consumers of the status payload must handle `basis` and the new
  `contractVersion`. The console renders this surface today.
- Most dimensions will initially report `undetermined`, which will make the
  platform look less ready than the current payload implies. That is the
  correction, not a regression, but it will read as one.
- `measured` checks cost real observation work per reconciliation pass, on a path
  that currently does none.

## Pros and Cons of the Options

### Keep the dimensions, add a basis, forbid slug branching

- Good, because it makes the existing payload honest without blocking on backup,
  TLS, or a secret manager.
- Good, because it fixes the drift from 20260623's own decision rather than
  ratifying it.
- Bad, because it changes a payload the console already consumes.

### Implement all seven as measurements first

- Good, because the payload would be uniformly trustworthy.
- Bad, because `backup` and `exposure` cannot be measured without deciding
  backup and TLS, which 20260623 deliberately deferred and this ADR does not
  reopen. It makes an honesty fix wait on unrelated feature work.

### Drop the payload until it means something

- Good, because silence cannot mislead.
- Bad, because the deferrals are genuinely useful information, and removing the
  surface loses the one dimension that is real today.

## Links

- Supersedes [Service Production Readiness Contract](20260623-service-production-readiness-contract.md)
- Motivated by [SeaweedFS filer-backed S3 provisioning](20260816-seaweedfs-filer-backed-s3-provisioning.md)
- Related [Health and status model](20260517-health-and-status-model.md)
