# nephos

Nephos API 0.0.1 backend/control-plane implementation.

Manual test instructions: [docs/testing/api-0-0-1-manual.md](docs/testing/api-0-0-1-manual.md).

## How Nephos Works

Nephos is a desired-state control plane. API calls write platform intent into
SQLite, then the reconciler converges Nephos-owned runtime resources into the
selected Kubernetes context.

```mermaid
flowchart LR
  user["User or CLI"]
  api["Nephos API\nFastAPI"]
  db[("SQLite\ncanonical desired state")]
  queue["Reconciliation requests"]
  reconciler["In-process reconciler"]
  providers["Python provider layer\nPulumi + Kubernetes API"]
  cluster["Selected Kubernetes context"]

  user -->|"POST /apps, /services, lifecycle actions"| api
  api -->|"transaction: desired state + request"| db
  db --> queue
  queue --> reconciler
  reconciler --> providers
  providers --> cluster
  cluster -->|"observed runtime/status"| reconciler
  reconciler -->|"status snapshots"| db
  api -->|"GET resources/status"| user
```

> [!IMPORTANT]
> SQLite is the source of truth for Nephos desired state. Kubernetes and Pulumi
> are observed runtime/provider state, not the canonical platform model.

## Minimal Backend Flow

```bash
uv run nephos-api init
uv run nephos-api serve
```

```mermaid
sequenceDiagram
  autonumber
  participant Dev as Developer
  participant Init as nephos-api init
  participant DB as SQLite desired state
  participant Serve as nephos-api serve
  participant API as FastAPI + reconciler

  Dev->>Init: uv run nephos-api init
  Init->>DB: apply migrations
  Init->>DB: ensure internal platform domain
  Dev->>Serve: uv run nephos-api serve
  Serve->>DB: apply pending migrations
  Serve->>API: start API and reconciler worker
```

`init` does not install Apps, install Services, mutate Kubernetes, run Helm, or
create runtime reconciliation requests.

## Runtime And Ingress

Nephos targets the Kubernetes context selected by kubeconfig and environment,
not a specific Kubernetes distribution.

```mermaid
flowchart TB
  env[".env / process environment"]
  api["nephos-api"]
  kube["Selected kubeconfig/context"]
  ingress["IngressClass\nexplicit or auto-detected"]
  dns["Local DNS suffix\nexample: nephos.localhost"]
  browser["Browser"]
  controller["Ingress controller\nnginx, Traefik, etc."]
  app["Nephos App Service"]

  env -->|"NEPHOS_API_KUBECONFIG\nNEPHOS_API_KUBE_CONTEXT"| api
  api --> kube
  env -->|"NEPHOS_API_INGRESS_CLASS optional"| ingress
  kube --> ingress
  browser -->|"http://app.nephos.localhost"| dns
  dns --> controller
  controller -->|"Host rule from Nephos Ingress"| app
```

> [!NOTE]
> Ingress controllers do not provide DNS. `nephos.localhost` is the local
> no-hosts development suffix; `nephos.local` remains the semantic fallback
> internal domain.

## Runtime Proof

```bash
uv run nephos-api dev smoke
```

The smoke command creates a temporary internal reference catalog, installs a
PostgreSQL Service and reference web App through the API/reconciler, verifies
binding materialization and route convergence, checks stop/start lifecycle, and
destroys the reference resources.
