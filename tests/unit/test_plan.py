import tomllib

from amibake.plan import BaseInfo, BuildPlan, ResolvedPackage, format_lockfile


def _base_package():
    return ResolvedPackage(
        name="os32-fixture", version="3.2.2", options={},
        recipe_path="recipes/os32-fixture/recipe.toml",
        recipe_sha256="d" * 64,
        sources={"assets": {"path": "os32-media.iso"}},
    )


def _plan():
    return BuildPlan(
        base=BaseInfo(name="os32-fixture", os_version="3.2.2", kickstart_version="47.102"),
        base_package=_base_package(),
        machine={"cpu": "68030", "fpu": True, "mmu": True},
        packages=(
            ResolvedPackage(
                name="roadshow-fixture", version="1.0", options={},
                recipe_path="recipes/roadshow-fixture/recipe.toml",
                recipe_sha256="a" * 64,
                sources={"assets": {"path": "Roadshow-1.0.lha"}},
            ),
            ResolvedPackage(
                name="p96-fixture", version="3.2", options={"card": "uaegfx"},
                recipe_path="recipes/p96-fixture/recipe.toml",
                recipe_sha256="b" * 64,
                sources={"aminet": {"url": "gfx/board/p96-3.2.lha", "sha256": "c" * 64}},
            ),
        ),
        output=("hdf", "dir"),
        emit=("copperline",),
    )


def test_lockfile_round_trips_through_toml():
    plan = _plan()
    text = format_lockfile(plan)
    parsed = tomllib.loads(text)
    assert parsed["base"]["name"] == "os32-fixture"
    assert parsed["base"]["os-version"] == "3.2.2"
    assert parsed["base"]["version"] == "3.2.2"
    assert parsed["base"]["recipe-sha256"] == "d" * 64
    assert parsed["base"]["sources"]["assets"]["path"] == "os32-media.iso"
    assert parsed["machine"]["cpu"] == "68030"
    assert parsed["output"] == ["hdf", "dir"]
    assert parsed["emit"] == ["copperline"]
    names = [p["name"] for p in parsed["package"]]
    assert names == ["roadshow-fixture", "p96-fixture"]
    p96 = parsed["package"][1]
    assert p96["version"] == "3.2"
    assert p96["options"] == {"card": "uaegfx"}
    assert p96["sources"]["aminet"]["sha256"] == "c" * 64
    roadshow = parsed["package"][0]
    assert roadshow["sources"]["assets"]["path"] == "Roadshow-1.0.lha"


def test_lockfile_is_deterministic():
    plan = _plan()
    assert format_lockfile(plan) == format_lockfile(plan)


def test_lockfile_omits_absent_kickstart_version():
    plan = BuildPlan(
        base=BaseInfo(name="aros68k-fixture", os_version="1.0"),
        base_package=ResolvedPackage(
            name="aros68k-fixture", version="1.0", recipe_path="x", recipe_sha256="e" * 64),
        machine={},
        packages=(),
        output=("hdf",),
        emit=(),
    )
    text = format_lockfile(plan)
    parsed = tomllib.loads(text)
    assert "kickstart-version" not in parsed["base"]
