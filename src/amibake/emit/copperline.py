"""Copperline emulator config emission.

Real format grounded against `copperline --help`, the real
`copperline.example.toml`, and hands-on use during M5's real boot
verification (see PLAN.md's M5/M6 notes) — not guessed.
"""

from __future__ import annotations

from pathlib import Path

from ..machine import format_bytes, parse_ram_spec
from ..plan import BuildPlan, toml_value

_RAM_KINDS = ("chip", "fast", "slow", "z3")

# hdf-controller directive value -> (config table, first-drive key).
# copperhf's slots are unit0..unit6, lide's drive0..drive3; only the
# first is ever emitted here — extra drives are an override's business
# (e.g. "lide.drive1" = "extra.hdf").
_HDF_CONTROLLERS = {"copperhf": ("copperhf", "unit0"), "lide": ("lide", "drive0")}


class EmitError(Exception):
    pass


def write_copperline_config(plan: BuildPlan, path: Path, rom_path: Path,
                            dir_output_path: Path | None, emulator_config: dict,
                            hdf_output_path: Path | None = None) -> None:
    """Write a `copperline.toml` that boots the build.

    Two routes to a bootable volume, in this order of preference:

    - an `hdf` output, attached to a hardfile controller. Preferred when
      the manifest builds one, because it boots the real artifact — the
      same RDB image a user would write to CF — rather than a
      host-directory stand-in for it. Which controller is the
      `hdf-controller` directive (an AmiBake-interpreted
      `[emulator-config.copperline]` key, consumed here, never written
      to the config):
        - `"copperhf"` (default since Copperline 0.19): `[copperhf]`,
          Copperline's emulator-only virtual hardfile controller — the
          copperhf.device equivalent of WinUAE's uaehf.device. No real
          board fiction (a `[lide]` build claiming to be an A1200 boots
          off a Zorro II board no A1200 ever had), no machine profile
          needed, autoboot ROM baked into the emulator. `unit0`..`unit6`
          keys, bare-path or table form like the other controllers.
        - `"lide"`: the pre-0.19 default, Copperline's built-in
          lide.device-compatible Zorro II IDE board (RIPPLE by default)
          — the right choice when the thing under test is a real
          controller stack rather than the build. `drive0`..`drive3`
          keys, one per (channel, master/slave) slot (0.18+; the older
          positional `drives = [...]` still parses but can't express a
          gap).
      Either way the partition's PBFB_BOOTABLE flag is required, which
      `emit/hdf.py` sets (see its own comment — amitools does not set
      it by default).
    - a `dir` output, mounted as a HOSTFS volume (`[[filesys]]` with
      `bootpri = 6`, ahead of DF0:'s 5) — M5's original boot-verification
      mechanism, and the fallback when no hdf was built.

    Only one is emitted, never both: they carry the same volume name, so
    mounting both would give the guest two identically-named volumes and
    ambiguous assigns.

    The road not taken is `[ide]`, the real Gayle (A600/A1200) or A4000
    IDE port: it needs `[machine] profile` set to a machine that has one,
    and AmiBake's `machine` block has no profile axis to derive that
    from, so Copperline rightly refuses with *"[ide] images need a
    machine with an IDE port"*. That is AmiBake's gap, not the
    emulator's — worth stating because this docstring's own earlier
    wording ("no IDE/hard-disk-controller modeling yet") was read at
    least once as a claim that Copperline can't boot a hardfile at all.
    All grounded against the real emulator (0.18.0/0.19.0), not the docs
    alone. See `docs/limits.md`."""
    if hdf_output_path is None and dir_output_path is None:
        raise EmitError(
            "the copperline emitter needs an 'hdf' or 'dir' build output to "
            "boot ([copperhf]/[lide] hardfile or [[filesys]] host directory) — "
            "add one of them to the manifest's output list")

    machine = plan.machine
    emulator_config = dict(emulator_config)  # consumed keys must not leak back
    controller = emulator_config.pop("hdf-controller", "copperhf")
    if controller not in _HDF_CONTROLLERS:
        raise EmitError(
            f"unknown hdf-controller {controller!r} — use one of: "
            f"{', '.join(sorted(_HDF_CONTROLLERS))}")
    root_overrides, table_overrides = _split_dotted_overrides(emulator_config)

    lines = [f"rom = {toml_value(str(rom_path))}", *root_overrides, ""]

    def table(name: str, keys: list[str]) -> None:
        """Emit one `[name]` table, folding in any `name.key` manifest
        override. Merged rather than left to the trailing override loop
        because two `[name]` headers in one document is a TOML error, not
        a last-one-wins override — so a manifest setting `cpu.model` on a
        config that already emits `[cpu]` would produce a file Copperline
        refuses to parse. An override of a key emitted here replaces it."""
        overridden = {line.split(" = ", 1)[0] for line in table_overrides.get(name, [])}
        lines.append(f"[{name}]")
        lines.extend(k for k in keys if k.split(" = ", 1)[0] not in overridden)
        lines.extend(table_overrides.pop(name, []))
        lines.append("")

    cpu = [f"model = {toml_value(machine.get('cpu', '68000'))}"]
    if "fpu" in machine:
        cpu.append(f"fpu = {toml_value(bool(machine['fpu']))}")
    table("cpu", cpu)

    ram = parse_ram_spec(machine["ram"]) if machine.get("ram") else {}
    if ram:
        table("memory", [f"{kind} = {toml_value(format_bytes(ram[kind]))}"
                         for kind in _RAM_KINDS if kind in ram])

    if machine.get("chipset"):
        table("chipset", [f"revision = {toml_value(machine['chipset'].upper())}"])

    if hdf_output_path is not None:
        # First slot only, no board/rom keys: both controllers' minimal
        # config is also the working one (copperhf's autoboot ROM is
        # baked into the emulator; lide's RIPPLE default bundles its own).
        controller_table, first_drive = _HDF_CONTROLLERS[controller]
        table(controller_table,
              [f"{first_drive} = {toml_value(str(hdf_output_path))}"])
    else:
        lines.append("[[filesys]]")
        lines.append(f"path = {toml_value(str(dir_output_path))}")
        lines.append(f"volume = {toml_value(dir_output_path.name)}")
        lines.append("bootpri = 6")
        lines.append("")

    for table in sorted(table_overrides):
        lines.append(f"[{table}]")
        lines.extend(table_overrides[table])
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n")


def _split_dotted_overrides(emulator_config: dict) -> tuple[list[str], dict[str, list[str]]]:
    """`{"hostsocket.net": "host"}` -> table overrides `{"hostsocket":
    ["net = ..."]}`. A dotted key's first segment names the TOML table;
    everything after the first `.` is the key within it (so
    `"foo.bar.baz"` -> table `foo`, key `bar.baz` — tables aren't nested
    more than one level deep by any real directive seen so far). A bare
    (undotted) key is a document-root override, returned separately:
    TOML bare keys are only valid before the first `[table]` header,
    never after one (the same rule the lockfile writer in plan.py has
    to follow), so callers must place these before any `[section]`,
    while `[table]`-header overrides are safe to place anywhere that
    doesn't already declare that same table."""
    root: list[str] = []
    tables: dict[str, list[str]] = {}
    for key, value in emulator_config.items():
        table, sep, rest = key.partition(".")
        if not sep:
            root.append(f"{key} = {toml_value(value)}")
        else:
            tables.setdefault(table, []).append(f"{rest} = {toml_value(value)}")
    return root, tables
