# Package ideas (uncommitted scratch list)

Candidates worth turning into recipes. Not authoritative, not linked from
PLAN.md — just a holding pen so ideas aren't lost between sessions.

## dev/debug trio (classic 68k debugging aids) — all shipped

- **MuForce** — shipped as `recipes/muforce` (Aminet
  `dev/debug/MuForce.lha`, real checksum verified). The mmu.library-
  aware successor to Mike Sinz's "Enforcer": traps illegal RAM
  accesses the instant they happen. mmu.library + disassembler.library
  to `SYS:Libs/`, `MuForce` to `SYS:C/`, started from `S:User-Startup`
  (`run >NIL: <NIL: MuForce`, after segtracker's own fragment).
  Requires `cpu >= 68020` and `mmu = true` (real MMU hardware/emulation
  needed).
- **MuGuardianAngel** — shipped as `recipes/muguardianangel` (Aminet
  `dev/debug/MuGuardianAngel.lha`, real checksum verified). Catches
  accesses into *non-allocated* memory too (MungWall/WipeOut/Guardian
  Angel superset). `depends = ["muforce"]` (its own guide: "requires
  MuForce to be up and running"), started after it from `S:User-
  Startup`.
- **SegTracker** — shipped as `recipes/segtracker` (Aminet
  `dev/debug/SegTracker.lha`, real checksum verified). Maps a crash
  address back to which library/device/program it came from; installed
  to `SYS:C/` and started from `S:User-Startup`. Handy alongside
  Copperline/Amiberry boot verification when a build crashes instead of
  booting cleanly.

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
  own `CPU CHECKINSTALL` boot nag on a 68030+ machine block. mmu.library
  and the MuTools themselves ship separately, from their own upstream
  Aminet leaves — see recipes/muforce and recipes/muguardianangel
  above.

(add more here as they come up)
