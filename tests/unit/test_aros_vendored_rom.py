"""The shipped AROS base vendors its own ROM (recipes/aros68k/rom/).

Guards the property the vendoring exists for: an AROS build can emit an
emulator config on a machine with no assets/ and no Kickstart, however
long ago the nightly it was pinned to was pruned from SourceForge.
"""

import tomllib

from .conftest import REPO_ROOT

RECIPE = REPO_ROOT / "recipes" / "aros68k" / "recipe.toml"


def _base():
    return tomllib.loads(RECIPE.read_text())["base"]


def test_recipe_declares_a_vendored_rom_and_the_files_are_there():
    base = _base()
    for key, size in (("rom-file", 512 * 1024), ("rom-ext-file", 512 * 1024)):
        path = RECIPE.parent / base[key]
        assert path.is_file(), f"{key} names a missing file: {path}"
        # A 512K ROM image, not a Git LFS pointer or a truncated copy.
        assert path.stat().st_size == size


def test_aros_base_has_no_kickstart_version_to_fall_back_on():
    """If AROS ever grew one, the fallback in cli._resolve_rom_paths
    would start mattering for it — and the ordering (vendored wins)
    would need a deliberate look, not a silent inheritance."""
    assert "kickstart-version" not in _base()


def test_vendored_rom_licence_travels_with_the_binaries():
    """The APL requires it; rom/README.md records the provenance."""
    rom_dir = RECIPE.parent / "rom"
    assert "AROS PUBLIC LICENSE" in (rom_dir / "LICENSE").read_text()
    assert (rom_dir / "README.md").is_file()
