"""Manifest loading and validation. Spec: docs/manifest.md."""

from __future__ import annotations

import re
from pathlib import Path

from ._validate import Checker, load_toml
from .errors import Problem
from .versionspec import is_name, parse_constraint, parse_package_spec

CPU_FAMILIES = {"68000", "68010", "68020", "68030", "68040", "68060"}
CHIPSETS = {"ocs", "ecs", "aga"}
OUTPUT_FORMATS = {"hdf", "dir", "tgz", "zip"}
EMULATORS = {"copperline", "amiberry", "winuae"}

TOP_KEYS = {"base", "machine", "packages", "output", "emit", "providers"}
MACHINE_KEYS = {"cpu", "fpu", "mmu", "ram", "rtg", "chipset"}

_RAM_SPEC_RE = re.compile(r"^(chip|fast|slow|z3):\d+[KMG]$")


def validate_manifest(path: Path) -> list[Problem]:
    """Validate one manifest file, returning all problems found."""
    doc = load_toml(path)
    c = Checker(str(path))

    c.unknown_keys(doc, TOP_KEYS, "")
    base = c.typed(doc, "base", str, "", required=True)
    if base is not None and not is_name(base):
        c.error("base", f"bad base name {base!r}",
                "base names are lower-case slugs like 'os3.2.2', 'wb1.3', 'aros68k'")

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

    providers = c.typed(doc, "providers", dict, "", default={})
    for cap, provider in providers.items():
        if not isinstance(provider, str) or not is_name(provider):
            c.error(f"providers.{cap}", "provider must be a package name string",
                    'e.g. bsdsocket = "roadshow"')
        if not is_name(cap):
            c.error(f"providers.{cap}", f"bad capability name {cap!r}",
                    "capability names are lower-case slugs")

    return c.problems


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
