# Nephos Decisions

## D001: Nephos is a platform control plane

Nephos is a platform control plane for composable self-hosted infrastructure.

It should not be modeled as a generic container manager.

## D002: K3s is the default runtime backend

K3s is the primary runtime backend.

Other Kubernetes backends may be supported later through cluster adapters.

## D003: Kubernetes is the runtime API boundary

Nephos can be backend-agnostic mostly above the Kubernetes API layer.

Below that layer, cluster lifecycle is backend-specific.

## D004: Apps and Services are top-level concepts

Nephos has two primary installable concepts:

- Apps
- Services

Apps are user-facing workloads.

Services are shared platform infrastructure/capabilities.

## D005: Services expose capabilities

Services expose typed capabilities.

Apps consume capabilities through bindings.
