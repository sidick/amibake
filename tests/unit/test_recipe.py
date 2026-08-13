import pytest

from amibake.recipe import validate_recipe

from .conftest import REPO_ROOT, errors_of

SHA = "0" * 64

VALID = f'''
[package]
name     = "amissl"
versions = ["5.20", "5.18"]
depends  = ["bsdsocket"]

[requires]
os  = ">= 3.0"
cpu = ">= 68020"
[requires.per-version."5.18"]
os = ">= 2.0"

[source.aminet]
url    = "util/libs/AmiSSL-{{version}}.lha"
sha256 = {{ "5.20" = "{SHA}", "5.18" = "{SHA}" }}

[install]
copy = [
  {{ from = "AmiSSL/Libs/#?", to = "SYS:Libs/", cpu-variant = true }},
]
envarc = [{{ name = "AmiSSL/opts", content = "x" }}]
user-startup = [{{ order = 50, lines = ["Assign AmiSSL: SYS:Devs/AmiSSL"] }}]
assigns = [{{ name = "AmiSSL", path = "SYS:Devs/AmiSSL" }}]

[verify]
exists = ["SYS:Libs/amisslmaster.library"]

[options.variant]
type     = "enum"
values   = ["light", "full"]
required = false
default  = "full"
[options.variant.requires.full]
os = ">= 3.1"
'''


def test_valid_recipe(write):
    path = write(VALID, name="recipe.toml", subdir="amissl")
    assert validate_recipe(path) == []


def test_shipped_recipes_lint_clean():
    recipes = sorted((REPO_ROOT / "recipes").rglob("recipe.toml"))
    assert recipes, "no shipped recipes found"
    for r in recipes:
        assert validate_recipe(r) == [], f"{r} should lint clean"


def _minimal(**overrides):
    """A minimal valid recipe, with sections replaceable per test."""
    parts = {
        "package": '[package]\nname = "pkg"\nversions = ["1.0"]\n',
        "source": f'[source.aminet]\nurl = "x/pkg.lha"\nsha256 = {{ "1.0" = "{SHA}" }}\n',
    }
    parts.update(overrides)
    return "\n".join(parts.values())


INVALID = [
    (_minimal(package="[package]\nversions = [\"1.0\"]\n"), "name"),
    (_minimal(package='[package]\nname = "pkg"\n'), "versions"),
    (_minimal(package='[package]\nname = "pkg"\nversions = []\n'), "versions"),
    (_minimal(package='[package]\nname = "pkg"\nversions = [5.20]\n'), "versions[0]"),
    (_minimal(package='[package]\nname = "pkg"\nversions = ["1.0"]\nfoo = 1\n'),
     "package].foo"),
    (_minimal(package='[package]\nname = "pkg"\nversions = ["1.0"]\ndepends = ["A B C"]\n'),
     "depends[0]"),
    (_minimal(package='[package]\nname = "pkg"\nversions = ["1.0"]\nstrategy = "magic"\n'),
     "strategy"),
    (_minimal() + '\n[requires]\nos = "3.0"\n', "requires].os"),
    (_minimal() + '\n[requires]\nemulator = ["fs-uae"]\n', "emulator[0]"),
    (_minimal() + '\n[requires.per-version."9.9"]\nos = ">= 2.0"\n', "per-version"),
    (_minimal(source=""), "[source]"),
    (_minimal(source='[source.aminet]\nsha256 = { "1.0" = "' + SHA + '" }\n'),
     "aminet].url"),
    (_minimal(source='[source.aminet]\nurl = "x/pkg.lha"\nsha256 = { "1.0" = "abc" }\n'),
     'sha256."1.0"'),
    (_minimal(source='[source.aminet]\nurl = "x/pkg.lha"\nsha256 = {}\n'), "sha256"),
    (_minimal(source='[source.assets]\npath = 3\n'), "assets].path"),
    (_minimal(source='[source.github]\nasset = "pkg.lha"\nsha256 = { "1.0" = "'
     + SHA + '" }\n'), "github].repo"),
    (_minimal(source='[source.github]\nrepo = "ownername"\nasset = "pkg.lha"\n'
     'sha256 = { "1.0" = "' + SHA + '" }\n'), "github].repo"),
    (_minimal(source='[source.github]\nrepo = "owner/name"\nsha256 = { "1.0" = "'
     + SHA + '" }\n'), "github].asset"),
    (_minimal(source='[source.github]\nrepo = "owner/name"\nasset = "pkg.lha"\n'
     'tag = "vX"\nsha256 = { "1.0" = "' + SHA + '" }\n'), "github].tag"),
    (_minimal(source='[source.github]\nrepo = "owner/name"\nasset = "pkg.lha"\n'
     'sha256 = { "1.0" = "abc" }\n'), 'github].sha256."1.0"'),
    (_minimal() + '\n[install]\ncopy = [{ from = "a" }]\n', "copy[0].to"),
    (_minimal() + '\n[install]\ncopy = [{ from = "a", to = "Libs" }]\n', "copy[0].to"),
    (_minimal() + '\n[install]\ncopy = [{ from = "a", to = "SYS:Libs/", when = "???" }]\n',
     "copy[0].when"),
    (_minimal() + '\n[install]\nuser-startup = [{ order = true, lines = [] }]\n',
     "user-startup[0].order"),
    (_minimal() + '\n[options.card]\nvalues = ["a"]\n', "type"),
    (_minimal() + '\n[options.card]\ntype = "enum"\n', "values"),
    (_minimal() + '\n[options.card]\ntype = "bool"\nvalues = ["a"]\n', "values"),
    (_minimal() + '\n[options.card]\ntype = "enum"\nvalues = ["a"]\ndefault = "b"\n',
     "default"),
    (_minimal() + '\n[options.card]\ntype = "enum"\nvalues = ["a"]\n'
     '[options.card.requires.zz]\nos = ">= 3.0"\n', "requires.zz"),
]


@pytest.mark.parametrize(("text", "field"), INVALID, ids=[f[1] for f in INVALID])
def test_invalid_recipes(write, text, field):
    problems = errors_of(validate_recipe(write(text, name="recipe.toml", subdir="pkg")))
    assert problems, "expected at least one error"
    assert any(field in p.field for p in problems), (
        f"no problem mentioning {field!r} in {[p.field for p in problems]}")
    for p in problems:
        assert p.remedy, "every error carries a remedy"


def test_directory_name_must_match_package_name(write):
    path = write(_minimal(), name="recipe.toml", subdir="wrongname")
    problems = errors_of(validate_recipe(path))
    assert any("does not match recipe directory" in p.problem for p in problems)


def test_hook_lints_as_warning(write):
    text = _minimal() + '\n[hook]\nscript = "hook.py"\n'
    problems = validate_recipe(write(text, name="recipe.toml", subdir="pkg"))
    warnings = [p for p in problems if p.severity == "warning"]
    assert warnings and "hook" in warnings[0].problem
    assert not errors_of(problems)


def test_valid_github_source(write):
    text = (
        '[package]\nname = "pkg"\nversions = ["1.0", "2.0"]\n\n'
        '[source.github]\nrepo = "owner/name"\n'
        'asset = "pkg-{version}.lha"\n'
        f'sha256 = {{ "1.0" = "{SHA}", "2.0" = "{SHA}" }}\n'
    )
    problems = validate_recipe(write(text, name="recipe.toml", subdir="pkg"))
    assert problems == []


def test_multi_version_asset_needs_placeholder(write):
    text = (
        '[package]\nname = "pkg"\nversions = ["1.0", "2.0"]\n\n'
        '[source.github]\nrepo = "owner/name"\nasset = "pkg.lha"\n'
        f'sha256 = {{ "1.0" = "{SHA}", "2.0" = "{SHA}" }}\n'
    )
    problems = errors_of(validate_recipe(write(text, name="recipe.toml", subdir="pkg")))
    assert any("{version}" in p.problem for p in problems)


def test_multi_version_url_needs_placeholder(write):
    text = (
        '[package]\nname = "pkg"\nversions = ["1.0", "2.0"]\n\n'
        '[source.aminet]\nurl = "x/pkg.lha"\n'
        f'sha256 = {{ "1.0" = "{SHA}", "2.0" = "{SHA}" }}\n'
    )
    problems = errors_of(validate_recipe(write(text, name="recipe.toml", subdir="pkg")))
    assert any("{version}" in p.problem for p in problems)
