import zipfile

import pytest

from amibake.extract import ExtractError, extract_archive

from .conftest import make_iso, make_lha_archive


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
