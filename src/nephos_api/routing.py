"""Host and URL derivation for generated routes and Service portals.

Three call sites must agree byte-for-byte on a portal's host: the Kubernetes
Ingress rule, the URL reported in the API, and the value a `kind: portal` runtime
mapping feeds a provider (e.g. Zitadel's `externalHost`, which is its OIDC issuer
identity). Keeping the derivation here is what makes those three the same string.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

# ADR 20260517: "Phase 1 Nephos-managed ingress is HTTP-only" and
# "Nephos-generated URLs use `http://`". This is the single conforming
# implementation.
#
# ! Do not reintroduce scheme guessing here. `zitadel._route_scheme` still infers
# ! https from any suffix that is not `.local`/`.localhost` (so `nephos.lcl`
# ! yields https), which contradicts the ADR above; issue #61 tracks replacing it
# ! on the App redirect-URI path. A portal feeds `externalSecure`, where a wrong
# ! guess breaks OIDC issuer validation rather than merely mislabeling a status
# ! URL, so the portal path must never depend on that inference.
PLATFORM_ROUTE_SCHEME = "http"
PLATFORM_ROUTE_PORT = 80
PLATFORM_ROUTE_SECURE = False


class RootDomain(Protocol):
    """The subset of `PlatformDomain` this module reads."""

    @property
    def domain(self) -> str: ...

    @property
    def is_default(self) -> bool: ...

    @property
    def allows_service_portals(self) -> bool: ...


def service_portal_host_prefix(
    *,
    service_slug: str,
    portal_name: str,
    is_first_portal: bool,
) -> str:
    """The label(s) a portal host prepends to a root domain (ADR 20260726).

    App-symmetric: the first portal is bare `<service-slug>`, later ones are
    `<portal>.<service-slug>`. The bare form is what lets an operator name the
    hostname by installing under a role slug (`auth`) instead of inheriting the
    implementation's name, since the portal name drops out of the first host.
    """
    if is_first_portal:
        return service_slug
    return f"{portal_name}.{service_slug}"


def app_route_host_prefix(
    *,
    app_slug: str,
    route_name: str,
    is_default_route: bool,
) -> str:
    if is_default_route:
        return app_slug
    return f"{route_name}.{app_slug}"


def service_portal_host(
    *,
    service_slug: str,
    portal_name: str,
    domain: str,
    is_first_portal: bool,
) -> str:
    prefix = service_portal_host_prefix(
        service_slug=service_slug,
        portal_name=portal_name,
        is_first_portal=is_first_portal,
    )
    return f"{prefix}.{domain}"


def service_portal_url(
    *,
    service_slug: str,
    portal_name: str,
    domain: str,
    is_first_portal: bool,
) -> str:
    host = service_portal_host(
        service_slug=service_slug,
        portal_name=portal_name,
        domain=domain,
        is_first_portal=is_first_portal,
    )
    return f"{PLATFORM_ROUTE_SCHEME}://{host}"


def app_route_host_prefixes(
    *,
    app_slug: str,
    routes: Sequence[Mapping[str, object]],
) -> set[str]:
    return {
        app_route_host_prefix(
            app_slug=app_slug,
            route_name=str(route["name"]),
            is_default_route=index == 0,
        )
        for index, route in enumerate(routes)
    }


def service_portal_host_prefixes(
    *,
    service_slug: str,
    portals: Sequence[Mapping[str, object]],
) -> set[str]:
    return {
        service_portal_host_prefix(
            service_slug=service_slug,
            portal_name=str(portal["name"]),
            is_first_portal=index == 0,
        )
        for index, portal in enumerate(portals)
    }


@dataclass(frozen=True)
class ServicePortalIdentity:
    """A Service's canonical external address, derived from its first portal.

    The identity a provisioner needs when it configures a Service to know its
    own address — Zitadel's OIDC issuer is exactly this. The deploy path already
    feeds the same value through a `kind: portal` runtime mapping; this is the
    provisioning path's equivalent, derived here so the two cannot disagree.
    """

    host: str
    port: int
    secure: bool


def service_portal_identity(
    *,
    service_slug: str,
    first_portal_name: str | None,
    domains: Sequence[RootDomain],
) -> ServicePortalIdentity | None:
    """The Service's external identity, or None when it has no published one.

    The **first** portal, matching `service_portal_host_prefix`: the first
    portal takes the bare `<service-slug>.<domain>` host, which is what makes
    installing Zitadel under the slug `auth` produce the issuer `auth.<domain>`.
    A later portal is prefixed and is therefore never the Service's identity.

    None is a legitimate answer, not an error: a Service may declare no portal
    at all, and a fresh install has no portal-eligible domain until an operator
    opts one in. The caller decides what to do about it.
    """
    if first_portal_name is None:
        return None
    domain = portal_canonical_domain(domains)
    if domain is None:
        return None
    return ServicePortalIdentity(
        host=service_portal_host(
            service_slug=service_slug,
            portal_name=first_portal_name,
            domain=domain.domain,
            is_first_portal=True,
        ),
        port=PLATFORM_ROUTE_PORT,
        secure=PLATFORM_ROUTE_SECURE,
    )


def portal_eligible_domains(
    domains: Iterable[RootDomain],
) -> list[RootDomain]:
    """Root domains an operator has opted in to carrying Service portals.

    Empty is the expected state on a fresh install: a declared portal then
    publishes nowhere, which callers must report rather than treat as healthy.
    """
    return [domain for domain in domains if domain.allows_service_portals]


def portal_canonical_domain(
    domains: Sequence[RootDomain],
) -> RootDomain | None:
    """The domain a portal's canonical URL is built from, or None if unpublished.

    The default root domain when it is portal-eligible, otherwise the first
    eligible domain. The fallback is the common case, not an edge case: the
    default domain is typically the public/tunnelled one while only the local
    domain is portal-eligible, and returning None there would report a reachable
    portal as having no URL.

    Callers pass domains already ordered by name (as the repository lists them),
    so the fallback is deterministic.
    """
    eligible = portal_eligible_domains(domains)
    if not eligible:
        return None
    return next(
        (domain for domain in eligible if domain.is_default),
        eligible[0],
    )


# Routing-only reconciliation. Distinct from `reconcile` on purpose: every other
# handler guards on its own action, so a new verb is inert everywhere it is not
# wanted, and a platform-domain change can reach a Service's Ingress without
# deploying the Service. Not a lifecycle action, so it is never operator-requested.
#
# Lives here rather than in the reconciler because the read path needs it too: the
# API surfaces a failed routing pass by looking up the last request with this
# action, and importing the reconciler from an endpoint module would be backwards.
PORTAL_RECONCILE_ACTION = "reconcile-portals"
