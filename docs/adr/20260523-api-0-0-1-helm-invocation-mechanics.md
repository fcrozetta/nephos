# API 0.0.1 Helm Invocation Mechanics

- Status: superseded
- Date: 2026-05-23
- Tags: helm, runtime, reconciliation, phase-1

Superseded by:

- `20260529-pulumi-provider-boundary.md`

This ADR records the direct Helm CLI adapter that proved the initial runtime
path. The accepted forward direction is an internal Python Pulumi provider
package behind the reconciler. Helm may still be used underneath that provider
where Helm charts give leverage.

## Context and Problem Statement

Phase 1 accepts Helm chart runtime deployment references underneath Nephos manifests.

API 0.0.1 now needs an implementation path that lets the reconciler deploy App and Service runtime resources without making Helm the product API or letting API handlers mutate Kubernetes inline.

## Decision

Use the Helm CLI as a backend-owned runtime adapter for API 0.0.1.

The reconciler invokes Helm only through a narrow Python adapter.

API handlers and CLI clients do not call Helm directly.

The adapter uses argument lists, not shell strings.

Initial install/update operation:

```text
helm upgrade --install <release> <chart>
  --repo <repository>
  --version <version>
  --namespace <namespace>
  --create-namespace
  --wait
  --timeout <duration>
  -f <generated-values-file>
```

Initial teardown operation:

```text
helm uninstall <release>
  --namespace <namespace>
  --wait
  --timeout <duration>
```

Release names use the accepted runtime namespace names:

- App instance: `app-<slug>`
- Service instance: `svc-<slug>`

Namespaces use the same names.

The adapter may pass `--kube-context` when `NEPHOS_API_KUBE_CONTEXT` is set.

When `NEPHOS_API_KUBECONFIG` is set, the adapter passes it through the `KUBECONFIG` environment variable.

Nephos generates Helm values from validated manifest mappings and desired state.

Generated values files are temporary runtime artifacts and must not become product API, catalog source of truth, or committed examples.

Do not expose arbitrary Helm values as primary Nephos UX in API 0.0.1.

## Consequences

Helm remains runtime plumbing below the Nephos manifest layer.

The implementation can use pinned chart repository/name/version from validated catalog manifests.

Runtime errors from Helm are reconciler errors and become failed reconciliation requests with status evidence.

Future SDK-based Helm integration, server-side controllers, or raw-manifest fallback can replace the adapter without changing API handler semantics.

## Open Questions

- exact timeout default after real K3s timings are measured
- exact status evidence fields for Helm release revision and chart metadata
- raw Kubernetes manifest fallback invocation shape
