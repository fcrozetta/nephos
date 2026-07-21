# Getting started

This walks you from nothing to a running Nephos control plane with a web console,
your own admin account, and an installed workload whose secrets Nephos generates
for you. By the end you will not have typed a single service password.

> [!WARNING]
> Nephos is early and local-first. For a one-command LCL bootstrap that stands up
> the control plane in-cluster with OpenBao + the console, see
> [Quickstart: in-cluster (LCL)](#quickstart-in-cluster-lcl). The manual host-run
> flow below is the alternative and shows each moving part; the postgres/zitadel
> backbone is still installed by hand (see [What's still rough](#whats-still-rough)).

## Quickstart: in-cluster (LCL)

Run Nephos itself inside a local k3d cluster, one command, from the repo root:

```bash
uv run nephos setup lcl
```

This creates the k3d cluster + local routing (via
[`scripts/setup-local-routing.sh`](../scripts/setup-local-routing.sh); uses sudo
for dnsmasq/DNS), builds and imports the `nephos-api` image, applies the
in-cluster control-plane manifest, then drives the backbone over a one-shot
port-forward: sets the default domain (`nephos.lcl`), installs OpenBao (the core
secrets backend), and installs the console pointed at the in-cluster API. It ends
by printing the console `/setup` URL for your first-run admin.

Other verbs:

```bash
uv run nephos up lcl        # converge the control plane (idempotent apply)
uv run nephos status lcl    # deployment readiness
uv run nephos down lcl      # stop (scale to 0); --destroy --yes removes state
```

`setup` is convergent: re-run it if a step is interrupted. The rest of this page
walks the manual host-run flow, which is useful for understanding the pieces.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for the Python backend.
- [pnpm](https://pnpm.io/) for the console.
- A local Kubernetes cluster (e.g. [k3d](https://k3d.io/) or kind) **only if you
  want to deploy** workloads. Browsing the catalog and creating desired state
  work without one.

## 1. Run the Nephos API

```bash
cp .env.example .env          # local settings (SQLite path, internal domain)
uv run nephos-api init        # apply migrations, seed the internal domain
uv run nephos-api serve --port 8099
```

The API defaults to port 8000; use `--port 8099` so the console finds it out of
the box (or set `NEPHOS_API_URL` on the console instead). Browse the OpenAPI docs
at http://127.0.0.1:8099/docs.

## 2. Run the console and create your admin

The Nephos admin account is the **only credential a human provides**. It is
created on first run, through the browser.

```bash
cd ../nephos-console
pnpm install
export NEPHOS_CONSOLE_SESSION_SECRET="$(openssl rand -hex 32)"   # signs the session cookie
# export NEPHOS_API_URL=http://127.0.0.1:8000   # only if the API is not on 8099
pnpm dev
```

Open the printed URL. On first run every route redirects to `/setup`: pick a
username and password, and Nephos creates the admin (only ever once — the API
refuses a second admin). You are signed straight in.

## 3. Browse and install from the catalog

The catalog lists Apps and Services from the managed registries. Pick one and
install it: Nephos records your intent (returns `202 Accepted`) and a reconciler
converges it. To actually deploy to a cluster, point the API at one before you
`serve`:

```bash
# in .env
NEPHOS_API_KUBE_CONTEXT=k3d-nephos
```

## 4. Secrets, without passwords

You never supply service passwords. Nephos generates them and keeps them in a
secrets provider; the only human credential is the admin from step 2.

### As an author: declare a generated secret

In a Service (or App) manifest, mark a config option as generated and map it to a
runtime value:

```yaml
spec:
  config:
    options:
      - name: admin-password
        type: string
        generate:
          kind: password   # v1: password only
          length: 32
  runtime:
    type: provider
    provider:
      name: my-service
    values:
      mappings:
        - from: { kind: config, name: admin-password }
          to:   { helmValue: adminPassword }
```

You do **not** write a `secrets://` reference. Nephos synthesizes one
(`secrets://svc/<slug>/admin-password/value`) and materializes it at deploy time.

### As an operator: nothing to fill in

The install form hides generated options (it shows a short "Nephos generates these
for you" note). At deploy Nephos generates the value **once**, stores it in the
secrets provider, and injects it into the workload. On every later deploy or
reconcile it reads the existing value back and never regenerates it, so a redeploy
can never rotate a live secret out from under a running workload.

### Prerequisite: the secrets provider

`secrets://` resolves through the managed OpenBao Service. Install the `openbao`
Service (it provides the `secrets-backend` capability), then enable the
materializer before `serve`:

```bash
# in .env
NEPHOS_API_OPENBAO_PERSISTENT=1
NEPHOS_API_BAO_ADDR=http://127.0.0.1:8200   # your OpenBao address
NEPHOS_API_BAO_KV_MOUNT=secret
```

Nephos-owned values live under `secret/data/nephos/<scope>/<name>` so they never
collide with anything you store by hand. If OpenBao is not configured, a
`secrets://` reference fails closed at deploy time rather than deploying without a
secret.

> The older `op://` (1Password CLI) and `bao://` (OpenBao path) references still
> resolve read-only for existing installs, but new manifests should use generated
> options as above.

## What's still rough

Honest edges you will hit today:

- **Backbone is OpenBao + console.** `nephos setup lcl` brings up the control
  plane, OpenBao, and the console. Capability providers like postgres are not
  installed by setup; the plan is to install them on demand when something needs
  them (lazy provider install, resolving core -> mythos -> community; see
  #79). For now, install postgres/zitadel by hand.
- **Local ingress/DNS needs one setup step.** Apps get URLs on the internal
  domain (`<slug>.<domain>`). For those to open directly in a browser, run
  [`scripts/setup-local-routing.sh`](../scripts/setup-local-routing.sh) — it
  publishes the k3d ingress on ports 80/443 and configures a dnsmasq wildcard so
  `*.<domain>` resolves. `.localhost` is the only suffix that needs no DNS setup
  (Chrome resolves it), but it can't reach a non-80 ingress port; a dnsmasq'd
  suffix like `nephos.lcl` on ports 80/443 gives clean, portless URLs in any
  browser. Requires host ports 80/443 to be free.
- **Single admin, password login.** Roles and OIDC (via Zitadel) are planned, not
  here yet.
