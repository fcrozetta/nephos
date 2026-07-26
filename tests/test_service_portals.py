"""Service portal schema, host derivation, and runtime mapping (ADR 20260726)."""

from pathlib import Path

import pytest

from nephos_api.catalog import CatalogLoader, CatalogValidationError
from nephos_api.domain import PlatformDomain
from nephos_api.routing import (
    PLATFORM_ROUTE_SCHEME,
    app_route_host_prefixes,
    portal_canonical_domain,
    portal_eligible_domains,
    service_portal_host,
    service_portal_host_prefixes,
    service_portal_url,
)


def _write_service_with_portals(
    root: Path,
    *,
    portals_yaml: str,
    mappings_yaml: str = "      mappings: []",
    name: str = "arcadedb",
) -> Path:
    path = root / "services" / name / "service.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: {name}
  displayName: ArcadeDB
spec:
  provides:
    - capability: sql
      protocol: arcadedb
      as: sql
  config:
    options: []
{portals_yaml}
  provisioning:
    mode: app-scoped-resource
  operations: []
  runtime:
    type: provider
    provider:
      name: {name}
    values:
{mappings_yaml}
""".strip()
    )
    return path


def _domain(
    name: str,
    domain: str,
    *,
    is_default: bool = False,
    allows_service_portals: bool = False,
) -> PlatformDomain:
    return PlatformDomain(
        id=f"domain_{name}",
        name=name,
        domain=domain,
        is_default=is_default,
        generation=1,
        allows_service_portals=allows_service_portals,
    )


def test_first_portal_host_is_bare_so_the_instance_slug_names_it() -> None:
    # The point of the bare first host: an operator installs Zitadel as instance
    # `auth` and the issuer is auth.<domain>, named after the role rather than the
    # implementation. The portal name drops out entirely.
    assert (
        service_portal_host(
            service_slug="auth",
            portal_name="console",
            domain="nephos.lcl",
            is_first_portal=True,
        )
        == "auth.nephos.lcl"
    )
    assert (
        service_portal_url(
            service_slug="auth",
            portal_name="console",
            domain="nephos.lcl",
            is_first_portal=True,
        )
        == "http://auth.nephos.lcl"
    )


def test_later_portals_are_prefixed_under_the_instance_slug() -> None:
    assert (
        service_portal_host(
            service_slug="arcadedb",
            portal_name="metrics",
            domain="nephos.lcl",
            is_first_portal=False,
        )
        == "metrics.arcadedb.nephos.lcl"
    )


def test_portal_host_prefixes_mirror_app_route_prefixes() -> None:
    # Both kinds now share one hostname namespace, which is what makes the
    # collision check at install time necessary.
    portals = [{"name": "studio"}, {"name": "metrics"}]
    routes = [{"name": "web"}, {"name": "metrics"}]

    assert service_portal_host_prefixes(service_slug="x", portals=portals) == {
        "x",
        "metrics.x",
    }
    assert app_route_host_prefixes(app_slug="x", routes=routes) == {"x", "metrics.x"}


def test_portal_scheme_does_not_guess_from_domain_suffix() -> None:
    # ADR 20260517 is HTTP-only for Nephos-generated ingress. `nephos.lcl` is
    # neither .local nor .localhost, which is exactly the input that makes
    # zitadel._route_scheme return https (issue #61); the portal path must not
    # inherit that inference because it feeds externalSecure.
    assert PLATFORM_ROUTE_SCHEME == "http"
    assert service_portal_url(
        service_slug="zitadel",
        portal_name="console",
        domain="nephos.lcl",
        is_first_portal=True,
    ).startswith("http://")


def test_portal_eligible_domains_defaults_to_none() -> None:
    domains = [
        _domain("local", "nephos.lcl", is_default=True),
        _domain("cloudflare", "nephos.example.test"),
    ]

    assert portal_eligible_domains(domains) == []
    assert portal_canonical_domain(domains) is None


def test_portal_canonical_domain_prefers_the_default_domain() -> None:
    local = _domain(
        "local",
        "nephos.lcl",
        is_default=True,
        allows_service_portals=True,
    )
    other = _domain("other", "nephos.other.test", allows_service_portals=True)

    assert portal_canonical_domain([local, other]) is local


def test_portal_canonical_domain_falls_back_when_default_is_not_eligible() -> None:
    # The expected production setup: the default domain is the public tunnelled
    # one and only the local domain carries portals. Returning None here would
    # report a reachable portal as having no URL.
    public = _domain("cloudflare", "nephos.example.test", is_default=True)
    local = _domain("local", "nephos.lcl", allows_service_portals=True)

    assert portal_canonical_domain([public, local]) is local


def test_catalog_loader_exposes_service_portals(tmp_path: Path) -> None:
    root = tmp_path / "default"
    _write_service_with_portals(
        root,
        portals_yaml=(
            "  portals:\n"
            "    - name: studio\n"
            "      displayName: ArcadeDB Studio\n"
            "      target:\n"
            "        port: http"
        ),
    )

    entry = CatalogLoader((root,)).get_service("arcadedb")

    assert entry["portals"] == [
        {
            "name": "studio",
            "displayName": "ArcadeDB Studio",
            "target": {"port": "http"},
        }
    ]


def test_catalog_loader_defaults_service_portals_to_empty(tmp_path: Path) -> None:
    root = tmp_path / "default"
    _write_service_with_portals(root, portals_yaml="  portals: []")

    assert CatalogLoader((root,)).get_service("arcadedb")["portals"] == []


def test_catalog_loader_rejects_duplicate_portal_names(tmp_path: Path) -> None:
    root = tmp_path / "default"
    _write_service_with_portals(
        root,
        portals_yaml=(
            "  portals:\n"
            "    - name: studio\n"
            "      target:\n"
            "        port: http\n"
            "    - name: studio\n"
            "      target:\n"
            "        port: 2480"
        ),
    )

    with pytest.raises(CatalogValidationError, match="duplicate portal name"):
        CatalogLoader((root,)).get_service("arcadedb")


def test_catalog_loader_rejects_out_of_range_portal_port(tmp_path: Path) -> None:
    root = tmp_path / "default"
    _write_service_with_portals(
        root,
        portals_yaml=(
            "  portals:\n"
            "    - name: studio\n"
            "      target:\n"
            "        port: 70000"
        ),
    )

    with pytest.raises(CatalogValidationError, match="portal target port"):
        CatalogLoader((root,)).get_service("arcadedb")


def test_catalog_loader_rejects_mapping_for_undeclared_portal(tmp_path: Path) -> None:
    root = tmp_path / "default"
    _write_service_with_portals(
        root,
        portals_yaml=(
            "  portals:\n"
            "    - name: studio\n"
            "      target:\n"
            "        port: http"
        ),
        mappings_yaml=(
            "      mappings:\n"
            "        - from:\n"
            "            kind: portal\n"
            "            name: console\n"
            "            field: host\n"
            "          to:\n"
            "            helmValue: externalHost"
        ),
    )

    with pytest.raises(CatalogValidationError, match="undeclared portal"):
        CatalogLoader((root,)).get_service("arcadedb")


def test_catalog_loader_rejects_unknown_portal_mapping_field(tmp_path: Path) -> None:
    root = tmp_path / "default"
    _write_service_with_portals(
        root,
        portals_yaml=(
            "  portals:\n"
            "    - name: studio\n"
            "      target:\n"
            "        port: http"
        ),
        mappings_yaml=(
            "      mappings:\n"
            "        - from:\n"
            "            kind: portal\n"
            "            name: studio\n"
            "            field: hostname\n"
            "          to:\n"
            "            helmValue: externalHost"
        ),
    )

    with pytest.raises(CatalogValidationError, match="portal mapping field"):
        CatalogLoader((root,)).get_service("arcadedb")


def test_catalog_loader_rejects_portal_mapping_in_app_manifest(tmp_path: Path) -> None:
    root = tmp_path / "default"
    path = root / "apps" / "paperless" / "app.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
apiVersion: nephos.pro/v1alpha1
kind: App
metadata:
  name: paperless
spec:
  routes:
    - name: web
      visibility: local
      target:
        port: http
  config:
    options: []
  runtime:
    type: provider
    provider:
      name: paperless
    values:
      mappings:
        - from:
            kind: portal
            name: console
            field: host
          to:
            helmValue: externalHost
""".strip()
    )

    with pytest.raises(CatalogValidationError, match="only valid for Service"):
        CatalogLoader((root,)).get_app("paperless")


def _write_service_with_credentials(
    root: Path,
    *,
    credentials_yaml: str,
    options_yaml: str = (
        "    - name: root-password\n"
        "      type: string\n"
        "      required: true\n"
        "    - name: admin-username\n"
        "      type: string\n"
        "      default: root@example.test"
    ),
) -> Path:
    path = root / "services" / "arcadedb" / "service.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
apiVersion: nephos.pro/v1alpha1
kind: Service
metadata:
  name: arcadedb
spec:
  provides:
    - capability: sql
      protocol: arcadedb
      as: sql
  config:
    options:
{options_yaml}
{credentials_yaml}
  provisioning:
    mode: app-scoped-resource
  operations: []
  runtime:
    type: provider
    provider:
      name: arcadedb
    values:
      mappings: []
""".strip()
    )
    return path


def test_catalog_exposes_a_literal_credential_username(tmp_path: Path) -> None:
    # The postgres/arcadedb case: the runtime fixes the account name, so it is a
    # literal rather than something the operator picks.
    root = tmp_path / "default"
    _write_service_with_credentials(
        root,
        credentials_yaml=(
            "  credentials:\n"
            "    username: root\n"
            "    passwordOption: root-password"
        ),
    )

    entry = CatalogLoader((root,)).get_service("arcadedb")

    assert entry["credentials"] == {
        "username": "root",
        "usernameOption": None,
        "passwordOption": "root-password",
    }


def test_catalog_exposes_a_config_backed_credential_username(tmp_path: Path) -> None:
    # The Zitadel case: the operator chooses the admin identity at install.
    root = tmp_path / "default"
    _write_service_with_credentials(
        root,
        credentials_yaml=(
            "  credentials:\n"
            "    usernameOption: admin-username\n"
            "    passwordOption: root-password"
        ),
    )

    entry = CatalogLoader((root,)).get_service("arcadedb")

    assert entry["credentials"]["usernameOption"] == "admin-username"
    assert entry["credentials"]["username"] is None


def test_catalog_rejects_credentials_with_both_username_forms(tmp_path: Path) -> None:
    root = tmp_path / "default"
    _write_service_with_credentials(
        root,
        credentials_yaml=(
            "  credentials:\n    username: root\n"
            "    usernameOption: admin-username\n    passwordOption: root-password"
        ),
    )

    with pytest.raises(CatalogValidationError, match="exactly one of"):
        CatalogLoader((root,)).get_service("arcadedb")


def test_catalog_rejects_credentials_with_neither_username_form(tmp_path: Path) -> None:
    root = tmp_path / "default"
    _write_service_with_credentials(
        root,
        credentials_yaml="  credentials:\n    passwordOption: root-password",
    )

    with pytest.raises(CatalogValidationError, match="exactly one of"):
        CatalogLoader((root,)).get_service("arcadedb")


def test_catalog_rejects_credentials_referencing_an_undeclared_option(
    tmp_path: Path,
) -> None:
    root = tmp_path / "default"
    _write_service_with_credentials(
        root,
        credentials_yaml=(
            "  credentials:\n    username: root\n    passwordOption: nope-password"
        ),
    )

    with pytest.raises(CatalogValidationError, match="not a declared config option"):
        CatalogLoader((root,)).get_service("arcadedb")


def test_catalog_rejects_a_password_option_that_is_not_treated_as_secret(
    tmp_path: Path,
) -> None:
    # Otherwise the manifest would name a credential the API prints in clear text
    # and the reveal endpoint refuses to serve.
    root = tmp_path / "default"
    _write_service_with_credentials(
        root,
        options_yaml=(
            "    - name: login-phrase\n"
            "      type: string\n"
            "      required: true"
        ),
        credentials_yaml=(
            "  credentials:\n    username: root\n    passwordOption: login-phrase"
        ),
    )

    with pytest.raises(CatalogValidationError, match="is not treated as a secret"):
        CatalogLoader((root,)).get_service("arcadedb")
