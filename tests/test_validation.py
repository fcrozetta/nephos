from __future__ import annotations

import pytest

from nephos_api.domain import validate_machine_identifier, validate_root_domain
from nephos_api.errors import NephosError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("value", ["paperless", "postgres-main", "a1", "x"])
def test_valid_machine_identifiers(value):
    assert validate_machine_identifier(value) == value


@pytest.mark.parametrize("value", ["Paperless", "-bad", "bad-", "bad_name", ""])
def test_invalid_machine_identifiers(value):
    with pytest.raises(NephosError):
        validate_machine_identifier(value)


@pytest.mark.parametrize("value", ["nephos.local", "apps.example.test"])
def test_valid_root_domains(value):
    assert validate_root_domain(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "https://nephos.local",
        "*.nephos.local",
        "nephos.local/path",
        "nephos.local:8080",
        ".nephos.local",
        "localhost",
        "Bad.example",
    ],
)
def test_invalid_root_domains(value):
    with pytest.raises(NephosError):
        validate_root_domain(value)
