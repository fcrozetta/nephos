# Resource Policy Philosophy

- Status: accepted
- Date: 2026-05-17
- Tags: resources, phase-1, kubernetes, scaling, non-goals

## Context and Problem Statement

Nephos needs to decide how much resource management it owns initially.

Kubernetes exposes many low-level resource and scheduling controls:

- CPU requests and limits
- memory requests and limits
- replicas
- autoscaling
- quotas
- affinity and anti-affinity
- node selectors
- tolerations
- storage class details

Nephos should not expose raw Kubernetes knobs as the primary product UX, but Phase 1 also should not pretend to have a mature resource management model.

## Decision

Phase 1 does not implement a Nephos resource policy system.

Phase 1 runtime replica behavior is simple:

- running App or Service: replicas `1`
- stopped or disabled App or Service: replicas `0`

Resource profiles are reserved for future design but not defined in Phase 1.

Do not introduce named profiles such as small, medium, or large until schema design is approved.

Do not expose raw Kubernetes CPU/memory requests and limits as the primary Nephos UX.

Do not implement HA, autoscaling, affinity, anti-affinity, quotas, or scheduling policy in Phase 1.

If an underlying chart or curated runtime manifest includes sane CPU/memory defaults, Nephos may pass or preserve those values as deployment plumbing.

Those values are not a Nephos-level resource policy yet.

## Consequences

Pods may run without explicit Nephos-defined CPU/memory requests or limits.

In Kubernetes this can place workloads into BestEffort or chart-defined QoS behavior depending on the generated runtime objects.

This is acceptable for the local-first Phase 1 target, but it is not a production-grade isolation model.

Under node pressure, workloads without requests/limits may be starved, evicted, or killed.

Nephos should not claim capacity planning or resource isolation guarantees in Phase 1.

Future resource profiles should be designed after real workload patterns are clearer.

## Notes

The Phase 1 priority is preserving the platform model:

Apps + Services + capabilities + bindings + lifecycle semantics.

Do not turn resource management into raw Kubernetes UX.
