# Nephos Resource Policy

## Phase 1 Decision

Phase 1 does not implement a Nephos resource policy system.

Runtime replica behavior is simple:

- running App or Service: replicas `1`
- stopped or disabled App or Service: replicas `0`

No HA is supported in Phase 1.

No autoscaling is supported in Phase 1.

No affinity or anti-affinity is supported in Phase 1.

No quota system is supported in Phase 1.

No scheduling policy is supported in Phase 1.

## CPU and Memory

Nephos does not expose CPU/memory requests or limits as the primary Phase 1 UX.

Nephos does not invent global CPU/memory defaults in Phase 1.

If an underlying Helm chart or curated runtime manifest includes sane resource defaults, Nephos may preserve or pass those as deployment plumbing.

Those values are not a Nephos-level resource policy.

If Nephos does not specify resources and the generated Kubernetes objects do not specify resources, Kubernetes may run the Pods as BestEffort workloads.

This is acceptable for local-first Phase 1, but it is not a production-grade isolation model.

## Resource Profiles

Resource profiles are reserved for future design.

Do not define names such as small, medium, large, or custom until Fer approves the resource-profile schema.

Future profiles should be Nephos-level concepts, not raw Kubernetes resource snippets exposed as the main UX.

## Failure Modes

Without explicit resource requests and limits:

- a workload can consume too much memory
- node pressure may cause eviction or OOM kills
- noisy workloads can degrade other Apps or Services
- Nephos cannot provide strong capacity planning

Phase 1 should be honest about this limitation.

## Guardrail

Do not turn resource policy into a Kubernetes dashboard feature.

Nephos may eventually provide sizing intent, but raw Kubernetes knobs must not become the primary product model.
