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


def test_write_hdf_default_dos_type_rejects_long_filenames(tmp_path):
    t = Tree()
    t.put("SYS:Fonts/Dustismo Roman Bold Italic.font", b"fontdata")
    out = tmp_path / "out.hdf"
    import amitools.fs.FSError

    try:
        write_hdf(t, out)
    except amitools.fs.FSError.FSError:
        pass
    else:
        raise AssertionError("expected the default ffs-intl (no longname) to reject this name")


def test_write_hdf_longname_dos_type_allows_long_filenames(tmp_path):
    t = Tree()
    t.put("SYS:Fonts/Dustismo Roman Bold Italic.font", b"fontdata")
    out = tmp_path / "out.hdf"
    write_hdf(t, out, dos_type="ffs-intl-longname")
    contents = _read_hdf(out)
    assert contents["Fonts/Dustismo Roman Bold Italic.font"] == b"fontdata"


def test_write_hdf_scratch_partition(tmp_path):
    from amitools.fs.blkdev.RawBlockDevice import RawBlockDevice
    from amitools.fs.block.rdb.PartitionBlock import PartitionBlock
    from amitools.fs.rdb.RDisk import RDisk

    out = tmp_path / "out.hdf"
    scratch = 2 * 1024 * 1024
    write_hdf(_tree(), out, scratch=scratch)

    # open the RDB directly (not through BlkDevFactory's partition
    # auto-open) so both partitions are visible
    raw = RawBlockDevice(str(out), read_only=True)
    raw.open()
    rdisk = RDisk(raw)
    assert rdisk.open()
    try:
        parts = [rdisk.get_partition(i) for i in range(rdisk.get_num_partitions())]
        assert [p.get_drive_name().get_unicode() for p in parts] == ["DH0", "DH1"]
        sys_part, scratch_part = parts
        assert sys_part.get_flags() & PartitionBlock.FLAG_BOOTABLE
        assert not scratch_part.get_flags() & PartitionBlock.FLAG_BOOTABLE
        assert not scratch_part.get_flags() & PartitionBlock.FLAG_NO_AUTOMOUNT
        # at least the requested bytes, contiguous to the end of the disk
        assert scratch_part.get_num_bytes() >= scratch
        # the scratch region is genuinely unformatted: no filesystem was
        # created there, so its first block carries no DOS signature
        blkdev = scratch_part.create_blkdev()
        blkdev.open()
        try:
            assert blkdev.read_block(0)[0:3] != b"DOS"
        finally:
            blkdev.close()
    finally:
        rdisk.close()
        raw.close()
    # ...and the system volume is still intact alongside it
    assert _read_hdf(out)["Libs/foo.library"] == b"libdata"


def test_write_hdf_scratch_is_deterministic(tmp_path):
    out_a = tmp_path / "a.hdf"
    out_b = tmp_path / "b.hdf"
    write_hdf(_tree(), out_a, scratch=1024 * 1024)
    write_hdf(_tree(), out_b, scratch=1024 * 1024)
    assert out_a.read_bytes() == out_b.read_bytes()


def test_write_hdf_explicit_size(tmp_path):
    out = tmp_path / "out.hdf"
    write_hdf(_tree(), out, size=16 * 1024 * 1024)
    # amitools derives a geometry fitting within the requested size
    assert 15 * 1024 * 1024 < out.stat().st_size <= 16 * 1024 * 1024


def test_write_hdf_scratch_larger_than_size_is_a_named_error(tmp_path):
    from amibake.emit.hdf import EmitError

    out = tmp_path / "out.hdf"
    try:
        write_hdf(_tree(), out, size=4 * 1024 * 1024, scratch=8 * 1024 * 1024)
    except EmitError as e:
        assert "[hdf].scratch" in str(e)
    else:
        raise AssertionError("expected EmitError for scratch > size")


def test_write_hdf_content_overflowing_explicit_size_is_a_named_error(tmp_path):
    from amibake.emit.hdf import EmitError

    t = Tree()
    t.put("SYS:big", b"\x5a" * (3 * 1024 * 1024))
    out = tmp_path / "out.hdf"
    try:
        write_hdf(t, out, size=4 * 1024 * 1024, scratch=3 * 1024 * 1024)
    except EmitError as e:
        assert "[hdf].size" in str(e)
    else:
        raise AssertionError("expected EmitError for content not fitting")


def test_to_physical_path_matches_hdf_layout():
    assert to_physical_path("SYS:Libs/foo.library") == "Libs/foo.library"
    assert to_physical_path("ENVARC:AmiSSL/opts") == "Prefs/Env-Archive/AmiSSL/opts"
