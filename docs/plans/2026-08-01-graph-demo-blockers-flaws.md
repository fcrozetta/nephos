# Flaws found in the graph-demo blockers plan

A running log of places where
[`2026-08-01-graph-demo-blockers-plan.md`](2026-08-01-graph-demo-blockers-plan.md)
turned out to be wrong during implementation.

Kept because a plan flaw is evidence about how the plan was written, not just a
bug to patch. Fixing each one silently in place — which is what happened
building `graph-demo`, roughly ten times — leaves the pattern invisible and lets
the same classes recur. Appended as found, not reconstructed afterwards.

Each entry: what the plan said, what was actually true, how it was caught, and
the rule that would have prevented it.

---

## 0. Carried over: the classes that produced ~10 flaws in the previous plan

Recorded before starting, so they can be watched for rather than rediscovered.
All came from writing plan code without running it.

**Library API shape assumed, not verified against the installed version.**
`httpx`'s `json=` serializes compactly, which broke a test asserting on
whitespace. `sveltekit` is exported from `@sveltejs/kit/vite`, not
`@sveltejs/vite-plugin-svelte`. `PyJWKClient`'s constructor validates its URL,
so building it eagerly crashed module import. ArcadeDB returns `RETURN n` rows
flat, not wrapped in `{"n": ...}` — that one *was* verified against a live
container, and it was the only one of the four that did not ship broken.
**Rule: if a plan asserts what a library returns or accepts, run it first.**

**Framework behaviour assumed to be position-independent.** FastAPI resolves
`Annotated[X, Depends(fn)]` against the enclosing callable's `__globals__`, so
dependency callables nested inside a factory silently degrade into required
query parameters under `from __future__ import annotations`. No error — eight
tests failed with a confusing shape.
**Rule: when a framework resolves something by name at runtime, check where it
looks.**

**Security primitive used without checking its failure mode.**
`timingSafeEqual` throws on differing buffer byte lengths, and the guard
compared JS string length. A non-ASCII cookie made it throw on every request.
**Rule: for a crypto or comparison primitive, read what it does on mismatched
input, not just on matching input.**

**Prose contradicting the code block beneath it.** The plan's text required
"add/remove controls visible and disabled"; its own markup replaced one with a
hint line. Two reviewers had to escalate it.
**Rule: after writing a task, read its prose and its code against each other.**

---

## 1. Spec placed `ServicePortalIdentity` in the wrong module

**Plan/spec said:** the design doc puts `ServicePortalIdentity` in
`provisioners/base.py`, alongside `BindingProvisioningContext`.

**Actually true:** it belongs in `routing.py`. That module already owns portal
host derivation and the `PLATFORM_ROUTE_*` constants the identity is built
from, and its docstring states that keeping the derivation in one place is what
makes the Ingress, the API, and the runtime mapping agree byte-for-byte.
Defining the type next to its consumer instead of next to its derivation would
have split that.

**Caught by:** writing the plan's file-structure table and having to name what
each file is responsible for. The design doc never asked that question.

**Rule:** a design doc naming a file for a new type is a guess until the plan
states that file's responsibility in one sentence. If the sentence does not fit,
the type is in the wrong place.

**Resolution:** plan overrides the spec here; noted in the plan's file table.
The spec text is now stale on this point.

---

## 2. Task 1 executed out of order (implementation before test)

**Plan said:** Step 1 write the failing test, Step 2 run it and watch it fail,
Step 3 implement.

**Actually did:** implemented `routing.py` first, then wrote the tests, then ran
them once. They passed on the first run, which proves nothing — a test that has
never been seen to fail is not known to be connected to the code.

**Caught by:** noticing the green run came without a preceding red one.

**Recovered by:** mutation instead of rewind — broke the implementation three
ways and confirmed a test caught each. Equivalent evidence, and cheaper than
reverting.

**Rule:** if the red step gets skipped, the debt is real and must be paid before
committing. Mutation testing settles it; asserting "the tests look right" does
not.

---

## 3. A no-op mutation reported as a missed test

**What happened:** one of the three mutations above appended `# noqa` to a
guard rather than removing it. Behaviour was unchanged, the suite stayed green,
and the check printed `MISSED` — reading as though
`test_identity_is_none_when_no_domain_allows_portals` was not load-bearing.

**Actually true:** that test does cover the path. Deleting the guard raises
`AttributeError` on `domain.domain` and the test fails.

**Why it matters:** a false MISS invites exactly the wrong response — weakening
or rewriting a test that was fine, or adding a redundant one.

**Rule:** a mutation must change behaviour. Before trusting a MISS, confirm the
mutated source actually differs semantically, not just textually.
