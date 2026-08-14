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
- `recipes/p96` — no licensed copy available to any session that's
  worked on this recipe; structure inferred from an older pre-rename
  archive's confirmed layout, explicitly flagged unverified in the
  recipe's own comments.
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
`[options.card]` in `recipes/p96` for the pattern), or is named here
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
`docs/recipe-contract.md`) handles the case confirmed against a real
archive: a generic fallback file plus sibling CPU/FPU-tier files
alongside it, one archive-relative path per candidate (`recipes/lha`,
built against the real `util/arc/lha.run`, which ships `lha_68k` /
`lha_68020` / `lha_68040` side by side).

Not yet handled by `variants`: a whole **subdirectory** swap rather
than sibling files — real AmiSSL ships
`AmiSSL/Libs/AmigaOS3/AmiSSL/68020-40/amissl_v#?.library` next to a
`68060/` sibling *directory*, not a same-directory suffixed file, so
`recipes/amissl` still hardcodes the 68020-40 pin with a comment
pointing here rather than using `variants`. `recipes/classact`'s real
archive (`layout.gadget` vs `layout.gadget.020`) is the same-directory
shape `variants` does cover, but its recipe still pattern-excludes the
suffix (`Classes/gadgets/#?.gadget`) rather than selecting it — not yet
revisited to use `variants` instead. See `src/amibake/layer.py`'s own
module docstring; tracked in `PLAN.md`.

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

`emit/hdf.py` writes a single-partition RDB image. A base needing
multiple real partitions (a separate work/swap partition, for
instance) isn't supported — later milestone, see `emit/hdf.py`'s own
module docstring.

## Emulator config: `dir` output only

The M6 config emitters (`emit/copperline.py`, `emit/uae.py`) can only
mount a `dir` build output as the bootable volume — Copperline via
`[[filesys]]` HOSTFS, Amiberry/WinUAE via `filesystem2=`. Neither
attempts a real hardfile/RDB boot (Copperline's `[ide]` needs an
IDE-equipped machine profile — A600/A1200/A4000/A3000-SCSI, not a
plain A500 — that AmiBake's `machine` block has no way to select; UAE's
`uaehf0`/hardfile2 path wasn't grounded against a real example yet
either). A manifest with `emit` set needs `dir` in `output` or the
emitter fails with a named error.

The ROM-path convention (`assets/roms/kickstart-{[base].kickstart-
version}.rom`) is keyed only by revision number, but real hardware
classes sharing the same nominal revision can burn genuinely different
ROM binaries — confirmed directly: `recipes/os3.1.4`'s own real media
ships both an `a500a600a2000` and a separate `a500`-only ROM image,
both "46.143". Not solved — a second real hardware-class base sharing
a revision number with an existing one would collide on the same
`assets/roms/kickstart-{version}.rom` path; see `recipes/os3.1.4`'s
own comments.

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
