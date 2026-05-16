# Ingress and Visibility Model

- Status: draft
- Date: 2026-05-17
- Tags: ingress, networking, traefik, visibility

## Context and Problem Statement

Nephos needs to expose Apps and possibly some Services through routes.

Ingress behavior must support local-first infrastructure while allowing public/private/tailnet modes later.

K3s commonly includes Traefik, making it a practical default.

## Current Leaning

Use Traefik initially, especially with K3s.

Nephos should own ingress intent.

Kubernetes owns ingress resources.

## Possible Visibility Modes

- local
- private
- public
- tailnet

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

- default ingress controller
- local DNS behavior
- wildcard domain behavior
- Cloudflare integration
- Tailscale integration
- TLS/cert-manager strategy
- whether Services can expose admin routes
- whether stopped Apps keep ingress

## Status Notes

This is draft.

Do not leak raw ingress configuration as the primary product UX.
