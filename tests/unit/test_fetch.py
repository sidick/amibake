import hashlib

import pytest

from amibake.fetch import FetchError, fetch_sources

DATA = b"archive contents\n"
SHA = hashlib.sha256(DATA).hexdigest()


def _fake_http_get(calls):
    def _get(url):
        calls.append(url)
        return DATA
    return _get


def test_fetch_github_source(tmp_path):
    calls = []
    sources = {"github": {"repo": "owner/name", "asset": "pkg-1.0.lha",
                          "tag": "1.0", "sha256": SHA}}
    path = fetch_sources(sources, tmp_path, http_get=_fake_http_get(calls))
    assert path.read_bytes() == DATA
    assert calls == ["https://github.com/owner/name/releases/download/1.0/pkg-1.0.lha"]


def test_fetch_aminet_source(tmp_path):
    calls = []
    sources = {"aminet": {"url": "util/libs/pkg-1.0.lha", "sha256": SHA}}
    path = fetch_sources(sources, tmp_path, http_get=_fake_http_get(calls))
    assert path.read_bytes() == DATA
    assert calls == ["https://aminet.net/util/libs/pkg-1.0.lha"]


def test_assets_source_wins_over_network_sources(tmp_path):
    assets_root = tmp_path / "assets"
    assets_root.mkdir()
    (assets_root / "pkg-1.0.lha").write_bytes(b"the real asset\n")
    calls = []
    sources = {
        "assets": {"path": "pkg-1.0.lha"},
        "github": {"repo": "owner/name", "asset": "pkg-1.0.lha", "tag": "1.0", "sha256": SHA},
    }
    path = fetch_sources(sources, tmp_path, assets_root, http_get=_fake_http_get(calls))
    assert path.read_bytes() == b"the real asset\n"
    assert calls == []  # network source never touched


def test_missing_asset_file_is_named(tmp_path):
    assets_root = tmp_path / "assets"
    assets_root.mkdir()
    sources = {"assets": {"path": "pkg-1.0.lha"}}
    with pytest.raises(FetchError, match="pkg-1.0.lha"):
        fetch_sources(sources, tmp_path, assets_root)


def test_asset_source_without_assets_root_is_named(tmp_path):
    sources = {"assets": {"path": "pkg-1.0.lha"}}
    with pytest.raises(FetchError, match="no assets directory"):
        fetch_sources(sources, tmp_path, assets_root=None)


def test_checksum_mismatch_is_named(tmp_path):
    calls = []
    sources = {"github": {"repo": "owner/name", "asset": "pkg-1.0.lha",
                          "tag": "1.0", "sha256": "0" * 64}}
    with pytest.raises(FetchError, match="checksum mismatch"):
        fetch_sources(sources, tmp_path, http_get=_fake_http_get(calls))


def test_no_usable_source_is_named(tmp_path):
    with pytest.raises(FetchError, match="no usable source"):
        fetch_sources({}, tmp_path)


def test_http_failure_is_wrapped(tmp_path):
    def _fail(url):
        raise OSError("network unreachable")
    sources = {"github": {"repo": "owner/name", "asset": "pkg-1.0.lha",
                          "tag": "1.0", "sha256": SHA}}
    with pytest.raises(FetchError, match="failed to fetch"):
        fetch_sources(sources, tmp_path, http_get=_fail)


def test_cache_hit_skips_network(tmp_path):
    calls = []
    sources = {"github": {"repo": "owner/name", "asset": "pkg-1.0.lha",
                          "tag": "1.0", "sha256": SHA}}
    fetch_sources(sources, tmp_path, http_get=_fake_http_get(calls))
    fetch_sources(sources, tmp_path, http_get=_fake_http_get(calls))
    assert len(calls) == 1  # second fetch hit the cache


def test_content_addressed_cache_path_keyed_by_checksum(tmp_path):
    calls = []
    sources = {"github": {"repo": "owner/name", "asset": "pkg-1.0.lha",
                          "tag": "1.0", "sha256": SHA}}
    path = fetch_sources(sources, tmp_path, http_get=_fake_http_get(calls))
    assert path.name == f"{SHA}.lha"
    assert path.parent.name == SHA[:2]
