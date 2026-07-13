# Expose Config Schema in Catalog Summaries

- Status: accepted
- Date: 2026-07-12
- Tags: api, catalog, config, public-contract, console

## Context and Problem Statement

The catalog endpoints `GET /catalog/apps[/{name}]` and
`GET /catalog/services[/{name}]` return manifest summaries that include
`requires`, `provides`, and `routes`, but omit `spec.config.options`.

Install requests (`POST /apps`, `POST /services`) accept a `config` object and
validate it against the manifest's config options, returning
`*_config_unknown` / `*_config_required` / `*_config_invalid` on mismatch. But a
client (notably nephos-console) has no way to learn the config field names,
types, required flags, enum values, or defaults ahead of time. A typed install
form is impossible; the flow degrades to a blind config blob corrected one 400 at
a time.

## Decision

Include a `config` key in both catalog summaries:

```json
"config": {
  "options": [
    {"name": "...", "type": "string|integer|boolean|enum",
     "label": "...", "description": "...", "default": ...,
     "required": true, "values": [{"value": "..."}]}
  ]
}
```

The shape mirrors the existing `ConfigOption` manifest model. Both the list and
get-by-name endpoints return the same summary, so both expose the schema.

This is additive: existing fields are unchanged, and clients that ignore `config`
are unaffected.

## Consequences

- Clients can render typed install forms and validate before submitting, instead
  of relying on install-time 400s.
- The catalog summary is now the authoritative published config contract for an
  App/Service; changes to config options are visible through the API.
- Config option `default` values may be non-secret literals; secrets are always
  passed as `op://` / `bao://` references by the installer, never surfaced here.

## Non-Goals

- No change to install validation or the config value types.
- No JSON Schema / richer validation vocabulary beyond the current option model.
- Redaction is unchanged: this exposes the option schema, not any stored values.
