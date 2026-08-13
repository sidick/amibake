import io
import zipfile

import pycdlib
import pytest

from amibake.extract import ExtractError, extract_archive

from .conftest import make_adf, make_iso, make_lha_archive


def test_extract_lha(tmp_path):
    archive = tmp_path / "test.lha"
    archive.write_bytes(make_lha_archive({
        "foo.txt": b"hello world\n",
        "sub/bar.txt": b"nested\n",
    }))
    tree = extract_archive(archive)
    assert set(tree.paths()) == {"foo.txt", "sub/bar.txt"}
    assert tree.get("foo.txt").data == b"hello world\n"
    assert tree.get("sub/bar.txt").data == b"nested\n"


def test_extract_lha_normalizes_backslash_separators(tmp_path):
    """Some .lha archives (DOS-era archiving tools — a real one found in
    ClassAct 3.3) store paths with '\\' instead of '/'; [install].copy
    patterns assume '/', so extraction must normalize."""
    archive = tmp_path / "test.lha"
    archive.write_bytes(make_lha_archive({
        "Classes\\arexx.class": b"data",
        "Classes\\gadgets\\layout.gadget": b"gadget",
    }))
    tree = extract_archive(archive)
    assert set(tree.paths()) == {"Classes/arexx.class", "Classes/gadgets/layout.gadget"}
    assert tree.get("Classes/gadgets/layout.gadget").data == b"gadget"


def test_extract_lha_rejects_corrupt_archive(tmp_path):
    archive = tmp_path / "bad.lha"
    archive.write_bytes(b"not an lha archive at all")
    with pytest.raises(ExtractError, match="not a valid"):
        extract_archive(archive)


def test_extract_zip(tmp_path):
    archive = tmp_path / "test.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("foo.txt", "hello world\n")
        zf.writestr("sub/bar.txt", "nested\n")
        zf.writestr("sub/", "")  # explicit directory entry, should be skipped
    tree = extract_archive(archive)
    assert set(tree.paths()) == {"foo.txt", "sub/bar.txt"}


def test_extract_zip_rejects_corrupt_archive(tmp_path):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(b"not a zip archive at all")
    with pytest.raises(ExtractError, match="not a valid"):
        extract_archive(archive)


def test_extract_unknown_suffix(tmp_path):
    archive = tmp_path / "test.rar"
    archive.write_bytes(b"whatever")
    with pytest.raises(ExtractError, match="don't know how to extract"):
        extract_archive(archive)


def test_extract_adf(tmp_path):
    archive = tmp_path / "test.adf"
    archive.write_bytes(make_adf({"C/Dir": b"dir-binary", "S/Startup-Sequence": b"lines"}))
    tree = extract_archive(archive)
    assert tree.get("C/Dir").data == b"dir-binary"
    assert tree.get("S/Startup-Sequence").data == b"lines"


def test_extract_adf_preserves_real_protection_bits(tmp_path):
    """Real bug, found by booting a real extracted disk under
    Copperline: extract.py wasn't reading each file's real ADF
    protection bits at all (every extracted file silently got
    AmigaMeta()'s default, protection=0), so real 1.3 media's own
    `resident ... pure`-eligible binaries lost their real PURE bit and
    Copperline correctly warned "Pure bit not set" at boot — a warning
    that doesn't happen on real hardware with the real disk."""
    from amitools.fs.ProtectFlags import ProtectFlags

    archive = tmp_path / "test.adf"
    archive.write_bytes(make_adf(
        {"C/Execute": b"binary", "S/Startup-Sequence": b"script"},
        protection={"C/Execute": ProtectFlags.FIBF_PURE,
                    "S/Startup-Sequence": ProtectFlags.FIBF_SCRIPT},
    ))
    tree = extract_archive(archive)
    assert tree.get("C/Execute").meta.protection == ProtectFlags.FIBF_PURE
    assert tree.get("S/Startup-Sequence").meta.protection == ProtectFlags.FIBF_SCRIPT


def test_extract_iso(tmp_path):
    archive = tmp_path / "test.iso"
    archive.write_bytes(make_iso({
        "foo.txt": b"hello world\n",
        "sub/bar.txt": b"nested\n",
        "sub/deep/baz.txt": b"deeper\n",
    }))
    tree = extract_archive(archive)
    assert set(tree.paths()) == {"foo.txt", "sub/bar.txt", "sub/deep/baz.txt"}
    assert tree.get("foo.txt").data == b"hello world\n"
    assert tree.get("sub/deep/baz.txt").data == b"deeper\n"


def _make_plain_iso9660(files: dict[str, bytes]) -> bytes:
    """A real, no-Rock-Ridge ISO9660 image — the format a real 1990s/
    2000s-mastered Amiga CD (e.g. AmigaOS 3.2's own install CD) actually
    uses. Unlike `make_iso` (always Rock Ridge, whose names come back
    clean of ISO9660's own ";<version>" path-table decoration), this
    exercises the plain-ISO9660 code path where that decoration is real
    and, until fixed, leaked straight into extracted tree paths."""
    iso = pycdlib.PyCdlib()
    iso.new()
    for name, data in files.items():
        iso_name = f"/{name.upper()};1"
        iso.add_fp(io.BytesIO(data), len(data), iso_name)
    buf = io.BytesIO()
    iso.write_fp(buf)
    iso.close()
    return buf.getvalue()


def test_extract_plain_iso9660_strips_version_suffix(tmp_path):
    """Real bug: plain ISO9660 (no Rock Ridge) names carry a
    ";<version>" suffix in their path-table entry — previously never
    stripped, so every extracted path from a disc like this silently
    ended in ";1". [install].copy's `#?` wildcard still matched (it
    matches ";1" too), masking the bug in patterns, but the actual
    destination would land as e.g. "SYS:C/Dir;1" — wrong, and
    unrunnable. Found exploring the real AmigaOS 3.2 install CD."""
    archive = tmp_path / "plain.iso"
    archive.write_bytes(_make_plain_iso9660({"foo.txt": b"hello\n"}))
    tree = extract_archive(archive)
    assert set(tree.paths()) == {"FOO.TXT"}
    assert tree.get("FOO.TXT").data == b"hello\n"


def test_extract_iso_rejects_corrupt_archive(tmp_path):
    archive = tmp_path / "bad.iso"
    archive.write_bytes(b"not an iso image at all")
    with pytest.raises(ExtractError, match="not a valid"):
        extract_archive(archive)


def test_extract_nested_iso_inside_zip(tmp_path):
    """The AROS-nightly packaging shape: a .zip wrapping one .iso member,
    transparently expanded so [install].copy patterns match the ISO's own
    internal paths without the recipe needing to know about the wrapper."""
    iso_bytes = make_iso({"boot/rom.bin": b"romdata", "readme.txt": b"hi\n"})
    archive = tmp_path / "wrapped.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("nightly/system.iso", iso_bytes)
        zf.writestr("nightly/LICENSE", "license text\n")
    tree = extract_archive(archive)
    assert set(tree.paths()) == {"nightly/LICENSE", "boot/rom.bin", "readme.txt"}
    assert tree.get("boot/rom.bin").data == b"romdata"
    assert not any(p.lower().endswith(".iso") for p in tree.paths())


def test_extract_nested_adfs_inside_zip_are_prefixed_by_member_name(tmp_path):
    """A real multi-disk OS install (e.g. AmigaOS 3.1.4's Hyperion zip)
    wraps several .adf disks that often share root-level filenames —
    unlike the single-nested-ISO case, these must NOT merge flat or
    same-named files from different disks would collide and silently
    drop. Each expanded disk's paths land under its own
    <member-filename>/ prefix instead."""
    adf_a = make_adf({"Disk.info": b"disk-a-icon", "C/Dir": b"a-dir-binary"})
    adf_b = make_adf({"Disk.info": b"disk-b-icon", "C/List": b"b-list-binary"})
    archive = tmp_path / "wrapped.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("A.adf", adf_a)
        zf.writestr("B.adf", adf_b)
    tree = extract_archive(archive)
    assert set(tree.paths()) == {
        "A.adf/Disk.info", "A.adf/C/Dir", "B.adf/Disk.info", "B.adf/C/List",
    }
    assert tree.get("A.adf/Disk.info").data == b"disk-a-icon"
    assert tree.get("B.adf/Disk.info").data == b"disk-b-icon"
    assert not any(p.lower().endswith(".adf") for p in tree.paths())
