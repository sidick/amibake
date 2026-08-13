"""Resolver tests against a small fixture recipe library, not the real
recipes/ tree — these exercise resolution mechanics (versions,
capabilities, [requires] cross-axis checks, options) independent of any
real package."""


from amibake._validate import load_toml
from amibake.resolver import load_recipe_library, resolve

SHA = "0" * 64


def _lib(tmp_path, recipes: dict[str, str]):
    """Write {name: recipe.toml text} under tmp_path/recipes/<name>/recipe.toml
    and return the loaded library."""
    root = tmp_path / "recipes"
    for name, text in recipes.items():
        d = root / name
        d.mkdir(parents=True)
        (d / "recipe.toml").write_text(text)
    return load_recipe_library(root)


def _manifest(tmp_path, text: str):
    path = tmp_path / "manifest.toml"
    path.write_text(text)
    return path, load_toml(path)


OS32_BASE = '''
[package]
name     = "os32-fixture"
versions = ["3.2.2"]
strategy = "extract"

[base]
os-version        = "3.2.2"
kickstart-version = "47.102"
'''

WB13_BASE = '''
[package]
name     = "wb13-fixture"
versions = ["1.3"]
strategy = "extract"

[base]
os-version = "1.3"
'''

AMISSL = f'''
[package]
name     = "amissl-fixture"
versions = ["5.27", "5.20"]

[requires]
os  = ">= 3.0"
cpu = ">= 68020"

[source.aminet]
url    = "libs/amissl-{{version}}.lha"
sha256 = {{ "5.27" = "{SHA}", "5.20" = "{SHA}" }}

[install]
copy = [{{ from = "Libs/#?", to = "SYS:Libs/" }}]
'''


class TestBaseAndVersions:
    def test_unknown_base_is_named(self, tmp_path):
        library = _lib(tmp_path, {})
        path, manifest = _manifest(tmp_path, 'base = "nope"\n')
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("nope" in p.problem for p in result.problems)

    def test_simple_package_resolves(self, tmp_path):
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "amissl-fixture": AMISSL})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'machine = { cpu = "68030" }\n'
            'packages = ["amissl-fixture = 5.27"]\n'
        ))
        result = resolve(path, manifest, library)
        assert result.ok, result.problems
        assert result.plan.packages[0].name == "amissl-fixture"
        assert result.plan.packages[0].version == "5.27"

    def test_picks_highest_satisfying_version_amiga_order(self, tmp_path):
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "amissl-fixture": AMISSL})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'machine = { cpu = "68030" }\n'
            'packages = ["amissl-fixture >= 5.0"]\n'
        ))
        result = resolve(path, manifest, library)
        assert result.ok, result.problems
        assert result.plan.packages[0].version == "5.27"

    def test_no_version_satisfies_constraint(self, tmp_path):
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "amissl-fixture": AMISSL})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'machine = { cpu = "68030" }\n'
            'packages = ["amissl-fixture >= 6.0"]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("no version" in p.problem for p in result.problems)

    def test_unknown_package_is_named(self, tmp_path):
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\npackages = ["nonexistent"]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("nonexistent" in p.problem for p in result.problems)


class TestRequiresValidation:
    def test_ks13_base_rejects_os3_package_with_named_error(self, tmp_path):
        """Proposal success criterion: a KS 1.3 base paired with a >= 3.0
        package fails with the resolver's named-package error."""
        library = _lib(tmp_path, {"wb13-fixture": WB13_BASE, "amissl-fixture": AMISSL})
        path, manifest = _manifest(tmp_path, (
            'base = "wb13-fixture"\n'
            'machine = { cpu = "68030" }\n'
            'packages = ["amissl-fixture = 5.27"]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        problem = next(p for p in result.problems if "requires.os" in p.field)
        assert "amissl-fixture" in problem.field
        assert "wb13-fixture" in problem.problem
        assert ">= 3.0" in problem.problem

    def test_base_missing_os_version_metadata_is_named(self, tmp_path):
        bare_base = '[package]\nname = "bare-fixture"\nversions = ["1.0"]\n'
        library = _lib(tmp_path, {"bare-fixture": bare_base, "amissl-fixture": AMISSL})
        path, manifest = _manifest(tmp_path, (
            'base = "bare-fixture"\n'
            'machine = { cpu = "68030" }\n'
            'packages = ["amissl-fixture = 5.27"]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("does not declare an os-version" in p.problem for p in result.problems)

    def test_cpu_floor_enforced(self, tmp_path):
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "amissl-fixture": AMISSL})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'machine = { cpu = "68000" }\n'
            'packages = ["amissl-fixture = 5.27"]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("requires.cpu" in p.field for p in result.problems)

    def test_mmu_requirement_enforced(self, tmp_path):
        mmu_pkg = '''
[package]
name = "enforcer-fixture"
versions = ["1.0"]

[requires]
mmu = true
'''
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "enforcer-fixture": mmu_pkg})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'machine = { cpu = "68030" }\n'
            'packages = ["enforcer-fixture"]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("MMU" in p.problem for p in result.problems)

        path2, manifest2 = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'machine = { cpu = "68030", mmu = true }\n'
            'packages = ["enforcer-fixture"]\n'
        ))
        result2 = resolve(path2, manifest2, library)
        assert result2.ok, result2.problems


class TestCapabilities:
    UAE_ONLY_EMULATION = '''
[package]
name     = "uae-only-emulation-fixture"
versions = ["1.0"]
provides = ["bsdsocket"]

[requires]
emulator = ["amiberry", "winuae"]
'''

    ROADSHOW = '''
[package]
name     = "roadshow-fixture"
versions = ["1.0"]
provides = ["bsdsocket"]

[source.assets]
path = "Roadshow-{version}.lha"

[install]
copy = [{ from = "Roadshow/#?", to = "SYS:" }]
'''

    def test_single_provider_resolves_unambiguously(self, tmp_path):
        depender = '''
[package]
name    = "app-fixture"
versions = ["1.0"]
depends  = ["bsdsocket"]
'''
        library = _lib(tmp_path, {
            "os32-fixture": OS32_BASE,
            "app-fixture": depender,
            "roadshow-fixture": self.ROADSHOW,
        })
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\npackages = ["app-fixture"]\n'
        ))
        result = resolve(path, manifest, library)
        assert result.ok, result.problems
        names = {p.name for p in result.plan.packages}
        assert names == {"app-fixture", "roadshow-fixture"}

    def test_ambiguous_provider_lists_candidates(self, tmp_path):
        depender = '[package]\nname = "app-fixture"\nversions = ["1.0"]\ndepends = ["bsdsocket"]\n'
        library = _lib(tmp_path, {
            "os32-fixture": OS32_BASE,
            "app-fixture": depender,
            "roadshow-fixture": self.ROADSHOW,
            "uae-only-emulation-fixture": self.UAE_ONLY_EMULATION,
        })
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'machine = { cpu = "68030" }\n'
            'emit = ["amiberry"]\n'
            'packages = ["app-fixture"]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        problem = next(p for p in result.problems if "ambiguous" in p.problem)
        assert "roadshow-fixture" in problem.problem
        assert "uae-only-emulation-fixture" in problem.problem

    def test_manifest_providers_resolves_ambiguity(self, tmp_path):
        depender = '[package]\nname = "app-fixture"\nversions = ["1.0"]\ndepends = ["bsdsocket"]\n'
        library = _lib(tmp_path, {
            "os32-fixture": OS32_BASE,
            "app-fixture": depender,
            "roadshow-fixture": self.ROADSHOW,
            "uae-only-emulation-fixture": self.UAE_ONLY_EMULATION,
        })
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'packages = ["app-fixture"]\n'
            '[providers]\n'
            'bsdsocket = "roadshow-fixture"\n'
        ))
        result = resolve(path, manifest, library)
        assert result.ok, result.problems
        assert {p.name for p in result.plan.packages} == {"app-fixture", "roadshow-fixture"}

    def test_noop_provider_requires_matching_emulator(self, tmp_path):
        """Generic resolver mechanics: a no-op capability provider whose
        [requires].emulator the manifest's emit list doesn't cover fails
        with a named, remediable error. This fixture is *not* a stand-in
        for the real bsdsocket-emulation recipe — that one genuinely
        supports Copperline too (see recipes/bsdsocket-emulation); this
        one is deliberately UAE-only so there's still a real "package
        needs an emulator emit doesn't have" fixture to exercise (the
        real bsdsocket-emulation itself no longer has an unsupported-
        emulator case at all)."""
        depender = '[package]\nname = "app-fixture"\nversions = ["1.0"]\ndepends = ["bsdsocket"]\n'
        library = _lib(tmp_path, {
            "os32-fixture": OS32_BASE,
            "app-fixture": depender,
            "uae-only-emulation-fixture": self.UAE_ONLY_EMULATION,
        })
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'emit = ["copperline"]\n'
            'packages = ["app-fixture"]\n'
            '[providers]\n'
            'bsdsocket = "uae-only-emulation-fixture"\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("requires.emulator" in p.field for p in result.problems)

    def test_mismatched_provider_override_is_named(self, tmp_path):
        library = _lib(tmp_path, {
            "os32-fixture": OS32_BASE,
            "amissl-fixture": AMISSL,
        })
        # providers table names a real recipe not actually providing the
        # capability it's assigned to — only checked when something depends
        # on that capability, so add a depender and reload the library.
        depender = '[package]\nname = "app2-fixture"\nversions = ["1.0"]\ndepends = ["bsdsocket"]\n'
        (tmp_path / "recipes" / "app2-fixture").mkdir()
        (tmp_path / "recipes" / "app2-fixture" / "recipe.toml").write_text(depender)
        library = load_recipe_library(tmp_path / "recipes")
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'machine = { cpu = "68030" }\n'
            'packages = ["app2-fixture"]\n'
            '[providers]\n'
            'bsdsocket = "amissl-fixture"\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("does not declare provides" in p.problem for p in result.problems)


class TestOptions:
    P96 = f'''
[package]
name     = "p96-fixture"
versions = ["3.2"]

[source.aminet]
url    = "gfx/board/p96-{{version}}.lha"
sha256 = {{ "3.2" = "{SHA}" }}

[install]
copy = [{{ from = "P96/#?", to = "SYS:" }}]

[options.card]
type     = "enum"
values   = ["uaegfx", "zz9000"]
required = true

[options.card.requires.uaegfx]
emulator = ["amiberry", "winuae"]
'''

    def test_required_option_missing_is_named(self, tmp_path):
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "p96-fixture": self.P96})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\npackages = ["p96-fixture"]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("card" in p.field for p in result.problems)

    def test_option_answered_resolves(self, tmp_path):
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "p96-fixture": self.P96})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'emit = ["amiberry"]\n'
            'packages = [{ name = "p96-fixture", card = "uaegfx" }]\n'
        ))
        result = resolve(path, manifest, library)
        assert result.ok, result.problems
        assert result.plan.packages[0].options == {"card": "uaegfx"}

    def test_option_value_cross_axis_requirement(self, tmp_path):
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "p96-fixture": self.P96})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'emit = ["copperline"]\n'
            'packages = [{ name = "p96-fixture", card = "uaegfx" }]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("requires.emulator" in p.field for p in result.problems)

    def test_unknown_option_is_named(self, tmp_path):
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "p96-fixture": self.P96})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'emit = ["amiberry"]\n'
            'packages = [{ name = "p96-fixture", card = "uaegfx", turbo = true }]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("unknown option" in p.problem for p in result.problems)

    def test_invalid_enum_value_is_named(self, tmp_path):
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "p96-fixture": self.P96})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'emit = ["amiberry"]\n'
            'packages = [{ name = "p96-fixture", card = "voodoo" }]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("voodoo" in p.problem for p in result.problems)

    def test_auto_resolves_to_default(self, tmp_path):
        p96_with_default = self.P96.replace(
            'required = true', 'required = true\ndefault  = "zz9000"')
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "p96-fixture": p96_with_default})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\n'
            'emit = ["amiberry"]\n'
            'packages = [{ name = "p96-fixture", card = "auto" }]\n'
        ))
        result = resolve(path, manifest, library)
        assert result.ok, result.problems
        assert result.plan.packages[0].options == {"card": "zz9000"}


class TestConflictsAndCycles:
    def test_conflicting_packages_named(self, tmp_path):
        a = '[package]\nname = "a-fixture"\nversions = ["1.0"]\nconflicts = ["b-fixture"]\n'
        b = '[package]\nname = "b-fixture"\nversions = ["1.0"]\n'
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "a-fixture": a, "b-fixture": b})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\npackages = ["a-fixture", "b-fixture"]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("conflicts" in p.problem for p in result.problems)

    def test_circular_dependency_named(self, tmp_path):
        a = '[package]\nname = "a-fixture"\nversions = ["1.0"]\ndepends = ["b-fixture"]\n'
        b = '[package]\nname = "b-fixture"\nversions = ["1.0"]\ndepends = ["a-fixture"]\n'
        library = _lib(tmp_path, {"os32-fixture": OS32_BASE, "a-fixture": a, "b-fixture": b})
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\npackages = ["a-fixture"]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("circular" in p.problem for p in result.problems)

    def test_shared_dependency_resolves_once_and_version_conflict_named(self, tmp_path):
        common = '[package]\nname = "common-fixture"\nversions = ["2.0", "1.0"]\n'
        a = ('[package]\nname = "a-fixture"\nversions = ["1.0"]\n'
             'depends = ["common-fixture = 2.0"]\n')
        b = ('[package]\nname = "b-fixture"\nversions = ["1.0"]\n'
             'depends = ["common-fixture = 1.0"]\n')
        library = _lib(tmp_path, {
            "os32-fixture": OS32_BASE, "common-fixture": common,
            "a-fixture": a, "b-fixture": b,
        })
        path, manifest = _manifest(tmp_path, (
            'base = "os32-fixture"\npackages = ["a-fixture", "b-fixture"]\n'
        ))
        result = resolve(path, manifest, library)
        assert not result.ok
        assert any("already resolved" in p.problem for p in result.problems)


def test_exemplar_manifest_reports_missing_base_cleanly():
    """The shipped os32-p96-amissl.toml references a real base (os3.2.2)
    that doesn't exist yet (its base recipe arrives in a later milestone) —
    resolve must fail with a clean, well-worded error, not a crash."""
    from pathlib import Path

    from amibake.resolver import load_recipe_library

    root = Path(__file__).resolve().parents[2]
    manifest_path = root / "manifests" / "os32-p96-amissl.toml"
    manifest = load_toml(manifest_path)
    library = load_recipe_library(root / "recipes")
    result = resolve(manifest_path, manifest, library)
    assert not result.ok
    assert any("os3.2.2" in p.problem for p in result.problems)
