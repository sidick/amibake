# Changelog

AmiBake has not had a tagged release yet — see
[the index page](index.md)'s note on project status. This page tracks
major development milestones (see
[PLAN.md](https://github.com/sidick/amibake/blob/main/PLAN.md) in the
repository for the full detail behind each one); once the first release
ships, it will follow the version scheme in `pyproject.toml`.

## Unreleased (0.1, in development)

- **Core pipeline**: `manifest → resolver → build plan → fetch/extract/
  layer → tree → verify → emit`, end to end. `amibake lint`/`resolve`/
  `build` all work today.
- **Resolver**: dependency graph with version constraints, real Amiga
  version-string comparison (`5.20` > `5.3`, never floats),
  capability/provider resolution, cross-axis `[requires]` validation
  (OS/Kickstart/CPU/FPU/MMU/emulator), typed per-package `[options]`.
- **Fetch/extract**: Aminet, GitHub Releases, and direct-URL sources,
  sha256 verification, a content-addressed cache; `.lha` (pure Python),
  `.zip`, ADF, and ISO9660 (with Rock Ridge) extraction, plus real
  Unix-compress (`.Z`) decoding for Hyperion's own update packages.
- **Four bases ship**: `aros68k` (free nightly, zero-encumbrance CI
  target), `wb1.3`, `os3.1.4`, `os3.2.2` (the last three need your own
  licensed install media) — each real-boot-verified interactively under
  Copperline and/or Amiberry, not just screenshot-checked.
- **20+ package recipes ship** — see the [Recipe Library](Recipes.md)
  for the full list, including AmiSSL, Picasso96 (both the free 2.0 and
  commercial 3.x), ClassAct, MUI (3.8 and 5.0), BGUI, ReqTools, and the
  `bsdsocket-emulation` no-op capability provider.
- **Emitters**: `hdf` (RDB/partitioned hard-disk image via amitools),
  `dir` (host tree + `.uaem` sidecars), `tgz`/`zip`; Copperline and
  Amiberry `.uae` emulator-config emission (WinUAE reuses the same
  writer, unverified against a real WinUAE install), with a
  recipe-contributed `[emulator-config.*]` directive mechanism.
- **Contribution machinery**: `amibake lint` as the contribution
  linter, a CI smoke build that auto-discovers and builds every
  network-fetchable recipe, `docs/recipe-contract.md` validated by a
  fresh-context recipe write-up that found and fixed two real
  documentation gaps, a fenced `[hook]` escape hatch (`--allow-hooks`)
  for the rare case declarative `[install]` genuinely can't express.
- **Determinism enforced from early on**: a build-twice-byte-compare
  test guards every output format; real nondeterminism bugs (an
  amitools API defaulting to wall-clock timestamps) were found and
  fixed this way, not retrofitted after the fact.

## What's not done yet

- A packaged/tagged release.
- A GitHub Action for wiring AmiBake into another project's own CI
  (inputs = manifest list, outputs = built images as artifacts keyed by
  lockfile hash) — the next milestone (see PLAN.md's M9).
- Automated, assertable "did it boot" CI checks — today's boot
  verification is real but manual (screenshots + live input probes over
  each emulator's own automation interface), not yet wired into CI
  itself.
