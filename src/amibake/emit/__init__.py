"""Shared helpers for the config emitters (emit/copperline.py, emit/uae.py)."""

from __future__ import annotations


def collect_emulator_config(plan, library: dict, emitter: str) -> dict:
    """Merge every resolved recipe's `[emulator-config.<emitter>]`
    directives (base first, then packages in resolution order — the same
    order `cli.py` already walks for `[verify]`), later recipes winning
    on key conflict. Recipes with no directives for this emitter simply
    contribute nothing."""
    merged: dict = {}
    for pkg in (plan.base_package, *plan.packages):
        recipe = library[pkg.name]
        directives = (recipe.doc.get("emulator-config") or {}).get(emitter) or {}
        merged.update(directives)
    return merged
