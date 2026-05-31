CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE app_instances (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    catalog_kind TEXT NOT NULL,
    catalog_name TEXT NOT NULL,
    catalog_version TEXT,
    catalog_source_id TEXT NOT NULL,
    catalog_source_path TEXT NOT NULL,
    manifest_digest TEXT NOT NULL,
    lifecycle TEXT NOT NULL CHECK (lifecycle IN ('running', 'stopped', 'removed')),
    generation INTEGER NOT NULL CHECK (generation >= 1),
    config_json TEXT NOT NULL DEFAULT '{}',
    delete_requested_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE service_instances (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    catalog_kind TEXT NOT NULL,
    catalog_name TEXT NOT NULL,
    catalog_version TEXT,
    catalog_source_id TEXT NOT NULL,
    catalog_source_path TEXT NOT NULL,
    manifest_digest TEXT NOT NULL,
    lifecycle TEXT NOT NULL CHECK (lifecycle IN ('running', 'stopped', 'removed')),
    generation INTEGER NOT NULL CHECK (generation >= 1),
    config_json TEXT NOT NULL DEFAULT '{}',
    delete_requested_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE bindings (
    id TEXT PRIMARY KEY,
    app_instance_id TEXT NOT NULL,
    service_instance_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    capability TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    output_summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (app_instance_id) REFERENCES app_instances(id) ON DELETE RESTRICT,
    FOREIGN KEY (service_instance_id) REFERENCES service_instances(id) ON DELETE RESTRICT,
    UNIQUE (app_instance_id, alias)
);

CREATE TABLE platform_domains (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL UNIQUE,
    is_default INTEGER NOT NULL CHECK (is_default IN (0, 1)),
    generation INTEGER NOT NULL CHECK (generation >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE status_snapshots (
    id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL CHECK (
        resource_type IN ('app_instance', 'service_instance', 'binding', 'platform_domain')
    ),
    resource_id TEXT NOT NULL,
    level TEXT NOT NULL CHECK (
        level IN ('unknown', 'pending', 'healthy', 'degraded', 'blocked', 'stopped', 'not_applicable')
    ),
    lifecycle TEXT NOT NULL,
    reconciliation TEXT NOT NULL,
    reason TEXT,
    message TEXT,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    observed_generation INTEGER,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (resource_type, resource_id)
);

CREATE TABLE reconciliation_requests (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (
        target_type IN ('app_instance', 'service_instance', 'binding', 'platform_domain')
    ),
    target_id TEXT NOT NULL,
    target_generation INTEGER,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    target_snapshot_json TEXT NOT NULL DEFAULT '{}',
    state TEXT NOT NULL CHECK (state IN ('pending', 'running', 'succeeded', 'failed', 'blocked')),
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_platform_domains_one_default
ON platform_domains(is_default)
WHERE is_default = 1;

CREATE INDEX idx_reconciliation_requests_queue
ON reconciliation_requests(state, created_at);
