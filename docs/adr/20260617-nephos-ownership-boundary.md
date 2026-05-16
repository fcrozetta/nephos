# Nephos Ownership Boundary

- Status: accepted
- Date: 2026-05-17
- Tags: architecture, ownership, kubernetes, boundaries

## Context and Problem Statement

Nephos must avoid reimplementing Kubernetes while still providing a higher-level platform model.

The project needs a clear ownership boundary.

## Decision

Nephos owns platform intent and platform relationships.

Kubernetes owns runtime mechanics.

## Nephos Owns

Nephos owns:

- app catalog
- service catalog
- dependency resolution
- capability binding
- resource provisioning
- secrets injection policy
- lifecycle state
- health/status aggregation
- ingress abstraction
- backup semantics
- platform relationships

## Kubernetes Owns

Kubernetes owns:

- scheduling
- networking primitives
- runtime objects
- Deployments
- StatefulSets
- Services
- Ingress
- PVCs
- Secrets
- ConfigMaps
- Jobs
- CronJobs
- probes

## Rationale

Nephos should use Kubernetes as a substrate, not compete with it.

Nephos should not leak raw Kubernetes complexity directly into the product model.

## Consequences

Nephos must provide platform abstractions for Apps, Services, capabilities, bindings, lifecycle, ingress intent, and storage intent.

Kubernetes resources are implementation details beneath those abstractions.

## Notes

Nephos is not Kubernetes exposed to users.

Nephos is a platform model implemented on Kubernetes.
