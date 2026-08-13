"""Archive fetching: source resolution, checksum verification, and a
content-addressed local cache.

Network access goes through an injectable `http_get` callable so tests
never touch the network; the default implementation uses urllib
(stdlib — no new runtime dependency).
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

HttpGet = Callable[[str], bytes]
Warn = Callable[[str], None]

AMINET_MIRROR = "https://aminet.net/"


class FetchError(Exception):
    pass


def default_http_get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 (fixed https URLs from recipes)
        return resp.read()


def _default_warn(message: str) -> None:
    print(message, file=sys.stderr)


def fetch_sources(sources: dict, cache_root: Path, assets_root: Path | None = None,
                  http_get: HttpGet = default_http_get, warn: Warn = _default_warn) -> Path:
    """Resolve one package's declared `sources` (the shape of
    plan.ResolvedPackage.sources / the lockfile's [package.sources.*]) to a
    local archive file, verifying checksums on every network fetch.

    Assets win when present, matching the recipe contract's "assets always
    wins" rule — a user-supplied file is authoritative. If the recipe
    happens to declare a checksum for it, a mismatch only *warns* (via
    `warn`, injectable for tests) rather than failing the build: unlike a
    network source, there's no single canonical upload to compare
    against — older media especially has multiple legitimate dumps of
    the same official disk that are byte-different, so treating a
    mismatch as fatal would reject a real user's valid copy.
    """
    assets = sources.get("assets")
    if assets:
        if assets_root is None:
            raise FetchError(
                f"source is {assets['path']!r} in assets/, but no assets "
                f"directory was given (pass --assets)")
        candidate = assets_root / assets["path"]
        if not candidate.is_file():
            raise FetchError(
                f"asset {assets['path']!r} not found under {assets_root} — "
                f"supply it there, or remove the package that needs it")
        data = candidate.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        expected = assets.get("sha256") or None
        if expected and actual != expected:
            warn(f"warning: asset {assets['path']!r} doesn't match the "
                f"recipe's known sha256 (expected {expected}, got "
                f"{actual}) — proceeding anyway; this may just be a "
                f"different (but valid) dump of the same media")
        suffix = Path(assets["path"]).suffix
        return _store(cache_root, actual, data, suffix)

    for kind, build_url, filename_field in (
        ("github", _github_url, "asset"),
        ("aminet", _aminet_url, "url"),
        ("url", _url_url, "filename"),
    ):
        src = sources.get(kind)
        if not src:
            continue
        suffix = Path(src[filename_field]).suffix
        expected = src.get("sha256") or None
        if expected:
            cached = _cache_path(cache_root, expected, suffix)
            if cached.is_file():
                return cached
        url = build_url(src)
        try:
            data = http_get(url)
        except Exception as e:
            raise FetchError(f"failed to fetch {url}: {e}") from e
        actual = hashlib.sha256(data).hexdigest()
        if expected and actual != expected:
            raise FetchError(
                f"checksum mismatch fetching {url}: recipe declares "
                f"{expected}, downloaded archive is {actual} — it may have "
                f"changed upstream; verify by hand and update the recipe's "
                f"sha256 if this is expected")
        return _store(cache_root, actual, data, suffix)

    raise FetchError("no usable source declared (none of assets/github/aminet/url)")


def _github_url(src: dict) -> str:
    return f"https://github.com/{src['repo']}/releases/download/{src['tag']}/{src['asset']}"


def _aminet_url(src: dict) -> str:
    return AMINET_MIRROR.rstrip("/") + "/" + src["url"].lstrip("/")


def _url_url(src: dict) -> str:
    return src["url"]


def _cache_path(cache_root: Path, sha256: str, suffix: str) -> Path:
    # The suffix is kept in the cache filename (not just the checksum) so
    # extract.py can pick its parser from the path alone.
    return cache_root / "archives" / sha256[:2] / f"{sha256}{suffix}"


def _store(cache_root: Path, sha256: str, data: bytes, suffix: str) -> Path:
    path = _cache_path(cache_root, sha256, suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_bytes(data)
    return path
