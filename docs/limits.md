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
target CPU (`layout.gadget` vs `layout.gadget.020`, seen in
`recipes/classact`'s real ClassAct archive). `[install].copy` accepts
`cpu-variant = true` on a copy entry, but selection isn't implemented
yet — every match is copied, so recipes work around it today by
pattern-excluding the variant suffix directly (`Classes/gadgets/#?.gadget`
naturally excludes `#?.gadget.020`) or, where the real Install script
encodes a variant-selection convention worth confirming first
(AmiSSL), by copying only the generic binary until that convention is
verified against a real example. See `src/amibake/layer.py`'s own
module docstring; tracked in `PLAN.md`.

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
