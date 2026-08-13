"""Execute a recipe's [verify] block against a built Tree."""

from __future__ import annotations

from .tree import Tree


def verify_exists(tree: Tree, recipe_name: str, recipe_doc: dict) -> list[str]:
    """Check a recipe's [verify].exists paths against the built tree.
    Returns a list of human-readable problem strings; empty means pass."""
    exists = (recipe_doc.get("verify") or {}).get("exists") or []
    problems = []
    for path in exists:
        if not tree.exists(path):
            problems.append(f"{recipe_name}: [verify] expected {path!r} to exist, but it doesn't")
    return problems
