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


def fields_of(problems):
    return [p.field for p in problems]


def errors_of(problems):
    return [p for p in problems if p.severity == "error"]
