import pytest

from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.provisioners.zitadel import (
    _issuer_url,
    _oidc_uris,
    _provisioning_domain,
    _provisioning_port,
    _provisioning_secure,
)
from nephos_api.routing import ServicePortalIdentity
from nephos_api.runtime_errors import RuntimeBlockedError

PORTAL = ServicePortalIdentity(host="auth.nephos.lcl", port=80, secure=False)


def _ctx(service_portal=None, service_config=None):
    return BindingProvisioningContext(
        binding_id="b1",
        app_slug="graph-demo",
        service_slug="auth",
        alias="auth",
        capability="oidc",
        protocol="oidc",
        service_config=service_config or {},
        service_portal=service_portal,
    )


def _route_ctx(domain="nephos.lcl"):
    return BindingProvisioningContext(
        binding_id="b1",
        app_slug="graph-demo",
        service_slug="auth",
        alias="auth",
        capability="oidc",
        protocol="oidc",
        app_routes=({"name": "web"},),
        platform_domains=({"domain": domain, "default": True},),
    )


def test_domain_prefers_the_portal_identity():
    context = _ctx(
        service_portal=PORTAL,
        service_config={"external-host": "stale.example"},
    )

    assert _provisioning_domain(context) == "auth.nephos.lcl"


def test_domain_falls_back_to_config_when_there_is_no_portal():
    context = _ctx(service_config={"external-host": "legacy.example"})

    assert _provisioning_domain(context) == "legacy.example"


def test_domain_blocks_when_neither_source_exists():
    with pytest.raises(RuntimeBlockedError) as excinfo:
        _provisioning_domain(_ctx())

    assert excinfo.value.reason == "binding_provisioner_unavailable"
    assert "portal" in str(excinfo.value)
    assert "external-host" in str(excinfo.value)


def test_port_and_secure_follow_the_portal():
    context = _ctx(service_portal=PORTAL)

    assert _provisioning_port(context) == 80
    assert _provisioning_secure(context) is False


def test_issuer_url_is_http_without_a_port_suffix_on_a_portal_identity():
    # Issue #61: the platform serves generated routes over http. An https issuer
    # here disagrees with the host Zitadel is actually reachable at.
    assert _issuer_url(_ctx(service_portal=PORTAL)) == "http://auth.nephos.lcl"


def test_redirect_uris_are_http_on_a_lcl_domain():
    # Issue #61: .lcl is the domain `nephos setup lcl` creates, and the platform
    # serves it over http. Guessing https from the suffix produced a redirect
    # URI that never matches what the browser sends.
    redirects, post_logout = _oidc_uris(_route_ctx())

    assert redirects == ("http://graph-demo.nephos.lcl/oauth/callback",)
    assert post_logout == ("http://graph-demo.nephos.lcl/",)
