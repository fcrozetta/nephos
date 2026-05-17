# Nephos Contribution And Agent Workflow

## Decision Authority

Fer has final decision authority for Nephos architecture.

Agents and contributors may recommend, compare, and implement, but must not silently invent architecture.

If Fer has not selected a decision, keep it as an open question or draft/proposed ADR.

## ADR Requirements

Create or update an ADR when a change affects:

- architecture structure
- lifecycle semantics
- source of truth
- manifest or schema shape
- runtime boundaries
- auth or security model
- backup or data lifecycle semantics
- public API or CLI contract
- catalog behavior
- Phase 1 scope

Minor implementation details inside accepted architecture do not require a new ADR.

## ADR Status Values

Use these statuses:

- `draft`: unresolved or exploratory
- `proposed`: candidate direction awaiting Fer confirmation
- `accepted`: Fer confirmed the decision
- `rejected`: explicitly not chosen
- `deprecated`: no longer recommended
- `superseded`: replaced by a later ADR

Accepted ADRs are durable.

Material changes to accepted decisions should normally be made through a new ADR that supersedes or amends the earlier decision.

## Context Locations

Use:

- `docs/adr/` for accepted, proposed, rejected, deprecated, or superseded architectural decisions
- `.agents/context/nephos-open-questions.md` for unresolved decisions
- `.agents/context/nephos-glossary.md` for definitions
- `.agents/context/nephos-architecture.md` for architecture structure
- `.agents/context/nephos-doctrine.md` for strategic guardrails
- `.agents/context/nephos-phase1.md` for Phase 1 scope
- `.agents/context/nephos-non-goals.md` for non-goals and anti-features
- topic-specific `.agents/context/nephos-*.md` files for agent-readable summaries

## Agent Uncertainty Rule

If architecture is unclear, ask Fer or record an open question before implementing.

Do not implement through ambiguity when the ambiguity affects product model, lifecycle semantics, source of truth, runtime boundaries, schema shape, security/auth, backups, public API/CLI contract, or catalog behavior.

Low-level implementation details may be chosen pragmatically when consistent with accepted ADRs and context.

## Architecture Documentation Writes

Before writing or changing architecture context or ADR files, tell Fer which files need to change and why.

Do not silently add, accept, or reshape decisions in:

- `.agents/context/`
- `docs/adr/`
- `examples/`
- `schemas/`

Changes that alter architecture or public contracts must update ADRs, context, or open questions in the same change.

## Schema And Example Workflow

Do not add canonical schema files under `schemas/` until Fer approves the shape.

Do not add canonical examples under `examples/` until Fer approves the manifest or example shape.

Temporary draft manifests may be used while designing schemas.

Temporary draft manifests must:

- live in a clearly marked draft workspace
- not live under `schemas/`
- not live under `examples/`
- be labeled as non-canonical
- not be treated as source of truth
- be deleted, moved, or converted after the schema/example shape is accepted

The exact draft workspace path is unresolved until the first schema-design task.

## Commit Discipline

Keep architecture decision batches in separate commits when feasible.

Do not mix unrelated architecture decisions into one commit when they can be split cleanly.

Implementation commits should update ADRs/context/open questions when they change architecture or public contracts.

## Branch And PR Notes

No branch naming convention is selected yet.

No PR template is selected yet.

Future PR rules should preserve the same principle:

- architecture-changing PRs update ADRs/context
- unresolved decisions remain visible as open questions
- agents ask before making architectural decisions
