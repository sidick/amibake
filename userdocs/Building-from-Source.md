# Building from Source

AmiBake has no tagged release yet (see [the index page](index.md)'s
note on project status) — building from source is currently the only
way to get it. See [Installation](Installation.md) for the quick
version; this page covers the full development loop.

## Setup

```sh
git clone https://github.com/sidick/amibake.git
cd amibake
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Requires Python 3.11+ (the stdlib `tomllib` module). Runtime
dependencies: `lhafile` (pure-Python `.lha` extraction), `amitools`
(used as a library for RDB/HDF/`.uaem` emission — never shelled out to
unless the library API is genuinely missing something, and any such
case is a code comment naming the gap), `pycdlib` (ISO9660/Rock Ridge
reading), `unlzw3` (Unix-compress/LZW decoding, needed by some real
update-package payloads).

## Running the test suite

```sh
.venv/bin/pytest              # everything
.venv/bin/pytest -q           # quiet
.venv/bin/pytest tests/unit/test_resolver.py -k name   # one test
```

Most tests are hermetic — no network access, tiny fixture archives
built in-process. Some real-media tests (`tests/unit/test_*_real_media.py`)
`skipif` when the corresponding proprietary media isn't present under
`assets/` — they never run in a fresh clone or in CI, only locally for
whoever has the media to exercise them against.

## Linting

```sh
.venv/bin/ruff check .                              # code (line-length 100)
.venv/bin/amibake lint recipes manifests             # shipped recipes/manifests
```

## The CI smoke build

```sh
python tools/ci_recipe_smoke.py
```

Auto-discovers every network-buildable package recipe (no `[base]`
table, a `[source]` naming Aminet/GitHub/a URL — proprietary
`[source.assets]`-only recipes are skipped, since CI has no legitimate
media for them) and builds each one against the `aros68k` base,
checking its `[verify]` block. This is exactly what runs in CI after
`amibake lint` — a new recipe PR gets this coverage automatically, with
no CI configuration change needed.

## Building the docs site locally

```sh
.venv/bin/pip install -r tools/docs-requirements.txt
.venv/bin/mkdocs serve
```

Serves the site at `http://127.0.0.1:8000/` with live reload —
`userdocs/` is the source; `mkdocs build --strict` (what CI runs) fails
on any broken internal link or malformed nav entry.

## Determinism

AmiBake enforces build-twice-byte-compare determinism from early in
its own test suite: no wall-clock timestamps in outputs, sorted
iteration orders, fixed metadata defaults. If you're touching
`emit/`, `layer.py`, or anything that writes bytes, run the relevant
determinism test explicitly — it's designed to catch exactly the kind
of nondeterminism (a library defaulting to real wall-clock timestamps,
an unsorted dict iteration) that's bitten this project for real before.

## Where to go next

- [CLI Reference](CLI-Reference.md) — the CLI you just built.
- [Writing a Recipe](Writing-Recipes.md) — contribute support for a new
  package.
