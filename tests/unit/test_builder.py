"""M2 exit criterion: a fixture manifest with fake recipes builds
end-to-end to an internal tree; identical inputs rebuild byte-identically
from a cold cache, and a shared layer is reused across two manifests."""

import hashlib

from amibake.builder import build_tree
from amibake.plan import BaseInfo, BuildPlan, ResolvedPackage

from .conftest import make_lha_archive

ARCHIVE = make_lha_archive({"AmiSSL/Libs/amisslmaster.library": b"libdata"})
ARCHIVE_SHA = hashlib.sha256(ARCHIVE).hexdigest()


def _fake_http_get(calls):
    def _get(url):
        calls.append(url)
        return ARCHIVE
    return _get


def _write_recipe(tmp_path, name="amissl"):
    path = tmp_path / f"{name}.recipe.toml"
    path.write_text(
        "[install]\n"
        'copy = [{ from = "AmiSSL/Libs/#?", to = "SYS:Libs/" }]\n'
    )
    return path


def _plan_with_one_package(tmp_path):
    recipe_path = _write_recipe(tmp_path)
    pkg = ResolvedPackage(
        name="amissl", version="5.27", options={},
        recipe_path=str(recipe_path),
        recipe_sha256=hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
        sources={"github": {"repo": "owner/name", "asset": "pkg.lha",
                            "tag": "5.27", "sha256": ARCHIVE_SHA}},
    )
    return BuildPlan(
        base=BaseInfo(name="fixture-base", os_version="3.2.2"),
        machine={"cpu": "68030"},
        packages=(pkg,),
        output=("hdf",),
        emit=(),
    )


def test_build_tree_end_to_end(tmp_path):
    plan = _plan_with_one_package(tmp_path)
    cache_root = tmp_path / "cache"
    calls = []
    tree = build_tree(plan, cache_root, http_get=_fake_http_get(calls))
    assert tree.get("SYS:Libs/amisslmaster.library").data == b"libdata"
    assert len(calls) == 1


def test_rebuild_from_cold_cache_is_byte_identical(tmp_path):
    plan = _plan_with_one_package(tmp_path)
    cache_a = tmp_path / "cache-a"
    cache_b = tmp_path / "cache-b"
    tree_a = build_tree(plan, cache_a, http_get=_fake_http_get([]))
    tree_b = build_tree(plan, cache_b, http_get=_fake_http_get([]))
    assert tree_a.content_hash() == tree_b.content_hash()


def test_cache_hit_skips_fetch_on_second_build(tmp_path):
    plan = _plan_with_one_package(tmp_path)
    cache_root = tmp_path / "cache"
    calls = []
    build_tree(plan, cache_root, http_get=_fake_http_get(calls))
    build_tree(plan, cache_root, http_get=_fake_http_get(calls))
    assert len(calls) == 1  # second build hit the layer cache, no re-fetch


def test_shared_prefix_layer_reused_across_two_plans(tmp_path):
    """Two manifests sharing the same first package reuse that layer's
    cache entry — the point of chaining parent keys."""
    recipe_a = _write_recipe(tmp_path, "shared")
    shared_pkg = ResolvedPackage(
        name="shared", version="1.0", options={},
        recipe_path=str(recipe_a),
        recipe_sha256=hashlib.sha256(recipe_a.read_bytes()).hexdigest(),
        sources={"github": {"repo": "owner/name", "asset": "pkg.lha",
                            "tag": "1.0", "sha256": ARCHIVE_SHA}},
    )
    base = BaseInfo(name="fixture-base", os_version="3.2.2")
    plan1 = BuildPlan(base=base, machine={}, packages=(shared_pkg,),
                      output=("hdf",), emit=())
    plan2 = BuildPlan(base=base, machine={}, packages=(shared_pkg,),
                      output=("dir",), emit=())  # different output, same layer

    cache_root = tmp_path / "cache"
    calls = []
    build_tree(plan1, cache_root, http_get=_fake_http_get(calls))
    assert len(calls) == 1
    build_tree(plan2, cache_root, http_get=_fake_http_get(calls))
    assert len(calls) == 1  # plan2's identical package hit the same cache entry


def test_no_op_package_skips_fetch(tmp_path):
    recipe_path = tmp_path / "noop.recipe.toml"
    recipe_path.write_text("")  # no [install] at all
    pkg = ResolvedPackage(
        name="bsdsocket-emulation", version="1.0", options={},
        recipe_path=str(recipe_path),
        recipe_sha256=hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
        sources={},
    )
    plan = BuildPlan(
        base=BaseInfo(name="fixture-base", os_version="3.2.2"), machine={},
        packages=(pkg,), output=("hdf",), emit=(),
    )
    calls = []
    tree = build_tree(plan, tmp_path / "cache", http_get=_fake_http_get(calls))
    assert calls == []
    assert tree.paths() == []
