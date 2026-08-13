"""Mapping from Tree paths (Amiga volume:path strings) to a physical
layout on the single system partition every M3 emitter writes.

Only one real partition exists in the output so far (multi-partition
output is a later milestone), so every Tree path collapses onto it.
Assigns that are conventionally physical directories on AmigaOS (ENVARC:
-> SYS:Prefs/Env-Archive/) are mapped explicitly; anything else is
treated as its own top-level directory under the system volume — a
provisional fallback, since only SYS: and ENVARC: are populated by any
recipe today (M0-M2). Revisit once a real base recipe (M4/M5) needs a
richer assign story.
"""

from __future__ import annotations

# volume prefix (upper-case) -> physical prefix on the system partition
_PHYSICAL_MAP = {
    "ENVARC": "Prefs/Env-Archive",
    "S": "S",
}

SYSTEM_VOLUME = "SYS"


def to_physical_path(amiga_path: str) -> str:
    """'SYS:Libs/foo' -> 'Libs/foo'; 'ENVARC:AmiSSL/x' -> 'Prefs/Env-Archive/AmiSSL/x'."""
    if ":" not in amiga_path:
        raise ValueError(f"not an absolute Amiga path (no volume prefix): {amiga_path!r}")
    volume, rest = amiga_path.split(":", 1)
    volume = volume.upper()
    if volume == SYSTEM_VOLUME:
        return rest
    physical_prefix = _PHYSICAL_MAP.get(volume)
    if physical_prefix is not None:
        return f"{physical_prefix}/{rest}" if rest else physical_prefix
    # Unmapped volume: fall back to a top-level directory named after it.
    return f"{volume}/{rest}" if rest else volume
