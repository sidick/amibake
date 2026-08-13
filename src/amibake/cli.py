"""amibake command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .errors import AmiBakeError, Problem
from .manifest import validate_manifest
from .recipe import validate_recipe


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

    for name, help_text in (("resolve", "resolve a manifest to a build plan + lockfile"),
                            ("build", "build a manifest's outputs")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("manifest", type=Path)

    args = parser.parse_args(argv)

    if args.command == "lint":
        return _cmd_lint(args.paths)
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
