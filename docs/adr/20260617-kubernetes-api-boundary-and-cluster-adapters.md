# Kubernetes API Boundary and Cluster Adapters

- Status: accepted
- Date: 2026-05-17
- Tags: kubernetes, cluster, adapters, runtime

## Context and Problem Statement

Different Kubernetes distributions and local cluster tools expose the same Kubernetes API after the cluster exists.

However, cluster lifecycle is not standardized by Kubernetes.

Starting, stopping, destroying, upgrading, and discovering clusters differs between K3s, kind, minikube, Docker Desktop Kubernetes, and external kubeconfig environments.

## Decision

Nephos will treat Kubernetes as the common runtime API only after a cluster exists.

Cluster lifecycle must be isolated behind backend-specific cluster adapters.

## Rationale

Nephos can be backend-agnostic for workload deployment, services, ingress, secrets, PVCs, config, and health checks.

Nephos cannot be backend-agnostic for cluster lifecycle without adapter-specific logic.

## Consequences

Nephos should have a cluster adapter layer.

Initial adapter:

- k3s

Possible later adapters:

- kind
- minikube
- external kubeconfig
- Docker Desktop Kubernetes

Cluster commands should route through adapters.

App and Service commands should operate against Nephos platform state and Kubernetes runtime state.

## Command Boundary

Cluster lifecycle:

- nephos cluster init
- nephos cluster up
- nephos cluster down
- nephos cluster status
- nephos cluster destroy

Platform lifecycle:

- nephos app *
- nephos service *

`nephos up` and `nephos down` may exist as shorthand for cluster lifecycle, not App lifecycle.

## Notes

Do not pretend all Kubernetes backends are equivalent.

They behave similarly above the Kubernetes API line.

They differ below it.
