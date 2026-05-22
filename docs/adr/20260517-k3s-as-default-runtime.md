# K3s as the Default Runtime

- Status: accepted
- Date: 2026-05-17
- Tags: runtime, kubernetes, k3s, cluster

## Context and Problem Statement

Nephos is being redesigned from a container-management-style system into a platform control plane for composable self-hosted infrastructure.

The runtime substrate needs to support Apps, Services, capability binding, lifecycle state, storage, ingress, health, and future dependency-aware operations.

Docker Compose is simple, but it becomes limiting once Nephos needs platform semantics.

Kubernetes provides a common runtime API for workloads, networking, storage, secrets, health probes, and declarative reconciliation.

## Decision

Use K3s as the default real runtime backend for Nephos.

Other Kubernetes-compatible backends may be added later through cluster adapters, but K3s is the primary backend.

## Rationale

K3s provides a practical Kubernetes substrate for local and self-hosted infrastructure.

Nephos should use Kubernetes as the runtime API rather than building its own orchestration layer.

The important abstraction boundary is:

- above the Kubernetes API: mostly backend-agnostic
- below the Kubernetes API: backend-specific cluster lifecycle

## Consequences

Nephos will target K3s first.

Future backends such as kind, minikube, or external kubeconfig environments may be implemented later.

These future backends should not be treated as equal priority unless a concrete need appears.

K3s is the default real runtime.

kind and minikube are better suited for development, testing, or demo scenarios.

## Notes

Nephos should not expose Kubernetes directly as the product model.

Kubernetes is the substrate.

Nephos is the platform control plane.
