# Nephos Vision

Nephos is a platform control plane for composable self-hosted infrastructure.

It provides a unified platform experience for installing, managing, wiring, stopping, starting, and observing self-hosted Apps and Services.

Nephos is local-first and intended to run on user-owned Kubernetes infrastructure selected through kubeconfig/context.

## Core Thesis

Self-hosting is currently too fragmented.

Most setups require users to manually combine:

- application containers
- databases
- object storage
- ingress
- secrets
- backups
- health checks
- service dependencies
- manual lifecycle operations

Nephos should turn these into platform-level relationships.

Core abstraction:

Apps consume capabilities exposed by Services.

## Strategic Direction

Nephos focuses on:

- composable infrastructure
- Apps and Services
- capability binding
- lifecycle management
- dependency awareness
- operational transparency
- local infrastructure ownership

Nephos intentionally operates above raw container/runtime orchestration abstractions.

## Product Shape

Nephos should eventually provide:

- CLI
- API
- Web UI
- App catalog
- Service catalog
- dependency graph
- install/start/stop/remove/destroy operations
- health/status views
- ingress visibility
- backup/status visibility

The first implementation should optimize for correctness of the platform model rather than UI polish.

## Non-Goals

Nephos should not become:

- a generic container dashboard
- a raw Kubernetes dashboard
- a thin wrapper around kubectl
- a collection of unrelated deployment scripts
- a runtime scheduler
- a replacement for Kubernetes primitives

Kubernetes owns runtime orchestration.

Nephos owns platform intent.
