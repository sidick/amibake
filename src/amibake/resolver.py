"""Dependency resolution: manifest + recipe library -> BuildPlan.

Assumes the manifest and every recipe it can reach have already passed
`amibake lint` (manifest.py / recipe.py) — this module does cross-
document validation only: does the named package exist, does its
[requires] accept this base and machine, is every capability provided
exactly once. Errors are collected (not fail-fast) and every one names
the offending package, the requirement, and the remedy.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ._validate import load_toml
from .errors import Problem
from .plan import BaseInfo, BuildPlan, ResolvedPackage
from .versionspec import Constraint, max_satisfying, parse_constraint, parse_package_spec, satisfies

CPU_ORDER = ["68000", "68010", "68020", "68030", "68040", "68060"]


@dataclass(frozen=True)
class LoadedRecipe:
    name: str
    path: Path
    doc: dict


def load_recipe_library(root: Path) -> dict[str, LoadedRecipe]:
    """Load every recipe.toml under `root`, keyed by package name.

    Assumes each recipe already lints clean; a recipe with no readable
    [package].name is silently skipped (lint will have already reported
    it as an error elsewhere).
    """
    library: dict[str, LoadedRecipe] = {}
    for recipe_path in sorted(root.rglob("recipe.toml")):
        doc = load_toml(recipe_path)
        name = (doc.get("package") or {}).get("name")
        if isinstance(name, str):
            library[name] = LoadedRecipe(name=name, path=recipe_path, doc=doc)
    return library


class ResolveResult:
    def __init__(self, plan: BuildPlan | None, problems: list[Problem]):
        self.plan = plan
        self.problems = problems

    @property
    def ok(self) -> bool:
        return self.plan is not None


def resolve(manifest_path: Path, manifest: dict, library: dict[str, LoadedRecipe]) -> ResolveResult:
    problems: list[Problem] = []
    manifest_file = str(manifest_path)

    base_name, base_answers = _parse_manifest_base(manifest["base"])
    base = library.get(base_name)
    if base is None:
        problems.append(Problem(
            manifest_file, "base", f"unknown base {base_name!r}",
            "no recipe with that name was found in the recipe library — "
            "check spelling, or the base recipe has not been added yet"))
        return ResolveResult(None, problems)
    base_info = _base_info(base)
    base_versions = (base.doc.get("package") or {}).get("versions") or []
    base_version = max_satisfying(base_versions, [])
    if base_version is None:
        problems.append(Problem(
            str(base.path), "base", f"base recipe {base.name!r} declares no versions",
            "add at least one version to [package].versions"))
        return ResolveResult(None, problems)

    machine = manifest.get("machine") or {}
    emit = manifest.get("emit") or []

    # The base is its own layer — applied first, same [install]/[requires]/
    # [options] machinery as any package, but resolved separately from
    # plan.packages (which stays exactly what the manifest asked for).
    base_requires = _effective_requires(base.doc, base_version)
    _validate_requires(problems, manifest_file, "base", base_requires,
                       base_info, machine, emit)
    base_options = _validate_options(problems, manifest_file, "base", base,
                                     base_answers, base_info, machine, emit)
    base_package = ResolvedPackage(
        name=base.name,
        version=base_version,
        options=base_options,
        recipe_path=str(base.path),
        recipe_sha256=hashlib.sha256(base.path.read_bytes()).hexdigest(),
        sources=_extract_sources(base.doc, base_version),
    )

    resolved: dict[str, ResolvedPackage] = {}
    order: list[str] = []
    visiting: set[str] = set()
    providers = manifest.get("providers") or {}

    def resolve_one(name: str, constraints: list[Constraint], options: dict,
                    label: str) -> None:
        if name in resolved:
            if not satisfies(resolved[name].version, constraints):
                problems.append(Problem(
                    manifest_file, label,
                    f"{name!r} was already resolved to version "
                    f"{resolved[name].version!r}, which does not satisfy "
                    f"{_fmt_constraints(constraints)}",
                    "align version constraints across every dependent, or "
                    "split into two differently-named packages"))
            return
        if name in visiting:
            problems.append(Problem(
                manifest_file, label, f"circular dependency involving {name!r}",
                "break the cycle in the recipes' [package].depends"))
            return

        recipe = library.get(name)
        if recipe is None:
            recipe = _resolve_capability(problems, manifest_file, label, name,
                                         providers, library)
            if recipe is None:
                return

        versions = (recipe.doc.get("package") or {}).get("versions") or []
        version = max_satisfying(versions, constraints)
        if version is None:
            problems.append(Problem(
                str(recipe.path), label,
                f"no version of {recipe.name!r} satisfies "
                f"{_fmt_constraints(constraints)}",
                f"available versions: {', '.join(versions) or '(none)'}"))
            return

        visiting.add(recipe.name)
        requires = _effective_requires(recipe.doc, version)
        _validate_requires(problems, manifest_file, label, requires,
                           base_info, machine, emit)
        resolved_options = _validate_options(problems, manifest_file, label,
                                             recipe, options, base_info, machine, emit)

        for dep_spec in (recipe.doc.get("package") or {}).get("depends") or []:
            dep_name, dep_constraints = parse_package_spec(dep_spec)
            resolve_one(dep_name, dep_constraints, {}, f"{label} -> {dep_name}")

        visiting.discard(recipe.name)
        recipe_sha256 = hashlib.sha256(recipe.path.read_bytes()).hexdigest()
        resolved[recipe.name] = ResolvedPackage(
            name=recipe.name,
            version=version,
            options=resolved_options,
            recipe_path=str(recipe.path),
            recipe_sha256=recipe_sha256,
            sources=_extract_sources(recipe.doc, version),
        )
        order.append(recipe.name)

    for i, entry in enumerate(manifest.get("packages") or []):
        name, constraints, options = _parse_manifest_entry(entry)
        resolve_one(name, constraints, options, f"packages[{i}] ({name})")

    for name in resolved:
        recipe = library[name]
        for conflict_spec in (recipe.doc.get("package") or {}).get("conflicts") or []:
            conflict_name, _ = parse_package_spec(conflict_spec)
            if conflict_name in resolved:
                problems.append(Problem(
                    manifest_file, name,
                    f"{name!r} conflicts with {conflict_name!r}, and both are "
                    f"in this build",
                    f"remove one of {name!r} / {conflict_name!r} from the manifest"))

    if problems:
        return ResolveResult(None, problems)

    plan = BuildPlan(
        base=base_info,
        base_package=base_package,
        machine=machine,
        packages=tuple(resolved[n] for n in order),
        output=tuple(manifest.get("output") or ["hdf"]),
        emit=tuple(emit),
    )
    return ResolveResult(plan, [])


def _parse_manifest_base(base) -> tuple[str, dict]:
    if isinstance(base, str):
        return base, {}
    return base["name"], {k: v for k, v in base.items() if k != "name"}


def _parse_manifest_entry(entry) -> tuple[str, list[Constraint], dict]:
    if isinstance(entry, str):
        name, constraints = parse_package_spec(entry)
        return name, constraints, {}
    name = entry["name"]
    constraints = parse_constraint(entry["version"]) if "version" in entry else []
    options = {k: v for k, v in entry.items() if k not in ("name", "version")}
    return name, constraints, options


def _resolve_capability(problems: list[Problem], manifest_file: str, label: str,
                        capability: str, providers: dict,
                        library: dict[str, LoadedRecipe]) -> LoadedRecipe | None:
    override = providers.get(capability)
    if override is not None:
        candidate = library.get(override)
        if candidate is None:
            problems.append(Problem(
                manifest_file, f"providers.{capability}",
                f"providers.{capability} names {override!r}, which is not in "
                f"the recipe library",
                "check spelling, or the recipe has not been added yet"))
            return None
        if capability not in ((candidate.doc.get("package") or {}).get("provides") or []):
            problems.append(Problem(
                manifest_file, f"providers.{capability}",
                f"{override!r} does not declare provides = [{capability!r}, ...]",
                f"point providers.{capability} at a recipe that actually "
                f"provides it, or add {capability!r} to {override!r}'s "
                f"[package].provides"))
            return None
        return candidate

    candidates = [r for r in library.values()
                 if capability in ((r.doc.get("package") or {}).get("provides") or [])]
    if not candidates:
        problems.append(Problem(
            manifest_file, label,
            f"unknown package or capability {capability!r}",
            f"no recipe named {capability!r}, and no recipe provides it — "
            f"check spelling or add a recipe"))
        return None
    if len(candidates) > 1:
        names = ", ".join(sorted(r.name for r in candidates))
        problems.append(Problem(
            manifest_file, label,
            f"ambiguous capability {capability!r}: provided by {names}",
            f'pick one via [providers] in the manifest, e.g. '
            f'providers.{capability} = "{sorted(r.name for r in candidates)[0]}"'))
        return None
    return candidates[0]


def _base_info(base: LoadedRecipe) -> BaseInfo:
    table = base.doc.get("base") or {}
    return BaseInfo(
        name=base.name,
        os_version=table.get("os-version"),
        kickstart_version=table.get("kickstart-version"),
        dos_type=table.get("dos-type"),
    )


def _effective_requires(doc: dict, version: str) -> dict:
    requires = dict(doc.get("requires") or {})
    per_version = requires.pop("per-version", {})
    override = per_version.get(version)
    if override:
        merged = dict(requires)
        merged.update(override)
        return merged
    return requires


def _validate_requires(problems: list[Problem], manifest_file: str, label: str,
                       requires: dict, base_info: BaseInfo, machine: dict,
                       emit: list[str]) -> None:
    os_constraint = requires.get("os")
    if os_constraint:
        constraints = parse_constraint(os_constraint)
        if base_info.os_version is None:
            problems.append(Problem(
                manifest_file, f"{label}.requires.os",
                f"needs os {os_constraint} but base {base_info.name!r} does "
                f"not declare an os-version",
                f"add [base] os-version to the {base_info.name!r} recipe, "
                f"or drop this package's os requirement"))
        elif not satisfies(base_info.os_version, constraints):
            problems.append(Problem(
                manifest_file, f"{label}.requires.os",
                f"needs os {os_constraint} but base {base_info.name!r} is "
                f"os {base_info.os_version}",
                f"use a base satisfying os {os_constraint}, or drop this "
                f"package from the manifest"))

    ks_constraint = requires.get("kickstart")
    if ks_constraint and base_info.kickstart_version is not None:
        constraints = parse_constraint(ks_constraint)
        if not satisfies(base_info.kickstart_version, constraints):
            problems.append(Problem(
                manifest_file, f"{label}.requires.kickstart",
                f"needs kickstart {ks_constraint} but base "
                f"{base_info.name!r} is kickstart {base_info.kickstart_version}",
                f"use a base satisfying kickstart {ks_constraint}, or drop "
                f"this package from the manifest"))

    cpu_constraint = requires.get("cpu")
    machine_cpu = machine.get("cpu")
    if cpu_constraint and machine_cpu:
        constraints = parse_constraint(cpu_constraint)
        try:
            ok = _cpu_satisfies(machine_cpu, constraints)
        except ValueError:
            ok = True  # unrecognized CPU family: nothing more we can check here
        if not ok:
            problems.append(Problem(
                manifest_file, f"{label}.requires.cpu",
                f"needs cpu {cpu_constraint} but machine.cpu is "
                f"{machine_cpu!r}",
                f"set machine.cpu to satisfy {cpu_constraint}, or drop "
                f"this package"))

    if requires.get("fpu") and not machine.get("fpu"):
        problems.append(Problem(
            manifest_file, f"{label}.requires.fpu",
            "needs an FPU but machine.fpu is not true",
            "set machine.fpu = true, or drop this package"))

    if requires.get("mmu") and not machine.get("mmu"):
        problems.append(Problem(
            manifest_file, f"{label}.requires.mmu",
            "needs an MMU but machine.mmu is not true",
            "set machine.mmu = true, or drop this package"))

    req_emulators = requires.get("emulator")
    if req_emulators and emit and not (set(req_emulators) & set(emit)):
        problems.append(Problem(
            manifest_file, f"{label}.requires.emulator",
            f"needs one of these emulators: {', '.join(req_emulators)}, but "
            f"the manifest's emit list is {emit}",
            f"add one of {', '.join(req_emulators)} to emit, or drop this "
            f"package"))


def _cpu_satisfies(cpu: str, constraints: list[Constraint]) -> bool:
    idx = CPU_ORDER.index(cpu)
    for op, target in constraints:
        target_idx = CPU_ORDER.index(target)
        if op == "=" and idx != target_idx:
            return False
        if op == ">=" and idx < target_idx:
            return False
        if op == "<=" and idx > target_idx:
            return False
        if op == ">" and idx <= target_idx:
            return False
        if op == "<" and idx >= target_idx:
            return False
    return True


def _validate_options(problems: list[Problem], manifest_file: str, label: str,
                      recipe: LoadedRecipe, provided: dict, base_info: BaseInfo,
                      machine: dict, emit: list[str]) -> dict:
    declared = recipe.doc.get("options") or {}
    for key in provided:
        if key not in declared:
            problems.append(Problem(
                manifest_file, f"{label}.{key}",
                f"unknown option {key!r} for package {recipe.name!r}",
                f"known options: {', '.join(sorted(declared)) or '(none)'}"))

    resolved: dict = {}
    for opt_name, opt in declared.items():
        opt_type = opt.get("type")
        values = opt.get("values") or []
        default = opt.get("default")
        value = provided.get(opt_name)

        if value is None:
            if opt.get("required") and default is None:
                problems.append(Problem(
                    manifest_file, f"{label}.{opt_name}",
                    f"required option {opt_name!r} was not answered",
                    f"add {opt_name} = ... to the package entry; choices: "
                    f"{', '.join(values) if values else opt_type}"))
                continue
            value = default
        elif opt_type == "enum" and value == "auto":
            if default is None:
                problems.append(Problem(
                    manifest_file, f"{label}.{opt_name}",
                    f'{opt_name} = "auto" but the recipe declares no default',
                    f"pick an explicit value from: {', '.join(values)}"))
                continue
            value = default
        elif opt_type == "enum" and value not in values:
            problems.append(Problem(
                manifest_file, f"{label}.{opt_name}",
                f"{value!r} is not a valid value for {opt_name!r}",
                f"choose one of: {', '.join(values)}"))
            continue
        elif opt_type == "bool" and not isinstance(value, bool):
            problems.append(Problem(
                manifest_file, f"{label}.{opt_name}",
                f"option {opt_name!r} must be a boolean", "use true/false"))
            continue
        elif opt_type == "string" and not isinstance(value, str):
            problems.append(Problem(
                manifest_file, f"{label}.{opt_name}",
                f"option {opt_name!r} must be a string", "quote the value"))
            continue

        if value is None:
            continue
        resolved[opt_name] = value
        sub_requires = (opt.get("requires") or {}).get(value)
        if sub_requires:
            _validate_requires(problems, manifest_file, f"{label}.{opt_name}={value}",
                               sub_requires, base_info, machine, emit)

    return resolved


def _extract_sources(doc: dict, version: str) -> dict:
    source = doc.get("source") or {}
    out: dict = {}

    aminet = source.get("aminet")
    if aminet:
        out["aminet"] = {
            "url": aminet["url"].replace("{version}", version),
            "sha256": (aminet.get("sha256") or {}).get(version, ""),
        }

    github = source.get("github")
    if github:
        tag_template = github.get("tag", "{version}")
        out["github"] = {
            "repo": github["repo"],
            "asset": github["asset"].replace("{version}", version),
            "tag": tag_template.replace("{version}", version),
            "sha256": (github.get("sha256") or {}).get(version, ""),
        }

    url_source = source.get("url")
    if url_source:
        filename = url_source.get("filename", url_source["url"])
        out["url"] = {
            "url": url_source["url"].replace("{version}", version),
            "filename": filename.replace("{version}", version),
            "sha256": (url_source.get("sha256") or {}).get(version, ""),
        }

    assets = source.get("assets")
    if assets:
        out["assets"] = {
            "path": assets["path"].replace("{version}", version),
            "sha256": (assets.get("sha256") or {}).get(version, ""),
        }

    return out


def _fmt_constraints(constraints: list[Constraint]) -> str:
    if not constraints:
        return "(any version)"
    return ", ".join(f"{op} {v}" for op, v in constraints)
