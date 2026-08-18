# Package ideas (uncommitted scratch list)

Candidates worth turning into recipes. Not authoritative, not linked from
PLAN.md — just a holding pen so ideas aren't lost between sessions.

## dev/debug trio (classic 68k debugging aids)

- **MuForce** — `dev/debug/MuForce.lha`. A 68k Enforcer clone: patches
  exec/dos to trap illegal RAM accesses and reports the offending
  task/address. No GUI, just starts silently.
- **MuGuardianAngel** — ships inside the `MMULibs` package (`MuTools`
  drawer), not its own Aminet leaf — the same real archive
  `recipes/mmulibs` now sources for its own narrower purpose (see
  below); MuGuardianAngel/MuTools themselves aren't shipped yet. Detects
  memory-management violations and helps explain what's crashing a
  program. **Requires MuForce running first** — MuGuardianAngel won't
  work without it, so these two are a package-with-`[requires]` pair,
  not independent recipes.
- **SegTracker** — shipped as `recipes/segtracker` (Aminet
  `dev/debug/SegTracker.lha`, real checksum verified). Maps a crash
  address back to which library/device/program it came from; installed
  to `SYS:C/` and started from `S:User-Startup`. Handy alongside
  Copperline/Amiberry boot verification when a build crashes instead of
  booting cleanly.

MuForce/MuGuardianAngel would round out a "classic debugging toolkit"
set alongside SegTracker, useful for verifying recipes that misbehave
rather than just for end-user manifests. Worth checking Aminet upload
dates/checksums before writing `[source.assets]`/`[source.aminet]`
entries for those two — they didn't look network-fetchable-with-known-
hash yet as of the SegTracker check, need to verify like the
HstWB-derived checksum work did for OS3.2/Kickstart.

## Others (parking lot — not yet researched)

- **AHI** — shipped as `recipes/ahi` (Aminet `driver/audio/
  ahiusr_4.18.lha`, real checksum verified). The retargetable
  audio system most audio-capable software depends on: ahi.device +
  AUDIO: handler + BGUI-flavoured prefs editor, Paula/Filesave drivers
  by default. `depends = ["bgui"]` so its prefs editor has a real
  bgui.library to run against.
- **BGUI** — shipped as `recipes/bgui` (Aminet `dev/gui/bgui.lha`,
  real checksum verified). The BOOPSI GUI toolkit AHI's prefs editor
  needs; bgui.library (68000/OS2 vs 68020+/OS3 `variants`), its five
  gadget libraries, and its own prefs utility.
- **MMULibs (CPU support libraries)** — shipped as `recipes/mmulibs`,
  sourced from the same `assets/hyperion/AmigaOS-3.2-full.lha` os3.2.2
  already pins (MMULibs.adf is bundled inside it). Narrow scope: just
  680x0.library + 68030/68040/68060.library, enough to stop the base's
  own `CPU CHECKINSTALL` boot nag on a 68030+ machine block — not
  mmu.library or the MuTools drawer (MuForce/MuGuardianAngel/etc, see
  the dev/debug trio above), which remain unshipped.

(add more here as they come up)
