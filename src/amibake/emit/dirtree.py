"""dir output: a host filesystem tree plus `.uaem` sidecar files carrying
the Amiga metadata a host FS can't (protection bits, comment, datestamp)
— the format UAE-family directory hard drives read natively.

The `.uaem` format itself is amitools' own (amitools.fs.MetaInfoFSUAE),
reused directly rather than reimplemented, so output is byte-compatible
with whatever amitools/UAE itself would produce. Host-FS hazards
(Windows-reserved names, trailing dots/spaces, filename encoding) are
NOT handled here — per the recipe contract, dir output is documented as
best-effort; tgz is the faithful record.
"""

from __future__ import annotations

from pathlib import Path

from amitools.fs.FSString import FSString
from amitools.fs.MetaInfo import MetaInfo
from amitools.fs.MetaInfoFSUAE import MetaInfoFSUAE
from amitools.fs.ProtectFlags import ProtectFlags
from amitools.fs.TimeStamp import TimeStamp

from ..paths import to_physical_path
from ..tree import AmigaMeta, Tree

_META = MetaInfoFSUAE()


def write_dirtree(tree: Tree, output_dir: Path) -> None:
    tree = tree.materialize()
    output_dir.mkdir(parents=True, exist_ok=True)
    for amiga_path in tree.paths():
        file = tree.get(amiga_path)
        host_path = output_dir / to_physical_path(amiga_path)
        host_path.parent.mkdir(parents=True, exist_ok=True)
        host_path.write_bytes(file.data)
        _META.save_meta(str(host_path) + _META.get_suffix(), _to_meta_info(file.meta))


def _to_meta_info(meta: AmigaMeta) -> MetaInfo:
    days, mins, ticks = meta.datestamp
    mod_ts = TimeStamp(days, mins, ticks)
    comment = FSString(meta.comment) if meta.comment else None
    return MetaInfo(protect_flags=ProtectFlags(meta.protection), mod_ts=mod_ts, comment=comment)
