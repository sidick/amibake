"""M5 exit criterion: a Workbench 1.3 manifest builds from real media
with no manual step. This test builds a synthetic-but-structurally-
faithful ADF (via `make_adf`, exercising the same amitools ADF-reading
code path a real dump would go through) and runs it through the real
`recipes/wb1.3/recipe.toml` and `manifests/wb13.toml` end-to-end:
resolve -> fetch -> extract -> layer -> [verify]. The manifest resolves
to the base's highest declared version (1.3.3); see
`test_wb13_real_media.py` for a real-media build gated on
`assets/Workbench-{version}.adf` actually being present.
"""

import dataclasses
import hashlib

from amibake._validate import load_toml
from amibake.builder import build_tree
from amibake.plan import ResolvedPackage
from amibake.resolver import load_recipe_library, resolve
from amibake.verify import verify_exists

from .conftest import REPO_ROOT, make_adf

RECIPES_ROOT = REPO_ROOT / "recipes"
MANIFEST_PATH = REPO_ROOT / "manifests" / "wb13.toml"

# Real 1.3 media has no S:User-Startup-sourcing Startup-Sequence and no
# ENVARC: (both 2.0+ conventions). This mirrors the real disk's full
# content (the recipe now ships the whole Workbench disk, not just a
# CLI subset) — the real on-disk Startup-Sequence content itself
# (S/Startup-Sequence) deliberately never mentions "user-startup",
# matching the real disk, so the auto-append behavior is exercised
# honestly rather than short-circuited by the fixture.
WB13_FILES = {
    "C/Dir": b"c-dir-binary",
    "C/Assign": b"c-assign-binary",
    "Devs/Kickstart": b"devs-kickstart",
    "L/FastFileSystem": b"l-ffs",
    "Libs/diskfont.library": b"libs-diskfont",
    "Fonts/topaz.font": b"topaz-font",
    "Fonts/topaz/9": b"topaz-9-glyphs",
    "Prefs/Preferences": b"prefs-preferences",
    "System/SetMap": b"system-setmap",
    "Utilities/Clock": b"utilities-clock",
    "Disk.info": b"disk-icon",
    "Shell": b"shell-binary",
    "S/Startup-Sequence": b"C:SetPatch >NIL:\nC:BindDrivers\n",
    "S/StartupII": b"C:Resident C:List pure\n",
}


def _build_wb13_tree(tmp_path):
    assets_root = tmp_path / "assets"
    assets_root.mkdir()
    (assets_root / "Workbench-1.3.3.adf").write_bytes(make_adf(WB13_FILES))

    manifest = load_toml(MANIFEST_PATH)
    library = load_recipe_library(RECIPES_ROOT)
    result = resolve(MANIFEST_PATH, manifest, library)
    assert result.ok, [str(p) for p in result.problems]

    # The real manifest now layers sana2loop, a real [source.aminet]
    # package — fetching it for real would make this hermetic test
    # depend on live network access on every run. Base-only here (same
    # pattern as test_builder.py's synthetic packages); sana2loop's own
    # real fetch+build was verified manually against the live Aminet
    # archive and real WB1.3 media, same as AmiSSL/ClassAct/AROS in M4.
    plan = dataclasses.replace(result.plan, packages=())
    tree = build_tree(plan, tmp_path / "cache", assets_root)
    return tree, plan, library


def test_wb13_builds_and_verifies(tmp_path):
    tree, plan, library = _build_wb13_tree(tmp_path)

    for pkg in (plan.base_package, *plan.packages):
        recipe = library[pkg.name]
        assert verify_exists(tree, pkg.name, recipe.doc) == []

    assert tree.get("SYS:C/Dir").data == b"c-dir-binary"
    assert tree.get("SYS:Devs/Kickstart").data == b"devs-kickstart"
    assert tree.get("SYS:L/FastFileSystem").data == b"l-ffs"
    assert tree.get("SYS:Libs/diskfont.library").data == b"libs-diskfont"
    assert tree.get("SYS:Fonts/topaz.font").data == b"topaz-font"
    assert tree.get("SYS:Fonts/topaz/9").data == b"topaz-9-glyphs"
    assert tree.get("SYS:Prefs/Preferences").data == b"prefs-preferences"
    assert tree.get("SYS:System/SetMap").data == b"system-setmap"
    assert tree.get("SYS:Utilities/Clock").data == b"utilities-clock"
    assert tree.get("SYS:Disk.info").data == b"disk-icon"
    assert tree.get("SYS:Shell").data == b"shell-binary"


def test_wb13_default_boot_uses_the_real_startup_sequence(tmp_path):
    """[options.boot] defaults to "workbench" (user, 2026-08-13: "always
    ship the full desktop... more representative install") — the real
    on-disk Startup-Sequence is copied verbatim, not the authored
    CLI-only one."""
    tree, _plan, _library = _build_wb13_tree(tmp_path)
    startup_sequence = tree.get("SYS:S/Startup-Sequence").data.decode("latin-1")
    assert startup_sequence == "C:SetPatch >NIL:\nC:BindDrivers\n"
    assert tree.get("SYS:S/StartupII").data == b"C:Resident C:List pure\n"


def test_wb13_cli_boot_option_authors_its_own_minimal_startup_sequence(tmp_path):
    """boot = "cli" skips the real (LoadWB-driving) Startup-Sequence
    entirely in favour of a hand-authored minimal one — the mode M5's
    own boot verification used, faster/more predictable for automation."""
    assets_root = tmp_path / "assets"
    assets_root.mkdir()
    (assets_root / "Workbench-1.3.3.adf").write_bytes(make_adf(WB13_FILES))

    manifest = load_toml(MANIFEST_PATH)
    library = load_recipe_library(RECIPES_ROOT)
    result = resolve(MANIFEST_PATH, manifest, library)
    assert result.ok, [str(p) for p in result.problems]

    cli_base = dataclasses.replace(result.plan.base_package, options={"boot": "cli"})
    plan = dataclasses.replace(result.plan, base_package=cli_base, packages=())
    tree = build_tree(plan, tmp_path / "cache", assets_root)

    startup_sequence = tree.get("SYS:S/Startup-Sequence").data.decode("latin-1")
    assert "SetPatch" in startup_sequence
    assert "BindDrivers" in startup_sequence
    assert not tree.exists("SYS:S/StartupII")  # real S/#? wasn't copied in this mode


def test_wb13_wires_up_a_downstream_packages_user_startup_fragment(tmp_path):
    """Real 1.3's Startup-Sequence never sources S:User-Startup at all —
    confirms the fix (Tree._ensure_startup_sequence_sources_user_startup)
    actually closes that gap end-to-end on the real wb1.3 recipe: a
    downstream package's user-startup fragment gets wired up and runs."""
    tree, plan, _library = _build_wb13_tree(tmp_path)

    recipe_path = tmp_path / "somepkg.recipe.toml"
    recipe_path.write_text(
        '[install]\nuser-startup = [{ order = 50, lines = ["Run Foo"] }]\n'
    )
    downstream_pkg = ResolvedPackage(
        name="somepkg", version="1.0", options={},
        recipe_path=str(recipe_path),
        recipe_sha256=hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
        sources={},
    )
    plan_with_downstream = dataclasses.replace(plan, packages=(downstream_pkg,))
    tree_with_downstream = build_tree(plan_with_downstream, tmp_path / "cache2",
                                      tmp_path / "assets")

    materialized = tree_with_downstream.materialize()
    startup_sequence = materialized.get("SYS:S/Startup-Sequence").data.decode("latin-1")
    assert "IF EXISTS S:User-Startup" in startup_sequence
    assert "EXECUTE S:User-Startup" in startup_sequence
    assert "Run Foo" in materialized.get("S:User-Startup").data.decode("latin-1")
