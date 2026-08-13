"""tgz (primary) and zip (convenience) archive outputs.

Both archive the same content the dir output would write — physical
paths plus `.uaem` sidecars — so all output formats come from one build
and agree byte-for-byte. tgz is primary because it carries raw bytes
honestly (Amiga names are Latin-1-ish; tar doesn't reinterpret them),
where zip's CP437-vs-UTF-8 filename flag history is a known mess. Both
are written deterministically: sorted entries, zeroed timestamps.
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

from amitools.fs.FSString import FSString
from amitools.fs.MetaInfo import MetaInfo
from amitools.fs.MetaInfoFSUAE import MetaInfoFSUAE
from amitools.fs.ProtectFlags import ProtectFlags
from amitools.fs.TimeStamp import TimeStamp

from ..paths import to_physical_path
from ..tree import AmigaMeta, Tree

_META = MetaInfoFSUAE()


def _entries(tree: Tree) -> list[tuple[str, bytes]]:
    """(archive member name, content) pairs, sorted, file + its .uaem
    sidecar adjacent — the same layout write_dirtree produces on disk."""
    tree = tree.materialize()
    out = []
    for amiga_path in tree.paths():
        file = tree.get(amiga_path)
        physical = to_physical_path(amiga_path)
        out.append((physical, file.data))
        out.append((physical + _META.get_suffix(), _uaem_bytes(file.meta)))
    return out


def _uaem_bytes(meta: AmigaMeta) -> bytes:
    days, mins, ticks = meta.datestamp
    info = MetaInfo(
        protect_flags=ProtectFlags(meta.protection),
        mod_ts=TimeStamp(days, mins, ticks),
        comment=FSString(meta.comment) if meta.comment else None,
    )
    return _META.generate_data(info).encode("utf-8")


def write_tgz(tree: Tree, path: Path) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, data in _entries(tree):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    path.write_bytes(_gzip(buf.getvalue()))


def _gzip(data: bytes) -> bytes:
    import gzip

    return gzip.compress(data, mtime=0)


def write_zip(tree: Tree, path: Path) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in _entries(tree):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zf.writestr(info, data)
