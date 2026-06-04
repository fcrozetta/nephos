# Kubernetes Runtime Target and Local Ingress DNS

- Status: accepted
- Date: 2026-06-01
- Tags: kubernetes, ingress, dns, testing, api-0-0-1

## Context and Problem Statement

Earlier Phase 1 language treated K3s as the default/reference runtime and tied
the local ingress controller choice to K3s shipping Traefik by default.

That is no longer the API 0.0.1 contract. Fer selected a Kubernetes-context
first model: Nephos should reconcile into whichever compatible Kubernetes
cluster the user selects through kubeconfig/context, such as Docker Desktop,
kind, kubeadm, K3s, or another local cluster.

The current local browser failure exposed a separate issue: creating a
Kubernetes Ingress and installing an ingress controller does not make
`hello-world.nephos.local` resolve on the developer machine.

## Decision

Nephos API 0.0.1 targets the selected Kubernetes kubeconfig/context, not a
specific Kubernetes distribution.

K3s is one compatible local cluster option, not an API assumption.

Runtime integration tests are Kubernetes tests, not K3s tests. They require a
pre-existing reachable selected Kubernetes cluster and explicit opt-in through:

```text
NEPHOS_API_RUN_KUBERNETES_TESTS=1
```

`NEPHOS_API_RUN_K3S_TESTS=1` remains a temporary compatibility alias.

`nephos-api` does not start, stop, reset, destroy, or otherwise manage the
cluster lifecycle for Docker Desktop, kind, kubeadm, K3s, or any other cluster.

Traefik may be the default Nephos-managed ingress controller for API 0.0.1, but
not because the selected cluster is assumed to be K3s.

Generated App Ingress resources set `ingressClassName` from:

1. `NEPHOS_API_INGRESS_CLASS`, when configured.
2. the selected cluster's single default `IngressClass`.
3. the selected cluster's single `IngressClass`.

If multiple `IngressClass` resources exist and none is default, Nephos leaves
`ingressClassName` unset and the cluster's ingress-controller behavior decides
whether the route is picked up.

Ingress routing and DNS resolution are separate:

- Traefik, or another ingress controller, watches Kubernetes Ingress resources
  and routes HTTP traffic once traffic reaches the cluster ingress endpoint.
- DNS, local resolver config, wildcard DNS, or a proxy decides whether a browser
  can resolve a hostname to that ingress endpoint.

For local no-`/etc/hosts` manual testing, use a resolvable root domain such as:

```text
nephos.localhost
```

With the default host pattern, an App named `hello-world` then gets:

```text
http://hello-world.nephos.localhost
```

This only removes the local DNS/hosts requirement. A reachable ingress
controller endpoint is still required.

## API 0.0.1 Bootstrap Impact

`uv run nephos-api init` keeps creating one default internal platform domain on
first initialization.

The fallback domain remains `nephos.local`.

For local browser testing without `/etc/hosts`, configure:

```text
NEPHOS_API_INTERNAL_DOMAIN=nephos.localhost
```

or pass:

```bash
uv run nephos-api init --internal-domain nephos.localhost
```

`init` remains desired-state/bootstrap work. Whether it should also install or
verify a cluster ingress controller is a separate API 0.0.1 bootstrap decision.

## Consequences

Documentation and test markers must stop using K3s as the general runtime
assumption.

Manual test instructions must not claim that Traefik removes the need for
hostnames to resolve.

The user-visible local route that avoids `/etc/hosts` cannot be
`*.nephos.local` unless Nephos also provides a local DNS/resolver helper later.

The first API 0.0.1 browser-openable local path is therefore:

```text
selected Kubernetes context + reachable ingress controller + resolvable local root domain
```

## Supersedes

- [K3s Dev Integration Mechanics](./20260522-k3s-dev-integration-mechanics.md)
  for runtime target naming and integration test naming.

## Open Questions

- Whether `uv run nephos-api init` should install/verify Traefik when a
  Kubernetes context is configured.
- Whether ingress controller bootstrap should instead be a separate
  `nephos-api platform bootstrap` command.
- Whether Nephos should provide a local DNS helper later for `*.nephos.local`.
