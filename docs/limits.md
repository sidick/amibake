# Honest limits

What AmiBake's declarative schema can't express, and what real recipes
do when they hit one of these — named here rather than half-supported
or silently worked around. If a package's real installer makes a
decision this list doesn't cover a path for, that's a real gap: open
an issue rather than stretching the schema or reaching for `[hook]`
by default (see below for when a hook actually is the right call).

## Real Installer-language scripting

AmigaOS's real Installer (the `Installer`/`Install` script format
driving most real 2.0+ package and OS installs — prompts, hardware
detection, conditional branches, `askdisk`/`askoptions`/`transcript`
directives) is not executed. `[install]` expresses the declarative
90%: file copies (with AmigaDOS pattern matching and `when`-gated
options), envarc/user-startup/assigns/files. It cannot express a real
Installer script's control flow.

**What recipes do instead**: read the real Installer script (or the
real install instructions/readme when there's no script — freeware
Aminet packages rarely ship one) and translate its *default, non-
interactive path* into `[install]` entries declaratively, same as
hand-copying the disk yourself. Every recipe built this way says so in
its own comments, naming what was read to derive it:

- `recipes/amissl` — real `Install-AmiSSL` script inspected directly;
  the cpu-variant selection logic it encodes isn't implemented yet
  (see below), so the recipe copies the generic (non-suffixed) binary.
- `recipes/wb1.3` — no Installer at all (real 1.3 predates it) but the
  same translation approach for its plain-copy Startup-Sequence.
- `recipes/picasso96-3` — grounded 2026-09-05 against the real
  `Picasso96-3.6.2.lha`, after a long spell describing a 3.x nobody had
  seen. What that spell cost, as a caution: the recipe named a version
  that was never released (`3.6.3`), invented the asset filename to
  match, copied a `fastlayers.library` that 3.6.2 doesn't contain, and
  copied `uaegfx.card`/`zz9000.card`, neither of which P96 ships any
  more. It all read as confidently as the grounded recipes around it.
  Structure inferred from a *related* archive is a hypothesis, and
  should say so in the recipe where a reader will see it. What remains
  unverified is now only the runtime: no session can boot a real
  graphics board, and `uaegfx` needs an emulator AmiBake doesn't emit
  configs for yet.
- `recipes/picasso96-2` / `recipes/picasso96-3` — the real
  `InstallPicasso96` script's board install is three steps: the `.card`,
  its matching `.chip`, and a `DEVS:Monitors/<BoardName>` entry whose
  **icon tool types** say which board the copied monitor program drives.
  The third was the schema's own gap for a while — it is now
  `[install].tooltypes` (see `docs/recipe-contract.md` and
  `src/amibake/icon.py`), so all three are expressible and both recipes
  do all three. What is still *not* expressible, and did not need to be:
  reading a tool type back out to make a later decision. Every real
  script that sets one only writes.
- `recipes/os3.1.4` — the first base built this way (`aros68k`/`wb1.3`
  are plain-copy floppy sets with no real Installer at all): the real
  152KB `Install/Install` Installer-language script was read directly
  and its default, non-interactive path translated declaratively. It
  also excludes a real `ModulesA500_3.1.4.adf`/`ModulesA600...`/
  `ModulesA2000...` set of per-board `LoadModule` ROM-patch modules —
  *not* a capability gap here, though (package author, 2026-08-13):
  those only matter when running an older, unpatched 3.0/3.1 ROM chip
  and using `LoadModule` to bring it up to 3.1.4 behaviour in
  software. This base pairs with the real, current 3.1.4 ROM image
  itself, on which the modules would be redundant. A future base
  deliberately targeting an older physical ROM patched up via
  `LoadModule` would be a real, different use case — hardware-board
  detection (which module variant to pick) would be the genuine
  `[install]`-can't-express limit there. See the recipe's own comments.
- `recipes/mmulibs` — the real base `Install/Install`'s "MMU-Library
  installation" branch, translated whole (everything on `MMULibs.adf`
  except `Configs/` and `Locale/` verbatim into the target, the MMUlib
  guides to `SYS:MuTools/`, one MMU configuration to `ENVARC:`). Its
  one interactive decision is an `askchoice` for the accelerator
  board's *manufacturer* — Other / GVP / Individual Computers (ACA) /
  Phase 5 — selecting which of `Configs/MMU-Configuration{,.GVP,.ACA,
  .P5}` is installed under the single name `MMU-Configuration`. The
  machine block has no accelerator-vendor axis to answer that with
  (`when` conditions need a real `[options]`/machine key to test), so
  the recipe takes the script's own `(default 0)` = "Other" generic
  config. Not fatal: the `Libs/mmu/` board-init files the vendor
  configs invoke are all installed, so switching a built tree is a
  one-file copy. A real vendor axis (a machine or `[options]` key)
  would be the honest fix if a manifest ever needs one of the three.
- `recipes/os3.2.2` — the first base needing more than one archive: real
  Hyperion point releases (3.2.1, 3.2.2, ...) are cumulative *update*
  packages applied over a base install, not standalone reinstalls.
  `[source.assets].path` accepts an array for this (each archive
  extracted independently and merged under its own `<filename>/`
  prefix — see `docs/recipe-contract.md`); the real 177KB base
  `Install/Install` script and the ~46-49KB `Install/Install` scripts
  each update package ships were all read directly. Their real payload
  is Unix-compress/LZW-encoded (`.Z`), decompressed by the Installer's
  own `UNCOMPRESS` command — `extract.py` now does this transparently
  for any `.Z` member (see its own module docstring).

This also covers **decisions the real Installer makes from filesystem
state rather than a user prompt** — e.g. a script that puts a manual
under `Help:` if that assign already exists, `Work:` otherwise. There's
no way for `[install]` to branch on "does this assign exist on the
target" (only on `[options]`, a manifest-author-facing choice); a
recipe hitting this picks one static, reasonable destination and says
so in a comment, the same as any other default-path translation.

When the default path alone can't produce a working install (a real
decision tree with no reasonable single answer), that package either
gets an `[options]` axis for the manifest to answer explicitly (see
`[options.card]` in `recipes/picasso96-3`/`recipes/picasso96-2` for the
pattern), or is named here
as genuinely unsupported rather than guessed at.

## `[hook]` — when the above isn't enough

For the genuine remainder — a real Installer script making a decision
no declarative option can reasonably stand in for — `[hook]` is the
fenced escape hatch (`docs/recipe-contract.md`). It's real, executable
Python, run only when `amibake build --allow-hooks` explicitly opts
in, and flagged by the linter on every recipe that declares one so it
gets reviewed harder in a recipe PR. No shipped recipe needs one yet —
every real installer read so far had a translatable default path.
Reach for `[hook]` only after confirming the declarative schema
genuinely can't express what's needed, not as a shortcut around
reading the real installer carefully.

## CPU/FPU archive variants

Some real archives ship more than one binary per library, suffixed by
target CPU. `[install].copy`'s `variants` (see
`docs/recipe-contract.md`) covers both real shapes confirmed so far:

- A generic fallback file plus sibling CPU/FPU-tier files alongside it
  in the same directory (`recipes/lha`, built against the real
  `util/arc/lha.run`, which ships `lha_68k` / `lha_68020` / `lha_68040`
  side by side).
- A whole **subdirectory** swap with a version-varying filename inside
  (`recipes/amissl`, built against the real GitHub-Releases archive,
  which ships `AmiSSL/Libs/AmigaOS3/AmiSSL/68020-40/amissl_v362.library`
  next to a `68060/` sibling directory) — `variants[].path` is itself an
  AmigaDOS pattern, not a literal filename, so it can match "this
  release's file, whichever tier" the same way `from` does.

Not yet migrated to `variants`: `recipes/classact`'s real archive
(`layout.gadget` vs `layout.gadget.020`) is the same-directory shape
`variants` covers, but its recipe still pattern-excludes the suffix
(`Classes/gadgets/#?.gadget`) rather than selecting it. See
`src/amibake/layer.py`'s own module docstring; tracked in `PLAN.md`.

## Per-version `[install]`

`[install].copy` is one flat list for a whole recipe — there's no way
to vary it by which version was resolved (`[requires]` already has
`per-version`; `[install]` doesn't). `recipes/os3.2.2` works around
this by hard-coding `versions = ["3.2.2"]` and listing base+3.2.1+3.2.2
content in one fixed order (later entries naturally overwrite earlier
same-path files, matching the real cumulative-update semantics). Real,
already-owned point-release media exists past this
(`AmigaOS-3.2.2.1-Hotfix.lha`, `AmigaOS-3.2.3.lha`) that can't be added
cleanly without per-version `[install]` — a genuine capability gap,
not attempted here.

## Multi-partition `hdf` output

`emit/hdf.py` writes one system partition, plus at most one
*unformatted* scratch partition at the end when the manifest asks for
it (`[hdf].scratch`, see `docs/manifest.md` — an RDB entry with no
filesystem, giving destructive block-device tests like devsoak a safe
target). Fuller layouts — a second *formatted* partition, a separate
work partition, per-partition filesystem or name choices — aren't
supported; later milestone, see `emit/hdf.py`'s own module docstring.

Also worth knowing here: both the writer and any amitools-based
checker share amitools' bugs (`emit/hdf.py` already documents one). If
an emitted RDB is ever disputed — amitools and an emulator disagree,
or both accept an image real hardware rejects — AmiPart's Linux CLI
(<https://github.com/ChuckyGang/AmiPart>, `amipart INFO out.hdf`) is
an independent C RDB parser useful as a third opinion. Debug tool
only, not a dependency: its Linux build can't format filesystems, and
booting the image under Copperline/Amiberry stays the real end-to-end
oracle.

## Emulator config: hardfile boot on Copperline only

`emit/copperline.py` boots either output: an `hdf` attached to a
hardfile controller (preferred — it boots the real RDB artifact), or a
`dir` as a `[[filesys]]` HOSTFS volume. `emit/uae.py` (Amiberry/
WinUAE) still mounts a `dir` only, via `filesystem2=`; its own
`uaehf0`/`hardfile2` path isn't grounded against a real example yet,
so a manifest emitting `amiberry`/`winuae` needs `dir` in `output`
regardless of what Copperline would accept. A manifest with `emit` set
and nothing bootable in `output` fails with a named error.

Which controller mounts the hdf is the manifest's
`[emulator-config.copperline] hdf-controller` directive (see
`docs/manifest.md`). Three Copperline routes exist; they differ in
what they ask of the config and in authenticity (checked against
0.18.0/0.19.0):

- `[copperhf]` (the default since Copperline 0.19 shipped it,
  2026-09-06) — Copperline's emulator-only virtual hardfile
  controller, copperhf.device: the equivalent of WinUAE's
  uaehf.device, with no real board's registers or timing modeled at
  all. No machine profile needed, autoboot ROM baked into the
  emulator, `unit0`..`unit6` slots. The honest default *because* it
  models nothing real: it claims to be nothing the machine wouldn't
  have had, where a `[lide]` A1200 build boots off a Zorro II board no
  A1200 ever carried.
- `[lide]` (`hdf-controller = "lide"`, the pre-0.19 default) —
  Copperline's built-in lide.device-compatible Zorro II board (RIPPLE
  by default, also RIDE/AT-Bus 2008): no machine profile needed, any
  model, autoboots under any Kickstart including 1.3, own bundled ROM.
  The right choice when the thing under test is a real controller
  stack (lide.device itself, RDB parsing by a real driver). Its config
  shape changed in 0.18: named `drive0`..`drive3` keys, one per
  (channel, master/slave) slot, replacing the positional
  `drives = [...]` array (still read, but it can't express an empty
  slot).
- `[ide]` — the road still not taken, and not because Copperline
  can't. Worth spelling out, because this emitter's own error used to
  read "no IDE/hard-disk-controller modeling yet" and another project
  read that as a claim about the emulator. `[ide]` is the real Gayle
  (A600/A1200) or A4000 IDE port, and needs a machine that *has* one:
  `[machine] profile = "A600"`/`"A1200"`/`"A4000"` (the A3000 has
  motherboard SCSI instead; an A500 carries Fat Gary, no Gayle at
  all). Without it Copperline refuses — *"[ide] images need a machine
  with an IDE port"*. AmiBake's `machine` block has no profile axis to
  derive one from, so that error is AmiBake's gap showing, not the
  emulator's. A machine-profile axis is what would unlock it — the
  route for when the thing under test is the machine's own port.

Both emitters mount exactly one volume even when both outputs exist —
they share a volume name, and two identically-named volumes give the
guest ambiguous assigns.

The ROM-path convention (`assets/roms/kickstart-{[base].kickstart-
version}.rom`) is keyed only by revision number, but real hardware
classes sharing the same nominal revision can burn genuinely different
ROM binaries — confirmed directly: `recipes/os3.1.4`'s own real media
ships both an `a500a600a2000` and a separate `a500`-only ROM image,
both "46.143". Not solved — a second real hardware-class base sharing
a revision number with an existing one would collide on the same
`assets/roms/kickstart-{version}.rom` path; see `recipes/os3.1.4`'s
own comments.

## `[[run]]` mode = "wbstartup" needs a shipped icon

A `wbstartup` run entry copies the program *and its icon* into
`SYS:WBStartup/` — Workbench only starts what has an icon, and AmiBake
cannot yet author a default `.info` from nothing (a structurally valid
minimal icon needs a rendered image; generating one deterministically
is future work). The build fails with a named error when
`<command>.info` isn't in the tree. What manifests do instead: use the
icon the package's archive ships (most WB tools have one), add one via
the recipe's `[install].files`, or start the program from a `mode =
"cli"` entry. Two adjacent honest gaps: the resolver checks the
Kickstart 36+ floor but *not* whether the base actually runs `LoadWB`
(a `boot = "cli"` wb1.3 build never scans WBStartup — the entry is
silently inert there), and a `cli` entry's `Stack` line persists into
subsequent entries because the base Shell's own default stack isn't
knowable portably (documented in `docs/manifest.md`).

## AmigaDOS pattern matching subset

`[install].copy`'s `from` patterns support the subset AmigaDOS
patterns most real archives actually need: `#?` (any sequence,
including path separators), `?` (any one character), `(a|b|c)`
alternation. Not supported: `%` (any one character *including none*),
`[...]` character classes, `~` negation. No real recipe has needed them
yet; if one does, extend `layer.py`'s `_amiga_pattern_to_regex`
deliberately rather than reaching for `[hook]` to work around a
missing pattern feature.

## Proprietary media

`[source.assets]` covers this by design, not as a limit — real OS/
commercial-package media (WB1.3, OS 3.x, P96, ...) is never fetched or
cached publicly, always supplied by the user under `assets/`
(gitignored). The real limit this creates: `tools/ci_recipe_smoke.py`
(the recipe-PR CI build+verify step) can only cover recipes with a
real network source; a proprietary-media recipe's build is verified
manually, by whoever has legitimate media, same as `wb1.3`'s and
`p96`'s own development history in `PLAN.md`.

## Real historical/emulator quirks (not AmiBake's to fix, but worth knowing)

- Pre-2.0 bases (real Kickstart 1.3) have no `ENVARC:` and their real
  Startup-Sequence never sources `S:User-Startup` — `[install].user-
  startup` fragments would be silently dead code on such a base if
  `Tree.materialize()` didn't auto-append the sourcing line itself (see
  `PLAN.md`'s M5 notes). This is handled, not a limit, but easy to
  assume works "by default" the way it does on 2.0+.
- Copperline's own `--press-after`/`--script`/repeated `--screenshot-
  after` CLI automation has real quirks (wrong arg counts silently
  misparsed as a second ROM path, repeated screenshots only honoring
  the last one) — see `PLAN.md`'s M5 notes and the emulator-config-
  formats memory if replicating this elsewhere.
