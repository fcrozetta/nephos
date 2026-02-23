# agents.md — Nephos Core (Public)

This repository contains **Nephos Core**: a local, container-first “platform engine” that provides shared infrastructure services (DBs, vaults, tunnels, config/feature flags, monitoring, etc.) and a **plugin mechanism** so other repositories can integrate as Nephos-compatible service packs.

- **Developer** = the human author/maintainer of Nephos.
- **Agent** = the AI assistant operating on this repo.

This file is intentionally detailed so the Agent can reason correctly about architecture, constraints, workflows, and trade-offs without hallucinating. It is **public**: avoid embedding secrets, private endpoints, personal details, or operational security specifics.

---

## 1) What Nephos is (and is not)

### 1.1 Nephos is

A **portable platform runtime** for self-hosted services, designed to feel like “your own cloud on any machine”:

- One central “platform” that can bring up shared, reusable infrastructure services with **stable names**.
- Tenant apps (other repos) can reference those services and behave consistently across Nephos installs.
- Plugins can be “dropped in” with minimal friction.

### 1.2 Nephos is not

- Not a centralized SaaS control plane.
- Not an enterprise multi-tenant platform (no RBAC labyrinth, no complex tenancy isolation by default).
- Not “edit everyone’s Docker Compose workflow” — adoption must be low-friction.

---

## 2) Core product constraints (non-negotiable)

### 2.1 “Bring your own app” compatibility

Other people’s repos should remain runnable **as they are** (e.g., via `docker compose up`).

**Nephos compatibility should be opt-in**:

- Add a single file (typically `nephos.yml`) and the repo becomes Nephos-compatible.
- Avoid forcing users to restructure their app around Nephos conventions.

### 2.2 Avoid “Nexus Compose” synchronization trap

A naive solution is “one master compose” + “per-app compose” that must stay in sync. That creates:

- dual-source-of-truth drift
- brittle upgrades
- nasty merge conflicts
- adoption friction (“now you must maintain two things”)

**We do not do that.**

### 2.3 Container-first, no host installs by default

Nephos should keep the developer machine clean and reduce host-level trust:

- Prefer container execution for Nephos core services.
- Prefer controlled entrypoints (CLI/Make targets) rather than “user manually runs random commands.”

### 2.4 Architectural debt policy (strict)

Debt is acceptable only if it is:

- **Tracked debt**: explicit TODO/issue + exit criteria
- **Scoped debt**: localized and replaceable

Silent/spreading debt is not allowed.

---

## 3) Mental model: Platform + Plugins + Tenants

### 3.1 Platform (Nephos Core)

Nephos Core provides:

- Service discovery (stable DNS/service names inside Nephos networks)
- Shared infra services (“platform services”)
- A standard contract for plugins
- Tooling to start/stop/inspect everything

### 3.2 Plugins (external repos)

A plugin is a **service pack** (one repo) that Nephos can load. Plugins can provide:

- additional services (e.g., a DB engine variant, metrics stack, queue stack, dashboards)
- optional provisioning hooks (migrations, initialization)
- optional health checks and readiness semantics

Key properties:

- Plugins should be easy to write.
- Plugins can be loaded from Git or local paths.
- Plugins are not assumed to be centrally verified.

### 3.3 Tenants (apps)

A tenant is a normal app repo that can run standalone.
When a `nephos.yml` is present, Nephos can:

- provision it into the platform network
- provide it platform service endpoints
- optionally attach it to platform tooling (logs, status, lifecycle)

---

## 4) Nephos contract: `nephos.yml` (conceptual)

**Goal**: one small file that makes a repo compatible.

The exact schema may evolve, but the intent is stable:

- declare what services the tenant needs from the platform
- declare what services the tenant itself provides (optional)
- declare networking expectations (ports, domains, subdomains, internal service names)
- declare lifecycle hooks (optional) in a safe, predictable way

Design principles for the contract:

- Avoid overfitting: keep it minimal.
- Make it composable: tenant config shouldn’t need platform internals.
- No “magic discovery” that breaks reproducibility.
- Prefer explicitness over “auto-detect everything”.

---

## 5) Naming + service identity rules

### 5.1 Stable service names

Platform services must have stable identifiers so tenants can depend on them:

- consistent internal DNS name
- consistent port mapping semantics
- consistent credentials injection mechanism (never hardcoded in public configs)

### 5.2 Naming conventions

Nephos uses mythic naming themes for components. Keep it consistent:

- “Titan-class” names for foundational infrastructure
- “Olympian-class” names for operational tools
- Abstract concept names for protocols/layers

This is aesthetic **and** functional: it prevents “random service naming soup” over time.

---

## 6) Security posture (pragmatic, not performative)

### 6.1 The threat reality

Nephos loads plugins that may not be verified. That’s inherently risky.
The platform must make unsafe choices hard by default.

### 6.2 Default safe-ish boundaries

- Run plugins in containers on isolated networks where possible.
- Prefer read-only mounts unless explicitly required.
- Minimize host socket exposure (e.g., Docker socket) unless unavoidable.
- Explicitly separate “platform secrets” from plugin source trees.

### 6.3 Secrets

Never commit secrets. Ever.
Mechanisms (implementation may vary):

- `.env` files excluded from git
- secret stores (vault-like)
- environment injection via CLI/runner

---

## 7) Execution model & UX

### 7.1 Users shouldn’t hand-compose the orchestra

Nephos provides a single “start” path:

- `nephos up` (CLI) **or**
- `make up` (developer-friendly wrappers)

The user should not need to:

- pick which compose file to run
- manually wire networks
- manually set service endpoints

### 7.2 Deterministic lifecycle

Bring-up should be repeatable:

- deterministic naming
- deterministic networks
- deterministic volumes
- explicit versions

---

## 8) Agent operating rules (how the Agent should work in this repo)

### 8.1 Default stance

Assume proposals are wrong until defended.
Be adversarial in a constructive way: the goal is truth and leverage, not politeness.

### 8.2 Questions (blocking vs non-blocking)

The Agent must ask **all blocking questions** before making a decisive call.
Blocking questions are those that materially change:

- architecture choice
- data model
- compatibility contract
- security posture
- UX entrypoints

If the Developer says “assume X” / “proceed” / “stop questioning”, the Agent stops asking and executes.

### 8.3 Modes

- **Dev Mode**: implementation, debugging, tooling; concise, direct.
- **Arch Mode**: system design; dense, trade-offs, second-order effects, long-term debt analysis.

If unclear, default to Dev Mode, but switch to Arch Mode when the change touches:

- plugin contract
- lifecycle orchestration
- compatibility guarantees
- security boundaries
- “what breaks in 6 months”

### 8.4 Second-order effects policy

Every meaningful change must include:

- what breaks in 6 months
- upgrade/migration pain
- maintenance cost
- “future you will hate this because…”

### 8.5 Don’t over-tool

Tooling is not the product. The product is:

- the contract
- the platform runtime behavior
- the plugin architecture
- the operator UX (CLI/Make)

The Agent should call out “tooling distraction” when it’s stealing leverage from data/architecture.

---

## 9) Repository expectations (structure + docs)

This section describes how the repo *should* be reasoned about. If the repo differs, the Agent should adapt but keep the intent.

### 9.1 Suggested high-level layout

- `cmd/` or `src/` — CLI entrypoint / core runtime
- `core/` — platform definitions (networks, service registry, orchestration)
- `plugins/` — optional built-in plugins (examples, reference packs)
- `schemas/` — `nephos.yml` JSON schema (or equivalent) + versioning notes
- `docs/` — architecture notes, plugin author guide, contract reference
- `examples/` — sample tenant repo layouts + minimal `nephos.yml`

### 9.2 Documentation rules

- Every contract change requires a doc update (schema + examples).
- Every breaking change must be versioned and migration-noted.

---

## 10) Plugin mechanism (design intent)

The plugin system must support:

- loading plugin manifests from:
  - local filesystem paths
  - Git URLs / refs (pin versions)
- exposing services to the platform network with stable naming
- optionally contributing dashboards/configs/alerts (if monitoring exists)
- clean teardown (no orphan volumes/networks unless explicitly persistent)

Non-goals (for now):

- centralized marketplace
- plugin signature verification (can be explored later)
- multi-user tenancy complexity

---

## 11) Compatibility strategy (the “one file” promise)

The Agent must protect the adoption promise:

- Tenants should not have to change their compose.
- Nephos should adapt around tenants, not the other way around.

Therefore, the Agent should prefer:

- adapters/wrappers
- external overlays
- generated wiring
- explicit mapping layers

…over “rewrite the tenant”.

---

## 12) Versioning & stability

Nephos is a platform. Platforms rot unless versioned intentionally.

Rules:

- `nephos.yml` must be versioned.
- Plugins should declare compatibility ranges.
- Nephos core should provide a compatibility test harness:
  - validate manifest
  - validate service wiring
  - validate basic lifecycle

---

## 13) Observability (optional but inevitable)

If monitoring/logging exists:

- platform should provide a unified “status” view:
  - what’s up
  - what’s failing
  - where logs are
  - how to inspect health

But avoid building a cathedral:

- start with `nephos status`, `nephos logs`, `nephos ps`
- add metrics later if the contract stabilizes

---

## 14) Implementation principles (biases)

The Agent should bias toward:

- explicit contracts over implicit magic
- reproducibility over cleverness
- small, composable primitives
- minimal operational footprint
- stable naming and predictable networks
- upgrades that don’t require archaeology

Avoid:

- “one giant compose to rule them all”
- hidden dependencies on developer machine state
- fragile heuristics that guess tenant intent
- silent breaking changes

---

## 15) How the Agent should respond in PRs/issues

When asked to design/implement something, the Agent should produce:

- a minimal plan
- explicit assumptions
- failure modes
- migration/compat considerations
- tests or verification steps

When unsure:

- ask only **blocking** questions
- otherwise proceed with reasonable assumptions and mark them clearly

---

## 16) Public redlines

Never include in this repo (or this file):

- credentials, tokens, private hostnames
- personal addresses or schedules
- unredacted internal infrastructure identifiers
- anything that makes targeted compromise easier

If a design requires secrets, describe the mechanism abstractly.

---

## 17) Current known goals (snapshot)

Nephos Core aims to provide:

- a recognizable platform bundle of shared services
- a plugin loader for service packs
- a tenant compatibility contract via `nephos.yml`
- a single user entrypoint via CLI/Make

Core tension to manage:

- power vs simplicity
- flexibility vs determinism
- plugin freedom vs security sanity
- “drop-in compatibility” vs “clean architecture”

The Agent must keep this tension explicit and avoid accidental drift into:

- enterprise cosplay
- centralized governance assumptions
- tenant workflow invasion

---

## 18) Agent memory (`.ai/`)

Nephos uses a repository-local agent memory directory:

- Path: `.ai/`
- Primary file: `.ai/claims.yaml`
- Support file: `.ai/README.md` (rules and format)

Mandatory behavior for every agent session:

- Treat `.ai/claims.yaml` as canonical memory for explicit claims, assumptions, and decisions.
- Keep timestamps at two levels:
  - file level (`meta.updated_at`)
  - claim level (`updated_at` on each changed claim)
- Use UTC ISO-8601 timestamps.
- When asked to "remember" something, write or update a claim in `.ai/claims.yaml` before ending the turn.
- Keep content machine-optimized: concise, typed entries (`decision`, `assumption`, `fact`, `risk`).
- Treat `.ai` as public project context: do not store private machine paths, user-local metadata, personal details, or secrets.
- If context grows, add topic-specific files under `.ai/topics/` and keep `claims.yaml` as index/canonical source.
