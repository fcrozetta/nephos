# Getting started

This walks you from nothing to a running Nephos control plane with a web console,
your own admin account, and an installed workload whose secrets Nephos generates
for you. By the end you will not have typed a single service password.

> [!WARNING]
> Nephos is early and local-first. The API + console + secrets flow below work
> today; the one-command local cluster and backbone bring-up do not yet (see
> [What's still rough](#whats-still-rough)).

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

- **No one-command local backbone.** Creating the cluster and installing OpenBao
  as the secrets provider is still manual; there is no `nephos up` yet.
- **Local ingress/DNS is manual.** Apps get URLs on the internal domain
  (`<slug>.nephos.localhost` by default); wiring that to your cluster's ingress is
  on you for now.
- **Single admin, password login.** Roles and OIDC (via Zitadel) are planned, not
  here yet.
