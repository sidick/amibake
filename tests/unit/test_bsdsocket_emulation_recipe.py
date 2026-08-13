"""M6: bsdsocket-emulation is a real, shipped no-op capability provider
(recipes/bsdsocket-emulation) -- unlike the synthetic UAE-only fixture
in test_resolver.py's TestCapabilities, it genuinely resolves against
all three emulators (Copperline included; see the recipe's own
comments for why). resolve() doesn't fetch anything, so this needs no
network or real assets -- aros68k is a real base with no [source.assets]
dependency to satisfy."""

import pytest

from amibake._validate import load_toml
from amibake.resolver import load_recipe_library, resolve

from .conftest import REPO_ROOT

RECIPES_ROOT = REPO_ROOT / "recipes"


def _manifest(tmp_path, emit):
    text = (
        'base = "aros68k"\n'
        f'emit = ["{emit}"]\n'
        'packages = ["bsdsocket-emulation"]\n'
    )
    path = tmp_path / "manifest.toml"
    path.write_text(text)
    return path, load_toml(path)


@pytest.mark.parametrize("emit", ["copperline", "amiberry", "winuae"])
def test_resolves_against_every_supported_emulator(tmp_path, emit):
    library = load_recipe_library(RECIPES_ROOT)
    path, manifest = _manifest(tmp_path, emit)
    result = resolve(path, manifest, library)
    assert result.ok, [str(p) for p in result.problems]
    assert {p.name for p in result.plan.packages} == {"bsdsocket-emulation"}
