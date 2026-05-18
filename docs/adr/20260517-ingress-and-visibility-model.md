# Ingress and Visibility Model

- Status: accepted
- Date: 2026-05-17
- Tags: ingress, networking, traefik, visibility, phase-1

## Context and Problem Statement

Nephos needs to expose Apps and possibly some Services through routes.

Ingress behavior must support local-first infrastructure while allowing public/private/tailnet modes later.

K3s commonly includes Traefik, making it a practical default.

## Decision

Use Traefik as the Phase 1 default ingress controller because K3s includes Traefik by default.

Nephos owns ingress intent.

Kubernetes owns ingress resources.

Nephos should generate and reconcile Kubernetes Ingress resources from Nephos route intent, but raw Ingress YAML must not become the primary Nephos UX.

## Visibility Modes

Phase 1 implements:

- local

Reserve these visibility modes for later:

- private
- public
- tailnet

`local` means the route is intended for the local/self-hosted environment and the user-controlled network path around it.

Phase 1 does not automate public DNS, Cloudflare Tunnel, Tailscale, tailnet exposure, or certificate management.

However, Nephos-generated local ingress must be compatible with a manually configured Cloudflare Tunnel or equivalent user-managed tunnel.

The practical requirement is:

- Fer may start/configure Cloudflare Tunnel manually
- the tunnel may route a wildcard or subdomain such as `*.nephos.fcrozetta.app` to the cluster ingress
- Nephos should not require a different ingress model for that to work
- Nephos does not manage Cloudflare credentials, tunnel lifecycle, or DNS automation in Phase 1

## Stopped And Removed Apps

Stopping an App keeps route intent.

In Phase 1, stopped Apps may keep runtime ingress objects.

Status should report that the App is stopped or unavailable rather than pretending the route is healthy.

Removing an App removes runtime ingress objects.

Destroying an App removes runtime ingress objects and persistent data according to lifecycle semantics.

## Nephos Responsibilities

Nephos should manage:

- route intent
- visibility mode
- ingress metadata
- user-facing URL/status
- public/private/tailnet distinction
- integration hooks for DNS/tunnels later

## Open Questions

Need to define:

- local DNS behavior
- wildcard domain behavior
- TLS/cert-manager strategy
- whether Services can expose admin routes
- future Cloudflare integration
- future Tailscale integration
- exact host naming rules
- ingress hostname collision handling

## Consequences

Traefik is a pragmatic default for K3s and avoids making ingress controller selection a Phase 1 product surface.

The visibility model gives Nephos room to add public, private, and tailnet exposure later without turning Phase 1 into tunnel/DNS automation.

Keeping stopped App ingress avoids losing temporary route intent during stop/start cycles, but status must make the stopped state explicit.

## Status Notes

Do not make Cloudflare Tunnel or Tailscale foundational in Phase 1.

Do not leak raw ingress configuration as the primary product UX.
