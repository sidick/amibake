"""Amiga `.info` (Workbench icon) tool-type editing.

The one thing a real Installer script does to an icon that a plain file
copy can't reproduce: `(tooltype (settooltype "BoardType" "Graffity"))`.
Several real installers configure a copied file entirely through its
icon's tool types — P96's `P_InstallCard` copies one generic
`Devs/Monitors/Picasso96` under each board's name and then *tells* the
copy which board it is that way, and the program reads `BoardType` back
with `GetDiskObject`/`FindToolType` at boot. Copying the icon verbatim
is not a workaround for that; it's worse than shipping no icon at all,
since the program then finds an icon and no `BoardType` in it.

Only the classic (pre-OS3.5) `DiskObject` body is parsed, and only as
far as is needed to find where the tool-type array lives:

    DiskObject      78 bytes    magic 0xE310, do_ToolTypes at +54
    DrawerData      56 bytes    only when do_DrawerData != 0
    Image 1         20 + planes only when do_Gadget.GadgetRender != 0
    Image 2         20 + planes only when do_Gadget.SelectRender != 0
    DefaultTool     u32 len + bytes (len counts the NUL)
    ToolTypes       u32 (n+1)*4, then n * (u32 len + bytes)
    ToolWindow      u32 len + bytes (never written by icon.library)

Anything after that — an OS3.5+ ColorIcon `FORM ICON` chunk, a NewIcon
tool-type blob, whatever a real icon editor appended — is opaque here
and spliced back unchanged, so editing tool types can't quietly discard
the modern half of a dual-format icon.

Sizes are the on-disk ones (`>H`/`>I` big-endian), not host-native: an
`.info` written on a real Amiga is what this reads and writes.
"""

from __future__ import annotations

import struct

MAGIC = 0xE310

_HEADER_SIZE = 78
_DRAWER_DATA_SIZE = 56
_OFF_GADGET_RENDER = 22
_OFF_SELECT_RENDER = 26
_OFF_DEFAULT_TOOL = 50
_OFF_TOOL_TYPES = 54
_OFF_DRAWER_DATA = 66
_OFF_TOOL_WINDOW = 70


class IconError(Exception):
    pass


def _string_size(data: bytes, off: int) -> int:
    """Size of a `u32 length + length bytes` record, length included."""
    if off + 4 > len(data):
        raise IconError("truncated icon: a string length runs past the end of the file")
    (length,) = struct.unpack_from(">I", data, off)
    if off + 4 + length > len(data):
        raise IconError("truncated icon: a string runs past the end of the file")
    return 4 + length


def _image_size(data: bytes, off: int) -> int:
    """20-byte Image header plus its bitplanes."""
    if off + 20 > len(data):
        raise IconError("truncated icon: an image header runs past the end of the file")
    width, height, depth = struct.unpack_from(">hhh", data, off + 4)
    if width < 0 or height < 0 or depth < 0:
        raise IconError(f"bad icon image geometry: {width}x{height} depth {depth}")
    # One plane row is padded to a whole number of 16-bit words.
    planes = ((width + 15) // 16) * 2 * height * depth
    return 20 + planes


def _tool_types_offset(data: bytes) -> int:
    """Byte offset of the tool-type array (or of where it would go)."""
    off = _HEADER_SIZE
    if struct.unpack_from(">I", data, _OFF_DRAWER_DATA)[0]:
        off += _DRAWER_DATA_SIZE
    if struct.unpack_from(">I", data, _OFF_GADGET_RENDER)[0]:
        off += _image_size(data, off)
    if struct.unpack_from(">I", data, _OFF_SELECT_RENDER)[0]:
        off += _image_size(data, off)
    if struct.unpack_from(">I", data, _OFF_DEFAULT_TOOL)[0]:
        off += _string_size(data, off)
    return off


def _tool_types_size(data: bytes, off: int) -> int:
    if not struct.unpack_from(">I", data, _OFF_TOOL_TYPES)[0]:
        return 0
    if off + 4 > len(data):
        raise IconError("truncated icon: the tool-type array runs past the end of the file")
    (raw,) = struct.unpack_from(">I", data, off)
    if raw % 4 or raw < 4:
        raise IconError(f"bad tool-type array size {raw} (expected a positive multiple of 4)")
    size = 4
    for _ in range(raw // 4 - 1):  # the count includes the NULL terminator
        size += _string_size(data, off + size)
    return size


def _encode(entries: list[str]) -> bytes:
    out = [struct.pack(">I", (len(entries) + 1) * 4)]
    for entry in entries:
        raw = entry.encode("latin-1") + b"\0"
        out.append(struct.pack(">I", len(raw)) + raw)
    return b"".join(out)


def read_tool_types(data: bytes) -> list[str]:
    """Tool types as their raw `"NAME=value"` strings, in file order."""
    if len(data) < _HEADER_SIZE or struct.unpack_from(">H", data, 0)[0] != MAGIC:
        raise IconError("not an Amiga .info file (bad magic — expected 0xE310)")
    off = _tool_types_offset(data)
    if not struct.unpack_from(">I", data, _OFF_TOOL_TYPES)[0]:
        return []
    (raw,) = struct.unpack_from(">I", data, off)
    off += 4
    entries = []
    for _ in range(raw // 4 - 1):
        size = _string_size(data, off)  # bounds-checks before the slice
        (length,) = struct.unpack_from(">I", data, off)
        entries.append(data[off + 4:off + 4 + length - 1].decode("latin-1"))
        off += size
    return entries


def set_tool_types(data: bytes, values: dict[str, str]) -> bytes:
    """`data` with each `NAME=value` set — replaced in place if the name
    is already there (keeping its position, the way a real `tooltype`
    statement does), appended in sorted order otherwise.

    Names are matched case-insensitively, as `FindToolType` matches
    them; the recipe's own spelling wins for the name it sets. Sorted
    appends keep the output deterministic, which the build-twice
    byte-compare test requires."""
    if len(data) < _HEADER_SIZE or struct.unpack_from(">H", data, 0)[0] != MAGIC:
        raise IconError("not an Amiga .info file (bad magic — expected 0xE310)")

    off = _tool_types_offset(data)
    size = _tool_types_size(data, off)
    entries = read_tool_types(data)

    remaining = dict(values)
    for i, entry in enumerate(entries):
        name = entry.partition("=")[0]
        match = next((k for k in remaining if k.lower() == name.lower()), None)
        if match is not None:
            entries[i] = f"{match}={remaining.pop(match)}"
    for name in sorted(remaining):
        entries.append(f"{name}={remaining[name]}")

    header = bytearray(data[:_HEADER_SIZE])
    # do_ToolTypes is a live RAM pointer that icon.library writes out
    # as-is, so real icons carry arbitrary junk in it (0x401DE130 on a
    # stock OS 3.2 Asl.info); only zero-vs-non-zero means anything on
    # disk. Leave a non-zero one exactly as found — that is what makes
    # setting a tool type to the value it already has a byte-for-byte
    # no-op, checked against every .info on the real OS 3.2 media — and
    # write 1 only when the icon carried no array at all.
    if not entries:
        struct.pack_into(">I", header, _OFF_TOOL_TYPES, 0)
    elif not struct.unpack_from(">I", data, _OFF_TOOL_TYPES)[0]:
        struct.pack_into(">I", header, _OFF_TOOL_TYPES, 1)
    return bytes(header) + data[_HEADER_SIZE:off] + _encode(entries) + data[off + size:]
