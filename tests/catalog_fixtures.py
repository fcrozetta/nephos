from pathlib import Path


def write_app(
    root: Path,
    name: str = "paperless",
    capability: str = "postgres",
    protocol: str | None = None,
    alias: str | None = "database",
) -> Path:
    path = root / "apps" / name / "app.yaml"
    path.parent.mkdir(parents=True)
    protocol_yaml = f"\n      protocol: {protocol}" if protocol is not None else ""
    alias_yaml = f"\n      as: {alias}" if alias is not None else ""
    path.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: {name}
  displayName: Paperless
  description: Document management
  version: "1.0.0"
spec:
  requires:
    - capability: {capability}{protocol_yaml}{alias_yaml}
  routes:
    - name: web
      visibility: local
      target:
        port: http
  config:
    options: []
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: paperless
      version: "1.0.0"
    values:
      mappings: []
""".strip()
    )
    return path


def write_service(
    root: Path,
    name: str = "postgres",
    capability: str = "postgres",
    protocol: str | None = None,
    alias: str | None = "__capability__",
    version: str = "16",
    engine: str | None = None,
) -> Path:
    path = root / "services" / name / "service.yaml"
    path.parent.mkdir(parents=True)
    protocol_yaml = f"\n      protocol: {protocol}" if protocol is not None else ""
    provided_alias = capability if alias == "__capability__" else alias
    alias_yaml = f"\n      as: {provided_alias}" if provided_alias is not None else ""
    engine_yaml = f"\n    engine: {engine}" if engine is not None else ""
    path.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: {name}
  displayName: PostgreSQL
spec:
  provides:
    - capability: {capability}{protocol_yaml}{alias_yaml}
      version: "{version}"
  bindings:
    outputs:
      - name: connection
        target: app-secret
  provisioning:
    mode: app-scoped-resource{engine_yaml}
  operations: []
  runtime:
    type: helm
    chart:
      repository: https://charts.example.test
      name: postgresql
      version: "16.0.0"
    values:
      mappings: []
""".strip()
    )
    return path
