#!/usr/bin/env python3
"""Recipe-PR CI smoke test (M7): lint -> fixture-manifest build -> its
[verify] block, for every recipe that's actually buildable in CI.

Auto-discovers "network-buildable" package recipes — no [base] table
(so real bases like aros68k/wb1.3 aren't tested as if they were
packages) and a [source] table naming at least one non-proprietary kind
(aminet/github/url; a recipe declaring only [source.assets], like p96
or wb1.3, needs media CI doesn't have and is skipped). New recipe PRs
are covered automatically, no CI config change needed.

Each discovered recipe is built against the real aros68k base (the
zero-encumbrance, no-user-assets base that exists exactly for this) in
a permissive machine block, and its [verify] block is checked against
the real build. amibake lint already runs as a separate CI step; this
is the "does it actually build and pass its own [verify]" half.
"""

from __future__ import annotations

import sys
import tempfile
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from amibake.builder import build_tree  # noqa: E402
from amibake.plan import BuildPlan  # noqa: E402
from amibake.resolver import LoadedRecipe, load_recipe_library, resolve  # noqa: E402
from amibake.verify import verify_exists  # noqa: E402

RECIPES_ROOT = REPO_ROOT / "recipes"
BASE_NAME = "aros68k"
MACHINE = {"cpu": "68030", "fpu": True, "mmu": True}


def _is_network_buildable(recipe: LoadedRecipe) -> bool:
    if "base" in recipe.doc:
        return False
    source = recipe.doc.get("source") or {}
    return bool(set(source) - {"assets"})


def _default_option_answers(recipe: LoadedRecipe) -> dict:
    """Best-effort answers for [options] the recipe requires with no
    declared default (e.g. picasso96-2's `card`, which p96-style recipes
    always needed but only a proprietary-source recipe had before —
    proprietary recipes are never auto-discovered, so this gap was never
    exercised until a real network-buildable one had a required option).
    Picks the first declared enum value / `false` for bool; a recipe
    whose only buildable combination isn't the first enum value would
    need a real fix here, not a workaround, since CI should exercise a
    genuinely representative build."""
    answers = {}
    for opt_name, opt in (recipe.doc.get("options") or {}).items():
        if not opt.get("required") or opt.get("default") is not None:
            continue
        if opt.get("type") == "enum" and opt.get("values"):
            answers[opt_name] = opt["values"][0]
        elif opt.get("type") == "bool":
            answers[opt_name] = False
    return answers


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return f'"{value}"'


def main() -> int:
    library = load_recipe_library(RECIPES_ROOT)
    targets = sorted(name for name, r in library.items() if _is_network_buildable(r))
    if not targets:
        print("no network-buildable recipes found — nothing to smoke test")
        return 0

    failures = []
    for name in targets:
        print(f"--- {name} ---")
        answers = _default_option_answers(library[name])
        if answers:
            fields = ", ".join(f"{k} = {_toml_value(v)}" for k, v in answers.items())
            package_entry = f'{{ name = "{name}", {fields} }}'
        else:
            package_entry = f'"{name}"'
        manifest_text = (
            f'base = "{BASE_NAME}"\n'
            f'machine = {{ cpu = "{MACHINE["cpu"]}", fpu = {str(MACHINE["fpu"]).lower()}, '
            f'mmu = {str(MACHINE["mmu"]).lower()} }}\n'
            f'packages = [{package_entry}]\n'
            f'output = ["dir"]\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "smoke.toml"
            manifest_path.write_text(manifest_text)
            manifest = tomllib.loads(manifest_text)

            result = resolve(manifest_path, manifest, library)
            if not result.ok:
                failures.append(name)
                for p in result.problems:
                    print(f"  resolve error: {p}")
                continue

            try:
                tree = build_tree(result.plan, tmp_path / "cache")
            except Exception as e:
                failures.append(name)
                print(f"  build error: {e}")
                continue

            plan: BuildPlan = result.plan
            problems = []
            for pkg in (plan.base_package, *plan.packages):
                problems.extend(verify_exists(tree, pkg.name, library[pkg.name].doc))
            if problems:
                failures.append(name)
                for p in problems:
                    print(f"  {p}")
            else:
                print("  ok")

    if failures:
        print(f"\n{len(failures)} recipe(s) failed the smoke build: {', '.join(failures)}")
        return 1
    print(f"\n{len(targets)} recipe(s) built and verified against {BASE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
