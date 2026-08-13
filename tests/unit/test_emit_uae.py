import pytest

from amibake.emit.uae import EmitError, write_uae_config
from amibake.plan import BaseInfo, BuildPlan, ResolvedPackage


def _plan(machine, output=("hdf", "dir")):
    base_pkg = ResolvedPackage(name="somebase", version="1.0", recipe_sha256="0" * 64)
    return BuildPlan(
        base=BaseInfo(name="somebase", os_version="3.1"),
        base_package=base_pkg, machine=machine,
        packages=(), output=output, emit=("amiberry",),
    )


def _parse(text):
    out = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition("=")
        out[key] = value
    return out


def test_writes_cpu_chipset_memory_rom_and_mount(tmp_path):
    plan = _plan({"cpu": "68030", "chipset": "aga", "ram": "chip:1M,fast:8M,slow:512K"})
    target = tmp_path / "out.uae"
    rom = tmp_path / "kick.rom"
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)

    write_uae_config(plan, target, rom, dir_out, {})

    cfg = _parse(target.read_text())
    assert cfg["cpu_model"] == "68030"
    assert cfg["cpu_24bit_addressing"] == "false"
    assert cfg["chipset"] == "aga"
    assert cfg["chipset_compatible"] == "A1200"
    assert cfg["chipmem_size"] == "2"  # 1M / 512K
    assert cfg["fastmem_size"] == "8"  # raw MB
    assert cfg["bogomem_size"] == "2"  # 512K / 256K
    assert cfg["kickstart_rom_file"] == str(rom)
    assert cfg["filesystem2"] == f"rw,DH0:mysetup:{dir_out},-1"


def test_defaults_for_68000(tmp_path):
    plan = _plan({})
    target = tmp_path / "out.uae"
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)

    write_uae_config(plan, target, tmp_path / "kick.rom", dir_out, {})

    cfg = _parse(target.read_text())
    assert cfg["cpu_model"] == "68000"
    assert cfg["cpu_24bit_addressing"] == "true"
    assert "chipset" not in cfg


def test_fpu_on_68040_uses_ondie_model(tmp_path):
    plan = _plan({"cpu": "68040", "fpu": True})
    target = tmp_path / "out.uae"
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)

    write_uae_config(plan, target, tmp_path / "kick.rom", dir_out, {})

    assert _parse(target.read_text())["fpu_model"] == "68040"


def test_fpu_on_68020_uses_generic_68882(tmp_path):
    plan = _plan({"cpu": "68020", "fpu": True})
    target = tmp_path / "out.uae"
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)

    write_uae_config(plan, target, tmp_path / "kick.rom", dir_out, {})

    assert _parse(target.read_text())["fpu_model"] == "68882"


def test_ram_not_a_whole_unit_is_an_error(tmp_path):
    plan = _plan({"ram": "fast:512K"})
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)
    with pytest.raises(EmitError, match="fastmem_size"):
        write_uae_config(plan, tmp_path / "out.uae", tmp_path / "kick.rom", dir_out, {})


def test_no_dir_output_raises_named_error(tmp_path):
    plan = _plan({}, output=("hdf",))
    with pytest.raises(EmitError, match="'dir' build output"):
        write_uae_config(plan, tmp_path / "out.uae", tmp_path / "kick.rom", None, {})


def test_emulator_config_overrides_applied(tmp_path):
    plan = _plan({})
    target = tmp_path / "out.uae"
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)

    write_uae_config(plan, target, tmp_path / "kick.rom", dir_out, {"bsdsocket_emu": "true"})

    assert _parse(target.read_text())["bsdsocket_emu"] == "true"


def test_winuae_flavor_still_writes(tmp_path):
    plan = _plan({})
    target = tmp_path / "out.uae"
    dir_out = tmp_path / "build" / "mysetup"
    dir_out.mkdir(parents=True)

    write_uae_config(plan, target, tmp_path / "kick.rom", dir_out, {}, flavor="winuae")

    assert target.exists()
