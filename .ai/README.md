# .ai Agent Memory

This directory is agent-only working memory for Nephos.

## Rules

- Primary memory file: `.ai/claims.yaml`.
- `claims.yaml` must include file-level timestamps and per-claim timestamps.
- When any claim changes, update:
  - `meta.updated_at`
  - that claim's `updated_at`
- When the developer asks to "remember" something, add or update a claim in `claims.yaml` in the same session.
- Keep entries machine-optimized: short, explicit, and typed (`decision`, `assumption`, `fact`, `risk`).
- Use UTC ISO-8601 timestamps (for example: `2026-02-21T23:36:08Z`).
- `.ai` content is public project context. Do not store private machine paths, user-local metadata, personal details, or secrets.

## Optional Organization

- Add topic files under `.ai/topics/` when context becomes large.
- Treat `claims.yaml` as the canonical index; topic files are supporting detail.

## Current Topic Files

- `.ai/topics/contract-v1.yaml`
- `.ai/topics/runtime-lifecycle.yaml`
- `.ai/topics/hostname-policy.yaml`

## Context Loading Strategy

- Load `claims.yaml` first for canonical decisions and timestamps.
- Load only topic files relevant to the active request.
- Do not bulk-load all topic files unless explicitly requested.
