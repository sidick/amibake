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


class HookError(Exception):
    pass


def build_tree(plan: BuildPlan, cache_root: Path, assets_root: Path | None = None,
               http_get: fetch.HttpGet = fetch.default_http_get,
               use_cache: bool = True, allow_hooks: bool = False) -> Tree:
    tree = Tree()
    parent_key: str | None = None

    for pkg in (plan.base_package, *plan.packages):
        tree, parent_key = _apply_one(
            tree, parent_key, pkg, cache_root, assets_root, http_get, use_cache, allow_hooks)

    return tree


def _apply_one(tree: Tree, parent_key: str | None, pkg: ResolvedPackage,
               cache_root: Path, assets_root: Path | None, http_get: fetch.HttpGet,
               use_cache: bool, allow_hooks: bool) -> tuple[Tree, str]:
    key = layer.compute_layer_key(
        parent_key, pkg.recipe_sha256, pkg.version, pkg.options, _archive_sha256(pkg))
    if use_cache:
        cached = layer.load_layer_cache(key, cache_root)
        if cached is not None:
            return cached, key

    recipe_path = Path(pkg.recipe_path)
    recipe_doc = load_toml(recipe_path)
    install = recipe_doc.get("install") or {}
    if install.get("copy"):
        archive_path = fetch.fetch_sources(pkg.sources, cache_root, assets_root, http_get)
        archive_tree = extract.extract_archive(archive_path)
    else:
        archive_tree = Tree()
    tree = layer.apply_layer(tree, pkg.name, install, archive_tree, pkg.options)

    hook = recipe_doc.get("hook")
    if hook:
        if not allow_hooks:
            raise HookError(
                f"{pkg.name}: this recipe declares a [hook] ({hook['script']!r}) — "
                f"review the script (it runs arbitrary Python during the build), "
                f"then pass --allow-hooks to amibake build to run it")
        tree = _run_hook(tree, archive_tree, pkg, recipe_path, hook)

    if use_cache:
        layer.save_layer_cache(tree, key, cache_root)
    return tree, key


def _run_hook(tree: Tree, archive_tree: Tree, pkg: ResolvedPackage,
             recipe_path: Path, hook: dict) -> Tree:
    """The fenced escape hatch: for the genuinely scripted-installer
    minority the declarative [install] schema can't express. A hook
    script sits next to its recipe.toml and defines `apply(tree,
    archive, options) -> Tree`, called after [install]'s own copy/
    envarc/user-startup/assigns/files have already been applied — same
    composition order as everything else, declarative-first. Only runs
    when the caller explicitly passed --allow-hooks; see docs/limits.md
    for why this isn't on by default."""
    script_path = recipe_path.parent / hook["script"]
    # exec() straight from source, not importlib's file-based loader: the
    # latter's __pycache__ bytecode cache was observed serving a stale
    # compiled hook.py after an in-place edit despite a changed mtime —
    # exec() never touches that cache at all, so there's nothing to
    # invalidate incorrectly.
    namespace: dict = {"__file__": str(script_path)}
    try:
        source = script_path.read_text()
    except OSError as e:
        raise HookError(f"{pkg.name}: can't read hook script {script_path}: {e}") from e
    try:
        exec(compile(source, str(script_path), "exec"), namespace)
    except Exception as e:
        raise HookError(f"{pkg.name}: {script_path} raised while loading: {e}") from e
    apply_fn = namespace.get("apply")
    if apply_fn is None:
        raise HookError(
            f"{pkg.name}: {script_path} has no top-level `apply(tree, archive, "
            f"options)` function")
    result = apply_fn(tree, archive_tree, pkg.options)
    if not isinstance(result, Tree):
        raise HookError(
            f"{pkg.name}: {script_path}'s apply() must return a Tree, got "
            f"{type(result).__name__}")
    return result


def _archive_sha256(pkg: ResolvedPackage) -> str:
    """Feeds the layer cache key. Network sources (aminet/github/url)
    declare a checksum the resolver already captured, so a changed
    upstream archive busts the cache correctly. Assets have an *optional*
    declared checksum (nothing to hash ahead of time for proprietary
    media unless the recipe author independently knows it) — when
    absent, an asset file edited in place without a version bump won't
    invalidate the cache; use --no-cache or bump the recipe version when
    that matters."""
    for kind in ("assets", "github", "aminet", "url"):
        src = pkg.sources.get(kind)
        if src and src.get("sha256"):
            return src["sha256"]
    return ""
