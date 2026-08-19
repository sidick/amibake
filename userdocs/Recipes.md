# Recipe Library

Every recipe lives under `recipes/<name>/recipe.toml` in the
repository — purely declarative TOML, no code. This page is a quick
index of what ships today; each recipe's own header comment has the
full sourcing/licensing detail, and `amibake lint recipes` (see
[CLI Reference](CLI-Reference.md)) is always the authoritative check
that a given recipe is currently valid.

Package names below are exactly what goes in a manifest's `packages =
[...]` list (see [Manifest Format](Manifest-Format.md)); base names go
in `base = "..."`.

## Bases

| Name | Versions | Source | Notes |
|---|---|---|---|
| `aros68k` | nightly-dated | Free SourceForge nightly | Zero-encumbrance smoke target — builds from nothing, no user-supplied media. Every recipe's own smoke test runs against this base. |
| `wb1.3` | `1.3.3`, `1.3` | User-supplied ADF (`assets/`) | Kickstart/Workbench 1.3 — a single 880K floppy, OFS, no Installer. `boot` option: `workbench` (full desktop, default) or `cli` (minimal, fast). |
| `os3.1.4` | `3.1.4` | User-supplied media (`assets/`) | Hyperion's current retail continuation of Commodore's original 3.1; the first base built from a genuinely Installer-driven original (translated declaratively, not executed). |
| `os3.2.2` | `3.2.2` | User-supplied media (`assets/`) | Base install + cumulative 3.2.1/3.2.2 point-release updates, matching Hyperion's real distribution model. |

## Packages

| Name | Versions | What it is |
|---|---|---|
| `ahi` | `4.18` | Retargetable audio system (`ahi.device` + `AUDIO:` handler + prefs). |
| `amipilot` | `1.1` | Object-level AmigaOS GUI automation (AmiInspect + AmiPilotServer, ARexx/network-driven). |
| `amissl` | `5.27`, `5.20` | OpenSSL as an Amiga shared library. |
| `bgui` | `41.11` | BOOPSI-based GUI toolkit (`bgui.library`). |
| `bsdsocket-emulation` | `1.0` | No-op capability provider: satisfies a `bsdsocket` requirement without installing a real TCP/IP stack, via each emulator's own bsdsocket emulation. |
| `classact` | `3.3` | BOOPSI GUI toolkit (`window.class`, `layout.gadget`, `listbrowser.gadget`, 30+ others) — needed by OS 3.1, bundled natively by OS 3.2. |
| `lha` | `2.15` | The standard Amiga archiver — provides the `lha` capability for other recipes/tools to depend on. |
| `mmulibs` | `3.2.2` | CPU support libraries (`680x0.library` + `68030`/`68040`/`68060.library`) — stops `CPU CHECKINSTALL` failing at boot on 68030+. |
| `muforce` | `47.1` | mmu.library-aware memory-protection debugger (Enforcer's successor). |
| `muguardianangel` | `40.52` | Access-protects non-allocated memory too — superset of classic MungWall/Guardian Angel. |
| `mui` | `3.8` | Magic User Interface — the most widely used Amiga GUI toolkit. |
| `mui5` | `5.0` | Actively-maintained MUI successor (`amiga-mui/muidev`), developed with the original author's permission. |
| `picasso96-2` | `2.0` | Freely-redistributable predecessor to P96 (same RTG architecture). |
| `picasso96-3` | `3.6.3` | P96, the commercial/copyrighted successor to Picasso96 — user-supplied media (`assets/`), unverified against the current licensed archive. |
| `reqtools` | `2.9a` | `reqtools.library`, the classic shared requester toolkit. |
| `sana2loop` | `1.1` | Hardware-free SANA-II loopback network device — the KS 1.3-capable exemplar package. |
| `segtracker` | `47.6` | Global segment-list tracking utility (address → library/device/program). |
| `whdload` | `20.0` | Hard-disk install/loader for floppy-only games and demos, plus its supporting tools. |
| `xfdmaster` | `1.38` | Single-file decrunching (`xfdmaster.library` + slave modules). |
| `xpk` | `5.2a` | Packer-library interfacing standard (`xpkmaster.library` + 16 compressor sub-libraries). |
| `phxass` | `4.39` | Frank Wille's optimizing 680x0/FPU/MMU macro assembler. |

Package versions with more than one entry (e.g. `amissl`'s `5.27`/
`5.20`) are both real, checksum-pinned releases — a manifest's version
constraint (`= 5.20`, `>= 3.2`, ...) picks among them.

## What's proprietary, and how AmiBake handles it

Some real Amiga software (OS 3.x media, Kickstart ROMs, the current P96
license) can't be legally redistributed — those recipes use
`[source.assets]`: you supply the file under your own `assets/`
directory (gitignored, never fetched or committed by AmiBake), and the
recipe reads it by declared filename/checksum. Everything else is
fetched automatically from Aminet, GitHub Releases, or a direct URL,
verified by sha256 against the recipe's own pinned checksum.

## Where to go next

- [Writing a Recipe](Writing-Recipes.md) — add a package that isn't
  here yet.
- [Manifest Format](Manifest-Format.md) — how to reference these in a
  manifest's `base`/`packages`.
