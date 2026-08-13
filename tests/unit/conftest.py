from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def write(tmp_path):
    """Write TOML text to a temp file and return its path."""

    def _write(text: str, name: str = "test.toml", subdir: str | None = None) -> Path:
        directory = tmp_path / subdir if subdir else tmp_path
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_text(text)
        return path

    return _write


def _lha_crc16(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def make_lha_archive(files: dict[str, bytes]) -> bytes:
    """Build a minimal stored (-lh0-, uncompressed) level-0 .lha archive
    in-process, for hermetic extract.py tests — no network, no external
    binary, no committed multi-KB fixture. Byte layout validated against
    both `lhafile` and (for the header-level fields) direct inspection of
    lhafile's own parser; see PLAN.md's M2 decision log for why extraction
    uses `lhafile` rather than the lhasa/`lha` CLI."""
    import struct

    out = b""
    for name, data in files.items():
        name_bytes = name.encode()
        rest = (
            b"-lh0-"
            + struct.pack("<I", len(data))  # compressed size (== original: stored)
            + struct.pack("<I", len(data))  # original size
            + struct.pack("<I", 0)  # modify_time (4-byte MS-DOS datetime; 0 is fine)
            + bytes([0, 0, len(name_bytes)])  # reserved, level=0, filename length
            + name_bytes
            + struct.pack("<H", _lha_crc16(data))
        )
        header_size = 1 + len(rest)  # + checksum byte
        checksum = sum(rest) & 0xFF
        out += bytes([header_size, checksum]) + rest + data
    return out + b"\x00"  # end-of-archive sentinel


def make_iso(files: dict[str, bytes]) -> bytes:
    """Build a small ISO9660+Rock Ridge image in-process via pycdlib, for
    hermetic extract.py tests. Keys are archive-relative paths (no
    leading '/'); intermediate directories are created automatically."""
    import io

    import pycdlib

    iso = pycdlib.PyCdlib()
    iso.new(rock_ridge="1.09")
    made_dirs: set[str] = set()

    def ensure_dir(iso_dir: str, rr_dir: str) -> None:
        if not rr_dir or rr_dir in made_dirs:
            return
        parent_rr = rr_dir.rsplit("/", 1)[0] if "/" in rr_dir else ""
        parent_iso = iso_dir.rsplit("/", 1)[0] if "/" in iso_dir else ""
        ensure_dir(parent_iso, parent_rr)
        iso.add_directory(iso_dir, rr_name=rr_dir.rsplit("/", 1)[-1])
        made_dirs.add(rr_dir)

    for name, data in files.items():
        rr_dir = name.rsplit("/", 1)[0] if "/" in name else ""
        iso_dir = "/" + rr_dir.upper().replace("/", "/") if rr_dir else ""
        ensure_dir(iso_dir, rr_dir)
        basename = name.rsplit("/", 1)[-1]
        iso_name = f"{iso_dir}/{basename.upper()};1" if iso_dir else f"/{basename.upper()};1"
        iso.add_fp(io.BytesIO(data), len(data), iso_name, rr_name=basename)

    buf = io.BytesIO()
    iso.write_fp(buf)
    iso.close()
    return buf.getvalue()


def make_adf(files: dict[str, bytes], volume_name: str = "Workbench") -> bytes:
    """Build a minimal OFS Amiga floppy disk image (.adf) in-process via
    amitools, for hermetic extract.py tests of the wb1.3 recipe's real
    source format — no network, no external tool, no committed 880K
    fixture. Keys are archive-relative paths ('C/Dir', 'S/Startup-
    Sequence'); intermediate directories are created automatically."""
    import io

    from amitools.fs.ADFSVolume import ADFSVolume
    from amitools.fs.blkdev.ADFBlockDevice import ADFBlockDevice
    from amitools.fs.FSString import FSString

    buf = io.BytesIO()
    blkdev = ADFBlockDevice(adf_file=None, fobj=buf)
    blkdev.create()
    volume = ADFSVolume(blkdev)
    volume.create(FSString(volume_name))

    made_dirs: set[str] = set()

    def ensure_dir(dir_path: str) -> None:
        if not dir_path or dir_path in made_dirs:
            return
        parent = dir_path.rsplit("/", 1)[0] if "/" in dir_path else ""
        ensure_dir(parent)
        volume.create_dir(FSString(dir_path))
        made_dirs.add(dir_path)

    for name, data in files.items():
        dir_path = name.rsplit("/", 1)[0] if "/" in name else ""
        ensure_dir(dir_path)
        volume.write_file(data, FSString(name))

    volume.close()
    blkdev.flush()
    return buf.getvalue()


def fields_of(problems):
    return [p.field for p in problems]


def errors_of(problems):
    return [p for p in problems if p.severity == "error"]
