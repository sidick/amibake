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

## Dev utilities and libraries (commonly used, not yet researched)

Candidates picked for real-world prevalence in Amiga development —
things most dev-oriented builds would actually want, not exhaustively
verified yet (no archives downloaded, no checksums pinned) the way the
shipped recipes above are. Paths below are believed-real Aminet
locations from search, not confirmed by download the way this
project's contract expects before a real recipe lands — verify before
writing `[source.*]` entries, same as every recipe above did.

- **MUI (Magic User Interface) 3.8** — `dev/mui/mui38dev.lha`
  (developer archive) / `util/libs/mui38usr.lha` (end-user runtime).
  The GUI toolkit most real Amiga software actually uses — far more
  prevalent in the wild than BGUI (`recipes/bgui`), which AHI alone
  needed. Worth its own recipe once licensing terms are confirmed:
  historically shareware/registration-gated for some features even
  though the runtime library itself is freely redistributable — needs
  checking directly, not assumed, before writing a recipe.
- **ixemul.library 48.x** — `util/libs/ixemul-48.0.lha`, plus
  per-CPU builds (e.g. `util/libs/ixemul48.2-060.lha`, same "variants"
  shape as lha/ahi/bgui). The BSD/NetBSD-style Unix-emulation runtime
  a great many classic GeekGadgets-gcc-linked freeware/open-source
  ports assume is present — without it those binaries simply won't
  run.
- **Installer** — `util/misc/Installer-43_3.lha` (V43.3, "Amiga
  Technologies Installer dev. package" per its own readme). The real
  Commodore/Amiga Technologies install-script interpreter this
  project's own `amiga-installer` skill already covers writing scripts
  for — shipping `C:Installer` itself onto a dev-oriented build would
  let a manifest actually run third-party Installer scripts on-target,
  not just this project's own declarative translation of them.
- **PhxAss** — shipped as `recipes/phxass` (Aminet `dev/asm/
  PhxAss439.lha`, real checksum verified). A widely-used, highly
  optimizing 68k/68881/68851 macro assembler — one of the two or three
  assemblers most classic Amiga asm source in the wild actually
  targets (alongside DevPac, which isn't freely redistributable). Both
  `PhxAss` and the line-limit-free `GigaPhxAss` to `SYS:C/`.
- **AmigaE** — `dev/e/amigae33a.lha` (V3.3a, Wouter van Oortmerssen,
  1997). A genuinely popular free compiler/language for quick native
  Amiga development — fast compiles, integrated assembler/linker,
  its own GUI toolkit. The freeware distribution is a limited compiler
  (a registered version was sold separately) — check exactly what that
  limitation was before assuming full functionality in a recipe.
- **GadToolsBox** — `dev/gui/GadToolsBox3.lha` (V3, gadtools.library
  GUI resource/layout generator). The classic tool for building
  GadTools-based GUIs without hand-writing gadget layout code;
  complements ReqTools (`recipes/reqtools`) and ClassAct
  (`recipes/classact`) as another commonly-reached-for GUI dev aid.

**Deliberately not listed as recipe candidates** — genuinely
host-side, not something a built Amiga *target* image needs:
- **vbcc** — the modern, actively-maintained retargetable C compiler
  most current Amiga dev actually uses, but distributed as
  multi-platform binaries meant to run *on the build host*
  (cross-compiling), not natively on the target Amiga — out of scope
  for what `[install].copy` puts on the emitted tree. (An older,
  self-hosted 68k-native `vc` did exist historically; if anyone
  actually wants on-target vbcc, that's a real but separate ask.)
- **libnix** — a *static* link library (this project's own `libnix`
  skill already documents it in depth); it gets linked into a program
  at host-side compile time, so there's nothing for a target-image
  recipe to install — no on-Amiga `SYS:Libs/` file corresponds to it
  the way `ixemul.library` above does.

(add more here as they come up)
