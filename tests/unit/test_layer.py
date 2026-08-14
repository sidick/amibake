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
    "AmiSSL/Libs/#?" also picks up an archive's CPU-variant subdirectory
    — and the destination mirrors that subdirectory rather than
    flattening both matches onto the same basename."""
    install = {"copy": [{"from": "AmiSSL/Libs/#?", "to": "SYS:Libs/"}]}
    tree = apply_layer(Tree(), "amissl", install, _archive())
    assert tree.exists("SYS:Libs/amisslmaster.library")
    assert tree.exists("SYS:Libs/AmigaOS3/amisslmaster.library")


def test_copy_preserves_subdirectory_structure():
    archive = Tree()
    archive.put("Devs/DOSDrivers/CD0", b"driver")
    archive.put("Devs/Keymaps/usa", b"keymap")
    install = {"copy": [{"from": "Devs/#?", "to": "SYS:Devs/"}]}
    tree = apply_layer(Tree(), "aros", install, archive)
    assert tree.get("SYS:Devs/DOSDrivers/CD0").data == b"driver"
    assert tree.get("SYS:Devs/Keymaps/usa").data == b"keymap"


def test_copy_bare_volume_is_directory_target():
    """"SYS:" (no trailing slash, no sub-path) is its own root directory —
    same into-directory semantics as an explicit trailing "/"."""
    install = {"copy": [{"from": "AmiSSL/Certs/#?", "to": "SYS:"}]}
    tree = apply_layer(Tree(), "amissl", install, _archive())
    assert set(tree.paths()) == {"SYS:root.0", "SYS:root.1"}


def test_copy_single_file_destination_with_multiple_matches_is_an_error():
    install = {"copy": [{"from": "AmiSSL/Certs/#?", "to": "SYS:Certs.dat"}]}
    with pytest.raises(LayerError, match="matched 2 files"):
        apply_layer(Tree(), "amissl", install, _archive())


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


def test_files_written_at_arbitrary_destination():
    install = {"files": [{"to": "SYS:S/Startup-Sequence", "content": "C:SetPatch\n"}]}
    tree = apply_layer(Tree(), "wb1.3", install, Tree())
    assert tree.get("SYS:S/Startup-Sequence").data == b"C:SetPatch\n"


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


class TestWhenConditions:
    def _install(self):
        return {"copy": [
            {"from": "AmiSSL/Certs/root.0", "to": "SYS:A", "when": "card = uaegfx"},
            {"from": "AmiSSL/Certs/root.1", "to": "SYS:B", "when": "card = zz9000"},
        ]}

    def test_only_matching_entry_applies(self):
        tree = apply_layer(Tree(), "p96", self._install(), _archive(), {"card": "uaegfx"})
        assert tree.exists("SYS:A")
        assert not tree.exists("SYS:B")

    def test_no_matching_entry_copies_nothing(self):
        tree = apply_layer(Tree(), "p96", self._install(), _archive(), {"card": "picasso-iv"})
        assert tree.paths() == []

    def test_bool_option_condition(self):
        install = {"copy": [
            {"from": "AmiSSL/Certs/root.0", "to": "SYS:A", "when": "debug = true"},
        ]}
        assert apply_layer(Tree(), "p", install, _archive(), {"debug": True}).exists("SYS:A")
        assert not apply_layer(Tree(), "p", install, _archive(), {"debug": False}).exists("SYS:A")


class TestCopyVariants:
    """The real formula: `util/arc/lha.run` ships lha_68k/lha_68020/
    lha_68040 side by side (recipes/lha) — the concrete case
    docs/recipe-contract.md's `variants` mechanism was designed for."""

    def _archive(self):
        archive = Tree()
        archive.put("lha_68k", b"generic")
        archive.put("lha_68020", b"020-build")
        archive.put("lha_68040", b"040-build")
        return archive

    def _install(self):
        return {"copy": [{
            "from": "lha_68k", "to": "SYS:C/LhA",
            "variants": [
                {"path": "lha_68040", "cpu": ">= 68040"},
                {"path": "lha_68020", "cpu": ">= 68020"},
            ],
        }]}

    def test_no_machine_uses_fallback(self):
        tree = apply_layer(Tree(), "lha", self._install(), self._archive())
        assert tree.get("SYS:C/LhA").data == b"generic"

    def test_low_cpu_uses_fallback(self):
        tree = apply_layer(Tree(), "lha", self._install(), self._archive(),
                            machine={"cpu": "68000"})
        assert tree.get("SYS:C/LhA").data == b"generic"

    def test_matching_tier_picks_variant(self):
        tree = apply_layer(Tree(), "lha", self._install(), self._archive(),
                            machine={"cpu": "68020"})
        assert tree.get("SYS:C/LhA").data == b"020-build"

    def test_highest_matching_tier_wins_by_list_order(self):
        tree = apply_layer(Tree(), "lha", self._install(), self._archive(),
                            machine={"cpu": "68040"})
        assert tree.get("SYS:C/LhA").data == b"040-build"

    def test_higher_cpu_than_any_variant_falls_through_to_highest_satisfied(self):
        # 68060 satisfies both ">= 68040" and ">= 68020" predicates; the
        # first satisfied entry in list order wins (68040 listed first).
        tree = apply_layer(Tree(), "lha", self._install(), self._archive(),
                            machine={"cpu": "68060"})
        assert tree.get("SYS:C/LhA").data == b"040-build"

    def test_destination_is_always_the_fallback_name(self):
        """Whichever sibling wins, it lands at `to`'s own name — a
        manifest never has to know which variant got picked (PNG_dt's
        real Installer does the same: unsuffixed name either way)."""
        tree = apply_layer(Tree(), "lha", self._install(), self._archive(),
                            machine={"cpu": "68020"})
        assert set(tree.paths()) == {"SYS:C/LhA"}

    def test_variant_path_missing_from_archive_falls_back(self):
        archive = Tree()
        archive.put("lha_68k", b"generic")  # no lha_68020/lha_68040 in this archive
        tree = apply_layer(Tree(), "lha", self._install(), archive,
                            machine={"cpu": "68040"})
        assert tree.get("SYS:C/LhA").data == b"generic"

    def test_fpu_predicate(self):
        install = {"copy": [{
            "from": "lha_68k", "to": "SYS:C/LhA",
            "variants": [{"path": "lha_68020", "cpu": ">= 68020", "fpu": True}],
        }]}
        archive = self._archive()
        no_fpu = apply_layer(Tree(), "lha", install, archive, machine={"cpu": "68020"})
        assert no_fpu.get("SYS:C/LhA").data == b"generic"
        with_fpu = apply_layer(Tree(), "lha", install, archive,
                                machine={"cpu": "68020", "fpu": True})
        assert with_fpu.get("SYS:C/LhA").data == b"020-build"

    def test_variants_with_multiple_fallback_matches_is_an_error(self):
        archive = Tree()
        archive.put("Lib/foo", b"a")
        archive.put("Lib/bar", b"b")
        install = {"copy": [{
            "from": "Lib/#?", "to": "SYS:Libs/",
            "variants": [{"path": "Lib/foo.040", "cpu": ">= 68040"}],
        }]}
        with pytest.raises(LayerError, match="only support a single fallback match"):
            apply_layer(Tree(), "lha", install, archive, machine={"cpu": "68040"})


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
        assert compute_layer_key(
            None, "recipe-sha", "1.0", {}, "archive-sha", {"cpu": "68040"}) != base

    def test_key_is_deterministic(self):
        a = compute_layer_key("p", "r", "1.0", {"x": 1, "y": 2}, "a")
        b = compute_layer_key("p", "r", "1.0", {"y": 2, "x": 1}, "a")
        assert a == b
