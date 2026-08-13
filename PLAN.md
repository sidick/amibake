# AmiBake Implementation Plan

Working plan for implementing the AmiBake proposal (manifest-driven Amiga
test setup builder). The proposal is the *what and why*; this document is
the *how and in what order*. Where the two disagree, update this file and
note the divergence.

## Ground rules

- Python 3.11+ (stdlib `tomllib`), packaged with `pyproject.toml`, src
  layout. amitools is a runtime dependency, used **as a library** (its
  `amitools.fs` / blkdev / rdb modules), shelling out to `xdftool`/
  `rdbtool` only where the library API is missing something — each such
  case gets a code comment naming the missing API. `.lha` extraction uses
  `lhafile` (pure Python) rather than the lhasa/`lha` CLI the proposal
  named — see the M2 entry in "Cross-cutting decisions" below.
- Every milestone ends in something runnable and tested. No milestone
  depends on assets the CI can't have: AROS 68k nightlies and Aminet
  packages are the CI substrate; OS 3.x/1.3 media paths are exercised
  locally and by asset-gated CI jobs that skip-with-notice when
  `assets/` is absent.
- Determinism is enforced from day one, not retrofitted: no wall-clock
  timestamps in outputs, sorted iteration orders, fixed metadata defaults.
  A `build twice, byte-compare` test exists from Milestone 2 onward.

## Repository layout

```
amibake/
  pyproject.toml
  src/amibake/
    cli.py            # argparse entry: build, resolve, lint, cache, verify
    manifest.py       # manifest load + schema validation (typed errors)
    recipe.py         # recipe.toml load + schema validation
    resolver.py       # dependency graph, capability/provider resolution,
                      # [requires] validation (os/ks/cpu/emulator axes)
    plan.py           # resolved build plan + lockfile read/write
    fetch.py          # Aminet/mirror + GitHub Releases fetch, checksum
                      # verify, local cache, assets/ lookup
    extract.py        # lha/zip/adf content extraction to internal tree
    tree.py           # internal FS representation: files + Amiga metadata
                      # (protection bits, comment, datestamp)
    layer.py          # layer application + content-addressed layer cache
    emit/
      hdf.py          # RDB/partitioned HDF via amitools
      dirtree.py      # host dir + .uaem sidecars
      archive.py      # tgz (primary), zip (convenience)
      configs/        # emulator config emitters: copperline.py,
                      # amiberry.py, winuae.py — one shared model in
                      # machine.py, per-emulator serializers
    machine.py        # machine block model: cpu family, fpu, mmu, ram,
                      # rtg, chipset; validation
    errors.py         # the error taxonomy: every user-facing failure is a
                      # typed error with package/requirement/remedy fields
  recipes/            # recipe library (versioned with repo for now;
                      # split out later per proposal if it grows)
    amissl/recipe.toml
    p96/recipe.toml
    classact/recipe.toml
    bases/os3.2/recipe.toml
    ...
  manifests/          # exemplar + fixture manifests
  tests/
    unit/             # resolver, manifest/recipe schema, cache keys
    fixtures/         # tiny fake recipes + archives for hermetic tests
    integration/      # real builds (AROS base in CI; OS3.x asset-gated)
  docs/
    recipe-contract.md   # THE published contract (docs-only bar)
    manifest.md
    limits.md            # honest-limits table
```

## Milestones

Milestones are finer-grained than the proposal's weekend phases so each
lands as a reviewable PR. Mapping to proposal phases noted per milestone.

### M0 — Skeleton and contracts (Phase 1)

- Package scaffold, CLI with `amibake build <manifest>` stub, CI running
  pytest + ruff on macOS and Linux.
- Write `docs/recipe-contract.md` and `docs/manifest.md` **first**, as the
  spec the code is tested against — the schema in the proposal (package /
  requires / source / install / verify / options / provides) transcribed
  and tightened: exact types, required vs optional, pattern syntax (`#?`
  AmigaDOS patterns), option typing, startup-fragment ordering keys.
- `manifest.py`, `recipe.py`: parse + validate against those docs with the
  typed-error style (every error names the file, the field, and the fix).
  Unit tests are table-driven over invalid documents.

Exit: `amibake lint recipes/… manifests/…` passes/fails correctly on
fixture documents.

### M1 — Resolver (Phase 1)

- Dependency graph with version constraints (`>=`, `=`, ranges), Amiga
  version-string comparison done properly (`5.20` > `5.3`; never floats).
  A small `AmigaVersion` type with its own tests.
- Capability/provider resolution: `provides`, one-provider-per-capability,
  ambiguity error listing candidates, manifest override to pick.
- `[requires]` validation across all axes — OS range, Kickstart, CPU floor
  (respecting fpu/mmu flags), emulator list — including per-*version*
  requirement ranges and transitive validation. The KS 1.3 + `>= 3.0`
  package pairing is a named unit-test fixture (it's a success criterion).
- Typed parameters (the P96 case): option declaration, manifest answers,
  option-value `[requires]`, `auto` defaults resolved into the plan.
- Output: a deterministic **build plan** (ordered layer list with all
  inputs pinned) and the **lockfile** format (`*.lock.toml`: every
  resolved version, checksum, option value, recipe content hash).

Exit: `amibake resolve manifest.toml` emits plan + lockfile; the full
error-message suite (missing package, version conflict, requires
violation, provider ambiguity, missing option) is unit-tested on wording
fields, not string matching.

### M2 — Fetch, extract, tree, layers, cache (Phase 1)

- `fetch.py`: Aminet URL templating, GitHub Releases URL templating
  (`[source.github]` — the better fit for actively maintained packages
  that tag releases, since Aminet often keeps only the current release
  under a rolling unversioned filename), configurable mirror list, sha256
  verify, content-addressed download cache (`~/.cache/amibake` or
  `AMIBAKE_CACHE`), `assets/` lookup by checksum for proprietary sources.
- `extract.py`: `.lha` via `lhafile` (pure Python), `.zip` via stdlib,
  plus reading files out of ADFs via amitools — all into `tree.py`'s
  internal representation carrying Amiga metadata.
- `layer.py`: apply a recipe's `[install]` (copy with AmigaDOS patterns,
  cpu-variant selection, envarc, ordered user-startup fragments, assigns)
  to a tree; cache key = hash(recipe text + resolved version + archive
  sha + options + parent layer key); cached layers stored as canonical
  tgz of the tree delta. `--no-cache` bypass.
- Determinism test: same manifest built twice from cold cache → identical
  tree hash. Runs in CI from here on.

Exit: a fixture manifest with fake recipes builds end-to-end to an
internal tree, layers cached and reused across two manifests sharing a
base layer.

### M3 — Emitters (Phase 1 + Phase 2 boundary)

- `emit/dirtree.py`: host tree + `.uaem` sidecars (UAE metadata format —
  match amisnap-tool's convention exactly; document byte format in code).
- `emit/archive.py`: tgz primary (honest Latin-1 bytes in names), zip
  convenience; both deterministic (sorted entries, zeroed mtimes unless
  the Amiga datestamp is meaningful — Amiga datestamps live in sidecars).
- `emit/hdf.py`: RDB + partition + FFS/OFS format per machine block via
  amitools, populate from tree with metadata. OFS + pre-2.0 constraints
  selectable (needed later for 1.3).
- `[verify]` execution: `exists` checks against the built tree.
- All emitters consume the same built tree; a test asserts hdf contents
  == dir contents (extract hdf back with amitools, compare).

Exit: `amibake build` produces hdf/dir/tgz from one build with one
lockfile; contents cross-verified.

### M4 — Real recipes + the AROS base (Phases 1–2, CI substrate first)

Deliberate reordering vs the proposal: AROS 68k base comes **before**
any real AmigaOS extract base, because it is the only base CI can build
from nothing and every subsequent milestone needs a CI-buildable base
to test against. Among the real AmigaOS bases that follow, WB 1.3 comes
next (M5) and OS 3.2 — the proposal's own Phase 1 exemplar — comes last
(M8); see M5's own entry for why.

- Base-recipe mechanics: `strategy = extract` support in recipe schema
  (multi-disk/ISO sources, selection options, startup-sequence steps).
- `bases/aros68k`: fetched nightly, checksum-pinned per lockfile build.
- Real recipes: AmiSSL, ClassAct 3.3 (both freely fetchable) — exercised
  in CI on the AROS base where compatible; P96 with the `card` option
  (uaegfx path testable, asset paths gated).
- First boot verification: build an AROS manifest, boot it under
  Amiberry, confirm a genuine interactive boot (not just a static
  screenshot) via live mouse-cursor response over MCP — see the
  "Cross-cutting decisions" boot-verification entry for what this did
  and didn't settle (real, manual, local verification; automated CI
  wiring is M9).

Status: done. `manifests/aros68k.toml` builds real content (96MB, 72
libraries, all core system dirs) and boots interactively under Amiberry,
verified locally. AmiSSL (already existed, fixed two real bugs surfaced
along the way — see decision log), ClassAct 3.3, and P96 (proprietary,
`[source.assets]`, unverified against a real archive — see its recipe's
own header comment) are real recipes. Base recipe content is now wired
into `build_tree` (previously a no-op). Not done: automated CI boot
assertion (M9); P96 build-tested against real data (no licensed archive
available to any session).

### M5 — WB 1.3 base (Phase 3 scope, proposal success criterion 3, moved earlier)

**Reordered vs both the proposal and this plan's own original M5/M8
split** (user, 2026-08-13): WB 1.3 first, OS 3.2 last among the
extract-base work — the proposal's own text calls 1.3 "the most
extract-friendly install of all" (plain file copies, no Installer),
and M4's `[base].dos-type` work already proved out exactly the
filesystem mode 1.3 needs (plain FFS/OFS, no international mode). OS
3.2 by contrast has real versioning surface area (3.2, 3.2.1, 3.2.2,
3.2.2.1, and whatever's shipped by the time this milestone starts)
worth deferring until the extract-base mechanism is proven on the
simplest real case first. Cost: the already-shipped exemplar manifest
(`manifests/os32-p96-amissl.toml`, `base = "os3.2.2"`) stays
unbuildable until M8 — acceptable, it was always going to be
unbuildable until *some* OS 3.x base landed.

- `bases/wb1.3`: install media (ADF set) from `assets/` keyed by
  checksum; plain-copy extract (no Installer); OFS or plain FFS output
  (`[base].dos-type`, never an `-intl` variant — 1.3 predates that FFS
  extension); 1.3 startup-sequence conventions; RAM-based `ENV:` assign;
  machine block pairing with a KS 1.3 ROM asset.
- CI fixtures (proposal's success criterion 3): a 1.3 manifest with a
  1.3-capable package (sana2loop is the proposal's own suggested
  exemplar) builds and boots; a 1.3 base + `>= 3.0` package fails with
  the resolver's named error — this half of the criterion already has
  fixture coverage in `tests/unit/test_resolver.py` from M1
  (`test_ks13_base_rejects_os3_package_with_named_error`), so this
  milestone's own new work is the *positive* build+boot fixture.

**Settled in M5**: `recipes/wb1.3/recipe.toml` and
`manifests/wb13.toml` are written and lint clean. `[source.assets]`'s
`path` names a raw `.adf` floppy image — `extract.py` had no ADF
reader (it only handled `.lha`/`.zip`/`.iso`), so ADF support was added
via `amitools.fs.ADFSVolume`/`ADFBlockDevice` (the same dependency the
`hdf` emitter already uses, now used for reading rather than writing).
Real KS 1.3 media is proprietary and unavailable to any session that's
worked on this recipe, so the recipe's structure is grounded in real
technical documentation (a genuine `Workbench1.3` ADF's
Startup-Sequence and disk-format analysis — see the recipe's own
comments) rather than independently re-derived from a full disk
listing; `tests/unit/test_wb13_recipe.py` builds the *real* recipe and
manifest end-to-end against a synthetic ADF fixture (`make_adf` in
`conftest.py`, which round-trips through the same amitools ADF-reading
code path a real dump would) — a permanent regression test independent
of whether real media is ever available, confirmed valuable in its own
right (user, 2026-08-13: "the synthetic one makes for a good test").
User may supply real media at `assets/Workbench-1.3.adf` (gitignored)
for a follow-up real-media build/boot pass. `sana2loop` (the proposal's
own 1.3-capable exemplar) is not yet a shipped recipe, so the manifest
lists no packages — the *positive* build+boot fixture landed here is
the base build itself, not yet a boot-verified full manifest; boot
verification (Copperline preferred per house policy) is still pending.

**Real media supplied and recipe corrected against it (user, 2026-08-13,
same day):** user dropped a TOSEC WB dump set into `assets/`. Built and
verified against real "Workbench v1.3 rev 34.20 (GB)" and
"Workbench v1.3.3 rev 34.34 (US)" floppy-1 ADFs (`assets/Workbench-1.3.adf`
/ `assets/Workbench-1.3.3.adf`, both real, legitimate, unmodified TOSEC
dumps — their sha256 is now in the recipe). This real-media pass found
and fixed real bugs/wrong assumptions, none of which the synthetic
fixture (matched case by construction) could have caught:
- **Real bug in `layer.py`**: `[install].copy` pattern matching is
  case-insensitive (`re.IGNORECASE`, correct — real archives mix case
  freely) but the literal-prefix relative-path stripping used to
  preserve subdirectory structure was case-*sensitive*, so a pattern
  like `Libs/#?` matching real lower-case `libs/diskfont.library` failed
  its prefix strip silently and produced `SYS:Libs/libs/diskfont.library`
  instead of `SYS:Libs/diskfont.library` — wrong path, no error. Fixed
  to strip case-insensitively while preserving the archive's real
  casing for the remainder.
- **Wrong recipe assumption**: the original recipe's `[verify]` checked
  for `SYS:Libs/dos.library` — real KS1.3-era `dos.library` (and
  `exec.library`, `mathffp.library`) are resident in Kickstart ROM, not
  shipped as disk files at all, unlike 2.0+ where more of the OS lives
  on-disk. Real disk content confirmed via the new ADF reader: only
  `mathieeedoubbas`/`mathieeedoubtrans`/`mathtrans`/`diskfont`/`icon`/
  `info`/`translator`/`version` libraries are on-disk. `[verify]` now
  checks `SYS:Libs/diskfont.library` instead.
- **Wrong recipe assumption**: original comment claimed Prefs/System/
  Utilities/Shell (the actual Workbench desktop GUI) were only on the
  "Extras1.3" disk excluded by design — false, real disk 1 ships them
  too. Recipe now explicitly scopes to a CLI/AmigaDOS-level boot
  environment (C:/Devs:/L:/Libs:/Fonts: only) as a real, documented
  choice rather than a mistaken assumption, and flags the known
  consequence: the *real* on-disk Startup-Sequence calls
  `SYS:System/SetMap` and `LoadWB`, neither viable with this subset, so
  it isn't copied.
- Added `tests/unit/test_wb13_real_media.py`, skipped when
  `assets/Workbench-1.3.3.adf` is absent (CI/fresh clones never have
  it) — the genuine real-media build+verify check; passes now.
- `[package].versions` now `["1.3.3", "1.3"]`, both backed by real
  checksums (34.34 US unmodified, 34.20 GB unmodified — no unmodified
  non-regional 34.20 dump was in the supplied set).

**Framework-level design gap resolved same day (user's suggestion,
2026-08-13, commit 92ac4cd):** the "real 1.3 never sources
S:User-Startup" gap above is fixed generally, not just for wb1.3 —
`Tree.materialize()` now appends an `IF EXISTS S:User-Startup /
EXECUTE S:User-Startup / ENDIF` stanza to whatever Startup-Sequence a
base installed, if it doesn't already source one (no-op on bases like
aros68k whose real Startup-Sequence already does). Since real 1.3's own
Startup-Sequence isn't shippable here at all (calls `SYS:System/SetMap`
and `LoadWB`, neither viable with this base's file subset), wb1.3 now
authors its own minimal one via a new `[install].files` mechanism
(literal-content file at an arbitrary destination, generalizing the
existing `envarc` pattern) — every command it uses (SetPatch,
Addbuffers, BindDrivers, Makedir, Assign, Mount) confirmed present on
the real disk. Found and fixed a second real bug while wiring this up:
`S:User-Startup` (written by `materialize()`) and
`SYS:S/Startup-Sequence` (what every recipe's `[install]` destinations
actually use) are different Tree keys pre-emit — they only unify at
emit time via `paths.py`'s `to_physical_path` — so the new lookup has
to check both forms; verified end-to-end with a synthetic downstream
package's `user-startup` fragment actually landing in, and being
sourced from, the real wb1.3 base's authored Startup-Sequence.

**`recipes/sana2loop` shipped (2026-08-13):** the proposal's own
suggested 1.3-capable exemplar package, real Aminet release
`comm/net/sana2loop.lha` (v1.1, `[requires].os = ">= 1.3"`). Real
archive layout confirmed against the actual downloaded .lha (not
guessed) — a `sana2loop/` dir with `loopback.device` and four
2.04+-only Shell tools (SanaInfo/SanaDump/SanaSend/SanaConform). Only
`loopback.device` is installed: per the archive's own readme the
device itself targets "plain 68000 and Kickstart 1.3", but the tools
need AmigaOS 2.04+ (V36+ Exec calls), and `[requires]` is one os floor
for the whole recipe — shipping only the part that's honestly `>= 1.3`
matches the recipe's own stated requirement. `manifests/wb13.toml` now
lists `packages = ["sana2loop = 1.1"]`; resolved and built for real
against both the live Aminet archive and real WB1.3 media via the CLI
(`SYS:Devs/Networks/sana2loop.device` lands correctly — path corrected
same day per the package author, see below — `[verify]` passes).
Not turned into a live-network pytest test (would make the hermetic
suite depend on network access every run, same reasoning as AmiSSL/
ClassAct/AROS in M4) — `test_wb13_recipe.py`/`test_wb13_real_media.py`
build the base with `packages=()` instead, `dataclasses.replace`d off
the real resolved plan, so they stay offline-only.

**Install path corrected (package author, 2026-08-13):** the real
convention is `DEVS:Networks/sana2loop.device` (renamed from the
archive's own `loopback.device`), not a plain `DEVS:` copy under the
archive's build name — the Aminet-hosted readme's install section was
stale. Verified for real via CLI build.

**Copperline boot verification done (2026-08-13), closing this
milestone.** A real `copperline` (and `copperline-ctl`) binary turned
out to be installed locally (`/opt/homebrew/bin/copperline`) — the
first time Copperline (rather than Amiberry, M4's substitute) has
actually been available and used in this project, per the standing
"prefer Copperline generally" guidance. Real KS1.3 ROM found at
`/Users/simond/src/copperline-bridgeboard-plugin/nondistributable/kickstart-1.3.rom`
(outside this repo, correctly marked non-distributable) and copied to
`assets/roms/kickstart-1.3.rom` (gitignored, per user request: "any
roms that get used, copy them into the asset directory for future
use"). Built `manifests/wb13.toml` for real (base + sana2loop, both
`hdf` and `dir` outputs) via the CLI, then booted the `dir` output
under Copperline headless (`--screenshot-after`, no window/display
connection needed — works in this sandboxed session) using a
`[[filesys]]` HOSTFS mount with `bootpri = 6` (Copperline's own
directory-as-bootable-AmigaDOS-volume mechanism — no RDB/real disk
controller authenticity concerns the way `[ide]`/`[scsi]` would raise
for a stock A500's real hardware limits). Confirmed genuinely booted,
not just "painted a screen and hung" (the M4 bar): a screenshot at 10s
shows the real AmigaDOS 1.3 copyright banner and a live `1>` prompt,
stable through 20s/30s captures; then, following M4's own "moving
cursor, not a static screenshot" precedent, scripted `version` +
return via `--press-after` and captured the CLI's live response —
`Kickstart version 34.5. Workbench version 34.34`, exactly matching
this build's own real Kickstart/Workbench versions, followed by a
fresh `1>` prompt. That's the shell genuinely executing our built
`SYS:C/Version` against ROM-resident `exec.library`/`dos.library`, not
a frozen frame.
   Real Copperline CLI gotchas found getting there (useful if this
   becomes an automated M9 CI check): `--press-after SECS KEY` takes
   only two arguments in this build, *not* three — the docs' own
   table agrees (`--key-after SECS KEY MS` is the one with a hold
   duration); passing a spurious third token gets silently misparsed
   as a second positional ROM path (`Error: more than one ROM path
   given`). `--script FILE` had the same failure mode in this build
   (the script's path itself got swallowed as a second ROM argument)
   — chained `--press-after`/`--key-after` flags on the command line
   worked fine and is what was used instead. Repeated
   `--screenshot-after SECS PATH` flags only honored the *last* one
   given in this build, contrary to the docs' "the flag repeats"
   claim — worked around by running one `copperline` invocation per
   timestamp instead of trying to batch several into one run.

Exit: a KS 1.3 manifest builds from WB 1.3 media and boots. **Met.**

### M6 — Machine block + emulator config emission (Phase 2)

- `machine.py` finalized: structured cpu (family + fpu + mmu), ram spec
  parsing, rtg, chipset; cross-axis validation wired into resolver
  (bsdsocket-emulation no-op recipe as the exemplar, `uaegfx` requiring a
  UAE-family emulator).
- Config emitters: Copperline first, then Amiberry `.uae`, WinUAE
  template. Recipes can contribute config directives (the general power
  behind the no-op bsdsocket provider). Emitted config matches chosen
  output (hdf mount vs directory mount).
- `bsdsocket-emulation` recipe shipped; Copperline-only manifest asking
  for it fails with the named error (unit fixture).

Exit: one manifest → ready-to-boot on Copperline and Amiberry with
emitted configs, no hand editing.

### M7 — Contribution machinery (Phase 3)

- `amibake lint` hardened into the contribution linter (hook-escape
  flagged loudly); recipe-PR CI: lint → fixture-manifest build → its
  `[verify]` block, on the AROS base wherever the package allows.
- `docs/recipe-contract.md` brought to the docs-only bar and validated
  the only way it can be: someone (or a fresh agent session given only
  the docs) writes a recipe for an unchosen package without reading
  builder source.
- `docs/limits.md` honest-limits table started; Python-hook escape hatch
  implemented and fenced.
- OS 3.1 base — the third extract base overall (after AROS, WB 1.3),
  proving the base-recipe format generalises across a genuinely
  Installer-driven OS, not just the plain-copy cases; 3.1+ClassAct
  manifest as fixture.

### M8 — OS 3.2 extract base (Phase 1's centrepiece, deferred from M5)

- Study Emu68-Imager's per-version handling before writing (proposal's
  prior-art rule); record findings in `docs/bases.md`.
- `bases/os3.2`: install media ADFs/ISO from `assets/` keyed by checksum;
  declarative multi-disk copy trees; locale/CPU selections as options.
  Pin one specific point release (3.2.2.1 or whatever's current) the
  same way `recipes/aros68k` pins one specific nightly — the proposal's
  own "manifest + lockfile rebuilds byte-identically" discipline applies
  to which point release a base recipe names, not just to packages.
- Fidelity check: one-time diff of extracted base vs a genuine reference
  install (local task, scripted as `amibake verify-base`), divergences
  encoded back into the recipe; the diff script stays in-repo.
- Asset-gated CI job (self-hosted or skip-with-notice) building
  `manifests/os32-p96-amissl.toml` (the proposal's example, shipped
  since M0 and finally buildable) and booting under Copperline.

Exit: proposal success criterion 1 — pristine media → bootable setup
passing an existing portfolio suite, no manual step.

### M9 — CI action + adoption + release (Phase 4)

- `amibake-action` per the amigui-action pattern: inputs = manifest list,
  outputs = built images as artifacts keyed by lockfile hash.
- Convert one real project's test matrix; `make test-target` manifest
  parameter in the amiga-dev image.
- Release per house pattern; six-month reproducibility criterion armed by
  archiving a release-day manifest+lockfile pair and a scheduled CI job
  that rebuilds and byte-compares against the local cache.

### M10 (optional, only if a base demands it) — `strategy = installer`

AmiPilot driving the genuine Installer under Copperline. Deferred exactly
as the proposal says; a first-boot deferred-install stage (Emu68-Imager's
technique) is the recorded alternative if determinism under the harness
proves hard.

## Future work (not scheduled)

Ideas flagged during implementation that are real and worth doing, but
aren't part of the M0-M10 sequence and haven't been sized/placed yet.

- **Update checking.** Recipes pin an exact version + checksum by
  design (reproducibility), so nothing should auto-upgrade — but
  there's currently no way to learn a recipe has fallen behind
  upstream without manually re-checking Aminet/GitHub by hand. A
  future `amibake check-updates` (name TBD) would compare each
  recipe's declared `[package].versions` against the live upstream
  (Aminet's current listing for `[source.aminet]`, the GitHub Releases
  API for `[source.github]`) and report which recipes have a newer
  upstream version available — purely advisory, prints a report, never
  edits a recipe or a lockfile itself.
- **GitHub as a fetch-time fallback for Aminet, not just an
  alternate-to-declare.** `docs/recipe-contract.md` already documents
  that a recipe may declare more than one non-assets source "as
  alternates for the fetcher to try," but `fetch.py`'s actual
  `fetch_sources()` doesn't implement that: it picks the first source
  present in a fixed priority (github > aminet > url) and hard-fails if
  *that one* fails — it never falls through to a second declared
  source. Real motivating case (user, 2026-08-13): Aminet often hosts
  only the *current* release under a rolling filename that gets
  replaced in place (already documented as a `[source.aminet]`
  limitation), so a pinned older version's archive can simply vanish
  from Aminet while remaining permanently available as a tagged GitHub
  release — sana2loop is the concrete example, still fetchable from
  every one of its tagged releases at github.com/sidick/sana2loop even
  once Aminet only shows the latest. Future feature: real fetch-time
  fallback — when a recipe declares both `[source.aminet]` and
  `[source.github]` for the same version and the preferred source's
  fetch fails (network error, 404, or a checksum mismatch that looks
  like "this version isn't there anymore" rather than "the file
  changed unexpectedly"), automatically retry the next declared
  alternate before raising `FetchError`, rather than failing on the
  first attempt.

## Cross-cutting decisions to settle early (flagged, not blocking M0)

1. **Settled in M4**: boot-verification channel — how CI observes "it
   booted." Copperline wasn't available to test against in this
   environment; validated the Amiberry MCP screenshot approach directly
   instead, manually, against the real `manifests/aros68k.toml` build:
   loaded the manifest's own pinned nightly ROM (softkicked via
   `kickstart_rom_file`/`kickstart_ext_rom_file` pointing at the exact
   `aros-rom.bin`/`aros-ext.bin` the recipe fetched) and the built `dir`
   output mounted as a directory hard drive, and confirmed a genuine
   interactive boot — not just a static "looks booted" screenshot — by
   moving the mouse via IPC and observing the cursor render and track in
   real time on a live "Workbench Screen". A static screenshot alone
   would have been ambiguous (a hung Intuition can still have painted a
   screen); the moving-cursor check is the actual reusable signal for a
   future automated harness. Two real findings from getting there:
   - AROS's own ROM (`aros-rom.bin` + `aros-ext.bin`, 512K each) loads
     as a normal split Kickstart/extended-ROM pair in Amiberry — no
     special "softkick" dance needed under emulation, since the
     emulator can just place the ROM image directly rather than
     bootstrapping it from a floppy the way real hardware must.
   - A directory-mounted base boots correctly but visibly slower during
     first-boot scanning than a native block device would — expected,
     not a bug, and a reason to prefer `hdf` output over `dir` for any
     future timed/automated boot-verification step.
   Turning this into an automated, assertable CI check (a real "did it
   boot" pass/fail, not a manually-eyeballed screenshot) is still open —
   tracked for M9 (CI action) rather than solved here. **User guidance
   (2026-08-13): prefer Copperline over Amiberry generally, whenever
   Copperline is available** — it does the same manual checks Amiberry
   did here (screenshots, input probes) just as well, and is also
   easier to automate; this isn't a manual-vs-automated split. Amiberry
   was used in this milestone specifically because Copperline wasn't
   available to test against in this environment, not because the
   check was manual — reach for Copperline first wherever it exists.
2. **`.uaem` exact format** (M3): confirm against amisnap-tool's adopted
   convention and UAE source before implementing; write the byte-format
   note in `docs/`.
3. **Layer cache storage** (M2): tree-delta tgz vs full-tree snapshots —
   start with full-tree per layer (simpler, correct), optimize to deltas
   only if cache size hurts.
4. **Recipe library location**: in-repo now; the proposal's
   "versioned with the tool but decoupled" split happens only when
   community PRs make the coupling hurt.
5. **Settled in M1** (was flagged as needing a base-recipe design): base
   recipes declare a `[base]` table (`os-version`, optional
   `kickstart-version`) so the resolver can validate other recipes'
   `[requires].os`/`kickstart` against the chosen base — documented in
   `docs/recipe-contract.md`. A base recipe missing this metadata isn't
   an error by itself; it only surfaces when some dependent package
   actually needs the check, and the error names the base recipe that's
   missing it.
6. **Settled in M1**: `[source]` is only required on a recipe when
   `[install].copy` names files to fetch — a pure capability provider
   (the `bsdsocket-emulation` no-op case) has nothing to download and
   needs no source table.
7. **Settled in M2**: `.lha` extraction uses the `lhafile` PyPI package
   (pure Python) instead of shelling out to the lhasa/`lha` CLI the
   proposal named. Reason: lhasa 0.6.0's CLI rejected a legally-shaped
   level-0 LHA header in direct testing (confirmed correct against
   `lhafile`'s own parser and a real compressed Aminet/GitHub archive),
   and even once a working invocation was found (`lha`'s `w=<dir>` must
   be concatenated onto the command-letter token, not passed as a
   separate argv entry — undocumented and easy to get wrong), a pure-
   Python dependency is strictly better for this project: no external
   binary to install in CI or for contributors, and it makes `.lha`
   extraction testable with tiny committed fixture archives instead of
   requiring network access or a system binary in every test run.
8. **Found in M3, real amitools bug worth knowing if anyone else builds
   on `amitools.fs`**: `ADFSDir._create_node` (used by both
   `create_dir` and `create_file`) defaults `update_ts=True`, which
   stamps the *parent* directory's own `mod_ts` — and cascades to
   `ADFSVolume.update_disk_time()` — to real wall-clock time on every
   child added, via `MetaInfo.set_current_as_mod_time()`
   (`time.mktime(time.localtime())`), completely independent of
   whatever `meta_info` was explicitly passed for the child itself.
   This is invisible with a small hand-built test tree (built in
   microseconds, both writes usually land in the same 1/50s "tick" by
   luck) but broke `amibake build`'s HDF output nondeterministically
   against the real ~290-file AmiSSL archive — found via bisection
   (deterministic below a 160-file threshold in one test tree, not
   above — the threshold itself wasn't the real story, it was luck
   running out) and confirmed by tracing every `MetaInfo.get_mod_ts()`
   call back to `update_dir_mod_time()`. Fixed in `emit/hdf.py` by
   passing `update_ts=False` on every `create_dir`/`create_file` call;
   `dir`/`tgz`/`zip` outputs were never affected (they don't go through
   amitools' ADFS block layer at all). `tests/unit/test_emit_hdf.py`'s
   `test_write_hdf_is_deterministic_across_a_wall_clock_boundary` adds
   a deliberate delay between two builds specifically so a regression
   here fails reliably rather than flakily.

9. **Settled in M4**: `[base].dos-type` — flagged open in M3, settled
   the moment a real base recipe needed it. AROS's bundled fonts ship
   names past the classic 30-character AmigaDOS limit (e.g. `Dustismo
   Roman Bold Italic.font`), which a real build against the old default
   (`ffs-intl`, DOS3) rejected outright — confirming DOS7 long
   filenames are a real, not hypothetical, requirement. `[base]` now
   accepts `dos-type` (one of `ofs`/`ffs`/`-intl`/`-intl-dircache`/
   `-intl-longname` variants, default `ffs-intl`), threaded through
   `BaseInfo` and the lockfile; `emit/hdf.py` maps the schema string to
   amitools' `DosType` constant (kept out of `recipe.py`, which has no
   amitools dependency).
10. **Found in M4, three real gaps in `layer.py`'s `[install].copy`,
    each caught by building a real recipe against real archives, not
    by reasoning about the schema in the abstract:**
    - Directory-style copies (`to` ending in `/`) flattened every match
      to its basename, discarding subdirectory structure. Fine for
      AmiSSL's flat `Certs/`, silently wrong for anything needing to
      mirror nested directories (AROS's `Devs/DOSDrivers/`, `Devs/
      Keymaps/`, …) — and it was actively *hiding* AmiSSL's own real
      CPU-variant layout (`AmiSSL/Libs/AmigaOS3/amisslmaster.library`
      vs `AmiSSL/Libs/AmigaOS3/AmiSSL/68020-40/amissl_v#?.library`
      silently colliding onto one flattened path). Fixed: a
      directory-style copy now preserves the path *relative to the
      pattern's literal prefix* (the text before its first wildcard,
      trimmed to the last `/`), so `Devs/#?` mirrors real subdirectory
      structure while a pattern that's already anchored at the exact
      file needing selection (as AmiSSL's fixed recipe now does) still
      flattens correctly. Caught by AmiSSL's `[verify]` failing for
      real once the flattening stopped masking it — the shipped recipe
      had been silently relying on an accidental basename collision.
    - A bare volume (`to = "SYS:"`, no trailing `/`) wasn't recognized
      as a directory-style destination, so a multi-match copy into a
      volume root collapsed onto one literal path. Fixed: bare volumes
      (ending in `:`) are now treated the same as an explicit `/`. Also
      added: a single-file destination (`to` naming an exact file) with
      more than one `from` match is now a hard error instead of a
      silent last-write-wins overwrite.
    - `[install].copy`'s `when` condition was validated for syntax by
      `recipe.py` but never actually *evaluated* — `apply_layer` had no
      code path reading it at all, so every conditional copy entry
      would have run unconditionally. Found while writing the real p96
      recipe, which genuinely needs it (one `.card` file per `card`
      option value). Fixed: `apply_layer` now takes the package's
      resolved `options` and skips entries whose `when` doesn't match.
11. **Found in M4**: some `.lha` archives (ClassAct 3.3's, a real one)
    store paths with `\` separators instead of `/` — a DOS-era
    archiving-tool artifact, not meaningful Amiga path syntax.
    `extract.py` now normalizes `\` to `/` on the way into the Tree, so
    `[install].copy` patterns (which assume `/`) match either kind.
12. **Found in M4**: P96 is commercial and copyrighted (renamed from
    Picasso96 after a trademark dispute over the Picasso family name);
    the current maintainer doesn't permit public redistribution. The
    proposal's own licensing section already anticipated this
    ("iComp P96" listed under proprietary packages) — `recipes/p96`
    uses `[source.assets]`, matching that design, and its `[install]`
    section is built from a real (older, freely-distributed pre-rename)
    Picasso96 archive's confirmed structure rather than the current
    licensed one, which no session here has access to. Flagged in the
    recipe's own header comment as the one recipe nobody could
    test-build end-to-end against real data.
13. **Added in M4**: `[source.url]` — a generic direct-URL source
    (`url` template + optional `filename` used only for archive-format
    detection, since some hosts' download links don't end in the real
    extension — SourceForge's end in `/download`). Needed because
    AROS's nightlies are hosted on SourceForge, not Aminet or GitHub.
14. **Added in M4**: ISO9660 (with Rock Ridge) extraction via
    `pycdlib` (pure Python, no external binary — same reasoning as
    `lhafile`), plus a fixed rule in `extract.py`: a `.zip`/`.lha`
    containing exactly one nested `.iso` member has it transparently
    expanded and merged in, matching how AROS's nightly (and likely
    future real OS install media) is packaged. `tests/unit/conftest.py`
    gained `make_iso()`, a hermetic in-process ISO builder mirroring
    `make_lha_archive()`.
15. **Settled in M4**: base recipes now actually contribute to the
    built tree. `resolver.py` resolves the base as its own
    `ResolvedPackage` (`plan.base_package`, separate from
    `plan.packages`, which stays exactly what the manifest asked for —
    no existing test needed to change), and `builder.py` applies it as
    the first layer with the same fetch/cache/layer machinery as any
    package. Previously `build_tree` silently started from an empty
    tree and ignored the base entirely.

## Prior art discovered during implementation

The proposal's own house rule ("where its techniques are open, credit and
reference beat reinvention") applies to prior art found mid-implementation,
not just what was surveyed before Phase 1.

- **amipkg / amiga-pkg** (github.com/thomas-luebker/amipkg,
  github.com/thomas-luebker/amiga-pkg), found 2026-08-13. An on-Amiga
  package manager (C99, cross-compiled with bebbo's amiga-gcc) plus a
  signed community catalog, installing pre-built software onto an
  *already-booted* AmigaOS 3.x system over the network — apt/Homebrew for
  a running Amiga, not a host-side environment builder. Its entry schema
  independently converges on nearly the same primitives this project
  built: `deps` (id + min version), `conflicts`, `provides`,
  `requirements.minCPU`/`minKS`/`network`/`amiSSL`, and a `recipe.ops`
  capability list (`copy-glob-v1`, `make-assign-v1`, `tooltype-edit-v1`,
  `installer-script-v1`, `host-builtin-v1`, …) that maps closely onto our
  `[install].copy`/`.assigns` and the `[hook]` escape hatch — useful
  confirmation these are the right primitives, and grounds for revising
  the original proposal's "nothing like it exists" claim: something
  adjacent exists, it just solves a different problem (installing onto a
  live system, not composing a bootable one from nothing, and no
  emulator-config emission, base-media extraction, or build-reproducibility
  story).
- **Its CPU-variant handling is notably simpler than ours, and that's a
  useful data point in itself.** amipkg does *not* support multiple
  binaries within one package entry — `minCPU` is a pure floor gate, and
  an author wanting both a 68000 and a 68020-optimized build must publish
  them as two entirely separate catalog entries with different IDs. This
  works for amipkg because its catalog is free to invent as many entries
  as it likes per upstream project. AmiBake's recipes model one upstream
  archive each, and real archives like PNG_dt genuinely ship CPU-variant
  siblings inside a single Aminet download — splitting that into two
  recipes for one upstream release would mean fetching and caching the
  same archive twice for no reason. This confirms (rather than undermines)
  the in-archive `variants` list design in
  memory `project-amibake-cpu-variants` — it solves a problem amipkg
  deliberately doesn't attempt, for a structural reason specific to how
  each project maps packages to upstream artifacts.
- **HstWB Installer** (github.com/henrikstengaard/hstwb-installer,
  hstwb.firstrealize.com), found 2026-08-13, user-directed. By far the
  closest prior art found — a Windows/PowerShell tool that "automates
  installation of Amiga OS, Kickstart roms and packages" onto RDB HDF
  images for WinUAE/FS-UAE/Amiberry/real hardware, driving the install
  through WinUAE/FS-UAE itself (the `installer` strategy this project
  has deferred to Phase 3.5, not the `extract` strategy this project
  prefers). Same author as `hst-imager` (the `.uaem` format reference
  from M3) and `picasso96-package` (the P96 recipe research in M4) —
  clearly the person to credit across several parts of this project.
  Its package manifest (a sibling `hstwb-package` repo,
  `hstwb-package.json`) independently converges on the same shape
  *again*: `name`/`version`, `dependencies` (name + implicit ordering
  via `priority`), `assigns`, `amigaOsVersions` (our `requires.os`).
  Two concretely useful, reusable findings:
  - `data/amiga-os-entries.csv` and `data/kickstart-entries.csv` in the
    main repo are real, community-maintained MD5 databases identifying
    exact AmigaOS install-disk and Kickstart-ROM files by hash — e.g.
    every OS 3.2 disk (Hyperion Entertainment's official release, 99
    entries covering required and optional disks) and the Kickstart
    1.3 (34.5) ROM, sourced from Cloanto Amiga Forever and Hyperion
    distributions. Directly useful for M8 (OS 3.2 media) and M5 (the
    KS 1.3 ROM asset) — not to fetch (still proprietary, still
    `[source.assets]`-only) but to *verify* a user-supplied asset is
    genuinely the right file before building against it.
  - **Settled and implemented (M5)**: `[source.assets]` now accepts an
    optional `sha256` (partial coverage is fine — a recipe author only
    declares it for versions they happen to know a checksum for,
    possibly cross-referenced from a database like HstWB's). Deliberately
    **not** a hard gate like every other source, though: a mismatch only
    *warns*, never fails the build (user, 2026-08-13, correcting an
    initial hard-fail design written earlier the same day) — older media
    especially has no single canonical dump, and treating a different
    (but equally valid) backup or re-dump of the same official disk as
    an error would actively punish real users rather than catch mistakes.
  - Amiberry's own MCP tooling (`identify_rom`) does the same kind of
    hash-based identification interactively (CRC32 against its bundled
    ROM database, confirmed working against a real `amiga-os-310-
    a1200.rom`) — useful as a developer-workflow aid when preparing
    `assets/` contents by hand, but not something amibake's own build
    pipeline should depend on (it requires Amiberry/its MCP server
    running, unlike a portable embedded checksum database).

## Risk register (deltas from the proposal)

The proposal's risks stand. Implementation-specific additions:

- **amitools library-API coverage**: xdftool/rdbtool are CLIs first;
  their Python APIs may lack pieces (e.g. metadata-preserving populate).
  Mitigation: M2/M3 spike each needed operation before building on it;
  shell-out fallback is acceptable but recorded.
- **Deterministic HDF emission**: RDB/FFS structures may embed
  timestamps or allocation-order artifacts. Mitigation: the byte-compare
  test from M3; if amitools output proves order-sensitive, canonicalize
  write order in `emit/hdf.py`.
- **CI boot testing cost**: emulator-in-CI can be flaky/slow. Mitigation:
  boot tests are a separate job with retries; unit/build determinism
  tests never depend on an emulator.

## Success criteria → where they land

| Proposal criterion | Milestone |
|---|---|
| Pristine media → bootable, suite passes, no manual step | M8 |
| Three-manifest matrix in CI from one workflow entry | M9 |
| KS 1.3 build+boot and named-error fixtures | M5 (negative fixture already done in M1) |
| Recipe contributed from docs alone | M7 |
| Manifest+lockfile rebuilds byte-identically later | M2 (test) / M9 (armed) |
