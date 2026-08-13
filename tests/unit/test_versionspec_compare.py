import pytest

from amibake.versionspec import AmigaVersion, max_satisfying, satisfies


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("5.20", "5.3"),  # the float-parsing trap: 5.20 > 5.3, never 5.2 < 5.3
        ("3.2.2.1", "3.2.2"),
        ("2.0", "1.99"),
        ("47.102", "47.99"),
    ],
)
def test_amiga_version_greater(a, b):
    assert AmigaVersion.parse(a) > AmigaVersion.parse(b)


def test_amiga_version_str_roundtrip():
    assert str(AmigaVersion.parse("3.2.2.1")) == "3.2.2.1"


def test_amiga_version_letter_suffix_str_roundtrip():
    assert str(AmigaVersion.parse("2.9a")) == "2.9a"


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("2.9a", "2.9"),   # letter suffix sorts after the letterless form
        ("2.9b", "2.9a"),  # and in letter order
        ("2.10", "2.9a"),  # a numeric component still wins over any suffix
    ],
)
def test_amiga_version_letter_suffix_greater(a, b):
    assert AmigaVersion.parse(a) > AmigaVersion.parse(b)


def test_max_satisfying_with_letter_suffixed_versions():
    assert max_satisfying(["2.9", "2.9a", "2.9b"], []) == "2.9b"


@pytest.mark.parametrize(
    ("version", "constraints", "expected"),
    [
        ("5.20", [(">=", "3.0")], True),
        ("5.20", [(">=", "5.20")], True),
        ("5.19", [(">=", "5.20")], False),
        ("3.0", [(">=", "2.0"), ("<", "4.0")], True),
        ("4.0", [(">=", "2.0"), ("<", "4.0")], False),
        ("5.20", [("=", "5.20")], True),
        ("5.18", [("=", "5.20")], False),
    ],
)
def test_satisfies(version, constraints, expected):
    assert satisfies(version, constraints) == expected


def test_max_satisfying_picks_amiga_order_not_string_order():
    # string order would put "5.3" after "5.20"; Amiga order must not.
    assert max_satisfying(["5.3", "5.20"], []) == "5.20"
    assert max_satisfying(["5.18", "5.20"], [(">=", "5.19")]) == "5.20"


def test_max_satisfying_no_match():
    assert max_satisfying(["5.18", "5.20"], [(">=", "6.0")]) is None
