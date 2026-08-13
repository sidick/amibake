"""amibake command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from ._validate import load_toml
from .builder import build_tree
from .emit import collect_emulator_config
from .emit.archive import write_tgz, write_zip
from .emit.copperline import EmitError as CopperlineEmitError
from .emit.copperline import write_copperline_config
from .emit.dirtree import write_dirtree
from .emit.hdf import DEFAULT_DOS_TYPE, write_hdf
from .emit.uae import EmitError as UaeEmitError
from .emit.uae import write_uae_config
from .errors import AmiBakeError, Problem
from .manifest import validate_manifest
from .plan import BuildPlan, format_lockfile, write_lockfile
from .recipe import validate_recipe
from .resolver import LoadedRecipe, load_recipe_library, resolve
from .verify import verify_exists


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
    build.add_argument("--recipes", type=Path, default=Path("recipes"),
                       help="recipe library root (default: ./recipes)")
    build.add_argument("--out", type=Path, default=None,
                       help="output directory (default: alongside the manifest)")
    build.add_argument("--cache", type=Path, default=Path(".amibake-cache"),
                       help="layer/archive cache root (default: ./.amibake-cache)")
    build.add_argument("--assets", type=Path, default=None,
                       help="assets/ directory for proprietary sources")
    build.add_argument("--no-cache", action="store_true",
                       help="bypass the layer cache")

    args = parser.parse_args(argv)

    if args.command == "lint":
        return _cmd_lint(args.paths)
    if args.command == "resolve":
        return _cmd_resolve(args.manifest, args.recipes, args.lockfile, args.print_only)
    return _cmd_build(args.manifest, args.recipes, args.out, args.cache,
                      args.assets, not args.no_cache)


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


def _lint_then_resolve(manifest_path: Path, recipes_root: Path):
    """Lint the manifest and every recipe, then resolve. Returns
    (result_or_None, library_or_None, problems); on any failure the first
    two are None and problems explains why (already un-printed)."""
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
        return None, None, problems, "lint"

    manifest = load_toml(manifest_path)
    library = load_recipe_library(recipes_root)
    result = resolve(manifest_path, manifest, library)
    if not result.ok:
        return None, None, result.problems, "resolve"
    return result, library, [], ""


def _print_lint_or_resolve_failure(manifest_path: Path, problems: list[Problem],
                                   stage: str) -> None:
    for problem in problems:
        print(problem, file=sys.stderr)
    if stage == "lint":
        print("resolve aborted: manifest or recipe library does not lint clean",
              file=sys.stderr)
    else:
        print(f"{len(problems)} error(s) resolving {manifest_path}", file=sys.stderr)


def _cmd_resolve(manifest_path: Path, recipes_root: Path, lockfile_path: Path | None,
                 print_only: bool) -> int:
    result, _library, problems, stage = _lint_then_resolve(manifest_path, recipes_root)
    if result is None:
        _print_lint_or_resolve_failure(manifest_path, problems, stage)
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


_EMITTERS = {
    "hdf": (".hdf", write_hdf),
    "dir": ("", write_dirtree),
    "tgz": (".tgz", write_tgz),
    "zip": (".zip", write_zip),
}


def _cmd_build(manifest_path: Path, recipes_root: Path, out_dir: Path | None,
               cache_root: Path, assets_root: Path | None, use_cache: bool) -> int:
    result, library, problems, stage = _lint_then_resolve(manifest_path, recipes_root)
    if result is None:
        _print_lint_or_resolve_failure(manifest_path, problems, stage)
        return 1
    plan: BuildPlan = result.plan

    tree = build_tree(plan, cache_root, assets_root, use_cache=use_cache)

    verify_problems: list[str] = []
    for pkg in (plan.base_package, *plan.packages):
        recipe: LoadedRecipe = library[pkg.name]
        verify_problems.extend(verify_exists(tree, pkg.name, recipe.doc))
    if verify_problems:
        for problem in verify_problems:
            print(problem, file=sys.stderr)
        print(f"{len(verify_problems)} [verify] failure(s)", file=sys.stderr)
        return 1

    out_dir = out_dir or manifest_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = manifest_path.stem
    written = []
    dir_output_path = None
    for fmt in plan.output:
        suffix, emit = _EMITTERS[fmt]
        target = out_dir / f"{stem}{suffix}"
        if fmt == "hdf":
            emit(tree, target, dos_type=plan.base.dos_type or DEFAULT_DOS_TYPE)
        else:
            emit(tree, target)
        if fmt == "dir":
            dir_output_path = target.resolve()
        written.append(str(target))

    if plan.emit:
        rom_path, rom_error = _resolve_rom_path(assets_root, plan.base.kickstart_version)
        if rom_error:
            print(rom_error, file=sys.stderr)
            return 1
        for emitter in plan.emit:
            emulator_config = collect_emulator_config(plan, library, emitter)
            try:
                if emitter == "copperline":
                    target = out_dir / f"{stem}.copperline.toml"
                    write_copperline_config(plan, target, rom_path, dir_output_path,
                                            emulator_config)
                else:
                    target = out_dir / f"{stem}-{emitter}.uae"
                    write_uae_config(plan, target, rom_path, dir_output_path,
                                     emulator_config, flavor=emitter)
            except (CopperlineEmitError, UaeEmitError) as e:
                print(f"{emitter}: {e}", file=sys.stderr)
                return 1
            written.append(str(target))

    print(f"built {manifest_path}: base={plan.base.name}, "
         f"packages=[{', '.join(p.name for p in plan.packages) or '(none)'}]")
    for w in written:
        print(f"wrote {w}")
    return 0


def _resolve_rom_path(assets_root: Path | None, kickstart_version: str | None):
    """`assets/roms/kickstart-{version}.rom`, under the same --assets root
    recipes already use. Returns (path, None) or (None, error message)."""
    if kickstart_version is None:
        return None, ("no ROM to emit a config with: the base recipe declares no "
                      "[base].kickstart-version")
    if assets_root is None:
        return None, (f"no ROM to emit a config with: need "
                      f"assets/roms/kickstart-{kickstart_version}.rom, but no assets "
                      f"directory was given (pass --assets)")
    rom_path = assets_root / "roms" / f"kickstart-{kickstart_version}.rom"
    if not rom_path.is_file():
        return None, (f"no ROM to emit a config with: {rom_path} not found — supply "
                      f"it there, or drop 'emit' from the manifest")
    return rom_path.resolve(), None


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
