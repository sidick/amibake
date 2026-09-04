import tomllib

import pytest

from amibake.emit.copperline import EmitError, write_copperline_config
from amibake.plan import BaseInfo, BuildPlan, ResolvedPackage


def _plan(machine, output=("hdf", "dir")):
    base_pkg = ResolvedPackage(name="somebase", version="1.0", recipe_sha256="0" * 64)
    return BuildPlan(
        base=BaseInfo(name="somebase", os_version="3.1"),
        base_package=base_pkg, machine=machine,
        packages=(), output=output, emit=("copperline",),
    )


def test_writes_rom_cpu_memory_chipset_and_filesys(tmp_path):
    plan = _plan({"cpu": "68030", "fpu": True, "ram": "chip:2M,fast:8M", "chipset": "aga"})
    target = tmp_path / "out.copperline.toml"
    rom = tmp_path / "kick.rom"
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)

    write_copperline_config(plan, target, rom, dir_out, {})

    doc = tomllib.loads(target.read_text())
    assert doc["rom"] == str(rom)
    assert doc["cpu"]["model"] == "68030"
    assert doc["cpu"]["fpu"] is True
    assert doc["memory"]["chip"] == "2M"
    assert doc["memory"]["fast"] == "8M"
    assert doc["chipset"]["revision"] == "AGA"
    assert doc["filesys"][0]["path"] == str(dir_out)
    assert doc["filesys"][0]["volume"] == "mysetup"
    assert doc["filesys"][0]["bootpri"] == 6


def test_defaults_when_machine_block_is_empty(tmp_path):
    plan = _plan({})
    target = tmp_path / "out.copperline.toml"
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)

    write_copperline_config(plan, target, tmp_path / "kick.rom", dir_out, {})

    doc = tomllib.loads(target.read_text())
    assert doc["cpu"]["model"] == "68000"
    assert "memory" not in doc
    assert "chipset" not in doc


def test_no_bootable_output_raises_named_error(tmp_path):
    plan = _plan({}, output=())
    with pytest.raises(EmitError, match="'hdf' or 'dir' build output"):
        write_copperline_config(plan, tmp_path / "out.toml", tmp_path / "kick.rom", None, {})


def test_hdf_output_boots_from_lide(tmp_path):
    plan = _plan({}, output=("hdf",))
    target = tmp_path / "out.copperline.toml"
    hdf = tmp_path / "build" / "mysetup.hdf"

    write_copperline_config(plan, target, tmp_path / "kick.rom", None, {}, hdf)

    doc = tomllib.loads(target.read_text())
    assert doc["lide"]["drive0"] == str(hdf)
    # No board: RIPPLE is the default and bundles its own boot ROM.
    assert "board" not in doc["lide"]
    assert "filesys" not in doc


def test_hdf_wins_over_dir_and_never_mounts_both(tmp_path):
    """Both would carry the same volume name — two identically-named
    volumes and ambiguous assigns for the guest."""
    plan = _plan({}, output=("hdf", "dir"))
    target = tmp_path / "out.copperline.toml"
    hdf = tmp_path / "build" / "mysetup.hdf"
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)

    write_copperline_config(plan, target, tmp_path / "kick.rom", dir_out, {}, hdf)

    doc = tomllib.loads(target.read_text())
    assert doc["lide"]["drive0"] == str(hdf)
    assert "filesys" not in doc


def test_lide_override_merges_into_one_table(tmp_path):
    """A second `[lide]` header would be a TOML parse error, not an
    override — so a manifest key for a table the emitter already writes
    has to be folded into it, replacing the emitted key."""
    plan = _plan({}, output=("hdf",))
    target = tmp_path / "out.copperline.toml"
    hdf = tmp_path / "build" / "mysetup.hdf"

    write_copperline_config(plan, target, tmp_path / "kick.rom", None,
                            {"lide.board": "atbus2008", "lide.drive1": "extra.hdf"}, hdf)

    doc = tomllib.loads(target.read_text())  # raises if the table is emitted twice
    assert doc["lide"] == {"drive0": str(hdf), "board": "atbus2008", "drive1": "extra.hdf"}


def test_override_of_an_emitted_key_replaces_it(tmp_path):
    plan = _plan({"cpu": "68030"}, output=("dir",))
    target = tmp_path / "out.copperline.toml"
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)

    write_copperline_config(plan, target, tmp_path / "kick.rom", dir_out,
                            {"cpu.model": "68040", "cpu.clock_mhz": 25})

    doc = tomllib.loads(target.read_text())
    assert doc["cpu"] == {"model": "68040", "clock_mhz": 25}
    assert doc["filesys"][0]["bootpri"] == 6


def test_emulator_config_dotted_key_becomes_nested_table(tmp_path):
    plan = _plan({})
    target = tmp_path / "out.copperline.toml"
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)

    write_copperline_config(plan, target, tmp_path / "kick.rom", dir_out,
                            {"hostsocket.net": "host"})

    doc = tomllib.loads(target.read_text())
    assert doc["hostsocket"]["net"] == "host"


def test_bare_emulator_config_key_at_document_root(tmp_path):
    plan = _plan({})
    target = tmp_path / "out.copperline.toml"
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)

    write_copperline_config(plan, target, tmp_path / "kick.rom", dir_out, {"identify": False})

    doc = tomllib.loads(target.read_text())
    assert doc["identify"] is False
