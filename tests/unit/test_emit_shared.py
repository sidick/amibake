import hashlib

from amibake.emit import collect_emulator_config
from amibake.plan import BaseInfo, BuildPlan, ResolvedPackage
from amibake.resolver import LoadedRecipe


def _recipe(name, doc):
    return LoadedRecipe(name=name, path=f"/fake/{name}.toml", doc=doc)


def _pkg(name):
    return ResolvedPackage(name=name, version="1.0", recipe_sha256=hashlib.sha256(b"x").hexdigest())


def test_collects_directives_from_base_and_packages():
    library = {
        "somebase": _recipe("somebase", {"emulator-config": {"amiberry": {"a": "1"}}}),
        "somepkg": _recipe("somepkg", {"emulator-config": {"amiberry": {"b": "2"}}}),
    }
    plan = BuildPlan(
        base=BaseInfo(name="somebase"), base_package=_pkg("somebase"),
        machine={}, packages=(_pkg("somepkg"),), output=("hdf",), emit=(),
    )
    assert collect_emulator_config(plan, library, "amiberry") == {"a": "1", "b": "2"}


def test_later_package_wins_on_conflict():
    library = {
        "somebase": _recipe("somebase", {"emulator-config": {"amiberry": {"k": "base"}}}),
        "somepkg": _recipe("somepkg", {"emulator-config": {"amiberry": {"k": "pkg"}}}),
    }
    plan = BuildPlan(
        base=BaseInfo(name="somebase"), base_package=_pkg("somebase"),
        machine={}, packages=(_pkg("somepkg"),), output=("hdf",), emit=(),
    )
    assert collect_emulator_config(plan, library, "amiberry") == {"k": "pkg"}


def test_other_emitters_ignored():
    directives = {"copperline": {"hostsocket.net": "host"}}
    library = {"somebase": _recipe("somebase", {"emulator-config": directives})}
    plan = BuildPlan(
        base=BaseInfo(name="somebase"), base_package=_pkg("somebase"),
        machine={}, packages=(), output=("hdf",), emit=(),
    )
    assert collect_emulator_config(plan, library, "amiberry") == {}
    assert collect_emulator_config(plan, library, "copperline") == {"hostsocket.net": "host"}


def test_manifest_directives_win_over_recipes():
    library = {
        "somebase": _recipe("somebase", {"emulator-config": {
            "copperline": {"k": "recipe", "only-recipe": "r"}}}),
    }
    plan = BuildPlan(
        base=BaseInfo(name="somebase"), base_package=_pkg("somebase"),
        machine={}, packages=(), output=("hdf",), emit=(),
        emulator_config={"copperline": {"k": "manifest", "only-manifest": "m"}},
    )
    assert collect_emulator_config(plan, library, "copperline") == {
        "k": "manifest", "only-recipe": "r", "only-manifest": "m"}


def test_no_directives_is_empty():
    library = {"somebase": _recipe("somebase", {})}
    plan = BuildPlan(
        base=BaseInfo(name="somebase"), base_package=_pkg("somebase"),
        machine={}, packages=(), output=("hdf",), emit=(),
    )
    assert collect_emulator_config(plan, library, "amiberry") == {}
