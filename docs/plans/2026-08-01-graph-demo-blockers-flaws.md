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

---

## 4. The plan's green-before-commit gate does not gate

**Plan said:** every task ends with
`uv run ruff check . && uv run ruff format --check . && ...` before `git commit`.

**Actually true:** as run, the format check was piped to `tail -2`, so the shell
saw `tail`'s exit status, not ruff's. `ruff format --check` reported seven files
it would reformat and the `&&` chain continued straight into the commit. The
gate was decorative.

**Caught by:** reading the output rather than the exit code — the "Would
reformat" line was visible even though nothing stopped.

**Rule:** never pipe a command whose exit code is the gate. Either run it bare,
or `set -o pipefail` first. A `&&` chain containing a pipe only gates on the
last element of that pipe.

---

## 5. Pre-existing format drift sets a trap for the files this plan edits

**Found:** seven files fail `ruff format --check` on `main`, before any change
here — including `reconciler.py`, which Tasks 2, 6, and 8 all modify. The drift
is pre-existing (verified by checking `main`'s copy of one of them), most likely
a ruff version difference.

**The trap:** running `ruff format` on `reconciler.py` after editing it would
reformat the entire file, burying a three-line behavioural change in hundreds of
unrelated diff lines and making the change unreviewable.

**Rule for the rest of this plan:** lint (`ruff check`) across the repo, but
format-check only the files this branch actually touches. Do not reformat
pre-existing drift as a side effect of editing a file — that is a separate
change, and mixing it in costs the reviewer far more than it saves.

**Verified clean under the real gate:** `src/nephos_api/routing.py`,
`tests/test_routing.py`.

**Confirmed at Task 2:** the only change ruff wanted in `reconciler.py` was at
line 1337, in a function this branch never touches. Formatting it would have
buried a three-line behavioural change. The rule held.

---

## 6. "Update the existing https test" understated what was there

**Plan said (Task 4, step 6):** "An existing test asserting an https redirect
URI is now wrong and should be updated to http — that is the fix, not a
regression."

**Actually true:** the test was
`test_pulumi_zitadel_client_uses_https_redirects_for_nonlocal_domains`. Its
*name* asserted the old behaviour as intended design, so silently flipping its
body would have left a test whose name contradicted what it checked — and would
have looked, to a reviewer, like the https behaviour was deliberate and I
overrode it.

**What the check needed to be:** does Nephos ever actually serve https?
`grep -n "tls\|V1IngressTLS" src/nephos_api/kubernetes_runtime.py` returns
nothing — `ensure_app_ingresses` configures no TLS at all. The https redirect
URI was never backed by anything the platform does. That is the justification,
and it was not in the plan.

**Rule:** when a plan says "update the existing test", it must also say what
evidence justifies the flip. A test encodes someone's intent; overriding it
needs a reason stronger than "my new test disagrees". Check the name and the
git history, not just the assertion.

**Also renamed** to `..._uses_the_platform_route_scheme_for_redirects`, so the
name states the property that now holds.

---

## 7. Plan quoted a source comment from memory, not from the file

**Plan said (Task 4, step 5):** replace the warning block at `routing.py:18-23`,
and gave the replacement text.

**Actually true:** the plan's rendition of the *existing* comment did not match
the file. The scripted edit asserted on the exact stale text and stopped rather
than silently doing nothing.

**Also missed entirely:** a second stale reference at
`tests/test_service_portals.py:127`, which the plan never mentioned. A plain
`grep -rn "_route_scheme" src/ tests/` at plan-writing time would have found
both. The plan grepped only `src/`.

**Rule:** never transcribe existing file content into a plan from memory — read
it, or describe the edit by anchor rather than quoting. And when a plan proposes
deleting a symbol, grep for it across `src/` *and* `tests/` *and* `docs/`;
comments referencing a deleted function rot silently because nothing compiles
them.

**Why it did not cost anything:** the edit script used
`assert stale in s` before writing. An unasserted `str.replace` would have
no-op'd and left the stale comment in place, claiming success.
