# AmiBake

AmiBake is a manifest-driven Amiga test-setup builder — a Dockerfile
for Amiga setups. A TOML manifest names a base OS, a machine variant
(CPU/FPU/MMU/RAM/RTG/chipset), and a list of packages; `amibake build`
resolves versions and dependencies, fetches and verifies every source,
and produces a bootable disk image (or host directory tree) plus
matching emulator configuration — ready to boot under Copperline or
Amiberry, no hand-editing required.

```toml
base     = "os3.2.2"
machine  = { cpu = "68030", fpu = true, mmu = true, ram = "fast:8M", rtg = true }
packages = [
  "picasso96-3 >= 3.2",
  "amissl = 5.20",
  "classact = 3.3",
]
output   = ["hdf", "dir"]
emit     = ["copperline", "amiberry"]
```

## Why AmiBake, not a hand-maintained disk image

- **Declarative, not scripted.** A recipe describes *what* a package
  needs (source, files to copy, requirements, options) — never *how* to
  build it. Adding a new package never requires touching AmiBake's own
  code, just a `recipe.toml`.
- **Reproducible on purpose.** Every build is pinned: exact package
  versions, checksummed sources, a lockfile recording everything that
  was resolved. No wall-clock timestamps, no nondeterministic iteration
  order — build the same manifest twice and get byte-identical output.
- **Real Amiga semantics throughout.** Case-insensitive/case-preserving
  filenames, `#?` AmigaDOS wildcards, volumes vs. assigns, CPU/FPU/MMU
  as independent hardware axes, Kickstart-version and CPU-floor
  requirements — the resolver understands the platform, not just files
  on disk.
- **One manifest, every output.** The same resolved build emits `hdf`
  (a bootable RDB/partitioned hard-disk image), a host directory tree,
  or an archive — and, for emulator use, a ready-to-go Copperline or
  Amiberry (or WinUAE) config pointed at it.
- **A real recipe library, not a toy example.** AmiSSL, Picasso96,
  ClassAct, MUI, BGUI, ReqTools, and more already ship — see the
  [Recipe Library](Recipes.md).

## Where to start

- [Installation](Installation.md) — getting `amibake` onto your `PATH`.
- [Getting Started](Getting-Started.md) — resolving and building your
  first manifest, from the zero-encumbrance AROS 68k base.
- [CLI Reference](CLI-Reference.md) — every subcommand and flag.
- [Manifest Format](Manifest-Format.md) — the full `base`/`machine`/
  `packages`/`output`/`emit` schema.
- [Recipe Library](Recipes.md) — every base and package recipe shipped
  today.
- [Writing a Recipe](Writing-Recipes.md) — contributing support for a
  new package.
- [Emulator Configs](Emulator-Configs.md) — how `emit` turns a build
  into a ready-to-boot Copperline/Amiberry/WinUAE config.

## A note on where AmiBake is today

AmiBake is pre-1.0, actively developed software, but its core pipeline
is real and end-to-end verified: `manifest → resolver → build plan →
fetch/extract/layer → tree → verify → emit` all work today, against
real recipes and real media. Four bases ship — AROS 68k (fetched from
a free nightly, the zero-encumbrance base CI builds from nothing),
Workbench 1.3, AmigaOS 3.1.4, and AmigaOS 3.2.2 (the last two need your
own licensed install media, never fetched or committed by AmiBake
itself) — and 20+ package recipes. Builds have been verified to
actually boot interactively (not just "painted a screen") under both
Copperline and Amiberry, with live mouse/keyboard interaction confirmed
over each emulator's own automation interface.

What hasn't shipped yet: a packaged release (build from source for
now — see [Building from Source](Building-from-Source.md)), and a
GitHub Action for wiring AmiBake into another project's own CI. See
[PLAN.md](https://github.com/sidick/amibake/blob/main/PLAN.md) in the
repository for the full milestone-by-milestone status.
