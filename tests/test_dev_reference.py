from nephos_api.dev_reference import _ensure_platform_domain


class FakeResponse:
    def __init__(self, status_code: int, body: dict[str, object]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> dict[str, object]:
        return self._body


class FakeApi:
    def __init__(self, domains: list[dict[str, object]]) -> None:
        self.domains = domains
        self.posts: list[tuple[str, dict[str, object] | None]] = []

    def get(self, path: str) -> FakeResponse:
        assert path == "/platform/config/domains"
        return FakeResponse(200, {"domains": self.domains})

    def post(
        self,
        path: str,
        json: dict[str, object] | None = None,
    ) -> FakeResponse:
        self.posts.append((path, json))
        return FakeResponse(202, {"resource": {}, "reconciliation": {}})


def test_reference_smoke_reuses_existing_default_platform_domain() -> None:
    api = FakeApi(
        [
            {
                "name": "local",
                "domain": "nephos.localhost",
                "default": True,
            }
        ]
    )

    _ensure_platform_domain(api, domain="nephos.localhost", name_hint="local")

    assert api.posts == []


def test_reference_smoke_sets_existing_platform_domain_as_default() -> None:
    api = FakeApi(
        [
            {
                "name": "dev",
                "domain": "nephos.localhost",
                "default": False,
            }
        ]
    )

    _ensure_platform_domain(api, domain="nephos.localhost", name_hint="local")

    assert api.posts == [("/platform/config/domains/dev/actions/set-default", None)]


def test_reference_smoke_uses_unique_platform_domain_name_on_name_conflict() -> None:
    api = FakeApi(
        [
            {
                "name": "local",
                "domain": "nephos.local",
                "default": True,
            }
        ]
    )

    _ensure_platform_domain(api, domain="nephos.localhost", name_hint="local")

    assert api.posts == [
        (
            "/platform/config/domains",
            {
                "name": "local-smoke",
                "domain": "nephos.localhost",
                "default": True,
            },
        )
    ]
