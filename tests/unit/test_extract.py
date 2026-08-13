import zipfile

import pytest

from amibake.extract import ExtractError, extract_archive

from .conftest import make_lha_archive


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
