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

Deliberate reordering vs the proposal: AROS 68k base comes **before** the
OS 3.2 extract base, because it is the only base CI can build from
nothing and every subsequent milestone needs a CI-buildable base to test
against. OS 3.2 (the proposal's Phase 1 exemplar) follows immediately in M5.

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

### M5 — OS 3.2 extract base (Phase 1's centrepiece)

- Study Emu68-Imager's per-version handling before writing (proposal's
  prior-art rule); record findings in `docs/bases.md`.
- `bases/os3.2`: install media ADFs/ISO from `assets/` keyed by checksum;
  declarative multi-disk copy trees; locale/CPU selections as options.
- Fidelity check: one-time diff of extracted base vs a genuine reference
  install (local task, scripted as `amibake verify-base`), divergences
  encoded back into the recipe; the diff script stays in-repo.
- Asset-gated CI job (self-hosted or skip-with-notice) building
  `manifests/os32-p96-amissl.toml` (the proposal's example) and booting
  under Copperline.

Exit: proposal success criterion 1 — pristine media → bootable setup
passing an existing portfolio suite, no manual step.

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
- Second extract base: OS 3.1 — proves the base-recipe format
  generalises; 3.1+ClassAct manifest as fixture.

### M8 — KS 1.3 base (Phase 3 scope, proposal success criterion 3)

- `bases/wb1.3`: plain-copy extract (no Installer), OFS output, 1.3
  startup-sequence conventions, RAM-based ENV:, machine block pairing
  with KS 1.3 ROM asset.
- CI fixtures: 1.3 manifest with a 1.3-capable package builds and boots;
  1.3 base + `>= 3.0` package fails with the resolver's named error.

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
| Pristine media → bootable, suite passes, no manual step | M5 |
| Three-manifest matrix in CI from one workflow entry | M9 |
| KS 1.3 build+boot and named-error fixtures | M8 |
| Recipe contributed from docs alone | M7 |
| Manifest+lockfile rebuilds byte-identically later | M2 (test) / M9 (armed) |
