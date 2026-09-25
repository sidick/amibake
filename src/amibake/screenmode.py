"""Applies a manifest's `[screenmode]` to a built Tree: the startup
screen mode Workbench opens on, expressed the way the OS itself stores
it — an `ENVARC:Sys/screenmode.prefs` IFF PREF file (PRHD + SCRM, per
NDK 3.2 `prefs/screenmode.h`/`prefs/prefhdr.h`) that IPrefs reads at
boot. No patching, no third-party tools: the same file ScreenMode
Preferences' own Save button writes.

The interesting half is naming an RTG mode without magic numbers. A
`ScreenModePrefs.smp_DisplayID` is a 32-bit mode ID; for a Picasso96
board those IDs are assigned from the board's settings file — a
`FORM P96S` IFF (Picasso96Mode's own format) whose per-resolution RSHD
chunks each carry the DisplayID, dimensions, and the display name
ScreenMode Preferences shows ("Z3660:1024x384"). Grounded against the
real `p96-z3660-hdmi` file shipped on the Z3660 drivers disk (parsed,
and its 1024x384 entry cross-checked against what the booted guest's
ScreenMode Preferences lists), not against P96 source. So a manifest
says `screenmode = { name = "Z3660:1024x384", depth = 8 }` and the
builder resolves the ID from whatever P96 settings file the layers
installed — the name is exactly the string the guest's own screen-mode
requester displays. Native Amiga modes (or anything else) take the
escape hatch: an explicit `id` with `width`/`height` stated.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .tree import Tree

SCREENMODE_PREFS_PATH = "ENVARC:Sys/screenmode.prefs"

# RSHD chunk layout, from the real file (offsets verified against every
# entry in p96-z3660-hdmi): ULONG DisplayID, UWORD Width, UWORD Height,
# then 6 bytes this writer never needs, then the NUL-terminated display
# name padded to the chunk end.
_RSHD_NAME_OFFSET = 14


class ScreenModeError(Exception):
    pass


@dataclass(frozen=True)
class P96Mode:
    display_id: int
    width: int
    height: int
    name: str
    settings_path: str  # tree path of the settings file that declares it


def parse_p96_settings(data: bytes, settings_path: str) -> list[P96Mode]:
    """The resolutions a `FORM P96S` settings file declares, in file
    order. Raises ScreenModeError on anything that isn't such a file or
    is too truncated to walk."""
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] != b"P96S":
        raise ScreenModeError(f"{settings_path}: not a Picasso96 settings file "
                              "(expected IFF FORM P96S)")
    modes: list[P96Mode] = []
    off = 12
    while off + 8 <= len(data):
        chunk_id = data[off:off + 4]
        (size,) = struct.unpack_from(">I", data, off + 4)
        body = data[off + 8:off + 8 + size]
        if len(body) < size:
            raise ScreenModeError(f"{settings_path}: truncated {chunk_id!r} chunk")
        if chunk_id == b"RSHD":
            if size < _RSHD_NAME_OFFSET + 1:
                raise ScreenModeError(f"{settings_path}: RSHD chunk too short "
                                      f"({size} bytes)")
            display_id, width, height = struct.unpack_from(">IHH", body, 0)
            name = body[_RSHD_NAME_OFFSET:].split(b"\0", 1)[0].decode("latin-1")
            modes.append(P96Mode(display_id, width, height, name, settings_path))
        off += 8 + size + (size & 1)
    return modes


def tree_p96_modes(tree: Tree) -> list[P96Mode]:
    """Every resolution declared by every P96 settings file in the tree,
    found by content (the FORM P96S signature), not by name — a settings
    file's name is whatever the board vendor chose (`p96-z3660-hdmi`,
    `Picasso96Settings`, ...)."""
    modes: list[P96Mode] = []
    for path in tree.paths():
        data = tree.get(path).data
        if len(data) >= 12 and data[:4] == b"FORM" and data[8:12] == b"P96S":
            modes.extend(parse_p96_settings(data, path))
    return modes


def build_screenmode_prefs(display_id: int, width: int, height: int,
                           depth: int, autoscroll: bool = True) -> bytes:
    """A complete `screenmode.prefs` file: FORM PREF holding a PRHD
    (version 0, type 0, flags 0 — what ScreenMode Preferences itself
    writes) and one SCRM chunk (struct ScreenModePrefs). Both chunk
    sizes are even, so no pad bytes arise."""
    prhd = struct.pack(">BBI", 0, 0, 0)
    scrm = struct.pack(">4I I HHHH", 0, 0, 0, 0, display_id, width, height,
                       depth, 1 if autoscroll else 0)
    body = b"PREF" + b"PRHD" + struct.pack(">I", len(prhd)) + prhd \
        + b"SCRM" + struct.pack(">I", len(scrm)) + scrm
    return b"FORM" + struct.pack(">I", len(body)) + body


def apply_screenmode(tree: Tree, screenmode: dict | None) -> Tree:
    """A clone of `tree` with the manifest's `screenmode` written as
    `ENVARC:Sys/screenmode.prefs`; `tree` itself is never mutated (same
    contract as layer.apply_layer). No-op when the manifest has none.

    `screenmode` is the manifest's validated table: either `name` (a P96
    display name, resolved against the settings files the layers
    installed) or `id` + `width` + `height`, plus `depth` and optional
    `autoscroll`."""
    if not screenmode:
        return tree

    name = screenmode.get("name")
    if name is not None:
        modes = tree_p96_modes(tree)
        matches = [m for m in modes if m.name.lower() == name.lower()]
        if not matches:
            available = ", ".join(sorted(m.name for m in modes)) or "(none)"
            raise ScreenModeError(
                f"screenmode.name {name!r} matches no mode declared by any "
                f"Picasso96 settings file in the build — available: {available}. "
                f"Install a package that ships the mode, fix the spelling, or "
                f"state an explicit id/width/height instead")
        if len(matches) > 1:
            where = ", ".join(sorted({m.settings_path for m in matches}))
            raise ScreenModeError(
                f"screenmode.name {name!r} is declared by more than one "
                f"settings file ({where}) — state an explicit id/width/height "
                f"to disambiguate")
        mode = matches[0]
        display_id, width, height = mode.display_id, mode.width, mode.height
    else:
        display_id = screenmode["id"]
        width = screenmode["width"]
        height = screenmode["height"]

    tree = tree.clone()
    tree.put(SCREENMODE_PREFS_PATH,
             build_screenmode_prefs(display_id, width, height,
                                    screenmode["depth"],
                                    screenmode.get("autoscroll", True)))
    return tree
