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

A one-package manifest can't disambiguate a capability with several
providers the way a real manifest usually does (by listing the provider
it wants), so the fixture manifest answers those itself — see
`_capability_providers`.
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
from amibake.versionspec import parse_package_spec  # noqa: E402

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


def _capability_providers(library: dict[str, LoadedRecipe]) -> dict[str, str]:
    """A `[providers]` answer for every capability more than one recipe
    provides and no recipe is named after — the fixture manifest lists
    only the target and its option-bearing dependencies, so nothing else
    disambiguates, and the resolver rightly refuses to guess (`z3660`
    depends on the `picasso96` capability, which both `picasso96-2` and
    `picasso96-3` provide). A capability that *is* also a package name
    needs no answer: the resolver matches the recipe by name first and
    never asks who provides it.

    Network-buildable providers win: picking `picasso96-3` would send CI
    looking for a proprietary archive it cannot have, turning a real
    build into an asset error. Ties break on sorted name, so the choice
    is deterministic rather than dict-order luck. A capability with no
    network-buildable provider still gets one (the first by name) — the
    recipe that needs it is unbuildable in CI either way, and a named
    fetch failure explains that better than an ambiguity error does."""
    providers: dict[str, list[str]] = {}
    for name, recipe in library.items():
        for capability in ((recipe.doc.get("package") or {}).get("provides") or []):
            providers.setdefault(capability, []).append(name)

    answers = {}
    for capability, names in providers.items():
        if len(names) < 2 or capability in library:
            continue
        buildable = sorted(n for n in names if _is_network_buildable(library[n]))
        answers[capability] = buildable[0] if buildable else sorted(names)[0]
    return answers


def _dependencies_needing_answers(name: str, library: dict[str, LoadedRecipe],
                                  provider_answers: dict[str, str]) -> list[str]:
    """Recipes in `name`'s dependency closure that have a required
    [options] entry with no default, deepest first.

    A dependency's options are the manifest's job to answer, not the
    dependent recipe's: `z3660` depends on the `picasso96` capability,
    and whichever P96 recipe provides it still demands a `card`. Real
    manifests answer that by listing the provider with its option
    (`manifests/os32-z3660-rtg.toml` does, as `card = "none"`), so the
    fixture manifest does the same rather than the resolver having to
    invent an answer."""
    seen, ordered = set(), []

    def walk(current: str) -> None:
        if current in seen:
            return
        seen.add(current)
        for spec in ((library[current].doc.get("package") or {}).get("depends") or []):
            dep, _ = parse_package_spec(spec)
            if dep not in library:
                # A capability, not a package name: whichever recipe
                # provides it is what the build will actually pull in.
                dep = provider_answers.get(dep) or _sole_provider(dep, library)
                if dep is None:
                    continue
            walk(dep)
            if dep != name and dep not in ordered and _default_option_answers(library[dep]):
                ordered.append(dep)

    walk(name)
    return ordered


def _sole_provider(capability: str, library: dict[str, LoadedRecipe]) -> str | None:
    names = [n for n, r in library.items()
             if capability in ((r.doc.get("package") or {}).get("provides") or [])]
    return names[0] if len(names) == 1 else None


def _package_entry(name: str, library: dict[str, LoadedRecipe]) -> str:
    answers = _default_option_answers(library[name])
    if not answers:
        return f'"{name}"'
    fields = ", ".join(f"{k} = {_toml_value(v)}" for k, v in answers.items())
    return f'{{ name = "{name}", {fields} }}'


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

    provider_answers = _capability_providers(library)
    providers_text = "".join(
        f'providers.{cap} = "{provider_answers[cap]}"\n'
        for cap in sorted(provider_answers))
    for cap in sorted(provider_answers):
        print(f"ambiguous capability {cap!r} -> {provider_answers[cap]}")

    failures = []
    for name in targets:
        print(f"--- {name} ---")
        # Dependencies first: a listed provider both answers its own
        # options and settles the capability, exactly as a hand-written
        # manifest does (the resolver honors a provider the manifest
        # picked only if it resolved first).
        deps = _dependencies_needing_answers(name, library, provider_answers)
        entries = [_package_entry(dep, library) for dep in deps]
        entries.append(_package_entry(name, library))
        if deps:
            print(f"  answering options for {', '.join(deps)}")
        manifest_text = (
            f'base = "{BASE_NAME}"\n'
            f'machine = {{ cpu = "{MACHINE["cpu"]}", fpu = {str(MACHINE["fpu"]).lower()}, '
            f'mmu = {str(MACHINE["mmu"]).lower()} }}\n'
            f'packages = [{", ".join(entries)}]\n'
            f'output = ["dir"]\n'
            + providers_text
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
