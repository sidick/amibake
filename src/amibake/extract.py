"""Archive extraction into an in-memory Tree.

`.lha` via `lhafile` (pure Python — no external binary, unlike the
`lha`/lhasa CLI, which turned out to reject some legally-shaped level-0
headers in testing); `.zip` via the stdlib. Extracted paths keep their
archive-relative form (no Amiga volume prefix) — layer.py's `copy`
patterns match against these.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import lhafile

from .tree import Tree


class ExtractError(Exception):
    pass


def extract_archive(path: Path) -> Tree:
    suffix = path.suffix.lower()
    if suffix == ".lha":
        return _extract_lha(path)
    if suffix == ".zip":
        return _extract_zip(path)
    raise ExtractError(
        f"don't know how to extract {path.name!r} (supported: .lha, .zip)")


def _extract_lha(path: Path) -> Tree:
    tree = Tree()
    try:
        lf = lhafile.LhaFile(str(path))
        for info in lf.infolist():
            if info.filename.endswith("/"):
                continue
            tree.put(info.filename, lf.read(info.filename))
    except lhafile.BadLhafile as e:
        raise ExtractError(f"{path.name} is not a valid .lha archive: {e}") from e
    return tree


def _extract_zip(path: Path) -> Tree:
    tree = Tree()
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                tree.put(info.filename, zf.read(info))
    except zipfile.BadZipFile as e:
        raise ExtractError(f"{path.name} is not a valid zip archive: {e}") from e
    return tree
