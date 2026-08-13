"""Amiberry / WinUAE `.uae` config emission.

Real format grounded two ways: real `.uae` content pulled live from a
local Amiberry install via the `mcp__amiberry__*` tools
(`amibake-aros68k.uae` — the actual M4 boot-verification config;
`default.uae`; `amirfb_p96_free.uae`, a real in-use project's config
confirming `bsdsocket_emu=true`), and the real key-scaling formulas read
directly out of a local Amiberry source checkout's `cfgfile.cpp`
(`cfgfile_readramboard`/the `chipmem_size`/`bogomem_size` writers) — not
guessed. WinUAE shares the same flat key=value format (Amiberry is a UAE
derivative) but has no local install to verify against; treated as
best-effort, same honesty bar as this project's other unverified pieces
(P96, the original wb1.3 recipe).
"""

from __future__ import annotations

from pathlib import Path

from ..machine import parse_ram_spec
from ..plan import BuildPlan

# The confirmed-real, working key set from amibake-aros68k.uae (a much
# shorter set than the full ~150-key default.uae, which also boots
# fine) plus amirfb_p96_free.uae's confirmed keys. Overrides below are
# applied on top of this at emit time.
_TEMPLATE = {
    "cpu_compatible": "true",
    "sound_channels": "stereo",
    "sound_frequency": "44100",
    "sound_output": "exact",
    "nr_floppies": "0",
    "floppy0type": "-1",
    "floppy_speed": "100",
    "gfx_resolution": "hires",
    "gfx_linemode": "double",
    "gfx_width": "640",
    "gfx_height": "512",
}

# Real cfgfile.cpp scaling (cfgfile_readramboard's per-key multiplier,
# and the chipmem_size/bogomem_size writers): chipmem_size and
# bogomem_size are counted in fixed 512K/256K units (not raw MB, unlike
# every other *mem_size key) -- confirmed both from source and by
# empirically probing a live Amiberry config via
# mcp__amiberry__create_config/modify_config/parse_config.
_CHIPMEM_UNIT = 512 * 1024
_BOGOMEM_UNIT = 256 * 1024
_MB = 1024 * 1024


class EmitError(Exception):
    pass


def write_uae_config(plan: BuildPlan, path: Path, rom_path: Path,
                     dir_output_path: Path | None, emulator_config: dict,
                     flavor: str = "amiberry") -> None:
    """Write a `.uae` config. Mounts `dir_output_path` as `DH0:` via
    `filesystem2=rw,DH0:<stem>:<path>,-1` (confirmed real syntax, e.g.
    `amirfb_p96_free.uae`'s own working config). Raises if no `dir`
    output exists to mount, same reasoning as the Copperline emitter."""
    if dir_output_path is None:
        raise EmitError(
            f"the {flavor} emitter needs a 'dir' build output to mount as "
            f"DH0: (no hardfile/RDB mount implemented yet) — add 'dir' to "
            f"the manifest's output list")

    settings = dict(_TEMPLATE)
    machine = plan.machine

    settings["cpu_model"] = machine.get("cpu", "68000")
    has_32bit_bus = machine.get("cpu") in ("68020", "68030", "68040", "68060")
    settings["cpu_24bit_addressing"] = "false" if has_32bit_bus else "true"
    if "fpu" in machine:
        settings["fpu_model"] = _fpu_model(machine) if machine["fpu"] else "0"

    if machine.get("chipset"):
        settings["chipset"] = machine["chipset"]
        settings["chipset_compatible"] = _chipset_compatible(machine["chipset"])

    ram = parse_ram_spec(machine["ram"]) if machine.get("ram") else {}
    for kind, key, unit in (("chip", "chipmem_size", _CHIPMEM_UNIT),
                            ("slow", "bogomem_size", _BOGOMEM_UNIT),
                            ("fast", "fastmem_size", _MB),
                            ("z3", "z3mem_size", _MB)):
        if kind not in ram:
            continue
        if ram[kind] % unit != 0:
            raise EmitError(
                f"machine.ram's {kind!r} size ({ram[kind]} bytes) isn't a "
                f"whole number of the real {key} unit ({unit} bytes) — use "
                f"a size that divides evenly")
        settings[key] = str(ram[kind] // unit)

    settings["kickstart_rom_file"] = str(rom_path)
    settings["filesystem2"] = f"rw,DH0:{dir_output_path.name}:{dir_output_path},-1"

    settings.update({k: _uae_scalar(v) for k, v in emulator_config.items()})

    lines = [f"{key}={settings[key]}" for key in settings]
    path.write_text("\n".join(lines) + "\n")


def _fpu_model(machine: dict) -> str:
    """68040/68060 have an on-die FPU of the same name; anything else
    that asks for one gets a generic 68882 -- a real, common external
    FPU choice, not the only correct answer (a recipe can override via
    [emulator-config] if it needs a specific part)."""
    cpu = machine.get("cpu")
    return cpu if cpu in ("68040", "68060") else "68882"


def _chipset_compatible(chipset: str) -> str:
    """Best-effort board-family guess from chipset alone -- AmiBake's
    machine block has no board/profile concept to draw on directly.
    Approximate; a recipe wanting a specific board should override via
    [emulator-config]."""
    return {"aga": "A1200", "ecs": "A600", "ocs": "A500"}.get(chipset, "A500")


def _uae_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
