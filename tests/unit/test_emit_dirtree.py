from amitools.fs.MetaInfoFSUAE import MetaInfoFSUAE

from amibake.emit.dirtree import write_dirtree
from amibake.tree import AmigaMeta, Tree


def _tree():
    t = Tree()
    t.put("SYS:Libs/foo.library", b"libdata", AmigaMeta(comment="a lib"))
    t.put("ENVARC:AmiSSL/opts", b"key=value\n")
    t.add_assign("amissl", "AmiSSL", "SYS:Devs/AmiSSL")
    t.add_user_startup(50, "amissl", ["Run Foo"])
    return t


def test_write_dirtree_layout(tmp_path):
    out = tmp_path / "out"
    write_dirtree(_tree(), out)
    assert (out / "Libs" / "foo.library").read_bytes() == b"libdata"
    assert (out / "Prefs" / "Env-Archive" / "AmiSSL" / "opts").read_bytes() == b"key=value\n"
    assert (out / "S" / "User-Startup").is_file()


def test_write_dirtree_uaem_sidecars(tmp_path):
    out = tmp_path / "out"
    write_dirtree(_tree(), out)
    sidecar = out / "Libs" / "foo.library.uaem"
    assert sidecar.is_file()
    info = MetaInfoFSUAE().load_meta(str(sidecar))
    assert info.get_comment().get_unicode() == "a lib"


def test_write_dirtree_is_deterministic(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    write_dirtree(_tree(), out_a)
    write_dirtree(_tree(), out_b)
    files_a = sorted(p.relative_to(out_a) for p in out_a.rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(out_b) for p in out_b.rglob("*") if p.is_file())
    assert files_a == files_b
    for rel in files_a:
        assert (out_a / rel).read_bytes() == (out_b / rel).read_bytes()
