"""Shared validation plumbing for manifest.py and recipe.py."""

from __future__ import annotations

import tomllib
from pathlib import Path

from .errors import AmiBakeError, Problem


def load_toml(path: Path) -> dict:
    """Read and parse a TOML file, aborting with a typed error on failure."""
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise AmiBakeError(
            Problem(str(path), "(file)", f"cannot read file: {e.strerror}",
                    "check the path exists and is readable")
        ) from e
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise AmiBakeError(
            Problem(str(path), "(file)", f"not valid TOML: {e}",
                    "fix the syntax error; remember version numbers must be "
                    'quoted strings ("5.20"), not bare numbers')
        ) from e


class Checker:
    """Collects Problems against one file with typed helper checks."""

    def __init__(self, file: str):
        self.file = file
        self.problems: list[Problem] = []

    def error(self, field: str, problem: str, remedy: str) -> None:
        self.problems.append(Problem(self.file, field, problem, remedy))

    def warning(self, field: str, problem: str, remedy: str) -> None:
        self.problems.append(Problem(self.file, field, problem, remedy, severity="warning"))

    def unknown_keys(self, table: dict, known: set[str], where: str) -> None:
        for key in table:
            if key not in known:
                self.error(
                    f"{where}.{key}" if where else key,
                    "unknown key",
                    f"remove it or fix the spelling; known keys here: "
                    f"{', '.join(sorted(known))}",
                )

    def typed(self, table: dict, key: str, typ: type, where: str,
              required: bool = False, default=None):
        """Fetch table[key], checking its type. Returns default if absent or
        wrong-typed (a Problem is recorded for wrong types / missing required)."""
        label = f"{where}.{key}" if where else key
        if key not in table:
            if required:
                self.error(label, "required key is missing", f"add {key!r}")
            return default
        value = table[key]
        ok = isinstance(value, typ)
        # bool is an int subclass; don't let `order = true` pass as integer.
        if typ is int and isinstance(value, bool):
            ok = False
        if not ok:
            self.error(label, f"must be a {_typename(typ)}, got {_typename(type(value))}",
                       f"change the value to a {_typename(typ)}")
            return default
        return value

    def string_list(self, table: dict, key: str, where: str) -> list[str]:
        value = self.typed(table, key, list, where, default=[])
        label = f"{where}.{key}" if where else key
        out = []
        for i, item in enumerate(value):
            if not isinstance(item, str):
                self.error(f"{label}[{i}]", f"must be a string, got {_typename(type(item))}",
                           "quote it — all AmiBake values in lists of names/paths are strings")
            else:
                out.append(item)
        return out


def _typename(typ: type) -> str:
    return {str: "string", bool: "boolean", int: "integer", list: "array",
            dict: "table", float: "float"}.get(typ, typ.__name__)
