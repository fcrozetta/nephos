from dataclasses import dataclass

from nephos_api.routing import (
    ServicePortalIdentity,
    service_portal_identity,
)


@dataclass(frozen=True)
class _Domain:
    domain: str
    is_default: bool = False
    allows_service_portals: bool = False


def _identity(first_portal_name="console", domains=None):
    return service_portal_identity(
        service_slug="auth",
        first_portal_name=first_portal_name,
        domains=domains
        if domains is not None
        else [_Domain("nephos.lcl", is_default=True, allows_service_portals=True)],
    )


def test_identity_uses_the_bare_host_of_the_first_portal():
    assert _identity() == ServicePortalIdentity(
        host="auth.nephos.lcl", port=80, secure=False
    )


def test_identity_is_none_when_the_service_declares_no_portal():
    assert _identity(first_portal_name=None) is None


def test_identity_is_none_when_no_domain_allows_portals():
    domains = [_Domain("nephos.lcl", is_default=True, allows_service_portals=False)]

    assert _identity(domains=domains) is None


def test_identity_falls_back_to_the_first_eligible_non_default_domain():
    domains = [
        _Domain("public.example", is_default=True, allows_service_portals=False),
        _Domain("nephos.lcl", allows_service_portals=True),
    ]

    assert _identity(domains=domains).host == "auth.nephos.lcl"


def test_identity_is_never_https_on_a_lcl_domain():
    # Issue #61: the platform serves generated routes over http. A provisioner
    # that guesses https from the suffix produces an issuer nothing serves.
    identity = _identity()

    assert identity.secure is False
    assert identity.port == 80
