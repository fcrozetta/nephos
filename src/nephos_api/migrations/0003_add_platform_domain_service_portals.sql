-- ADR 20260726: Service portals are default-deny per root domain.
-- Existing domains keep admin surfaces unpublished until an operator opts in,
-- so applying this migration cannot expose a portal that was not already
-- reachable.
ALTER TABLE platform_domains
ADD COLUMN allows_service_portals INTEGER NOT NULL DEFAULT 0
CHECK (allows_service_portals IN (0, 1));
