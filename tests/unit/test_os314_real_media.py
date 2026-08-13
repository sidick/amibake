"""Real-media build of the os3.1.4 base, gated on the user having
actually dropped the real Hyperion media into `assets/hyperion/`
(gitignored, never committed). Skips cleanly when absent — CI and
fresh clones never have it. This is the genuine M7 "builds from real
media" check for the first genuinely Installer-driven base."""

import pytest

from amibake._validate import load_toml
from amibake.builder import build_tree
from amibake.resolver import load_recipe_library, resolve
from amibake.verify import verify_exists

from .conftest import REPO_ROOT

RECIPES_ROOT = REPO_ROOT / "recipes"
ASSETS_ROOT = REPO_ROOT / "assets"
MANIFEST_PATH = REPO_ROOT / "manifests" / "os314.toml"
REAL_MEDIA = ASSETS_ROOT / "hyperion" / "AmigaOS-3.1.4-A500_A600_A2000.zip"

pytestmark = pytest.mark.skipif(
    not REAL_MEDIA.exists(),
    reason=f"no real AmigaOS 3.1.4 media at {REAL_MEDIA}",
)


def test_os314_builds_and_verifies_from_real_media(tmp_path):
    manifest = load_toml(MANIFEST_PATH)
    library = load_recipe_library(RECIPES_ROOT)
    result = resolve(MANIFEST_PATH, manifest, library)
    assert result.ok, [str(p) for p in result.problems]

    tree = build_tree(result.plan, tmp_path / "cache", ASSETS_ROOT)

    for pkg in (result.plan.base_package, *result.plan.packages):
        recipe = library[pkg.name]
        assert verify_exists(tree, pkg.name, recipe.doc) == []

    # Workbench disk content
    assert tree.get("SYS:Libs/diskfont.library").data
    # Extras disk content — confirms it isn't dropped as "just bonus" bulk
    assert tree.get("SYS:Tools/Commodities/Exchange").data
    # Storage disk content
    assert any(p.startswith("SYS:Storage/DOSDrivers/") for p in tree.paths())
    # Install-disk-sourced files, not Workbench/Storage
    assert tree.get("SYS:Libs/workbench.library").data
    assert tree.get("SYS:L/FastFileSystem").data
