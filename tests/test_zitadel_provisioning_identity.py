import pytest

from nephos_api.provisioners.base import BindingProvisioningContext
from nephos_api.provisioners.zitadel import (
    _issuer_url,
    _oidc_uris,
    _provisioning_domain,
    _provisioning_port,
    _provisioning_secure,
    _should_use_internal_forward,
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


def test_auto_transport_port_forwards_for_a_nephos_generated_portal_host():
    # A portal host is served by Nephos-managed ingress, which ADR 20260517
    # fixes at HTTP-only. The Zitadel provider speaks gRPC, which does not
    # survive that path, so `auto` must reach the Service directly. The old
    # heuristic keyed off `.localhost`/loopback and sent `.lcl` -- the domain
    # `nephos setup lcl` creates -- down the broken route.
    assert _should_use_internal_forward(_ctx(service_portal=PORTAL)) is True


def test_auto_transport_uses_the_issuer_endpoint_for_an_operator_supplied_host():
    # No portal: the host came from Service config, which means an operator
    # pointed it at an endpoint they manage and can route gRPC through.
    context = _ctx(service_config={"external-host": "zitadel.example.com"})

    assert _should_use_internal_forward(context) is False


def test_explicit_transport_still_overrides_the_portal_default():
    forced = _ctx(
        service_portal=PORTAL,
        service_config={"provisioning-transport": "issuer-endpoint"},
    )

    assert _should_use_internal_forward(forced) is False
