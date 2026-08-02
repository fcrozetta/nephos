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

---

## 8. Adding a migration has a blast radius the plan never mentioned

**Plan said (Task 7, step 1):** create
`0005_add_reconciliation_attempts.sql`. Nothing else.

**Actually true:** seven tests across two files hardcode the full migration
list and all seven failed —
`tests/test_db_migrations.py` (three lists: filenames, applied versions,
idempotency) and `tests/test_cli.py` (`_MIGRATION_ROWS`, consumed by four
tests). The suite went from green to `7 failed, 569 passed` on a one-line SQL
file.

**Caught by:** running the full suite. A task-scoped run of only
`tests/test_reconciliation_retry.py` was green and would have hidden every one
of them.

**Rule:** before adding a migration, `grep -rn "<previous migration name>"
tests/` and list the hits in the plan. More generally, when adding an item to
any enumerated set the codebase asserts on — migrations, registered engines,
expected catalog entries, provider names — the plan must name the assertions
that enumerate it. These fail loudly, so they cost time rather than
correctness, but a plan that omits them is not a plan someone can follow.

**Related:** `scripts/validate_catalog.py` in core-registry has exactly this
shape (`EXPECTED_APPS`, `EXPECTED_SERVICES`), and the graph-demo plan *did*
remember it there. The same author forgot it here.

---

## 9. A careless substitution silently deleted a list entry

**What happened:** patching `_MIGRATION_ROWS` in `tests/test_cli.py`, the
replacement swapped `("0004_add_admin_tokens",)` **for**
`("0005_add_reconciliation_attempts",)` rather than appending after it. The
list lost `0004`, and four tests kept failing — with the same names as before
the edit, which read as "the fix did not work" rather than "the fix broke
something else".

**Caught by:** the failure count going from 7 to 4 instead of to 0, then
printing the list.

**Rule:** when appending to a literal list by string substitution, the
replacement must contain the original text. `s.replace(old, old + new)`, never
`s.replace(old, new)`. And assert the post-condition — here,
`"0004_add_admin_tokens" in s` — not just the pre-condition.

---

## 10. Flaw 4 recurred: a commit landed on top of two lint errors

**What happened:** the Task 7 commit ran `ruff check` (which reported `I001`
and `E501`), then `ruff format --check`, then `git add -A && git commit` — as
separate statements on separate lines. Nothing chained them, so the commit
proceeded on a red lint. Fixed and amended, but the commit existed for a
minute in a state the plan says is impossible.

**Why the earlier fix did not hold:** flaw 4 was recorded as "do not pipe a
command whose exit code is the gate." The rule was too narrow. This time
nothing was piped — the statements simply were not chained at all. The
underlying mistake is the same and the recorded rule did not cover it.

**Rule, restated to cover both:** a gate is only a gate if the failing command
can stop what follows. In practice: `set -o pipefail` once, then chain
everything from the first check to `git commit` with `&&`. Never put a check
and a commit in the same block as separate statements.

**Meta-observation worth keeping:** this is the first flaw in this log to
recur, and it recurred because the rule was written against the *instance*
(piping) rather than the *cause* (an ungated gate). When writing a rule, state
what must be true, not what must be avoided.

---

## 11. The deploy step deployed someone else's image

**Plan said (Task 9, step 1):** `docker build -t nephos-api:dev .`, then
`k3d image import`, then `rollout restart` — as though the cluster ran the
local dev tag.

**Actually true:** the deployment runs
`ghcr.io/fcrozetta/nephos-api:0.3.0` at revision 7. The build and import
succeeded and were simply irrelevant; the rollout restarted a released image.
The failure was silent — `rollout status` reported success, `/healthz` returned
200, and only checking for the `attempts` column showed the new code was not
running.

**Where the wrong belief came from:** hours earlier I read the deployment's
`kubectl.kubernetes.io/last-applied-configuration` annotation, which said
`"image":"nephos-api:dev"`. That annotation records the last `kubectl apply`,
not the live spec. Something changed the image afterwards and the annotation
kept its old value. I carried that stale reading forward as fact.

**Rule:** `last-applied-configuration` is history, not state. Read live fields
(`-o jsonpath='{.spec.template.spec.containers[*].image}'`) and read them at
the moment you depend on them. More generally: a deploy step must *verify the
new code is running*, not infer it from a successful rollout. `rollout status`
proves pods started, not that they contain your build.

**Rule for the plan:** any "build, import, restart" sequence needs a fourth
step that observes something only the new build can produce. Here that is the
`attempts` column; the plan happened to include an equivalent check further
down, which is the only reason this was caught before the install run.

---

## 12. A dependency bump had already broken OIDC provisioning, independently

**Found during validation, not planned for:** with the portal fix in place, the
`auth` binding stopped complaining about `external-host` and started actually
running Pulumi — which then failed with
`ModuleNotFoundError: No module named 'pkg_resources'`.

**Cause:** `b3837c5 chore(deps): bump setuptools from 80.10.2 to 83.0.0 (#84)`.
setuptools 81 removed `pkg_resources`, and `pulumiverse-zitadel` 0.2.0 imports
it at module load. nephos never imports setuptools or `pkg_resources` itself —
the dependency existed *only* to supply `pkg_resources` to that provider, and
nothing recorded that, so a routine bump sailed past the version that removed
the thing it was there for.

**Why no test caught it:** the provider is imported inside the Pulumi program
(`zitadel._oidc_pulumi_program`), which unit tests never execute. The suite was
green across the bump and has been green ever since.

**Fixed** by pinning `setuptools>=80.10.2,<81` with a seven-line comment naming
the consumer, the failure mode, and the condition for lifting the pin. The
comment is the actual fix; the version range is just its consequence.

**Rule:** a dependency that exists only to satisfy another package's import is
invisible to whoever bumps it. Say so at the pin. If a pin has no comment
explaining why it exists, treat that as a defect in its own right.

**Also worth noting:** this was the *second* independent cause of the same
user-visible symptom. Fixing the first one is what made the second one
reachable. A validation run that stops at "still broken" would have concluded
the portal fix did not work.

---

## 13. I walked into the exact hazard I had documented

**What happened:** restarting `nephos-api` after `kubectl cp`-ing the demo
catalog entry into the pod's registry clone crashlooped the init container —
`managed catalog registry core-registry has local changes; refusing to refresh`.
The deployment uses `strategy: Recreate`, so the old pod was already gone: the
control plane was **down**, not degraded.

**Why it is embarrassing:** this hazard is written up in the graph-demo
authoring report as a named finding, and again in this plan's own Task 9 step 2
as a "cleanup obligation". I wrote both, then did the restart before the
cleanup.

**Recovered by** scaling to zero, mounting the `nephos-state` PVC in a
throwaway pod, running `git checkout -- . && git clean -fd` there, and scaling
back. Roughly four minutes of downtime on a local cluster.

**Rule:** an obligation written as prose next to a step is not a safeguard. If
a sequence has a cleanup that must happen before some *later, unrelated* action,
either do the cleanup immediately after the action that creates the mess, or
make the later action verify the precondition first. Here: check
`git status --porcelain` in the pod *as the first line of* any restart, not as
a note further down the plan.

**Platform observation this earns:** a registry sync failure taking down the
whole control plane is harsh. The sync guards against refreshing a dirty
checkout, which is right, but the consequence — API will not boot — is
disproportionate to the cause, and there is no way to clean the checkout
without a PVC-mounting pod because the only container that could is the one
crashlooping. Degrading to "serve the catalog as-is and report the sync failure"
would be kinder. Not fixed here; out of scope.

---

## 14. Validation found a third blocker the plan could not have known about

**Not a plan flaw so much as a plan limit.** With the portal fix and the
setuptools pin both in place, OIDC provisioning gets all the way to creating a
Zitadel Project and then fails:

```
failed to create project: rpc error: code = Unimplemented
  desc = unexpected HTTP status code received from server: 404 (Not Found);
  transport: received unexpected content-type "application/json"
```

The installed `auth` Service runs `provisioning-transport: issuer-endpoint`,
which points the Pulumi provider at `auth.nephos.lcl:80` — the portal host, now
correctly derived. gRPC to that endpoint returns an HTTP error page rather than
gRPC.

Worth noting for whoever picks this up: `_should_use_internal_forward`'s `auto`
mode has the same blind spot as issue #61 — it port-forwards only for
`localhost`, `127.0.0.1`, `::1`, or a `.localhost` suffix, so `.lcl` (the domain
`nephos setup lcl` creates) falls through to `issuer-endpoint` and hits this.
Two suffix heuristics, same missing suffix, found one after the other.

**Rule:** a validation plan should expect that fixing one blocker exposes the
next. Budget for it, and do not let a run that ends "still broken" be read as
"the fix did not work" — check *which* error you are looking at. Here the error
changed three times, and each change was progress.

---

## 15. I fixed a symptom twice before finding the cause

**What happened:** the OIDC binding failed with a gRPC 404 through the portal
host. I concluded the transport heuristic was wrong (it does have the same
`.lcl` blind spot as #61), changed `auto` to port-forward for portal hosts, then
changed the client to dial the forward's own host. Both shipped and both were
wrong.

**Why they were wrong:** Zitadel validates the request origin against its
`ExternalDomain` and rejects a loopback origin outright —
`unable to set instance using origin http://127.0.0.1:53435 (ExternalDomain is
auth.nephos.lcl): Instance not found`. Port-forwarding can only work when the
external domain *also* resolves to the forward, which is exactly why the
original heuristic was restricted to `localhost`/`.localhost`. That restriction
was a correctness precondition wearing the costume of a suffix guess, and I read
the costume.

Worse: the second change would have broken the `.localhost` path that did work.

**The actual cause:** Zitadel serves gRPC and HTTP on one port over h2c, and
Traefik speaks HTTP/1.1 to a backend by default. Nothing told it otherwise, so
gRPC through any Nephos-generated Ingress 404s. One annotation on the Service
fixes it, and then the original transport default is correct after all.

**Both changes reverted.** Live testing is what exposed it; the unit suite was
green for both wrong versions.

**Rule:** when a mechanism has a narrow-looking guard, find out *why* the guard
is narrow before widening it. A precondition and a bad heuristic look identical
from the outside — the difference is whether something breaks when you relax it,
and the only way to know is to relax it and watch.

**Second rule:** two fixes in a row that move the error without resolving it is
a signal you are working on a symptom. Stop and ask what has to be true for the
call to succeed at all, rather than adjusting how it is dialled.
