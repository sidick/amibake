"""amibake command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from ._validate import load_toml
from .errors import AmiBakeError, Problem
from .manifest import validate_manifest
from .plan import format_lockfile, write_lockfile
from .recipe import validate_recipe
from .resolver import load_recipe_library, resolve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="amibake",
        description="Manifest-driven Amiga test setup builder",
    )
    parser.add_argument("--version", action="version", version=f"amibake {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    lint = sub.add_parser("lint", help="validate recipes and manifests")
    lint.add_argument("paths", nargs="+", type=Path,
                      help="recipe dirs, recipe.toml files, or manifest .toml files")

    res = sub.add_parser("resolve", help="resolve a manifest to a build plan + lockfile")
    res.add_argument("manifest", type=Path)
    res.add_argument("--recipes", type=Path, default=Path("recipes"),
                     help="recipe library root (default: ./recipes)")
    res.add_argument("--lockfile", type=Path, default=None,
                     help="lockfile output path (default: <manifest>.lock.toml)")
    res.add_argument("--print", dest="print_only", action="store_true",
                     help="print the lockfile to stdout instead of writing it")

    build = sub.add_parser("build", help="build a manifest's outputs")
    build.add_argument("manifest", type=Path)

    args = parser.parse_args(argv)

    if args.command == "lint":
        return _cmd_lint(args.paths)
    if args.command == "resolve":
        return _cmd_resolve(args.manifest, args.recipes, args.lockfile, args.print_only)
    print(f"amibake {args.command} is not implemented yet (arrives in a later "
          f"milestone; see PLAN.md)", file=sys.stderr)
    return 2


def _cmd_lint(paths: list[Path]) -> int:
    problems: list[Problem] = []
    checked = 0
    for path in _collect(paths, problems):
        checked += 1
        try:
            if path.name == "recipe.toml":
                problems.extend(validate_recipe(path))
            else:
                problems.extend(validate_manifest(path))
        except AmiBakeError as e:
            problems.append(e.problem)

    for problem in problems:
        print(problem, file=sys.stderr)
    errors = [p for p in problems if p.severity == "error"]
    warnings = [p for p in problems if p.severity == "warning"]
    summary = (f"{checked} file(s) checked: "
               f"{len(errors)} error(s), {len(warnings)} warning(s)")
    print(summary)
    return 1 if errors else 0


def _cmd_resolve(manifest_path: Path, recipes_root: Path, lockfile_path: Path | None,
                 print_only: bool) -> int:
    problems: list[Problem] = []
    try:
        if not manifest_path.is_file():
            problems.append(Problem(str(manifest_path), "(file)",
                                    "no such file", "check the path"))
        else:
            problems.extend(validate_manifest(manifest_path))
        if not recipes_root.is_dir():
            problems.append(Problem(str(recipes_root), "(dir)",
                                    "recipe library not found",
                                    "pass --recipes pointing at a directory of "
                                    "recipe.toml files"))
        else:
            for recipe_path in sorted(recipes_root.rglob("recipe.toml")):
                problems.extend(validate_recipe(recipe_path))
    except AmiBakeError as e:
        problems.append(e.problem)

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print("resolve aborted: manifest or recipe library does not lint clean",
              file=sys.stderr)
        return 1

    manifest = load_toml(manifest_path)
    library = load_recipe_library(recipes_root)
    result = resolve(manifest_path, manifest, library)

    if not result.ok:
        for problem in result.problems:
            print(problem, file=sys.stderr)
        print(f"{len(result.problems)} error(s) resolving {manifest_path}",
              file=sys.stderr)
        return 1

    if print_only:
        print(format_lockfile(result.plan), end="")
    else:
        out = lockfile_path or manifest_path.with_suffix("").with_suffix(".lock.toml")
        write_lockfile(result.plan, out)
        names = ", ".join(p.name for p in result.plan.packages) or "(none)"
        print(f"resolved {manifest_path}: base={result.plan.base.name}, "
              f"packages=[{names}]")
        print(f"wrote {out}")
    return 0


def _collect(paths: list[Path], problems: list[Problem]) -> list[Path]:
    """Expand CLI arguments to concrete files: a directory means the recipes
    beneath it; a file is taken as-is (recipe.toml → recipe, else manifest)."""
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            found = sorted(path.rglob("recipe.toml"))
            if found:
                files.extend(found)
            else:
                manifests = sorted(p for p in path.rglob("*.toml"))
                if manifests:
                    files.extend(manifests)
                else:
                    problems.append(Problem(
                        str(path), "(dir)", "no recipe.toml or *.toml files found",
                        "point lint at recipe directories or manifest files"))
        elif path.is_file():
            files.append(path)
        else:
            problems.append(Problem(
                str(path), "(file)", "no such file or directory",
                "check the path"))
    return files


if __name__ == "__main__":
    sys.exit(main())
