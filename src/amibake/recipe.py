"""Recipe loading and validation. Spec: docs/recipe-contract.md."""

from __future__ import annotations

import re
from pathlib import Path

from ._validate import Checker, load_toml
from .errors import Problem
from .manifest import EMULATORS
from .versionspec import is_name, is_version, parse_constraint, parse_package_spec

TOP_KEYS = {"package", "requires", "source", "install", "verify", "options", "hook"}
PACKAGE_KEYS = {"name", "versions", "depends", "conflicts", "provides", "strategy"}
REQUIRES_KEYS = {"os", "kickstart", "cpu", "fpu", "mmu", "emulator", "per-version"}
SOURCE_KINDS = {"aminet", "github", "assets"}
INSTALL_KEYS = {"copy", "envarc", "user-startup", "assigns"}
COPY_KEYS = {"from", "to", "cpu-variant", "when"}
OPTION_TYPES = {"enum", "bool", "string"}
STRATEGIES = {"extract", "installer"}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WHEN_RE = re.compile(r"^[a-z0-9]+([.-][a-z0-9]+)*\s*=\s*\S+$")


def validate_recipe(path: Path) -> list[Problem]:
    """Validate one recipe.toml, returning all problems found."""
    doc = load_toml(path)
    c = Checker(str(path))

    c.unknown_keys(doc, TOP_KEYS, "")

    versions: list[str] = []
    package = c.typed(doc, "package", dict, "", required=True)
    if package is not None:
        versions = _check_package(c, package, path)

    requires = c.typed(doc, "requires", dict, "", default=None)
    if requires is not None:
        _check_requires(c, requires, "[requires]", versions)

    _check_sources(c, doc, versions)

    install = c.typed(doc, "install", dict, "", default=None)
    if install is not None:
        _check_install(c, install)

    verify = c.typed(doc, "verify", dict, "", default=None)
    if verify is not None:
        c.unknown_keys(verify, {"exists"}, "[verify]")
        c.string_list(verify, "exists", "[verify]")

    options = c.typed(doc, "options", dict, "", default={})
    for opt_name, opt in options.items():
        _check_option(c, opt_name, opt)

    hook = c.typed(doc, "hook", dict, "", default=None)
    if hook is not None:
        c.unknown_keys(hook, {"script"}, "[hook]")
        c.typed(hook, "script", str, "[hook]", required=True)
        c.warning("[hook]", "recipe declares a Python hook",
                  "hooks are the fenced escape hatch: expect stricter review, and "
                  "prefer expressing the install declaratively if at all possible")

    return c.problems


def _check_package(c: Checker, package: dict, path: Path) -> list[str]:
    c.unknown_keys(package, PACKAGE_KEYS, "[package]")

    name = c.typed(package, "name", str, "[package]", required=True)
    if name is not None:
        if not is_name(name):
            c.error("[package].name", f"bad package name {name!r}",
                    "names are lower-case slugs ([a-z0-9] with interior '-' or '.')")
        elif path.name == "recipe.toml" and path.parent.name != name:
            c.error("[package].name",
                    f"name {name!r} does not match recipe directory "
                    f"{path.parent.name!r}",
                    "the recipe directory must be named after the package")

    versions = c.typed(package, "versions", list, "[package]", required=True, default=[])
    good_versions: list[str] = []
    if versions is not None and not versions:
        c.error("[package].versions", "must be a non-empty array of version strings",
                'list at least one version, e.g. versions = ["5.20"]')
    for i, v in enumerate(versions or []):
        if not isinstance(v, str) or not is_version(v):
            c.error(f"[package].versions[{i}]",
                    f"bad version {v!r}",
                    'versions are quoted dotted-decimal strings like "5.20" — '
                    "unquoted 5.20 is a float and would silently become 5.2")
        else:
            good_versions.append(v)

    for key in ("depends", "conflicts"):
        for i, spec in enumerate(c.string_list(package, key, "[package]")):
            try:
                parse_package_spec(spec)
            except ValueError as e:
                c.error(f"[package].{key}[{i}]", str(e),
                        'e.g. "mui >= 3.8" or a bare capability name "bsdsocket"')

    for i, cap in enumerate(c.string_list(package, "provides", "[package]")):
        if not is_name(cap):
            c.error(f"[package].provides[{i}]", f"bad capability name {cap!r}",
                    "capability names are lower-case slugs")

    strategy = c.typed(package, "strategy", str, "[package]")
    if strategy is not None and strategy not in STRATEGIES:
        c.error("[package].strategy", f"unknown strategy {strategy!r}",
                f"use one of: {', '.join(sorted(STRATEGIES))} (base recipes only)")

    return good_versions


def _check_requires(c: Checker, requires: dict, where: str,
                    versions: list[str], nested: bool = False) -> None:
    known = REQUIRES_KEYS if not nested else REQUIRES_KEYS - {"per-version"}
    c.unknown_keys(requires, known, where)
    for key in ("os", "kickstart", "cpu"):
        value = c.typed(requires, key, str, where)
        if value is not None:
            try:
                parse_constraint(value)
            except ValueError as e:
                c.error(f"{where}.{key}", str(e), 'e.g. ">= 3.0" or ">= 2.0, < 4.0"')
    c.typed(requires, "fpu", bool, where)
    c.typed(requires, "mmu", bool, where)
    for i, emu in enumerate(c.string_list(requires, "emulator", where)):
        if emu not in EMULATORS:
            c.error(f"{where}.emulator[{i}]", f"unknown emulator {emu!r}",
                    f"use one of: {', '.join(sorted(EMULATORS))}")
    if not nested:
        per_version = c.typed(requires, "per-version", dict, where, default={})
        for ver, sub in per_version.items():
            label = f'{where}.per-version."{ver}"'
            if versions and ver not in versions:
                c.error(label, f"version {ver!r} is not listed in [package].versions",
                        "per-version requirement overrides must name a listed version")
            if isinstance(sub, dict):
                _check_requires(c, sub, label, versions, nested=True)
            else:
                c.error(label, "must be a table of requirement overrides",
                        'e.g. [requires.per-version."4.12"] with os = ">= 1.3"')


def _check_sources(c: Checker, doc: dict, versions: list[str]) -> None:
    source = c.typed(doc, "source", dict, "", default=None)
    if source is None or not source:
        c.error("[source]", "recipe declares no source",
                "add [source.aminet] (url + sha256) for redistributable archives "
                "or [source.assets] (path) for user-supplied ones")
        return
    c.unknown_keys(source, SOURCE_KINDS, "[source]")

    aminet = source.get("aminet")
    if isinstance(aminet, dict):
        c.unknown_keys(aminet, {"url", "sha256"}, "[source.aminet]")
        url = c.typed(aminet, "url", str, "[source.aminet]", required=True)
        if url is not None and len(versions) > 1 and "{version}" not in url:
            c.error("[source.aminet].url",
                    "recipe lists multiple versions but the url has no {version} "
                    "placeholder",
                    "add {version} where the version appears in the archive name")
        _check_sha256_map(c, aminet, "[source.aminet]", versions)
    elif aminet is not None:
        c.error("[source.aminet]", "must be a table", "write it as [source.aminet]")

    github = source.get("github")
    if isinstance(github, dict):
        c.unknown_keys(github, {"repo", "asset", "tag", "sha256"}, "[source.github]")
        repo = c.typed(github, "repo", str, "[source.github]", required=True)
        if repo is not None and repo.count("/") != 1:
            c.error("[source.github].repo", f"bad repo {repo!r}",
                    'must be "owner/name", e.g. "jens-maus/amissl"')
        asset = c.typed(github, "asset", str, "[source.github]", required=True)
        if asset is not None and len(versions) > 1 and "{version}" not in asset:
            c.error("[source.github].asset",
                    "recipe lists multiple versions but the asset name has no "
                    "{version} placeholder",
                    "add {version} where the version appears in the asset name, "
                    'e.g. "AmiSSL-{version}-OS3.lha"')
        tag = c.typed(github, "tag", str, "[source.github]")
        if tag is not None and "{version}" not in tag:
            c.error("[source.github].tag",
                    "tag template has no {version} placeholder",
                    'e.g. tag = "{version}" (the default) or "v{version}"')
        _check_sha256_map(c, github, "[source.github]", versions)
    elif github is not None:
        c.error("[source.github]", "must be a table", "write it as [source.github]")

    assets = source.get("assets")
    if isinstance(assets, dict):
        c.unknown_keys(assets, {"path"}, "[source.assets]")
        path = c.typed(assets, "path", str, "[source.assets]", required=True)
        if path is not None and len(versions) > 1 and "{version}" not in path:
            c.error("[source.assets].path",
                    "recipe lists multiple versions but the path has no {version} "
                    "placeholder",
                    "add {version} where the version appears in the file name")
    elif assets is not None:
        c.error("[source.assets]", "must be a table", "write it as [source.assets]")


def _check_sha256_map(c: Checker, table: dict, where: str, versions: list[str]) -> None:
    sha256 = c.typed(table, "sha256", dict, where, required=True, default={})
    for ver in versions:
        if ver not in sha256:
            c.error(f"{where}.sha256", f"no checksum for listed version {ver!r}",
                    "every version in [package].versions needs a sha256 entry")
    for ver, digest in sha256.items():
        if not isinstance(digest, str) or not _SHA256_RE.match(digest):
            c.error(f'{where}.sha256."{ver}"',
                    "checksum must be a 64-character lower-case hex string",
                    "use `shasum -a 256 <archive>` on the downloaded file")


def _check_install(c: Checker, install: dict) -> None:
    c.unknown_keys(install, INSTALL_KEYS, "[install]")

    copies = c.typed(install, "copy", list, "[install]", default=[])
    for i, entry in enumerate(copies):
        label = f"[install].copy[{i}]"
        if not isinstance(entry, dict):
            c.error(label, "copy entries must be tables",
                    'e.g. { from = "AmiSSL/Libs/#?", to = "SYS:Libs/" }')
            continue
        c.unknown_keys(entry, COPY_KEYS, label)
        c.typed(entry, "from", str, label, required=True)
        to = c.typed(entry, "to", str, label, required=True)
        if to is not None and ":" not in to:
            c.error(f"{label}.to", f"destination {to!r} is not an Amiga path",
                    "destinations are absolute Amiga paths like SYS:Libs/ or "
                    "ENVARC:")
        c.typed(entry, "cpu-variant", bool, label)
        when = c.typed(entry, "when", str, label)
        if when is not None and not _WHEN_RE.match(when):
            c.error(f"{label}.when", f"bad condition {when!r}",
                    'conditions are "<option> = <value>", e.g. "card = uaegfx"')

    for i, entry in enumerate(c.typed(install, "envarc", list, "[install]", default=[])):
        label = f"[install].envarc[{i}]"
        if not isinstance(entry, dict):
            c.error(label, "envarc entries must be tables",
                    'e.g. { name = "AmiSSL/config", content = "..." }')
            continue
        c.unknown_keys(entry, {"name", "content"}, label)
        c.typed(entry, "name", str, label, required=True)
        c.typed(entry, "content", str, label, required=True)

    for i, entry in enumerate(
            c.typed(install, "user-startup", list, "[install]", default=[])):
        label = f"[install].user-startup[{i}]"
        if not isinstance(entry, dict):
            c.error(label, "user-startup entries must be tables",
                    'e.g. { order = 50, lines = ["Assign AmiSSL: SYS:Devs/AmiSSL"] }')
            continue
        c.unknown_keys(entry, {"order", "lines"}, label)
        c.typed(entry, "order", int, label, required=True)
        c.string_list(entry, "lines", label)

    for i, entry in enumerate(c.typed(install, "assigns", list, "[install]", default=[])):
        label = f"[install].assigns[{i}]"
        if not isinstance(entry, dict):
            c.error(label, "assign entries must be tables",
                    'e.g. { name = "AmiSSL", path = "SYS:Devs/AmiSSL" }')
            continue
        c.unknown_keys(entry, {"name", "path"}, label)
        c.typed(entry, "name", str, label, required=True)
        c.typed(entry, "path", str, label, required=True)


def _check_option(c: Checker, opt_name: str, opt) -> None:
    where = f"[options.{opt_name}]"
    if not is_name(opt_name):
        c.error(where, f"bad option name {opt_name!r}",
                "option names are lower-case slugs")
    if not isinstance(opt, dict):
        c.error(where, "must be a table", "declare type/values/required/default keys")
        return
    c.unknown_keys(opt, {"type", "values", "required", "default", "requires"}, where)
    opt_type = c.typed(opt, "type", str, where, required=True)
    if opt_type is not None and opt_type not in OPTION_TYPES:
        c.error(f"{where}.type", f"unknown option type {opt_type!r}",
                f"use one of: {', '.join(sorted(OPTION_TYPES))}")
    values = c.string_list(opt, "values", where) if "values" in opt else []
    if opt_type == "enum" and not values:
        c.error(f"{where}.values", "enum options need a non-empty values array",
                'e.g. values = ["uaegfx", "zz9000"]')
    if opt_type in ("bool", "string") and "values" in opt:
        c.error(f"{where}.values", f"{opt_type} options do not take a values array",
                "remove it, or make the option an enum")
    c.typed(opt, "required", bool, where)
    if "default" in opt:
        default = opt["default"]
        if opt_type == "enum" and default not in values:
            c.error(f"{where}.default", f"default {default!r} is not one of values",
                    "the default must be a listed value")
        if opt_type == "bool" and not isinstance(default, bool):
            c.error(f"{where}.default", "default must be a boolean", "use true/false")
        if opt_type == "string" and not isinstance(default, str):
            c.error(f"{where}.default", "default must be a string", "quote it")
    requires = opt.get("requires")
    if requires is not None:
        if not isinstance(requires, dict):
            c.error(f"{where}.requires", "must be a table keyed by option value",
                    'e.g. [options.card.requires.uaegfx] with emulator = [...]')
        else:
            for value, sub in requires.items():
                label = f"{where}.requires.{value}"
                if values and value not in values:
                    c.error(label, f"{value!r} is not one of the option's values",
                            "per-value requirements must name a declared value")
                if isinstance(sub, dict):
                    _check_requires(c, sub, label, [], nested=True)
                else:
                    c.error(label, "must be a table of requirements",
                            'e.g. emulator = ["amiberry", "winuae"]')
