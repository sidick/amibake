import pytest

from amibake.versionspec import (
    is_name,
    is_version,
    parse_constraint,
    parse_package_spec,
)


@pytest.mark.parametrize("text", ["3.2.2.1", "5.20", "45.1", "0", "68020", "2.9a"])
def test_valid_versions(text):
    assert is_version(text)


@pytest.mark.parametrize("text", ["5.20ab", "v5.20", "5..20", ".5", "5.", "", "a5.20"])
def test_invalid_versions(text):
    assert not is_version(text)


@pytest.mark.parametrize("text", ["p96", "amissl", "classact", "bsdsocket-emulation",
                                  "os3.2.2", "wb1.3", "aros68k"])
def test_valid_names(text):
    assert is_name(text)


@pytest.mark.parametrize("text", ["AmiSSL", "p 96", "-p96", "p96-", "p96..x", ""])
def test_invalid_names(text):
    assert not is_name(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (">= 3.2", [(">=", "3.2")]),
        ("= 5.20", [("=", "5.20")]),
        (">= 2.0, < 4.0", [(">=", "2.0"), ("<", "4.0")]),
        (">=3.2", [(">=", "3.2")]),
    ],
)
def test_parse_constraint(text, expected):
    assert parse_constraint(text) == expected


@pytest.mark.parametrize("text", ["3.2", "~> 3.2", ">= five", ">= 3.2,", "== 3.2"])
def test_parse_constraint_rejects(text):
    with pytest.raises(ValueError):
        parse_constraint(text)


def test_parse_package_spec():
    assert parse_package_spec("amissl = 5.20") == ("amissl", [("=", "5.20")])
    assert parse_package_spec("bsdsocket") == ("bsdsocket", [])
    assert parse_package_spec("mui >= 3.8, < 4.0") == (
        "mui", [(">=", "3.8"), ("<", "4.0")])
    with pytest.raises(ValueError):
        parse_package_spec("AmiSSL = 5.20")
