import re

import pytest

from nephos_api.domain import (
    InvalidMachineIdentifierError,
    generate_id,
    validate_machine_identifier,
)


def test_validate_machine_identifier_accepts_dns_label_style_names() -> None:
    assert validate_machine_identifier("paperless") == "paperless"
    assert validate_machine_identifier("paperless-ngx") == "paperless-ngx"
    assert validate_machine_identifier("p1") == "p1"


@pytest.mark.parametrize(
    "value",
    ["Paperless", "paperless_", "-paperless", "paperless-", "paper.less", "", "a" * 64],
)
def test_validate_machine_identifier_rejects_invalid_names(value: str) -> None:
    with pytest.raises(InvalidMachineIdentifierError):
        validate_machine_identifier(value)


def test_generate_id_uses_typed_prefix_and_uuid4_hex() -> None:
    identifier = generate_id("appinst")

    assert re.fullmatch(r"appinst_[0-9a-f]{32}", identifier)
