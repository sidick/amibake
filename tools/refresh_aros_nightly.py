#!/usr/bin/env python3
"""Re-pin recipes/aros68k to the newest usable AROS nightly.

AROS's SourceForge nightlies are a moving target the recipe's own
determinism rule can't follow by hand: old dated directories are pruned
upstream (the pinned 20260814 404'd within a month), and the newest
dated directory doesn't always contain the m68k boot-iso artifact (a
nightly's m68k leg can fail or lag — 20260905 existed with no boot-iso
while 20260904 had one, observed 2026-09-06). So this tool walks the
dated directories newest-first, downloads the first date whose
`AROS-<date>-amiga-m68k-boot-iso.zip` actually exists, checksums it,
and rewrites the recipe's `versions` and `sha256` in place.

Builds stay fully deterministic — the recipe is always pinned to one
date + checksum; only *this tool* (run by a human, or by a scheduled CI
job opening a PR that the smoke build then validates) chases "latest".
Never wired into `amibake build` itself, on purpose.

Exit codes: 0 = recipe rewritten (or already at the newest usable
nightly, printed either way), 1 = discovery/download failed.
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RECIPE = REPO_ROOT / "recipes" / "aros68k" / "recipe.toml"
ROM_DIR = RECIPE.parent / "rom"
# ISO path -> vendored filename. `LICENSE` rides along because the APL
# requires the licence travel with the binaries we redistribute.
ROM_FILES = {
    "/boot/amiga/aros-rom.bin": "aros-rom.bin",
    "/boot/amiga/aros-ext.bin": "aros-ext.bin",
}

LISTING_URL = "https://sourceforge.net/projects/aros/files/nightly2/"
ARTIFACT_URL = ("https://sourceforge.net/projects/aros/files/nightly2/{date}"
                "/Binaries/AROS-{date}-amiga-m68k-boot-iso.zip/download")
# How many dated directories to try, newest-first, before giving up —
# enough to ride out a bad week of m68k nightlies without hammering
# SourceForge when something is systematically broken.
MAX_DATES_TO_TRY = 8

_DATE_RE = re.compile(r"nightly2/(\d{8})")


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (fixed https URLs)
        return resp.read()


def discover_dates() -> list[str]:
    """Dated nightly directories, newest first."""
    listing = _get(LISTING_URL).decode("utf-8", errors="replace")
    return sorted(set(_DATE_RE.findall(listing)), reverse=True)


def fetch_newest_usable(dates: list[str]) -> tuple[str, bytes] | None:
    """(date, archive bytes) for the newest date whose boot-iso exists.
    Downloads rather than HEADs: the checksum needs the bytes anyway,
    and only the winning date is ever downloaded."""
    for date in dates[:MAX_DATES_TO_TRY]:
        url = ARTIFACT_URL.format(date=date)
        try:
            data = _get(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"  {date}: no m68k boot-iso (404) — trying the next date")
                continue
            raise
        return date, data
    return None


def rewrite_recipe(date: str, sha256: str) -> bool:
    """Point the recipe at `date`. The old pin is *replaced*, not kept
    alongside: pruned upstream directories make stale nightly pins
    unfetchable anyway, so a multi-version history would be dead weight
    (the recipe's own never-edit-a-checksum-in-place rule is about a
    given version's checksum changing, which this doesn't do — the
    version changes with it). Returns False if already pinned there."""
    text = RECIPE.read_text()

    current = re.search(r'^versions = \["(\d{8})"\]$', text, flags=re.M)
    if current is None:
        sys.exit(f"can't find the versions line in {RECIPE} — its shape changed; "
                 f"update this tool to match")
    if current.group(1) == date:
        return False

    old = current.group(1)
    text = text.replace(f'versions = ["{old}"]', f'versions = ["{date}"]')
    text, n = re.subn(
        r'^sha256   = \{ "\d{8}" = "[0-9a-f]{64}" \}$',
        f'sha256   = {{ "{date}" = "{sha256}" }}',
        text, flags=re.M)
    if n != 1:
        sys.exit(f"can't find the sha256 line in {RECIPE} — its shape changed; "
                 f"update this tool to match")
    # Keep the header comment's "Pinned to ..." date honest too.
    text = re.sub(
        r"Pinned to the \d{4}-\d{2}-\d{2} nightly",
        f"Pinned to the {date[:4]}-{date[4:6]}-{date[6:]} nightly",
        text)
    RECIPE.write_text(text)
    return True


def extract_roms(archive: bytes) -> dict[str, bytes]:
    """The ROM images (and the licence) out of the nightly's zip-wrapped
    ISO. Both go through real files: pycdlib needs a seekable source,
    and the ISO is ~400 MB — far too big to hold in memory beside the
    archive it came from."""
    import pycdlib  # runtime dep of amibake proper; not needed to import this tool

    with tempfile.TemporaryDirectory() as tmp:
        iso_path = Path(tmp) / "aros.iso"
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".iso")]
            if len(names) != 1:
                sys.exit(f"expected exactly one .iso in the nightly zip, found {names} "
                         f"— the artifact's shape changed; update this tool to match")
            licence = next((n for n in zf.namelist()
                            if n.rsplit("/", 1)[-1] == "LICENSE"), None)
            out: dict[str, bytes] = {}
            if licence is not None:
                out["LICENSE"] = zf.read(licence)
            with zf.open(names[0]) as src, open(iso_path, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)

        iso = pycdlib.PyCdlib()
        iso.open(str(iso_path))
        try:
            for rr_path, filename in ROM_FILES.items():
                buf = io.BytesIO()
                iso.get_file_from_iso_fp(buf, rr_path=rr_path)
                out[filename] = buf.getvalue()
        finally:
            iso.close()
    return out


def write_roms(date: str, files: dict[str, bytes]) -> list[str]:
    """Replace the vendored ROM images, and keep rom/README.md's date
    and checksum table honest. Returns the files actually changed."""
    changed = []
    for name, data in sorted(files.items()):
        target = ROM_DIR / name
        if target.is_file() and target.read_bytes() == data:
            continue
        target.write_bytes(data)
        changed.append(name)

    readme = ROM_DIR / "README.md"
    text = readme.read_text()
    text = re.sub(r"\*\*AROS \d{8}\*\*", f"**AROS {date}**", text)
    for name in ROM_FILES.values():
        digest = hashlib.sha256(files[name]).hexdigest()
        text = re.sub(rf"^    [0-9a-f]{{64}}  {re.escape(name)}$",
                      f"    {digest}  {name}", text, flags=re.M)
    if text != readme.read_text():
        readme.write_text(text)
        changed.append(readme.name)
    return changed


def main() -> int:
    print(f"discovering nightlies at {LISTING_URL}")
    dates = discover_dates()
    if not dates:
        print("no dated nightly directories found in the listing", file=sys.stderr)
        return 1

    found = fetch_newest_usable(dates)
    if found is None:
        print(f"none of the newest {MAX_DATES_TO_TRY} nightlies "
              f"({', '.join(dates[:MAX_DATES_TO_TRY])}) has the m68k boot-iso",
              file=sys.stderr)
        return 1

    date, data = found
    sha256 = hashlib.sha256(data).hexdigest()
    print(f"newest usable nightly: {date} ({len(data)} bytes, sha256 {sha256})")

    repinned = rewrite_recipe(date, sha256)
    if repinned:
        print(f"re-pinned {RECIPE.relative_to(REPO_ROOT)} to {date}")
    else:
        print(f"already pinned to {date}")

    changed = write_roms(date, extract_roms(data))
    for name in changed:
        print(f"updated {(ROM_DIR / name).relative_to(REPO_ROOT)}")

    if repinned or changed:
        print("now run the smoke build to validate: python tools/ci_recipe_smoke.py")
    else:
        print("vendored ROM already matches — nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
