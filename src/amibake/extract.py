"""Archive extraction into an in-memory Tree.

`.lha` via `lhafile` (pure Python — no external binary, unlike the
`lha`/lhasa CLI, which turned out to reject some legally-shaped level-0
headers in testing); `.zip` via the stdlib; `.iso` (ISO9660, with Rock
Ridge extensions when present — real install/nightly media almost
always carries them) via `pycdlib`, another pure-Python dependency, no
external binary; `.adf` (a raw Amiga floppy disk image — OFS or FFS, the
`[source.assets]` format for pre-2.0 boot media like Workbench 1.3) via
`amitools`, the same dependency already used by the `hdf` emitter.
Extracted paths keep their archive-relative form (no Amiga volume
prefix) — layer.py's `copy` patterns match against these.

A `.zip`/`.lha` containing a nested `.iso` member (how AROS's nightly
builds are packaged, and likely how real OS install CDs will be too) is
transparently expanded: the `.iso` entry is replaced by its own
extracted file tree, merged into the result. This is a fixed, always-
applied rule, not size/count-based guessing.
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import lhafile
import pycdlib
from amitools.fs.ADFSVolume import ADFSVolume
from amitools.fs.blkdev.ADFBlockDevice import ADFBlockDevice
from amitools.fs.FSError import FSError

from .tree import AmigaMeta, Tree


class ExtractError(Exception):
    pass


def extract_archive(path: Path) -> Tree:
    suffix = path.suffix.lower()
    if suffix == ".lha":
        tree = _extract_lha(path)
    elif suffix == ".zip":
        tree = _extract_zip(path)
    elif suffix == ".iso":
        return _extract_iso(path)
    elif suffix == ".adf":
        return _extract_adf(path)
    else:
        raise ExtractError(
            f"don't know how to extract {path.name!r} (supported: .lha, .zip, .iso, .adf)")
    return _expand_nested_adfs(_expand_nested_isos(tree))


def _expand_nested_isos(tree: Tree) -> Tree:
    iso_members = [p for p in tree.paths() if p.lower().endswith(".iso")]
    if not iso_members:
        return tree
    merged = Tree()
    for path in tree.paths():
        if path in iso_members:
            continue
        f = tree.get(path)
        merged.put(path, f.data, f.meta)
    for iso_path in iso_members:
        with tempfile.NamedTemporaryFile(suffix=".iso") as tmp:
            tmp.write(tree.get(iso_path).data)
            tmp.flush()
            inner = _extract_iso(Path(tmp.name))
        for p in inner.paths():
            f = inner.get(p)
            merged.put(p, f.data, f.meta)
    return merged


def _expand_nested_adfs(tree: Tree) -> Tree:
    """Unlike `_expand_nested_isos` (built for AROS's single-nested-ISO
    nightly zip, safe to merge flat since there's only ever one), a real
    multi-disk OS install (e.g. AmigaOS 3.1.4's 7-.adf Hyperion zip) has
    *several* nested `.adf` disks that often share root-level filenames
    (every disk has its own `Disk.info`, etc.) — merging those flat would
    silently collide and drop files. Each expanded disk's paths are kept
    under a `<member-filename>/` prefix instead, so `[install].copy`
    patterns can address one disk unambiguously, e.g. `Workbench3_1_4.adf/
    C/Dir`."""
    adf_members = [p for p in tree.paths() if p.lower().endswith(".adf")]
    if not adf_members:
        return tree
    merged = Tree()
    for path in tree.paths():
        if path in adf_members:
            continue
        f = tree.get(path)
        merged.put(path, f.data, f.meta)
    for adf_path in adf_members:
        with tempfile.NamedTemporaryFile(suffix=".adf") as tmp:
            tmp.write(tree.get(adf_path).data)
            tmp.flush()
            inner = _extract_adf(Path(tmp.name))
        prefix = adf_path.rsplit("/", 1)[-1]
        for p in inner.paths():
            f = inner.get(p)
            merged.put(f"{prefix}/{p}", f.data, f.meta)
    return merged


def _extract_lha(path: Path) -> Tree:
    tree = Tree()
    try:
        lf = lhafile.LhaFile(str(path))
        for info in lf.infolist():
            if info.filename.endswith("/") or info.filename.endswith("\\"):
                continue
            # Some .lha archives (DOS-era archiving tools) store paths
            # with '\' separators instead of '/' — normalize so [install]
            # copy patterns (which assume '/') match either kind.
            name = info.filename.replace("\\", "/")
            tree.put(name, lf.read(info.filename))
    except lhafile.BadLhafile as e:
        raise ExtractError(f"{path.name} is not a valid .lha archive: {e}") from e
    return tree


def _extract_iso(path: Path) -> Tree:
    tree = Tree()
    iso = pycdlib.PyCdlib()
    try:
        iso.open(str(path))
    except Exception as e:
        raise ExtractError(f"{path.name} is not a valid ISO9660 image: {e}") from e
    try:
        # encoding="latin-1" (not pycdlib's UTF-8 default): a real 1990s/
        # 2000s-mastered Amiga CD (AmigaOS 3.2's own install CD, no Rock
        # Ridge or Joliet at all, confirmed against the real archive) can
        # have raw 8-bit filename bytes that aren't valid UTF-8 at all —
        # walk() would otherwise raise UnicodeDecodeError outright, not on
        # some obscure file, on the very first non-ASCII byte anywhere on
        # the disc. latin-1 never raises (every byte 0-255 maps to a
        # character), matching the encoding this project already uses
        # throughout for Amiga text (tree.py's render_user_startup, etc).
        has_rr = iso.has_rock_ridge()
        walk = iso.walk(rr_path="/", encoding="latin-1") if has_rr \
            else iso.walk(iso_path="/", encoding="latin-1")
        for dirpath, _dirnames, filenames in walk:
            for name in filenames:
                full = f"{dirpath}/{name}" if dirpath != "/" else f"/{name}"
                buf = io.BytesIO()
                try:
                    if has_rr:
                        iso.get_file_from_iso_fp(buf, rr_path=full)
                    else:
                        iso.get_file_from_iso_fp(buf, iso_path=full)
                except Exception:
                    # get_file_from_iso_fp has no encoding param of its
                    # own and re-resolves the path with pycdlib's UTF-8
                    # default internally, so a handful of real legacy
                    # 8-bit-charset filenames (accented characters from a
                    # non-Latin-1-compatible original encoding — real,
                    # confirmed against the same real disc, all in a
                    # cosmetic icon-theme bonus directory) fail lookup
                    # even though walk() enumerated them fine. Skipped
                    # rather than failing the whole extraction over an
                    # unrelated file a recipe was never going to copy
                    # anyway.
                    continue
                tree.put(full.lstrip("/"), buf.getvalue())
    finally:
        iso.close()
    return tree


def _extract_adf(path: Path) -> Tree:
    tree = Tree()
    blkdev = ADFBlockDevice(str(path), read_only=True)
    try:
        blkdev.open()
    except OSError as e:
        raise ExtractError(f"{path.name} is not a valid ADF image: {e}") from e
    volume = ADFSVolume(blkdev)
    try:
        volume.open()
    except FSError as e:
        raise ExtractError(f"{path.name} is not a valid Amiga filesystem: {e}") from e
    try:
        volume.root_dir.read(recursive=True)
        _walk_adf_dir(volume.root_dir, "", tree)
    finally:
        blkdev.close()
    return tree


def _walk_adf_dir(node, prefix: str, tree: Tree) -> None:
    for entry in node.get_entries():
        name = entry.get_file_name().get_unicode_name()
        rel = f"{prefix}{name}"
        if entry.is_dir():
            _walk_adf_dir(entry, f"{rel}/", tree)
        else:
            # Real protection bits (e.g. the "pure" flag real Startup-
            # Sequence/StartupII `resident ... pure` lines expect on
            # resident-safe binaries) live on the ADF's own directory
            # entry, not in the file data — amitools populates
            # meta_info.protect from the same raw block field its own
            # emit-side ProtectFlags(...) round-trips, so this is a
            # straight passthrough, not a re-derivation. Found by
            # booting a real extracted disk under Copperline and seeing
            # spurious "Pure bit not set" warnings that don't happen on
            # real hardware.
            protect = entry.get_meta_info().protect or 0
            tree.put(rel, bytes(entry.get_file_data()), AmigaMeta(protection=protect))


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
