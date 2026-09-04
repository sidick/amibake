import struct

import pytest

from amibake.icon import IconError, read_tool_types, set_tool_types


# A minimal but structurally real .info: DiskObject header, one 2x1x1
# image (so the image-skipping path is exercised), a DefaultTool string,
# and whatever tool types a test asks for. Field offsets are the ones
# icon.py documents; keeping the builder independent of icon.py's own
# constants is the point — a wrong offset in both would cancel out.
def _icon(tool_types=(), default_tool="sys:System/AddMonitor", trailing=b"",
          tool_types_ptr=None):
    header = bytearray(78)
    struct.pack_into(">HH", header, 0, 0xE310, 1)
    struct.pack_into(">I", header, 22, 0x12345678)          # GadgetRender
    struct.pack_into(">I", header, 50, 0xAABBCCDD if default_tool else 0)
    if tool_types_ptr is None:
        tool_types_ptr = 0x401DE130 if tool_types else 0
    struct.pack_into(">I", header, 54, tool_types_ptr)
    header[48] = 3                                          # WBPROJECT

    image = bytearray(20)
    struct.pack_into(">hhh", image, 4, 2, 1, 1)             # 2x1, depth 1
    image += b"\0\0"                                        # one padded row

    body = bytes(header) + bytes(image)
    if default_tool:
        raw = default_tool.encode("latin-1") + b"\0"
        body += struct.pack(">I", len(raw)) + raw
    if tool_types:
        body += struct.pack(">I", (len(tool_types) + 1) * 4)
        for entry in tool_types:
            raw = entry.encode("latin-1") + b"\0"
            body += struct.pack(">I", len(raw)) + raw
    return body + trailing


def test_reads_tool_types_in_file_order():
    icon = _icon(["BoardType=PicassoIV", "IgnoreMask=Yes"])
    assert read_tool_types(icon) == ["BoardType=PicassoIV", "IgnoreMask=Yes"]


def test_reads_none_from_an_icon_that_has_none():
    assert read_tool_types(_icon()) == []


def test_sets_the_first_tool_type_on_an_icon_with_none():
    """The real P96 monitor icon's case: an empty array, and BoardType is
    what the monitor program reads back to know which board it drives."""
    icon = _icon()
    out = set_tool_types(icon, {"BoardType": "Graffity"})

    assert read_tool_types(out) == ["BoardType=Graffity"]
    # do_ToolTypes has to become non-zero or icon.library sees no array.
    assert struct.unpack_from(">I", out, 54)[0] != 0


def test_replacing_a_value_keeps_the_entry_in_place():
    icon = _icon(["A=1", "BoardType=old", "Z=9"])
    out = set_tool_types(icon, {"BoardType": "new"})
    assert read_tool_types(out) == ["A=1", "BoardType=new", "Z=9"]


def test_name_matching_is_case_insensitive_like_findtooltype():
    icon = _icon(["boardtype=old"])
    out = set_tool_types(icon, {"BoardType": "Graffity"})
    assert read_tool_types(out) == ["BoardType=Graffity"]


def test_new_names_append_in_sorted_order_for_determinism():
    icon = _icon(["Existing=1"])
    out = set_tool_types(icon, {"Zebra": "z", "Alpha": "a"})
    assert read_tool_types(out) == ["Existing=1", "Alpha=a", "Zebra=z"]
    assert set_tool_types(icon, {"Alpha": "a", "Zebra": "z"}) == out


def test_setting_a_value_it_already_has_is_a_byte_for_byte_no_op():
    """What makes the real-media round-trip check meaningful: a live
    do_ToolTypes pointer value (junk, but real) must survive untouched."""
    icon = _icon(["BoardType=Graffity"], tool_types_ptr=0x401DE130)
    assert set_tool_types(icon, {"BoardType": "Graffity"}) == icon


def test_trailing_data_is_preserved():
    """An OS3.5+ ColorIcon chunk lives past the classic body; editing tool
    types must not truncate the modern half of a dual-format icon."""
    chunk = b"FORM\0\0\0\x08ICON"
    icon = _icon(["A=1"], trailing=chunk)
    out = set_tool_types(icon, {"B": "2"})
    assert out.endswith(chunk)


def test_a_parenthesised_entry_is_matched_by_its_literal_name():
    """How the real InstallPicasso96 writes a commented-out tool type:
    `(settooltype "(DisplayChain" "Yes)")` — the parens are part of the
    name and value, so plain name matching is the faithful behaviour."""
    icon = _icon(["(DisplayChain=No)"])
    out = set_tool_types(icon, {"(DisplayChain": "Yes)"})
    assert read_tool_types(out) == ["(DisplayChain=Yes)"]


def test_a_non_icon_is_refused_by_name():
    with pytest.raises(IconError, match="not an Amiga .info file"):
        set_tool_types(b"\x89PNG\r\n\x1a\n" + b"\0" * 100, {"BoardType": "x"})


def test_a_truncated_icon_is_refused_rather_than_misparsed():
    icon = _icon(["A=1"])
    with pytest.raises(IconError, match="truncated icon"):
        read_tool_types(icon[:-4])
