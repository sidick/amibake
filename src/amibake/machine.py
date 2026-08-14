"""Machine-block helpers shared by the config emitters, resolver, and
layer applier.

The manifest's `machine.ram` is a string (`"chip:2M,fast:8M"`) — valid
syntax is checked by `manifest.py`'s `_RAM_SPEC_RE`, but nothing turns it
into bytes a config emitter can act on. That's most of this module's job;
`CPU_ORDER`/`cpu_satisfies` also live here so resolver.py's
`[requires].cpu` check and layer.py's `variants` predicate matching (see
`docs/recipe-contract.md`'s `[install].copy` variants) share one
ordering, rather than two copies drifting apart.
"""

from __future__ import annotations

from .versionspec import Constraint

CPU_ORDER = ["68000", "68010", "68020", "68030", "68040", "68060"]

_UNITS = {"K": 1024, "M": 1024**2, "G": 1024**3}


def cpu_satisfies(cpu: str, constraints: list[Constraint]) -> bool:
    """Does machine.cpu `cpu` (e.g. "68030") satisfy every constraint in
    `constraints` (parsed from a "[requires].cpu"/variant "cpu" string
    like ">= 68020")? Raises ValueError via CPU_ORDER.index if `cpu` or a
    constraint target isn't a recognized CPU family — callers decide how
    to treat that (resolver.py: pass the check, since there's nothing
    more it can say)."""
    idx = CPU_ORDER.index(cpu)
    for op, target in constraints:
        target_idx = CPU_ORDER.index(target)
        if op == "=" and idx != target_idx:
            return False
        if op == ">=" and idx < target_idx:
            return False
        if op == "<=" and idx > target_idx:
            return False
        if op == ">" and idx <= target_idx:
            return False
        if op == "<" and idx >= target_idx:
            return False
    return True


def parse_ram_spec(spec: str) -> dict[str, int]:
    """`"chip:2M,fast:8M"` -> `{"chip": 2097152, "fast": 8388608}`.

    Assumes `spec` already passed manifest.py's validation (kind one of
    chip/fast/slow/z3, size an integer immediately followed by K/M/G) —
    this is a pure conversion, not a second validation pass.
    """
    out: dict[str, int] = {}
    for part in spec.split(","):
        kind, _, size = part.strip().partition(":")
        out[kind] = int(size[:-1]) * _UNITS[size[-1]]
    return out


def format_bytes(n: int) -> str:
    """The inverse of parse_ram_spec's per-kind value: `2097152` ->
    `"2M"`. Picks the largest of G/M/K that divides evenly — every value
    this sees originated from a manifest's own K/M/G spec, so one always
    does (K at worst, since specs are validated to be whole K/M/G)."""
    for suffix, factor in (("G", _UNITS["G"]), ("M", _UNITS["M"]), ("K", _UNITS["K"])):
        if n % factor == 0:
            return f"{n // factor}{suffix}"
    raise ValueError(f"{n} bytes is not a whole number of K")
