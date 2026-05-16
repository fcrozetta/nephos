# Public Positioning and Internal Doctrine

- Status: accepted
- Date: 2026-05-17
- Tags: documentation, positioning, doctrine

## Context and Problem Statement

Nephos will be public.

Public documentation should define Nephos positively rather than by comparing it to other tools in the same field.

Internal documentation still needs architectural guardrails to prevent drift.

## Decision

Public-facing docs should describe what Nephos is without naming similar tools or competitors.

Internal doctrine may state what Nephos must avoid becoming.

## Rationale

Naming other tools in public doctrine weakens positioning, dates the project, and makes Nephos sound reactive.

The repo should communicate Nephos as its own platform model.

## Public Positioning

Use language like:

Nephos is a platform control plane for composable self-hosted infrastructure.

Nephos focuses on:

- Apps and Services
- capability binding
- platform lifecycle
- infrastructure composition
- local-first platform operations

## Internal Doctrine

Internal docs may include guardrails such as:

- do not drift into generic container/runtime plumbing
- do not expose Kubernetes directly as the product model
- do not tie Nephos to an external deployment platform
- preserve Apps and Services as first-class concepts
- preserve capability binding as the differentiator

## Consequences

Root public documentation should avoid competitor names.

Internal files under `.agents/context/` may contain sharper architectural guardrails.
