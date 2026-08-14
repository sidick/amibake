# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AmiBake is a manifest-driven Amiga test-setup builder ("a Dockerfile for Amiga setups"): a TOML manifest names a base OS, a machine variant, and packages; `amibake build` produces a bootable disk image / directory tree plus matching emulator configs. Early development — see PLAN.md for milestone status (it is the authoritative *how and in what order*; update it when direction changes).

## Commands

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # setup
.venv/bin/pytest                                             # all tests
.venv/bin/pytest tests/unit/test_resolver.py -k name         # one test
.venv/bin/ruff check .                                       # lint (line-length 100)
.venv/bin/amibake lint recipes manifests                     # validate shipped recipes/manifests
.venv/bin/amibake resolve manifests/aros68k.toml             # manifest -> plan + lockfile
.venv/bin/amibake build manifests/aros68k.toml --assets assets  # full build
python tools/ci_recipe_smoke.py                              # CI smoke build (aros68k)
```

Python 3.11+ (stdlib `tomllib`). CI runs ruff, pytest, `amibake lint`, and the smoke build on ubuntu/macos × 3.11/3.13.

## Architecture

Data flow: **manifest.toml → resolver → BuildPlan → builder (fetch → extract → layer) → Tree → verify → emit**.

- `manifest.py` / `recipe.py` — TOML load + schema validation (shared plumbing in `_validate.py`, typed errors in `errors.py`). Unknown keys are errors, never ignored. All versions are strings, never floats.
- `resolver.py` — cross-document validation only (package exists, `[requires]` accepts base/machine, one provider per capability); assumes lint already passed. Errors are collected, not fail-fast, and each names package + requirement + remedy.
- `plan.py` — resolved BuildPlan + lockfile.
- `fetch.py` — Aminet/GitHub/`assets/` sources, sha256 verify, content-addressed cache. Network goes through an injectable `http_get`; tests never touch the network.
- `extract.py` — lha (via `lhafile`, pure Python — deliberate, see module docstring), zip, ADF, ISO9660 (pycdlib), .Z decompression.
- `tree.py` — internal FS representation with Amiga metadata (protection bits, comment, datestamp). Paths are Amiga strings (`SYS:Libs/foo.library`); lookups are case-insensitive, names case-preserving.
- `layer.py` — applies a recipe's `[install]` to a Tree; content-addressed layer cache so a shared base builds once.
- `builder.py` — base applied first as an ordinary layer, then packages in dependency order.
- `paths.py` — maps Amiga `volume:path` onto the single physical output partition.
- `emit/` — outputs: `hdf.py` (RDB/HDF via amitools-as-library), `dirtree.py` (host dir + `.uaem` sidecars), `archive.py`, plus emulator configs `copperline.py` / `uae.py` built from one shared model in `machine.py`.

Recipes (`recipes/<name>/recipe.toml`) are purely declarative; adding package support must never require a builder change. `docs/recipe-contract.md` is the contract and must stay sufficient to write a recipe without reading builder source — if it isn't, that's a documentation bug to fix. `docs/manifest.md` documents the manifest format; `docs/limits.md` records what the schema can't express yet.

## Key constraints

- **Determinism is enforced, not aspirational**: no wall-clock timestamps in outputs, sorted iteration orders, fixed metadata defaults. A build-twice-byte-compare test guards this.
- **CI substrate is freely-available assets** (AROS 68k nightlies, Aminet). Proprietary media (OS 3.x, Kickstart ROMs, Workbench 1.3) live under untracked `assets/` and are exercised by tests that `skipif` when the files are absent (`test_*_real_media.py`). Never commit anything from `assets/`.
- amitools is used **as a library** (`amitools.fs`, blkdev, rdb) — shell out to `xdftool`/`rdbtool` only when the library API is missing something, with a comment naming the missing API. `emit/hdf.py` documents a workaround for an amitools 0.8.1 `HDFBlockDevice` bug.
- AmigaDOS semantics matter throughout: case-insensitive/case-preserving filenames, `#?` wildcards, volume-vs-assign path rules.
