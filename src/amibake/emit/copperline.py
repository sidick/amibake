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


class EmitError(Exception):
    pass


def write_copperline_config(plan: BuildPlan, path: Path, rom_path: Path,
                            dir_output_path: Path | None, emulator_config: dict) -> None:
    """Write a `copperline.toml`. Mounts `dir_output_path` as a bootable
    HOSTFS volume (`[[filesys]]` with `bootpri = 6`) — the mechanism M5's
    own boot verification used and confirmed works, on any machine
    profile, without needing to model a real 1.3-era hard-disk
    controller the way `[ide]` would. Raises if no `dir` output exists
    to mount: there's no other bootable-volume path implemented yet."""
    if dir_output_path is None:
        raise EmitError(
            "the copperline emitter needs a 'dir' build output to mount as a "
            "bootable volume (no IDE/hard-disk-controller modeling yet, so hdf "
            "images can't be booted directly) — add 'dir' to the manifest's "
            "output list")

    machine = plan.machine
    root_overrides, table_overrides = _split_dotted_overrides(emulator_config)

    lines = [f"rom = {toml_value(str(rom_path))}", *root_overrides, ""]

    lines.append("[cpu]")
    lines.append(f"model = {toml_value(machine.get('cpu', '68000'))}")
    if "fpu" in machine:
        lines.append(f"fpu = {toml_value(bool(machine['fpu']))}")
    lines.append("")

    ram = parse_ram_spec(machine["ram"]) if machine.get("ram") else {}
    if ram:
        lines.append("[memory]")
        for kind in _RAM_KINDS:
            if kind in ram:
                lines.append(f"{kind} = {toml_value(format_bytes(ram[kind]))}")
        lines.append("")

    if machine.get("chipset"):
        lines.append("[chipset]")
        lines.append(f"revision = {toml_value(machine['chipset'].upper())}")
        lines.append("")

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
