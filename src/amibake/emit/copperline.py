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
                            dir_output_path: Path | None, emulator_config: dict,
                            hdf_output_path: Path | None = None) -> None:
    """Write a `copperline.toml` that boots the build.

    Two routes to a bootable volume, in this order of preference:

    - an `hdf` output, attached to `[lide]` — Copperline's built-in
      lide.device-compatible Zorro II IDE board (RIPPLE by default),
      which needs **no** `[machine] profile`, works on any machine
      model, autoboots under any Kickstart including 1.3, and brings its
      own bundled ROM. Preferred when the manifest builds one, because
      it boots the real artifact — the same RDB image a user would write
      to CF — rather than a host-directory stand-in for it. Note the
      0.18 config shape: named `drive0`..`drive3` keys, one per
      (channel, master/slave) slot; the older positional
      `drives = [...]` array still parses but can't express a gap.
      Requires the partition's PBFB_BOOTABLE flag, which `emit/hdf.py`
      sets (see its own comment — amitools does not set it by default).
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
    It can, both ways; `[lide]` is simply the one that asks nothing of a
    machine block that has no profile concept. All grounded against the
    real emulator (0.18.0), not the docs alone. See `docs/limits.md`."""
    if hdf_output_path is None and dir_output_path is None:
        raise EmitError(
            "the copperline emitter needs an 'hdf' or 'dir' build output to "
            "boot ([lide] hardfile or [[filesys]] host directory) — add one "
            "of them to the manifest's output list")

    machine = plan.machine
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
        # Channel 0 master. `board` is left unset: RIPPLE is the default
        # and brings its own bundled ROM, so the minimal config is also
        # the working one.
        table("lide", [f"drive0 = {toml_value(str(hdf_output_path))}"])
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
