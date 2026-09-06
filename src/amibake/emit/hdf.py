"""hdf output: an RDB-partitioned HDF image, populated via amitools —
the fidelity-target output format (bytes and metadata a real Amiga
filesystem driver reads natively, not a host directory approximation).

One system partition, plus optionally one *unformatted* scratch
partition at the end of the disk (the manifest's `[hdf].scratch` — an
RDB entry with no filesystem, giving destructive block-device tests
like devsoak a safe, mountable-by-name target). Fuller multi-partition
layouts are a later milestone.
Filesystem defaults to FFS international (AmigaOS 2.0+); a base recipe
needing OFS (pre-2.0, e.g. Kickstart 1.3) passes dos_type explicitly —
see PLAN.md's M2/M3 notes on why this can't be inferred from the tree
alone.
"""

from __future__ import annotations

from pathlib import Path

import amitools.fs.DosType as DosType
from amitools.fs.ADFSVolume import ADFSVolume
from amitools.fs.blkdev.BlkDevFactory import BlkDevFactory
from amitools.fs.blkdev.HDFBlockDevice import HDFBlockDevice
from amitools.fs.block.rdb.PartitionBlock import PartitionBlock
from amitools.fs.FSError import NO_FREE_BLOCKS, FSError
from amitools.fs.FSString import FSString
from amitools.fs.MetaInfo import MetaInfo
from amitools.fs.ProtectFlags import ProtectFlags
from amitools.fs.rdb.RDisk import RDisk
from amitools.fs.RootMetaInfo import RootMetaInfo
from amitools.fs.TimeStamp import TimeStamp

from ..paths import to_physical_path
from ..tree import AmigaMeta, Tree

# amitools defaults the volume root's and every directory's timestamps to
# the current wall-clock time unless a MetaInfo is passed explicitly —
# fine for interactive use, fatal for byte-reproducible builds. Files
# already get an explicit meta_info per their Tree entry; the root and
# every created directory get this fixed Amiga-epoch stamp instead.
_EPOCH = TimeStamp(0, 0, 0)

# amitools 0.8.1 bug: PartBlockDevice.read_block/write_block (used to
# access an RDB partition, which every hdf output needs) always call
# through with a `num_blks` kwarg, but HDFBlockDevice.read_block/
# write_block don't accept or forward it — unlike the sibling
# RawBlockDevice class, which does, and unlike ImageFile.read_blk/
# write_blk, which already support it. HDFBlockDevice is simply missing
# the pass-through. Patched here rather than routed around, since any
# partitioned-HDF population needs this path. Safe to delete once fixed
# upstream (harmless if amitools already forwards num_blks: the patched
# methods behave identically to correct ones).
if "num_blks" not in HDFBlockDevice.read_block.__code__.co_varnames:

    def _read_block(self, blk_num, num_blks=1):
        return self.img_file.read_blk(blk_num, num_blks=num_blks)

    def _write_block(self, blk_num, data, num_blks=1):
        return self.img_file.write_blk(blk_num, data, num_blks=num_blks)

    HDFBlockDevice.read_block = _read_block
    HDFBlockDevice.write_block = _write_block

# Overhead margin over raw file bytes for filesystem/block-allocation
# slack, then rounded up to whole megabytes; a floor keeps tiny builds
# from producing a geometry too small for RDB + one partition.
_SIZE_MARGIN = 1.5
_MIN_SIZE = 4 * 1024 * 1024
_MB = 1024 * 1024

# recipe.py's DOS_TYPES schema names -> amitools DosType constants.
# Kept here (not in recipe.py) because recipe.py has no amitools
# dependency — it validates the string, this module interprets it.
DOS_TYPE_MAP = {
    "ofs": DosType.DOS_OFS,
    "ffs": DosType.DOS_FFS,
    "ofs-intl": DosType.DOS_OFS_INTL,
    "ffs-intl": DosType.DOS_FFS_INTL,
    "ofs-intl-dircache": DosType.DOS_OFS_INTL_DIRCACHE,
    "ffs-intl-dircache": DosType.DOS_FFS_INTL_DIRCACHE,
    "ofs-intl-longname": DosType.DOS_OFS_INTL_LONGNAME,
    "ffs-intl-longname": DosType.DOS_FFS_INTL_LONGNAME,
}
DEFAULT_DOS_TYPE = "ffs-intl"


class EmitError(Exception):
    """A manifest-caused hdf layout problem (content or scratch doesn't
    fit the requested size) — reported as a named error, not a traceback."""


def write_hdf(tree: Tree, path: Path, dos_type: str = DEFAULT_DOS_TYPE,
             volume_name: str = "SYS", drive_name: str = "DH0",
             size: int | None = None, scratch: int | None = None,
             scratch_drive_name: str = "DH1") -> None:
    """`size`/`scratch` are byte counts (the manifest's [hdf] strings,
    already converted by the caller via machine.parse_size). `size`
    overrides the content-derived image size; `scratch` reserves an
    unformatted partition at the end. With `scratch` but no `size`, the
    image grows so the system partition keeps its estimated capacity."""
    tree = tree.materialize()
    scratch = scratch or 0
    if size is None:
        size = _estimate_size(tree) + _round_up_mb(scratch)
    else:
        size = _round_up_mb(size)
    dos_type_const = DOS_TYPE_MAP[dos_type]

    factory = BlkDevFactory()
    blkdev = factory.create(str(path), force=True, options={"size": size, "type": "hdf"})
    try:
        rdisk = RDisk(blkdev)
        rdisk.create(blkdev.get_geometry())
        lo, hi = rdisk.get_free_cyl_ranges()[0]
        scratch_cyls = 0
        if scratch:
            geo = blkdev.get_geometry()
            cyl_bytes = geo.heads * geo.secs * geo.block_bytes
            scratch_cyls = -(-scratch // cyl_bytes)  # ceil: at least what was asked
            if hi - scratch_cyls < lo:
                raise EmitError(
                    f"[hdf].scratch ({scratch} bytes) leaves no room for the "
                    f"system partition in a {size}-byte image — raise "
                    f"[hdf].size or shrink [hdf].scratch")
        lo_hi = (lo, hi - scratch_cyls)
        # `flags=FLAG_BOOTABLE` (PBFB_BOOTABLE, bit 0 of the PART block's
        # pb_Flags) is not amitools' default — `add_partition` defaults
        # `flags=0`, which writes a perfectly valid partition that
        # Kickstart's boot scan then skips, because strap only considers
        # partitions carrying that bit. Harmless while the emitted
        # emulator configs booted a HOSTFS directory instead; a real
        # requirement now that `[lide]` boots this image for real.
        # boot_pri stays 0, where real hard drives sit (DF0: is 5, so a
        # bootable floppy still wins if one is ever configured).
        partition = rdisk.add_partition(
            FSString(drive_name), lo_hi, dos_type=dos_type_const, boot_pri=0,
            flags=PartitionBlock.FLAG_BOOTABLE)

        if scratch_cyls:
            # An RDB entry with default flags (mountable, not bootable)
            # and *no filesystem written*: the guest sees a named,
            # unformatted device — exactly what a destructive tester
            # like devsoak should be pointed at. The dos_type recorded
            # is only the RDB's mount hint; nothing here formats it.
            rdisk.add_partition(
                FSString(scratch_drive_name), (hi - scratch_cyls + 1, hi),
                dos_type=dos_type_const, boot_pri=0)

        part_blkdev = partition.create_blkdev()
        part_blkdev.open()
        try:
            vol = ADFSVolume(part_blkdev)
            root_meta = RootMetaInfo(create_ts=_EPOCH, disk_ts=_EPOCH, mod_ts=_EPOCH)
            try:
                vol.create(FSString(volume_name), meta_info=root_meta,
                           dos_type=dos_type_const)
                _populate(vol, tree)
            except FSError as e:
                # Running out of blocks is only reachable with an
                # explicit [hdf].size (the auto-sized path always fits
                # by construction) — name the manifest key. Every other
                # FSError (bad filename, ...) is not a layout problem.
                if e.code != NO_FREE_BLOCKS:
                    raise
                raise EmitError(
                    f"the build's content does not fit the requested [hdf] "
                    f"layout ({size} bytes total, {scratch} reserved for "
                    f"scratch) — raise [hdf].size") from e
            vol.close()
        finally:
            part_blkdev.close()
    finally:
        blkdev.close()


def _estimate_size(tree: Tree) -> int:
    total = sum(len(tree.get(p).data) for p in tree.paths())
    size = max(int(total * _SIZE_MARGIN), _MIN_SIZE)
    return _round_up_mb(size)


def _round_up_mb(n: int) -> int:
    return ((n + _MB - 1) // _MB) * _MB


_DIR_META = MetaInfo(protect_flags=ProtectFlags(0), mod_ts=_EPOCH, comment=None)


def _populate(vol: ADFSVolume, tree: Tree) -> None:
    dir_nodes = {"": vol.get_root_dir()}

    def ensure_dir(physical_dir: str):
        if physical_dir in dir_nodes:
            return dir_nodes[physical_dir]
        parent_path = physical_dir.rsplit("/", 1)[0] if "/" in physical_dir else ""
        parent_node = ensure_dir(parent_path)
        basename = physical_dir.rsplit("/", 1)[-1]
        # update_ts=False: amitools' default (True) stamps the *parent*
        # directory's own mod_ts to wall-clock "now" on every child add
        # (ADFSDir._create_node -> update_dir_mod_time / Volume.
        # update_disk_time), independent of any meta_info passed for the
        # child itself — the actual source of the nondeterminism this
        # module works around throughout.
        node = parent_node.create_dir(
            FSString(basename), meta_info=_DIR_META, update_ts=False)
        dir_nodes[physical_dir] = node
        return node

    for amiga_path in tree.paths():
        file = tree.get(amiga_path)
        physical = to_physical_path(amiga_path)
        directory = physical.rsplit("/", 1)[0] if "/" in physical else ""
        basename = physical.rsplit("/", 1)[-1]
        parent_node = ensure_dir(directory)

        node = parent_node.create_file(
            FSString(basename), file.data, meta_info=_to_meta_info(file.meta),
            update_ts=False)
        node.flush()


def _to_meta_info(meta: AmigaMeta) -> MetaInfo:
    days, mins, ticks = meta.datestamp
    comment = FSString(meta.comment) if meta.comment else None
    return MetaInfo(
        protect_flags=ProtectFlags(meta.protection),
        mod_ts=TimeStamp(days, mins, ticks),
        comment=comment,
    )
