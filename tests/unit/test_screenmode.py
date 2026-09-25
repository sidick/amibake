import struct

import pytest

from amibake.screenmode import (
    SCREENMODE_PREFS_PATH,
    ScreenModeError,
    apply_screenmode,
    build_screenmode_prefs,
    parse_p96_settings,
)
from amibake.tree import Tree


def _rshd(display_id: int, width: int, height: int, name: str) -> bytes:
    """One RSHD chunk in the layout observed in the real p96-z3660-hdmi
    settings file: ULONG id, UWORD w, UWORD h, 6 opaque bytes, then the
    NUL-terminated display name padded to a fixed-width field."""
    body = struct.pack(">IHH", display_id, width, height) + b"\x00\x01\x00\x00\x00\x02"
    body += name.encode("latin-1") + b"\0" * (22 - len(name))
    return b"RSHD" + struct.pack(">I", len(body)) + body


def _p96s(*modes: tuple[int, int, int, str]) -> bytes:
    chunks = b"".join(_rshd(*m) for m in modes)
    return b"FORM" + struct.pack(">I", 4 + len(chunks)) + b"P96S" + chunks


Z3660_MODES = [
    (0x50041000, 640, 480, "Z3660:640x480"),
    (0x500D1000, 1024, 384, "Z3660:1024x384"),
]


def test_prefs_file_is_a_wellformed_pref_form():
    data = build_screenmode_prefs(0x500D1000, 1024, 384, 8)
    assert data[:4] == b"FORM"
    (form_size,) = struct.unpack_from(">I", data, 4)
    assert form_size == len(data) - 8
    assert data[8:12] == b"PREF"
    assert data[12:16] == b"PRHD"
    assert struct.unpack_from(">I", data, 16) == (6,)
    assert data[20:26] == bytes(6)  # PrefHeader: version 0, type 0, flags 0
    assert data[26:30] == b"SCRM"
    assert struct.unpack_from(">I", data, 30) == (28,)
    scrm = data[34:62]
    reserved = struct.unpack(">4I", scrm[:16])
    assert reserved == (0, 0, 0, 0)
    display_id, w, h, depth, control = struct.unpack(">IHHHH", scrm[16:])
    assert (display_id, w, h, depth) == (0x500D1000, 1024, 384, 8)
    assert control == 1  # SMF_AUTOSCROLL, the default
    assert len(data) == 62  # nothing trailing


def test_autoscroll_false_clears_the_control_flag():
    data = build_screenmode_prefs(0x29000, 640, 256, 4, autoscroll=False)
    assert struct.unpack(">H", data[-2:]) == (0,)


def test_parse_p96_settings_reads_every_resolution():
    modes = parse_p96_settings(_p96s(*Z3660_MODES), "SYS:Devs/p96-z3660-hdmi")
    assert [(m.display_id, m.width, m.height, m.name) for m in modes] == Z3660_MODES
    assert all(m.settings_path == "SYS:Devs/p96-z3660-hdmi" for m in modes)


def test_parse_rejects_non_p96s_data():
    with pytest.raises(ScreenModeError, match="FORM P96S"):
        parse_p96_settings(b"FORM\x00\x00\x00\x04PREF", "SYS:Devs/x")


def _tree_with_settings(path="SYS:Devs/p96-z3660-hdmi") -> Tree:
    tree = Tree()
    tree.put(path, _p96s(*Z3660_MODES))
    return tree


def test_apply_by_name_resolves_id_and_dimensions_from_the_settings_file():
    out = apply_screenmode(_tree_with_settings(),
                           {"name": "z3660:1024X384", "depth": 8})  # case-insensitive
    data = out.get(SCREENMODE_PREFS_PATH).data
    display_id, w, h, depth, _ = struct.unpack(">IHHHH", data[-12:])
    assert (display_id, w, h, depth) == (0x500D1000, 1024, 384, 8)


def test_apply_by_explicit_id_needs_no_settings_file():
    out = apply_screenmode(Tree(), {"id": 0x29000, "width": 640, "height": 256,
                                    "depth": 4, "autoscroll": False})
    data = out.get(SCREENMODE_PREFS_PATH).data
    assert struct.unpack(">IHHHH", data[-12:]) == (0x29000, 640, 256, 4, 0)


def test_apply_without_screenmode_is_a_noop():
    tree = _tree_with_settings()
    assert apply_screenmode(tree, None) is tree


def test_apply_never_mutates_the_input_tree():
    tree = _tree_with_settings()
    apply_screenmode(tree, {"name": "Z3660:640x480", "depth": 8})
    assert not tree.exists(SCREENMODE_PREFS_PATH)


def test_unknown_name_error_lists_what_is_available():
    with pytest.raises(ScreenModeError) as e:
        apply_screenmode(_tree_with_settings(), {"name": "Z3660:9999x9999", "depth": 8})
    assert "Z3660:1024x384" in str(e.value)
    assert "Z3660:640x480" in str(e.value)


def test_name_declared_by_two_settings_files_is_a_named_error():
    tree = _tree_with_settings()
    tree.put("SYS:Devs/other-board", _p96s((0x50101000, 1024, 384, "Z3660:1024x384")))
    with pytest.raises(ScreenModeError, match="more than one"):
        apply_screenmode(tree, {"name": "Z3660:1024x384", "depth": 8})
