"""Ties fetch, extract, and layer together: BuildPlan -> Tree.

The base is applied first as a layer exactly like any package (same
[install]/fetch/cache machinery) — plan.base_package is the resolver's
resolved record for it — then each of plan.packages in dependency order.
"""

from __future__ import annotations

from pathlib import Path

from . import extract, fetch, layer
from ._validate import load_toml
from .plan import BuildPlan, ResolvedPackage
from .tree import Tree


def build_tree(plan: BuildPlan, cache_root: Path, assets_root: Path | None = None,
               http_get: fetch.HttpGet = fetch.default_http_get,
               use_cache: bool = True) -> Tree:
    tree = Tree()
    parent_key: str | None = None

    for pkg in (plan.base_package, *plan.packages):
        tree, parent_key = _apply_one(
            tree, parent_key, pkg, cache_root, assets_root, http_get, use_cache)

    return tree


def _apply_one(tree: Tree, parent_key: str | None, pkg: ResolvedPackage,
               cache_root: Path, assets_root: Path | None, http_get: fetch.HttpGet,
               use_cache: bool) -> tuple[Tree, str]:
    key = layer.compute_layer_key(
        parent_key, pkg.recipe_sha256, pkg.version, pkg.options, _archive_sha256(pkg))
    if use_cache:
        cached = layer.load_layer_cache(key, cache_root)
        if cached is not None:
            return cached, key

    recipe_doc = load_toml(Path(pkg.recipe_path))
    install = recipe_doc.get("install") or {}
    if install.get("copy"):
        archive_path = fetch.fetch_sources(pkg.sources, cache_root, assets_root, http_get)
        archive_tree = extract.extract_archive(archive_path)
    else:
        archive_tree = Tree()
    tree = layer.apply_layer(tree, pkg.name, install, archive_tree, pkg.options)

    if use_cache:
        layer.save_layer_cache(tree, key, cache_root)
    return tree, key


def _archive_sha256(pkg: ResolvedPackage) -> str:
    """Feeds the layer cache key. Network sources (aminet/github) declare
    a checksum the resolver already captured, so a changed upstream
    archive busts the cache correctly. Assets have no declared checksum
    (they're user-supplied, verified only by presence) — an asset file
    edited in place without a version bump won't invalidate the cache;
    use --no-cache or bump the recipe version when that matters."""
    for kind in ("assets", "github", "aminet"):
        src = pkg.sources.get(kind)
        if src and src.get("sha256"):
            return src["sha256"]
    return ""
