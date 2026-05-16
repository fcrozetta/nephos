# Agent Instructions for Nephos

Nephos is a personal/local platform control plane, not a Portainer clone.

The core model is:

- Apps: user-facing workloads/products.
- Services: shared platform capabilities/infrastructure.
- Capabilities: typed abilities exposed by Services and consumed by Apps.
- Runtime: K3s/Kubernetes substrate.

Do not use "plugin" for shared infrastructure. Use "Service".

Default backend: K3s.

Other Kubernetes backends may be added later through cluster adapters, but K3s is the primary real backend.

Nephos owns platform intent, catalogs, service binding, lifecycle state, dependency resolution, secrets injection policy, health/status, backups semantics, and ingress abstraction.

Kubernetes owns runtime primitives: Deployments, StatefulSets, Services, Ingress, PVCs, Secrets, ConfigMaps, Jobs, CronJobs, probes, scheduling, networking.

Do not turn Nephos into a generic container UI.
The differentiator is composable self-hosted infrastructure: Apps & Services, capability binding, and platform-level relationships.
