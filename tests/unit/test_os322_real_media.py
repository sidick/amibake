"""Real-media build of the os3.2.2 base, gated on the user having
actually dropped the real Hyperion media into `assets/hyperion/`
(gitignored, never committed). Skips cleanly when absent — CI and
fresh clones never have it. This is the genuine M8 "builds from real
media" check for the first base spanning a real cumulative point-
release chain (base + 3.2.1-update + 3.2.2-update, each real content
Unix-compress/LZW-encoded and merged under its own <filename>/ prefix
— see recipes/os3.2.2's own comments)."""

import pytest

from amibake._validate import load_toml
from amibake.builder import build_tree
from amibake.resolver import load_recipe_library, resolve
from amibake.verify import verify_exists

from .conftest import REPO_ROOT

RECIPES_ROOT = REPO_ROOT / "recipes"
ASSETS_ROOT = REPO_ROOT / "assets"
MANIFEST_PATH = REPO_ROOT / "manifests" / "os322.toml"
REAL_MEDIA = [
    ASSETS_ROOT / "hyperion" / "AmigaOS-3.2-full.lha",
    ASSETS_ROOT / "hyperion" / "AmigaOS-3.2.1.lha",
    ASSETS_ROOT / "hyperion" / "AmigaOS-3.2.2.lha",
]

pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in REAL_MEDIA),
    reason=f"no real AmigaOS 3.2/3.2.1/3.2.2 media at {ASSETS_ROOT / 'hyperion'}",
)


def test_os322_builds_and_verifies_from_real_media(tmp_path):
    manifest = load_toml(MANIFEST_PATH)
    library = load_recipe_library(RECIPES_ROOT)
    result = resolve(MANIFEST_PATH, manifest, library)
    assert result.ok, [str(p) for p in result.problems]

    tree = build_tree(result.plan, tmp_path / "cache", ASSETS_ROOT)

    for pkg in (result.plan.base_package, *result.plan.packages):
        recipe = library[pkg.name]
        assert verify_exists(tree, pkg.name, recipe.doc) == []

    # Base-disk content
    assert tree.get("SYS:Libs/workbench.library").data
    assert tree.get("SYS:Tools/Commodities/Exchange").data
    assert any(p.startswith("SYS:Storage/DOSDrivers/") for p in tree.paths())
    # 3.2.1-update-only content, real and .Z-decompressed at extract
    # time — confirms the update layer actually landed, not just base
    assert tree.get("SYS:C/AssignWedge").data
    assert not any(p.endswith(".Z") for p in tree.paths())
    # 3.2.2-update content layered on top of 3.2.1's
    assert tree.get("SYS:Classes/DataTypes/icon.datatype").data
