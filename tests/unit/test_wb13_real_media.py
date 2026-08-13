"""Real-media build of the wb1.3 base, gated on the user having actually
dropped real WB 1.3 ADFs into `assets/` (gitignored, never committed).
Skips cleanly when absent — CI and fresh clones never have real media,
only a session where the user has supplied it does. This is the
genuine M5 "builds from real media" check; `test_wb13_recipe.py` covers
the mechanism hermetically with a synthetic fixture."""

import pytest

from amibake._validate import load_toml
from amibake.builder import build_tree
from amibake.resolver import load_recipe_library, resolve
from amibake.verify import verify_exists

from .conftest import REPO_ROOT

RECIPES_ROOT = REPO_ROOT / "recipes"
ASSETS_ROOT = REPO_ROOT / "assets"
MANIFEST_PATH = REPO_ROOT / "manifests" / "wb13.toml"

pytestmark = pytest.mark.skipif(
    not (ASSETS_ROOT / "Workbench-1.3.3.adf").exists(),
    reason="no real WB 1.3 media at assets/Workbench-1.3.3.adf",
)


def test_wb13_builds_and_verifies_from_real_media(tmp_path):
    manifest = load_toml(MANIFEST_PATH)
    library = load_recipe_library(RECIPES_ROOT)
    result = resolve(MANIFEST_PATH, manifest, library)
    assert result.ok, [str(p) for p in result.problems]

    tree = build_tree(result.plan, tmp_path / "cache", ASSETS_ROOT)

    for pkg in (result.plan.base_package, *result.plan.packages):
        recipe = library[pkg.name]
        assert verify_exists(tree, pkg.name, recipe.doc) == []

    assert tree.get("SYS:Libs/diskfont.library").data
    assert tree.get("SYS:Fonts/topaz.font").data
