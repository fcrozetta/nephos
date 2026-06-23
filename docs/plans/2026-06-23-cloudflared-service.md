# Cloudflared Service Plan

Goal:

- Add a Nephos-managed `cloudflared` Service so Cloudflare Tunnel runtime is reconciled by Nephos instead of depending on a local host process or the `nomad` debug route.

Non-goals:

- Do not create, delete, or update Cloudflare DNS records or tunnel routes in this slice.
- Do not store Cloudflare tunnel tokens, credentials JSON, certs, API tokens, or account credentials in Nephos SQLite Service config.
- Do not replace Zitadel production-readiness work; this Service enables the missing public TLS route later.
- Do not build a full Cloudflare API adapter or console extension yet.
- Do not touch Forgejo or `git.fcrozetta.app` routing.

Current understanding:

- `nomad.fcrozetta.app` is a debug/manual Cloudflare Tunnel route and must remain separate from production Nephos routing.
- `auth.fcrozetta.app` currently has no DNS record and should be wired later when Cloudflare route/DNS/TLS is intentionally configured.
- Nephos now supports Zitadel Service-owned Ingress for the canonical issuer host.
- Production Cloudflare should route to in-cluster ingress/service paths, not host port-forward chains.
- Phase 1 should support Kubernetes Secret references for tunnel credentials rather than persisting secret values in Nephos desired-state config.

Files likely to change:

- `PLANS.md`
- `docs/adr/20260623-service-production-readiness-contract.md`
- `src/nephos_api/dev_backbone.py`
- `src/nephos_api/providers/kubernetes.py`
- `tests/test_dev_backbone.py`
- `tests/test_pulumi_kubernetes_provider.py`

Proposed steps:

1. Record this plan and add a current-plan pointer in `PLANS.md`.
2. Amend the proposed Service production-readiness ADR follow-up section with the Cloudflared Service direction.
3. Add a generated alpha backbone Service manifest for `cloudflared`.
4. Add runtime mappings for safe non-secret config:
   - `image` -> `image`
   - `tunnel-name` -> `tunnelName`
   - `credentials-secret-name` -> `credentialsSecretName`
   - `credentials-secret-key` -> `credentialsSecretKey`
   - `origin-service-url` -> `originServiceUrl`
   - `hostname` -> `hostname`
   - `origin-host-header` -> `originHostHeader`
5. Implement a Pulumi/Kubernetes `cloudflared-service` workload that creates:
   - Deployment with one `cloudflared` container.
   - Secret volume mounting the referenced credentials Secret at `/etc/cloudflared/credentials.json`.
   - ConfigMap containing `config.yml` with one hostname route and a 404 fallback.
   - Readiness/liveness probes against cloudflared metrics on `127.0.0.1:2000/ready`.
6. Add tests proving the manifest options/mappings and Kubernetes workload shape.
7. Run focused tests, then full gate.
8. Commit as one slice.

Risks:

- Existing Cloudflare tunnels use local host config; this slice intentionally does not migrate them.
- A real live smoke requires a Secret containing tunnel credentials and Cloudflare DNS/route setup.
- Some clusters may require egress/network policy allowances for `cloudflared` to connect to Cloudflare; Phase 1 has no default-deny NetworkPolicy.
- Exact future API/CLI for creating or importing Cloudflare tunnels remains undecided.

Validation commands:

- `uv run ruff check src/nephos_api/dev_backbone.py src/nephos_api/providers/kubernetes.py tests/test_dev_backbone.py tests/test_pulumi_kubernetes_provider.py`
- `uv run pytest tests/test_dev_backbone.py tests/test_pulumi_kubernetes_provider.py -q`
- `uv lock --check`
- `uv run ruff check .`
- `uv run pytest -q`
- `git diff --check`

Rollback notes:

- Revert the Cloudflared Service commit if Cloudflare routing should be represented by a different Service/provider boundary.
- Existing Zitadel runtime/provisioning commits are independent and should not need rollback.

Open questions:

- Exact CLI/API shape for creating/importing a Cloudflare tunnel is deferred.
- Exact console extension shape for managing public routes is deferred.
- Whether Nephos later manages DNS records through Cloudflare API or only references pre-created DNS routes is deferred.
