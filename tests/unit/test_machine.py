from amibake.machine import format_bytes, parse_ram_spec


def test_single_spec():
    assert parse_ram_spec("chip:512K") == {"chip": 512 * 1024}


def test_multiple_specs():
    assert parse_ram_spec("chip:2M,fast:8M") == {
        "chip": 2 * 1024 * 1024,
        "fast": 8 * 1024 * 1024,
    }


def test_gigabyte_unit():
    assert parse_ram_spec("z3:1G") == {"z3": 1024 * 1024 * 1024}


def test_all_kinds():
    assert parse_ram_spec("chip:1M,fast:1M,slow:1M,z3:1M") == {
        "chip": 1024 * 1024, "fast": 1024 * 1024,
        "slow": 1024 * 1024, "z3": 1024 * 1024,
    }


def test_format_bytes_picks_largest_clean_unit():
    assert format_bytes(512 * 1024) == "512K"
    assert format_bytes(2 * 1024 * 1024) == "2M"
    assert format_bytes(1024 * 1024 * 1024) == "1G"


def test_format_bytes_round_trips_parse_ram_spec():
    for spec in ("chip:512K", "fast:8M", "z3:1G"):
        kind, value = next(iter(parse_ram_spec(spec).items()))
        assert f"{kind}:{format_bytes(value)}" == spec
