---
name: run-nephos-api
description: Build, run, deploy, test, and drive the nephos-api control plane. Use when asked to run or start nephos, serve the API, deploy nephos to the k3d cluster, install or reconcile a Service, reveal a Service credential, check portal URLs or ingress, or smoke-test nephos-api.
---

# Run nephos-api

`nephos-api` is a FastAPI control plane. It stores desired state in SQLite and
reconciles it into Kubernetes through Pulumi. There is no UI here (that is the
separate `nephos-console` repo), so **the API is the surface** and the way to
drive it is HTTP.

Everything runs through one harness:

```
.claude/skills/run-nephos-api/driver.sh
```

All paths below are relative to the repo root. Run `driver.sh` with no arguments
for the subcommand list.

## Two modes, and picking the right one

| Mode | What runs | Use it for |
|---|---|---|
| `local-*` | API on this host, throwaway SQLite + a generated catalog fixture, no cluster, no network | catalog/schema/API work. Most PRs. Seconds. |
| `cluster-*` | image built into k3d, driving the in-cluster Deployment | anything touching reconciliation, providers, ingress, secrets. Minutes. |

`local-*` has **no runtime adapter**, so installs record desired state and stop:
status stays `pending` and nothing reaches Kubernetes. That is not a failure. If
you need a workload to actually appear, you need `cluster-*`.

## Prerequisites

macOS with Docker Desktop running. Verified present:

```bash
which uv curl python3 docker k3d kubectl
```

`cluster-*` additionally needs a k3d cluster named `nephos`. The driver starts it
if it is stopped but will not create one.

## Bring up a cluster from nothing

The driver does not cover this. Verified 2026-08-15 on a machine with zero k3d
clusters.

`uv run nephos setup lcl` does the whole thing — cluster, host DNS, image, deploy,
port-forward, **and the OpenBao + console backbone**. But it shells out to `sudo`
unconditionally for dnsmasq and `/etc/resolver`, with no skip flag, so it cannot run
unattended. If the host is already routed from a previous install (check
`/etc/resolver/nephos.lcl` and `dig +short @127.0.0.1 foo.nephos.lcl`), that sudo
step is a no-op you still cannot skip.

The sudo-free path, and what each step actually needs:

```bash
# 1. cluster. Exactly what setup-local-routing.sh runs; the two @loadbalancer
#    mappings are what make http://<slug>.nephos.lcl portless. k3s' bundled
#    Traefik is used as-is: no --disable=traefik, no --api-port, no agents.
k3d cluster create nephos --port "80:80@loadbalancer" --port "443:443@loadbalancer" --wait

# 2. control plane only
docker build -t nephos-api:dev . && k3d image import nephos-api:dev -c nephos
uv run nephos up lcl

# 3. in-cluster DNS. `up` and `setup` BOTH skip this; cli.py has no coredns reference
kubectl --context k3d-nephos apply -f deploy/coredns-split-horizon.yaml
kubectl --context k3d-nephos -n kube-system rollout restart deploy/coredns

# 4. the backbone `up` did NOT install (see below)
```

**`nephos up lcl` is not `nephos setup lcl` minus sudo.** `up` renders, applies and
waits for the control plane and nothing else: **no OpenBao, no console**. Both
omissions bite:

- **OpenBao must exist before Postgres.** Postgres's `admin-password` is `required`
  *with* `generate:`, so it is minted through the secrets provider. With no provider
  the install sits at `secret_ref_provider_unavailable` — `lifecycle: running`, **no
  pod**, and nothing surfaces it except `status.reason`. Order is
  **OpenBao → Postgres → Zitadel**. And since a blocked reconciliation is terminal,
  installing OpenBao afterwards is not enough: re-POST
  `/services/postgres/actions/reconcile`.
- **No console means no UI**, so you end up driving the API by hand. See "The API has
  no Ingress" below before you reach for a port-forward.

**Read the platform domain row's name; do not derive it.** `up` seeds it as
**`internal`** (domain `nephos.lcl`); the `setup` path seeds `lcl`. Guessing 404s the
portal opt-in. `GET /platform/config/domains` tells you.

**Opt the domain in to Service portals BEFORE installing Zitadel.** Zitadel has no
`external-host` option at all — `externalHost`/`externalPort`/`externalSecure` are
portal-derived, and portals are default-deny per root domain, so without this the
mapping resolves to nothing and the deploy blocks:

```bash
curl -sS -X POST http://127.0.0.1:8099/platform/config/domains/internal/actions/set-service-portals \
  -H 'content-type: application/json' -d '{"allowed": true}'
```

Zitadel needs exactly three operator-supplied options, in **kebab-case** (the
camelCase names are the Helm values the mappings produce, never what you send):
`admin-password`, `master-key` (checked `!= 32`, so exactly 32 chars), and
`bootstrap-machine-key-expiration` (RFC3339 UTC). `admin-username` *does* have a
default, but it is the literal `root@zitadel.nephos.local` regardless of your slug —
set it, then read back what the instance actually got from
`kubectl -n svc-auth get secret svc-auth-zitadel -o jsonpath='{.data.admin-username}'`.

Install console last; it needs no config (`api-url` defaults to the in-cluster
Service DNS).

## The API has no Ingress, and the console is the interface

`deploy/nephos-incluster.yaml` contains **no `kind: Ingress`** for `nephos-api`. That
is deliberate: the console reaches the control plane in-cluster at
`http://nephos-api.nephos-system.svc.cluster.local:8099`, so nothing needs
forwarding. Humans drive Nephos at `console.nephos.lcl`.

`kubectl port-forward svc/nephos-api 8099:8099` — which `cluster-deploy` sets up, and
which every `curl` example here assumes — is a **debugging and scripting channel**,
not part of a working install. If you find yourself port-forwarding to *operate*
Nephos rather than to debug it, the console is probably missing. Install it.

## Run: local (start here)

```bash
.claude/skills/run-nephos-api/driver.sh local-smoke
```

That is the full loop and it exits non-zero on any failure. It syncs deps, writes
a self-contained catalog fixture, runs `init`, serves on `127.0.0.1:8099`, then
asserts its way through: catalog load, a turnkey install with `config={}`, a
portal reporting `unpublished`, opting a root domain in, an unauthenticated
reveal getting `401`, minting a token, and a fail-closed reveal.

Verified output:

```
== catalog sees the fixture Service
  services: ['demodb']
  portals: ['console']
  credentials: {'username': 'postgres', 'usernameOption': None, 'passwordOption': 'admin-password'}
== install (config={} : admin-password is generated, needs no input)
  slug: demodb | lifecycle: running
== portal reports unpublished (default-deny per root domain)
  published: False | reason: no_portal_eligible_domain
== opt the domain in to Service portals
  published: True | url: http://demodb.nephos.lcl
== reveal is gated
  unauthenticated reveal: 401
== mint a token and reveal
  fail-closed: secret_ref_provider_unavailable
== PASS
```

To poke it by hand instead of running the whole smoke:

```bash
.claude/skills/run-nephos-api/driver.sh local-up
.claude/skills/run-nephos-api/driver.sh api GET /catalog/services
.claude/skills/run-nephos-api/driver.sh api POST /services '{"catalogRef":{"kind":"Service","name":"demodb"},"config":{}}'
.claude/skills/run-nephos-api/driver.sh local-down
```

Server log while it is up: `/tmp/nephos-driver/serve.log`.

## Run: cluster

```bash
.claude/skills/run-nephos-api/driver.sh cluster-deploy
.claude/skills/run-nephos-api/driver.sh cluster-smoke
```

`cluster-deploy` builds, imports into k3d, repoints the Deployment, patches the
pull policy, waits for rollout, and leaves a port-forward on `127.0.0.1:8099`.
`cluster-smoke` lists installed services and the generated ingress. Verified:

```
== installed services
  arcadedb     running   healthy
  auth         running   healthy
  openbao      running   healthy
  postgres     running   healthy
== generated ingress
  app-console    nephos-route-web       console.nephos.lcl
  svc-arcadedb   nephos-route-studio    arcadedb.nephos.lcl
  svc-auth       nephos-route-console   auth.nephos.lcl
== PASS
```

Reveal a credential the platform generated (nobody ever typed the Postgres one):

```bash
TOK=$(.claude/skills/run-nephos-api/driver.sh cluster-mint-token 10 | tail -1)
NEPHOS_DRIVER_TOKEN="$TOK" .claude/skills/run-nephos-api/driver.sh \
  api POST /services/postgres/config/admin-password/actions/reveal
.claude/skills/run-nephos-api/driver.sh cluster-revoke-tokens
```

Verified: `source: secrets-provider | value: <32 chars>`. **Revoke when done** —
that token reads every Service credential until it expires.

## Test

```bash
.claude/skills/run-nephos-api/driver.sh test
```

Runs `ruff check` then `pytest -q -m "not kubernetes"`. Both clean on this branch.
No count is quoted here on purpose: it drifts every time a test lands, and a stale
number reads as a failure. The 3 deselected tests need a live cluster and
`NEPHOS_API_RUN_KUBERNETES_TESTS=1`.

## Gotchas

- **`NEPHOS_API_INTERNAL_DOMAIN` has no default and `init` fails fast without
  it.** Deliberate: a baked-in fallback used to diverge from the DB
  `platform_domains` row that actually drives routing, so editing `.env` looked
  like it did nothing. The driver passes it explicitly.
- **Registry sync runs at startup and is uncaught.** `create_app` calls
  `ensure_managed_catalog_registries` with no try/except, so a registry problem
  crashes the API on boot rather than degrading. It also refuses a checkout that
  is dirty or ahead of upstream, so you cannot just edit files in
  `.nephos/registries/core-registry` and restart.
- **`NEPHOS_API_CATALOG_ROOTS` replaces the managed registries, it does not add
  to them.** It also blanks the source ids, so entries arrive as source
  `default` instead of `core-registry`. Point it at a registry whose services are
  already installed and those instances break with `catalog_source_not_found`,
  because their rows still reference the old source. Fine for a throwaway DB
  (what `local-*` does), wrong against a real one.
- **To test local registry edits against the cluster, override the URL, not the
  roots.** Commit locally, `git clone --bare` it, `kubectl cp` it onto the PVC,
  set `NEPHOS_API_CORE_REGISTRY_URL` to that path, and delete
  `/data/registries/core-registry` first — otherwise the drift check sees the old
  https origin and refuses. This preserves the `core-registry` source id.
- **`set image` alone gives you `ImagePullBackOff`.** The manifest's default tag
  is `:latest`, so `imagePullPolicy` defaults to `Always`, and `set image` does
  not change the policy. A locally-imported tag still gets pulled and fails. The
  driver patches both containers to `IfNotPresent`; the manifest says so in a
  comment too.
- **`docker build` is not enough.** k3d nodes cannot see the host daemon's
  images; `k3d image import` is required every time.
- **A Service's Kubernetes Service is not named after the release.** Providers
  append a component suffix: `svc-postgres-postgresql`, `svc-arcadedb-arcadedb`,
  `svc-auth-zitadel`. Assuming `svc-<slug>` produces a valid Ingress that routes
  to nothing and serves 404.
- **`destroy` needs an explicit confirmation string** in the body:
  `{"confirm": "destroy <slug>"}`. Without it you get
  `409 destructive_confirmation_required`.
- **The API is unauthenticated except the reveal endpoint.** Any pod that can
  reach port 8099 gets `200` from `/services`. Only
  `/services/{slug}/config/{option}/actions/reveal` requires a bearer token. Do
  not read that as the API being authenticated.
- **Generated secrets are absent from config, not redacted.** For a generated
  option `config_json` is `{}`, so nothing shows even as `[REDACTED]`. Reveal
  resolves it from the secrets provider using the coordinate the deployer
  synthesizes, `secrets://svc/<slug>/<option>/value`.
- **Locally there is no secrets provider**, so revealing a generated secret
  correctly returns `503 secret_ref_provider_unavailable`. The smoke asserts that
  rather than treating it as a pass or a bug.
- **`*.nephos.lcl` does not resolve from inside the cluster** by default, only
  from the host. An in-cluster App cannot reach `auth.nephos.lcl`, and Zitadel
  rejects any other Host header because it looks up its instance by domain.
  `kubectl apply -f deploy/coredns-split-horizon.yaml` fixes it.
- **Zitadel install is fussy**: `master-key` must be exactly 32 characters, and
  `admin-password` must satisfy length plus lower, upper, digit and symbol. Both
  fail at deploy time inside Pulumi, not at install, so the API returns `202` and
  the service goes `degraded`.
- **`cluster-deploy` guards every step explicitly.** The driver sets `pipefail`
  but not `errexit`, so an unguarded failure would be skipped and the final
  health check would still pass against the old, still-running deployment:
  exit 0 having deployed nothing. Keep the `|| die` and `PIPESTATUS` checks if
  you add steps.
- **A blocked Service shows `lifecycle: running` with no pod.** Lifecycle is desired
  state, not health. A Service can sit at `running` forever while `status.reason`
  says `secret_ref_provider_unavailable` and nothing was ever created. Poll
  `status.reason` for `runtime_deployed`, and cross-check with `kubectl get pods -n
  svc-<slug>`; a lifecycle check alone reports success for a Service that does not
  exist.
- **A stopped k3d cluster looks like `0/1` servers, not absent.** `k3d cluster
  start nephos` is far cheaper than recreating; the driver checks for this.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `init` exits non-zero, log mentions internal domain | `NEPHOS_API_INTERNAL_DOMAIN` unset. Pass `--internal-domain`. |
| API exits at startup with a git/registry error | Startup registry sync. Use `NEPHOS_API_CATALOG_ROOTS` for a throwaway run, or fix the checkout. |
| `catalog_source_not_found` on an installed service | Source ids changed under it, usually from setting `CATALOG_ROOTS` against a real DB. |
| Pod `ImagePullBackOff` after `set image` | `imagePullPolicy` still `Always`. Patch both containers to `IfNotPresent`. |
| Ingress exists, host resolves, but 404 | Backend Service name wrong. It is `<release>-<component>`, not `svc-<slug>`. |
| `409 destructive_confirmation_required` | Add `{"confirm":"destroy <slug>"}`. |
| Service stuck `running`, `secret_ref_provider_unavailable`, no pod | No secrets provider. Install OpenBao, then **re-POST** `/services/<slug>/actions/reconcile` — blocked is terminal. |
| `404` on `/platform/config/domains/<name>/actions/set-service-portals` | Wrong row name. `nephos up` seeds `internal`, `nephos setup` seeds `lcl`. `GET /platform/config/domains` first. |
| Zitadel deploy blocks with nothing obviously wrong | Service portals not opted in for the root domain. Zitadel's `externalHost` is portal-derived and portals are default-deny. |
| `console.nephos.lcl` does not exist | `nephos up lcl` installs no console. `POST /apps` with `{"catalogRef":{"kind":"App","name":"console"}}`. |
| `401 auth_token_required` on reveal | Mint a token; `cluster-mint-token` for in-cluster, `mint-token` for local. |
| `401 auth_token_invalid` on reveal | Token expired or revoked. Mint a fresh one. |
| `503 secret_ref_provider_unavailable` | No secrets provider wired. Expected locally; in-cluster means OpenBao is unreachable. |
| Port 8099 already bound | A stale port-forward. `pkill -f "port-forward svc/nephos-api"`, or set `NEPHOS_DRIVER_PORT`. |
| `sqlite3.OperationalError: unable to open database file` from `mint-token` | In-cluster the DB is on the PVC. Use `cluster-mint-token`. |

## Notes

- `NEPHOS_DRIVER_PORT`, `NEPHOS_DRIVER_DIR`, and `NEPHOS_DRIVER_IMAGE` override
  the port, scratch dir (`/tmp/nephos-driver`), and image tag
  (`nephos-api:driver`).
- `cluster-deploy` repoints the Deployment at `nephos-api:driver`. If you were
  running a different local tag, that replaces it.
- The committed version stays `0.0.0`; the release tag is the source of truth and
  CI rewrites it at build.
