"""Version strings, constraints, and package specs — syntax only.

Comparison semantics (AmigaVersion ordering, constraint satisfaction) are
M1's resolver work; M0 validates that what was written is well-formed.
Versions are always strings: `5.20` is a version, never the float 5.2.
"""

from __future__ import annotations

import re

VERSION_RE = re.compile(r"^\d+(\.\d+)*$")
NAME_RE = re.compile(r"^[a-z0-9]+([.-][a-z0-9]+)*$")
_CONSTRAINT_RE = re.compile(r"^(>=|<=|=|>|<)\s*(\S+)$")

Constraint = tuple[str, str]  # (operator, version string)


def is_version(text: str) -> bool:
    return bool(VERSION_RE.match(text))


def is_name(text: str) -> bool:
    return bool(NAME_RE.match(text))


def parse_constraint(text: str) -> list[Constraint]:
    """Parse '>= 3.0' or '>= 2.0, < 4.0'. Raises ValueError with a
    user-ready message on bad syntax."""
    constraints: list[Constraint] = []
    for part in text.split(","):
        part = part.strip()
        m = _CONSTRAINT_RE.match(part)
        if not m:
            raise ValueError(
                f"bad constraint {part!r}: expected an operator (=, >=, <=, >, <) "
                f"followed by a version, e.g. '>= 3.0'"
            )
        op, version = m.groups()
        if not is_version(version):
            raise ValueError(
                f"bad version {version!r} in constraint {part!r}: versions are "
                f"dotted decimal strings like '3.2.2.1' or '5.20'"
            )
        constraints.append((op, version))
    return constraints


def parse_package_spec(text: str) -> tuple[str, list[Constraint]]:
    """Parse 'amissl = 5.20', 'p96 >= 3.2, < 4.0', or bare 'bsdsocket'."""
    text = text.strip()
    parts = text.split(None, 1)
    if not parts:
        raise ValueError("empty package spec")
    name = parts[0]
    if not is_name(name):
        raise ValueError(
            f"bad package name {name!r}: names are lower-case slugs "
            f"([a-z0-9] plus interior '-')"
        )
    if len(parts) == 1:
        return name, []
    return name, parse_constraint(parts[1])
