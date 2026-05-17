# Architecture Decision and Agent Workflow

- Status: accepted
- Date: 2026-05-17
- Tags: process, adr, agents, contribution, documentation

## Context and Problem Statement

Nephos is being defined through explicit architecture decisions.

Future contributors and agents need a clear rule for when to ask Fer, when to create ADRs, where context belongs, and how to avoid silently inventing architecture.

The project already uses Log4brains-style Markdown ADRs and `.agents/context/` for agent-readable architecture context.

## Decision

Use ADRs for architectural decisions that affect:

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

Minor implementation details that are clearly inside accepted architecture may be decided pragmatically in code.

## ADR Status Flow

Use these ADR statuses:

- `draft`: unresolved or exploratory
- `proposed`: candidate direction awaiting Fer confirmation
- `accepted`: Fer confirmed the decision
- `rejected`: explicitly not chosen
- `deprecated`: no longer recommended
- `superseded`: replaced by a later ADR

Accepted ADRs should be treated as durable.

Material changes to accepted decisions should normally create a new ADR that supersedes or amends the earlier decision, rather than silently rewriting history.

## Agent Uncertainty Rule

If architecture is unclear, agents must ask Fer or record an open question before implementing.

Open questions belong in `.agents/context/nephos-open-questions.md`.

Low-level implementation details may be chosen pragmatically when they are consistent with accepted ADRs and context.

Agents must not silently add, accept, or reshape architectural decisions.

## Context And ADR Updates

Architecture context lives in `.agents/context/`.

Accepted or proposed decisions live in `docs/adr/`.

Any change that alters architecture, public contracts, lifecycle behavior, manifest behavior, schema shape, runtime boundaries, security/auth behavior, backup/data semantics, or catalog behavior must update ADRs, context, or open questions in the same change.

Before writing or changing architecture context or ADR files, agents must tell Fer which files need to change and why.

## Schema And Example Gating

Do not add canonical schema files under `schemas/` until Fer approves the shape.

Do not add canonical examples under `examples/` until Fer approves the example or manifest shape.

Temporary draft manifests are allowed while designing schemas because examples make the target shape easier to evaluate.

Temporary draft manifests must:

- live in a clearly marked draft workspace
- not live under `schemas/`
- not live under `examples/`
- be labeled as non-canonical
- not be treated as source of truth
- be deleted, moved, or converted after the schema/example shape is accepted

The exact draft workspace path is not selected yet.

## Commit Discipline

When feasible, keep architecture decision batches in separate commits.

This makes review, rollback, and decision history cleaner.

## Consequences

Agents have a clear threshold for when an ADR is required.

Fer remains the decision authority for architecture.

Low-risk implementation work does not need to stop for every detail.

Draft manifests can be used for schema design without being mistaken for accepted examples.

The process adds some documentation overhead, but that is intentional because Nephos is still defining foundational architecture.

## Notes

Do not use this process to bypass Fer's approval for schema, manifest, runtime, or lifecycle decisions.

Do not turn draft manifests into hidden product contracts.
