"""Applying a recipe's [install] section to a Tree, and the content-
addressed layer cache that lets a shared base layer be built once and
reused across every manifest that shares it.

cpu-variant selection (picking the 000/020/040/060 binary from an
archive that ships several) is not yet implemented: recipes seen so far
ship one generic binary per library, and the real multi-variant archive
layout should be confirmed against an actual example before encoding a
convention. `cpu-variant = true` is currently accepted but has no
filtering effect — every match is copied. Tracked in PLAN.md.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

from .tree import AmigaMeta, Tree


class LayerError(Exception):
    pass


def _amiga_pattern_to_regex(pattern: str) -> re.Pattern:
    """Translate the AmigaDOS pattern subset the recipe contract documents
    (`#?`, `?`, `(a|b|c)` alternation) to a regex. `#?` matches any
    sequence including path separators, so a pattern like "AmiSSL/Libs/#?"
    matches archives that nest a CPU-variant subdirectory underneath."""
    out = []
    i = 0
    while i < len(pattern):
        if pattern[i:i + 2] == "#?":
            out.append(".*")
            i += 2
        elif pattern[i] == "?":
            out.append(".")
            i += 1
        elif pattern[i] == "(":
            j = pattern.find(")", i)
            if j == -1:
                raise LayerError(f"unterminated '(' in pattern {pattern!r}")
            alts = "|".join(re.escape(a) for a in pattern[i + 1:j].split("|"))
            out.append(f"(?:{alts})")
            i = j + 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$", re.IGNORECASE)


def apply_layer(base: Tree, package_name: str, install: dict, archive: Tree) -> Tree:
    """Apply one recipe's [install] section to `base`, returning a new
    Tree (base is not mutated). `archive` is the extracted source archive
    the [install].copy `from` patterns match against; pass an empty Tree
    for packages with no copy actions (pure capability providers)."""
    tree = base.clone()

    for entry in install.get("copy") or []:
        pattern = _amiga_pattern_to_regex(entry["from"])
        matches = [p for p in archive.paths() if pattern.match(p)]
        if not matches:
            raise LayerError(
                f"{package_name}: [install].copy pattern {entry['from']!r} "
                f"matched nothing in the archive")
        to = entry["to"]
        for src_path in matches:
            basename = src_path.rsplit("/", 1)[-1]
            dest = to if not to.endswith("/") else to + basename
            src = archive.get(src_path)
            tree.put(dest, src.data, src.meta)

    for entry in install.get("envarc") or []:
        tree.put(f"ENVARC:{entry['name']}", entry["content"].encode("latin-1"))

    for entry in install.get("user-startup") or []:
        tree.add_user_startup(entry["order"], package_name, list(entry["lines"]))

    for entry in install.get("assigns") or []:
        tree.add_assign(package_name, entry["name"], entry["path"])

    return tree


def compute_layer_key(parent_key: str | None, recipe_sha256: str, version: str,
                      options: dict, archive_sha256: str) -> str:
    """The cache key for the tree state *after* applying this layer on top
    of `parent_key`'s state. Chaining the parent key in means a hit at
    layer N implies every layer before it was identical too, so loading
    from cache can skip fetch+extract+apply for the whole prefix."""
    payload = json.dumps(
        {
            "parent": parent_key,
            "recipe_sha256": recipe_sha256,
            "version": version,
            "options": options,
            "archive_sha256": archive_sha256,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_path(cache_root: Path, key: str) -> Path:
    return cache_root / "layers" / key[:2] / f"{key}.tar.gz"


def save_layer_cache(tree: Tree, key: str, cache_root: Path) -> None:
    path = _cache_path(cache_root, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_tree_to_tar_gz(tree))


def load_layer_cache(key: str, cache_root: Path) -> Tree | None:
    path = _cache_path(cache_root, key)
    if not path.is_file():
        return None
    return _tree_from_tar_gz(path.read_bytes())


def _tree_to_tar_gz(tree: Tree) -> bytes:
    meta = {
        "files": {
            p: {
                "protection": tree.get(p).meta.protection,
                "comment": tree.get(p).meta.comment,
                "datestamp": list(tree.get(p).meta.datestamp),
            }
            for p in tree.paths()
        },
        "user_startup": [
            {"order": f.order, "source": f.source, "lines": list(f.lines)}
            for f in sorted(tree.user_startup, key=lambda f: (f.order, f.source))
        ],
        "assigns": [
            {"source": a.source, "name": a.name, "path": a.path}
            for a in sorted(tree.assigns, key=lambda a: (a.source, a.name, a.path))
        ],
    }
    meta_bytes = json.dumps(meta, sort_keys=True).encode()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        _add_tar_entry(tar, "__amibake_meta__.json", meta_bytes)
        for p in tree.paths():
            _add_tar_entry(tar, "data/" + p, tree.get(p).data)
    return gzip.compress(buf.getvalue(), mtime=0)


def _add_tar_entry(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    tar.addfile(info, io.BytesIO(data))


def _tree_from_tar_gz(blob: bytes) -> Tree:
    tree = Tree()
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(blob))) as tar:
        meta_bytes = tar.extractfile("__amibake_meta__.json").read()
        meta = json.loads(meta_bytes)
        for path, entry in meta["files"].items():
            member = tar.extractfile("data/" + path)
            data = member.read()
            amiga_meta = AmigaMeta(
                protection=entry["protection"],
                comment=entry["comment"],
                datestamp=tuple(entry["datestamp"]),
            )
            tree.put(path, data, amiga_meta)
        for frag in meta["user_startup"]:
            tree.add_user_startup(frag["order"], frag["source"], frag["lines"])
        for a in meta["assigns"]:
            tree.add_assign(a["source"], a["name"], a["path"])
    return tree
