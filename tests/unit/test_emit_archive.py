import gzip
import tarfile
import zipfile

from amibake.emit.archive import write_tgz, write_zip
from amibake.tree import AmigaMeta, Tree


def _tree():
    t = Tree()
    t.put("SYS:Libs/foo.library", b"libdata", AmigaMeta(comment="a lib"))
    t.put("ENVARC:AmiSSL/opts", b"key=value\n")
    return t


def test_write_tgz_contents(tmp_path):
    out = tmp_path / "out.tgz"
    write_tgz(_tree(), out)
    with tarfile.open(out, "r:gz") as tar:
        names = sorted(tar.getnames())
        assert "Libs/foo.library" in names
        assert "Libs/foo.library.uaem" in names
        assert tar.extractfile("Libs/foo.library").read() == b"libdata"


def test_write_tgz_is_byte_deterministic(tmp_path):
    out_a = tmp_path / "a.tgz"
    out_b = tmp_path / "b.tgz"
    write_tgz(_tree(), out_a)
    write_tgz(_tree(), out_b)
    assert out_a.read_bytes() == out_b.read_bytes()


def test_write_tgz_gzip_member_has_zero_mtime(tmp_path):
    out = tmp_path / "out.tgz"
    write_tgz(_tree(), out)
    with gzip.GzipFile(out) as gz:
        gz.read()
        assert gz.mtime == 0


def test_write_zip_contents(tmp_path):
    out = tmp_path / "out.zip"
    write_zip(_tree(), out)
    with zipfile.ZipFile(out) as zf:
        names = sorted(zf.namelist())
        assert "Libs/foo.library" in names
        assert "Libs/foo.library.uaem" in names
        assert zf.read("Libs/foo.library") == b"libdata"


def test_write_zip_is_byte_deterministic(tmp_path):
    out_a = tmp_path / "a.zip"
    out_b = tmp_path / "b.zip"
    write_zip(_tree(), out_a)
    write_zip(_tree(), out_b)
    assert out_a.read_bytes() == out_b.read_bytes()
