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

from amibake._validate import load_toml
from amibake.builder import build_tree
from amibake.resolver import load_recipe_library, resolve
from amibake.verify import verify_exists

from .conftest import REPO_ROOT, make_adf

RECIPES_ROOT = REPO_ROOT / "recipes"
MANIFEST_PATH = REPO_ROOT / "manifests" / "wb13.toml"

# Real 1.3 media has no S:User-Startup-sourcing Startup-Sequence and no
# ENVARC: (both 2.0+ conventions) — the recipe only copies C:/Devs:/
# L:/Libs:/Fonts:, so the fixture mirrors exactly that, not a full disk.
WB13_FILES = {
    "C/Dir": b"c-dir-binary",
    "C/Assign": b"c-assign-binary",
    "Devs/Kickstart": b"devs-kickstart",
    "L/FastFileSystem": b"l-ffs",
    "Libs/diskfont.library": b"libs-diskfont",
    "Fonts/topaz.font": b"topaz-font",
    "Fonts/topaz/9": b"topaz-9-glyphs",
}


def _build_wb13_tree(tmp_path):
    assets_root = tmp_path / "assets"
    assets_root.mkdir()
    (assets_root / "Workbench-1.3.3.adf").write_bytes(make_adf(WB13_FILES))

    manifest = load_toml(MANIFEST_PATH)
    library = load_recipe_library(RECIPES_ROOT)
    result = resolve(MANIFEST_PATH, manifest, library)
    assert result.ok, [str(p) for p in result.problems]

    tree = build_tree(result.plan, tmp_path / "cache", assets_root)
    return tree, result.plan, library


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
