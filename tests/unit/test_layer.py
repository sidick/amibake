import pytest

from amibake.layer import (
    LayerError,
    apply_layer,
    compute_layer_key,
    load_layer_cache,
    save_layer_cache,
)
from amibake.tree import AmigaMeta, Tree


def _archive():
    archive = Tree()
    archive.put("AmiSSL/Libs/amisslmaster.library", b"libdata", AmigaMeta(comment="lib"))
    archive.put("AmiSSL/Libs/AmigaOS3/amisslmaster.library", b"variant")
    archive.put("AmiSSL/Certs/root.0", b"cert1")
    archive.put("AmiSSL/Certs/root.1", b"cert2")
    return archive


def test_copy_directory_pattern():
    install = {"copy": [{"from": "AmiSSL/Certs/#?", "to": "SYS:Devs/AmiSSL/Certs/"}]}
    tree = apply_layer(Tree(), "amissl", install, _archive())
    assert set(tree.paths()) == {"SYS:Devs/AmiSSL/Certs/root.0", "SYS:Devs/AmiSSL/Certs/root.1"}


def test_copy_pattern_matches_nested_paths():
    """`#?` matches across path separators, so a pattern anchored at
    "AmiSSL/Libs/#?" also picks up an archive's CPU-variant subdirectory."""
    install = {"copy": [{"from": "AmiSSL/Libs/#?", "to": "SYS:Libs/"}]}
    tree = apply_layer(Tree(), "amissl", install, _archive())
    # both archive matches share the basename "amisslmaster.library";
    # directory-copy semantics mean the later match (sorted order) wins.
    assert tree.exists("SYS:Libs/amisslmaster.library")


def test_copy_preserves_metadata():
    install = {"copy": [{"from": "AmiSSL/Libs/amisslmaster.library", "to": "SYS:Libs/"}]}
    tree = apply_layer(Tree(), "amissl", install, _archive())
    assert tree.get("SYS:Libs/amisslmaster.library").meta.comment == "lib"


def test_copy_no_match_is_an_error():
    install = {"copy": [{"from": "Nope/#?", "to": "SYS:Libs/"}]}
    with pytest.raises(LayerError, match="matched nothing"):
        apply_layer(Tree(), "amissl", install, _archive())


def test_envarc_written():
    install = {"envarc": [{"name": "AmiSSL/config", "content": "key=value\n"}]}
    tree = apply_layer(Tree(), "amissl", install, Tree())
    assert tree.get("ENVARC:AmiSSL/config").data == b"key=value\n"


def test_user_startup_and_assigns_accumulate():
    install = {
        "user-startup": [{"order": 50, "lines": ["Run Foo"]}],
        "assigns": [{"name": "AmiSSL", "path": "SYS:Devs/AmiSSL"}],
    }
    tree = apply_layer(Tree(), "amissl", install, Tree())
    assert tree.user_startup[0].source == "amissl"
    assert tree.user_startup[0].lines == ("Run Foo",)
    assert tree.assigns[0].source == "amissl"
    assert tree.assigns[0].name == "AmiSSL"
    assert tree.assigns[0].path == "SYS:Devs/AmiSSL"


def test_apply_layer_does_not_mutate_base():
    base = Tree()
    base.put("SYS:existing", b"1")
    install = {"copy": [{"from": "AmiSSL/Certs/#?", "to": "SYS:Devs/AmiSSL/Certs/"}]}
    result = apply_layer(base, "amissl", install, _archive())
    assert not base.exists("SYS:Devs/AmiSSL/Certs/root.0")
    assert result.exists("SYS:existing")  # base content carried forward


def test_no_op_package_with_empty_install_and_archive():
    tree = apply_layer(Tree(), "bsdsocket-emulation", {}, Tree())
    assert tree.paths() == []


class TestLayerCache:
    def test_round_trips_files_and_metadata(self, tmp_path):
        tree = Tree()
        tree.put("SYS:Libs/x.library", b"data", AmigaMeta(comment="c", protection=5))
        tree.add_user_startup(50, "pkg", ["Run Foo"])
        tree.add_assign("pkg", "Foo", "SYS:Foo")
        key = compute_layer_key(None, "recipe-sha", "1.0", {}, "archive-sha")
        save_layer_cache(tree, key, tmp_path)
        loaded = load_layer_cache(key, tmp_path)
        assert loaded is not None
        assert loaded.content_hash() == tree.content_hash()

    def test_miss_returns_none(self, tmp_path):
        key = compute_layer_key(None, "a", "1.0", {}, "b")
        assert load_layer_cache(key, tmp_path) is None

    def test_key_depends_on_every_input(self):
        base = compute_layer_key(None, "recipe-sha", "1.0", {}, "archive-sha")
        assert compute_layer_key("parent", "recipe-sha", "1.0", {}, "archive-sha") != base
        assert compute_layer_key(None, "other-recipe-sha", "1.0", {}, "archive-sha") != base
        assert compute_layer_key(None, "recipe-sha", "2.0", {}, "archive-sha") != base
        assert compute_layer_key(
            None, "recipe-sha", "1.0", {"card": "uaegfx"}, "archive-sha") != base
        assert compute_layer_key(None, "recipe-sha", "1.0", {}, "other-archive-sha") != base

    def test_key_is_deterministic(self):
        a = compute_layer_key("p", "r", "1.0", {"x": 1, "y": 2}, "a")
        b = compute_layer_key("p", "r", "1.0", {"y": 2, "x": 1}, "a")
        assert a == b
