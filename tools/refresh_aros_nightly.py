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
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RECIPE = REPO_ROOT / "recipes" / "aros68k" / "recipe.toml"

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

    if rewrite_recipe(date, sha256):
        print(f"re-pinned {RECIPE.relative_to(REPO_ROOT)} to {date}")
        print("now run the smoke build to validate: python tools/ci_recipe_smoke.py")
    else:
        print(f"already pinned to {date} — nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
