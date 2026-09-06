"""Manifest loading and validation. Spec: docs/manifest.md."""

from __future__ import annotations

import re
from pathlib import Path

from ._validate import Checker, check_tooltype_values, load_toml
from .errors import Problem
from .versionspec import is_name, parse_constraint, parse_package_spec

CPU_FAMILIES = {"68000", "68010", "68020", "68030", "68040", "68060"}
CHIPSETS = {"ocs", "ecs", "aga"}
OUTPUT_FORMATS = {"hdf", "dir", "tgz", "zip"}
EMULATORS = {"copperline", "amiberry", "winuae"}
RUN_MODES = {"cli", "wbstartup"}
RUN_KEYS = {"command", "args", "stack", "output", "detach", "mode",
            "tooltypes", "startpri", "donotwait"}
# Which keys only make sense for which mode. `command`, `stack` and
# `mode` itself are mode-independent.
_RUN_CLI_ONLY = {"args", "output", "detach"}
_RUN_WBSTARTUP_ONLY = {"tooltypes", "startpri", "donotwait"}
# Sugar key -> the tool type it lowers into; setting both in one entry
# is a contradiction, not an override.
_RUN_SUGAR_TOOLTYPES = {"stack": "STACK", "startpri": "STARTPRI",
                        "donotwait": "DONOTWAIT"}

TOP_KEYS = {"base", "machine", "packages", "output", "emit", "providers", "run", "hdf"}
MACHINE_KEYS = {"cpu", "fpu", "mmu", "ram", "rtg", "chipset"}
HDF_KEYS = {"size", "scratch"}

_RAM_SPEC_RE = re.compile(r"^(chip|fast|slow|z3):\d+[KMG]$")
_SIZE_RE = re.compile(r"^\d+[KMG]$")


def validate_manifest(path: Path) -> list[Problem]:
    """Validate one manifest file, returning all problems found."""
    doc = load_toml(path)
    c = Checker(str(path))

    c.unknown_keys(doc, TOP_KEYS, "")
    _check_base(c, doc)

    machine = c.typed(doc, "machine", dict, "", default=None)
    if machine is not None:
        _check_machine(c, machine)

    packages = c.typed(doc, "packages", list, "", default=[])
    for i, entry in enumerate(packages):
        _check_package_entry(c, entry, f"packages[{i}]")

    for key, allowed, kind in (("output", OUTPUT_FORMATS, "output format"),
                               ("emit", EMULATORS, "emulator")):
        for i, item in enumerate(c.string_list(doc, key, "")):
            if item not in allowed:
                c.error(f"{key}[{i}]", f"unknown {kind} {item!r}",
                        f"use one of: {', '.join(sorted(allowed))}")

    hdf = c.typed(doc, "hdf", dict, "", default=None)
    if hdf is not None:
        _check_hdf(c, hdf, doc)

    runs = c.typed(doc, "run", list, "", default=[])
    for i, entry in enumerate(runs):
        _check_run_entry(c, entry, f"run[{i}]")

    providers = c.typed(doc, "providers", dict, "", default={})
    for cap, provider in providers.items():
        if not isinstance(provider, str) or not is_name(provider):
            c.error(f"providers.{cap}", "provider must be a package name string",
                    'e.g. bsdsocket = "roadshow"')
        if not is_name(cap):
            c.error(f"providers.{cap}", f"bad capability name {cap!r}",
                    "capability names are lower-case slugs")

    return c.problems


def _check_base(c: Checker, doc: dict) -> None:
    """`base` is either a bare name string (`base = "wb1.3"`) or a table
    naming the base plus answers to its own [options] (`base = { name =
    "wb1.3", boot = "cli" }`) — same shape as a `packages[]` table entry,
    minus `version` (a base always resolves to its newest declared
    version; there's no manifest-level way to pin an older one)."""
    if "base" not in doc:
        c.error("base", "required key is missing", "add 'base'")
        return
    base = doc["base"]
    if isinstance(base, str):
        if not is_name(base):
            c.error("base", f"bad base name {base!r}",
                    "base names are lower-case slugs like 'os3.2.2', 'wb1.3', 'aros68k'")
    elif isinstance(base, dict):
        name = c.typed(base, "name", str, "base", required=True)
        if name is not None and not is_name(name):
            c.error("base.name", f"bad base name {name!r}",
                    "base names are lower-case slugs like 'os3.2.2', 'wb1.3', 'aros68k'")
        for key, value in base.items():
            if key == "name":
                continue
            if not isinstance(value, str | int | bool):
                c.error(f"base.{key}",
                        "option answers must be strings, integers or booleans",
                        "check the base recipe's [options] declaration for the "
                        "expected type")
    else:
        c.error("base", "base must be a name string or a table",
                'e.g. base = "wb1.3" or base = { name = "wb1.3", boot = "cli" }')


def _check_hdf(c: Checker, hdf: dict, doc: dict) -> None:
    """The [hdf] table shapes the hdf output image: a total size
    override and an optional unformatted scratch partition at the end
    (a safe target for destructive block-device tests like devsoak).
    Spec: docs/manifest.md."""
    c.unknown_keys(hdf, HDF_KEYS, "hdf")
    for key in sorted(HDF_KEYS):
        value = c.typed(hdf, key, str, "hdf")
        if value is not None and not _SIZE_RE.match(value):
            c.error(f"hdf.{key}", f"bad size {value!r}",
                    'use an integer with a K/M/G unit, e.g. "64M"')
    output = doc.get("output")
    if isinstance(output, list) and "hdf" not in output:
        c.error("hdf", "[hdf] configures the hdf output, which this manifest's "
                "explicit output list does not include",
                'add "hdf" to output, or drop the [hdf] table')


def _check_run_entry(c: Checker, entry, label: str) -> None:
    """One [[run]] table: a program the built image runs at boot — via
    the generated S:AmiBake-Startup script (mode "cli", the default) or
    the SYS:WBStartup drawer (mode "wbstartup"). Spec: docs/manifest.md."""
    if not isinstance(entry, dict):
        c.error(label, "run entries must be tables",
                'e.g. [[run]] with command = "C:devsoak", args = "..."')
        return
    c.unknown_keys(entry, RUN_KEYS, label)

    command = c.typed(entry, "command", str, label, required=True)
    if command is not None and ":" not in command:
        c.error(f"{label}.command", f"{command!r} is not an Amiga path",
                'name the installed program by an absolute Amiga path, e.g. '
                '"C:devsoak" or "SYS:Tools/AmiInspect"')

    mode = c.typed(entry, "mode", str, label, default="cli")
    if mode not in RUN_MODES:
        c.error(f"{label}.mode", f"unknown run mode {mode!r}",
                f"use one of: {', '.join(sorted(RUN_MODES))}")
        mode = "cli"

    wrong = (_RUN_WBSTARTUP_ONLY if mode == "cli" else _RUN_CLI_ONLY) & set(entry)
    for key in sorted(wrong):
        other = "wbstartup" if mode == "cli" else "cli"
        c.error(f"{label}.{key}",
                f"{key!r} only applies to mode = \"{other}\" entries",
                "remove it, or change this entry's mode")

    stack = c.typed(entry, "stack", int, label)
    if stack is not None and stack <= 0:
        c.error(f"{label}.stack", f"stack must be a positive byte count, got {stack}",
                "e.g. stack = 65536")
    c.typed(entry, "args", str, label)
    c.typed(entry, "detach", bool, label)
    c.typed(entry, "startpri", int, label)
    c.typed(entry, "donotwait", bool, label)
    output = c.typed(entry, "output", str, label)
    if output is not None and ":" not in output:
        c.error(f"{label}.output", f"{output!r} is not an Amiga path",
                'redirect to an absolute Amiga path, e.g. "T:devsoak.log" or "SER:"')

    tooltypes = c.typed(entry, "tooltypes", dict, label)
    if tooltypes is not None:
        check_tooltype_values(c, tooltypes, f"{label}.tooltypes")
        for sugar, tooltype in _RUN_SUGAR_TOOLTYPES.items():
            if sugar in entry and any(k.lower() == tooltype.lower() for k in tooltypes):
                c.error(f"{label}.tooltypes.{tooltype}",
                        f"{tooltype} is also set via this entry's {sugar!r} key",
                        "within one entry that's a contradiction, not an "
                        "override — set it one way or the other")


def _check_machine(c: Checker, machine: dict) -> None:
    c.unknown_keys(machine, MACHINE_KEYS, "machine")
    cpu = c.typed(machine, "cpu", str, "machine")
    if cpu is not None and cpu not in CPU_FAMILIES:
        c.error("machine.cpu", f"unknown CPU family {cpu!r}",
                f"use one of {', '.join(sorted(CPU_FAMILIES))}; FPU and MMU are "
                "separate boolean keys, not packed into the CPU string")
    c.typed(machine, "fpu", bool, "machine")
    c.typed(machine, "mmu", bool, "machine")
    c.typed(machine, "rtg", bool, "machine")
    ram = c.typed(machine, "ram", str, "machine")
    if ram is not None:
        for spec in ram.split(","):
            if not _RAM_SPEC_RE.match(spec.strip()):
                c.error("machine.ram", f"bad RAM spec {spec.strip()!r}",
                        "use <kind>:<size> with kind chip/fast/slow/z3 and a "
                        "size like 512K, 8M or 1G, e.g. \"chip:2M,fast:8M\"")
    chipset = c.typed(machine, "chipset", str, "machine")
    if chipset is not None and chipset not in CHIPSETS:
        c.error("machine.chipset", f"unknown chipset {chipset!r}",
                f"use one of: {', '.join(sorted(CHIPSETS))}")


def _check_package_entry(c: Checker, entry, label: str) -> None:
    if isinstance(entry, str):
        try:
            parse_package_spec(entry)
        except ValueError as e:
            c.error(label, str(e), 'e.g. "amissl = 5.20" or "p96 >= 3.2"')
    elif isinstance(entry, dict):
        name = c.typed(entry, "name", str, label, required=True)
        if name is not None and not is_name(name):
            c.error(f"{label}.name", f"bad package name {name!r}",
                    "names are lower-case slugs ([a-z0-9] plus interior '-')")
        version = c.typed(entry, "version", str, label)
        if version is not None:
            try:
                parse_constraint(version)
            except ValueError as e:
                c.error(f"{label}.version", str(e), 'e.g. version = ">= 3.2"')
        for key, value in entry.items():
            if key in ("name", "version"):
                continue
            if not isinstance(value, str | int | bool):
                c.error(f"{label}.{key}",
                        "option answers must be strings, integers or booleans",
                        "check the recipe's [options] declaration for the "
                        "expected type")
    else:
        c.error(label, "package entries are strings or tables",
                'either "name = 5.20" spec strings or '
                '{ name = "p96", card = "uaegfx" } tables')
