from amitools.fs.ADFSVolume import ADFSVolume
from amitools.fs.blkdev.BlkDevFactory import BlkDevFactory
from amitools.fs.FSString import FSString

from amibake.emit.dirtree import write_dirtree
from amibake.emit.hdf import write_hdf
from amibake.paths import to_physical_path
from amibake.tree import AmigaMeta, Tree


def _tree():
    t = Tree()
    t.put("SYS:Libs/foo.library", b"libdata", AmigaMeta(comment="a lib"))
    t.put("SYS:Libs/AmigaOS3/bar.library", b"nested")
    t.put("ENVARC:AmiSSL/opts", b"key=value\n")
    t.add_assign("amissl", "AmiSSL", "SYS:Devs/AmiSSL")
    return t


def _read_hdf(path):
    """Open a built HDF read-only and return {physical_path: data}."""
    factory = BlkDevFactory()
    blkdev = factory.open(str(path), read_only=True)
    vol = ADFSVolume(blkdev)
    vol.open()
    contents = {}

    def walk(node, prefix):
        for child in node.get_entries():
            name = child.get_file_name().get_unicode_name()
            path_ = f"{prefix}{name}"
            if child.is_dir():
                walk(child, path_ + "/")
            else:
                contents[path_] = child.get_file_data()

    walk(vol.get_root_dir(), "")
    vol.close()
    blkdev.close()
    return contents


def test_write_hdf_contents(tmp_path):
    out = tmp_path / "out.hdf"
    write_hdf(_tree(), out)
    contents = _read_hdf(out)
    assert contents["Libs/foo.library"] == b"libdata"
    assert contents["Libs/AmigaOS3/bar.library"] == b"nested"
    assert contents["Prefs/Env-Archive/AmiSSL/opts"] == b"key=value\n"
    assert "S/User-Startup" in contents  # materialized from the assign


def test_write_hdf_metadata_round_trips(tmp_path):
    out = tmp_path / "out.hdf"
    write_hdf(_tree(), out)
    factory = BlkDevFactory()
    blkdev = factory.open(str(out), read_only=True)
    vol = ADFSVolume(blkdev)
    vol.open()
    node = vol.get_file_path_name(FSString("Libs/foo.library"))
    info = node.get_meta_info()
    assert info.get_comment().get_unicode() == "a lib"
    vol.close()
    blkdev.close()


def test_hdf_and_dir_outputs_agree(tmp_path):
    """M3 exit criterion: hdf contents == dir contents, from one build."""
    tree = _tree()
    hdf_path = tmp_path / "out.hdf"
    dir_path = tmp_path / "out"
    write_hdf(tree, hdf_path)
    write_dirtree(tree, dir_path)

    hdf_contents = _read_hdf(hdf_path)
    dir_files = {
        str(p.relative_to(dir_path)): p.read_bytes()
        for p in dir_path.rglob("*")
        if p.is_file() and not p.name.endswith(".uaem")
    }
    assert hdf_contents == dir_files


def test_write_hdf_is_deterministic(tmp_path):
    out_a = tmp_path / "a.hdf"
    out_b = tmp_path / "b.hdf"
    write_hdf(_tree(), out_a)
    write_hdf(_tree(), out_b)
    assert out_a.read_bytes() == out_b.read_bytes()


def test_write_hdf_is_deterministic_across_a_wall_clock_boundary(tmp_path):
    """Regression test for a real bug: amitools' ADFSDir._create_node
    defaults update_ts=True, which stamps the *parent* directory's own
    mod_ts to wall-clock "now" on every child added, independent of any
    meta_info passed for the child — invisible with a tiny fixture tree
    built in microseconds (both calls likely land in the same 1/50s
    tick), so this test forces a real delay to make a regression here
    fail reliably rather than flakily."""
    import time

    out_a = tmp_path / "a.hdf"
    out_b = tmp_path / "b.hdf"
    write_hdf(_tree(), out_a)
    time.sleep(0.1)
    write_hdf(_tree(), out_b)
    assert out_a.read_bytes() == out_b.read_bytes()


def test_to_physical_path_matches_hdf_layout():
    assert to_physical_path("SYS:Libs/foo.library") == "Libs/foo.library"
    assert to_physical_path("ENVARC:AmiSSL/opts") == "Prefs/Env-Archive/AmiSSL/opts"
