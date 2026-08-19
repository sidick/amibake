# Emulator Configs

Adding `emit = ["copperline", "amiberry"]` (also: `"winuae"`) to a
manifest makes `amibake build` write a ready-to-boot emulator config
pointed straight at the build — no hand-editing a `.uae` file or
Copperline TOML afterwards.

```toml
base    = "aros68k"
machine = { cpu = "68020" }
output  = ["hdf", "dir"]
emit    = ["copperline", "amiberry"]
```

```console
$ amibake build manifests/aros68k.toml --assets assets
built manifests/aros68k.toml: base=aros68k, packages=[(none)]
wrote manifests/aros68k.hdf
wrote manifests/aros68k
wrote manifests/aros68k.copperline.toml
wrote manifests/aros68k-amiberry.uae
```

## Requirements

- **A `dir` entry in `output`.** The config emitters only know how to
  mount a plain directory today (Copperline `[[filesys]]` HOSTFS with
  `bootpri = 6`; Amiberry/WinUAE `filesystem2=rw,DH0:...`) — there's no
  hardfile/RDB mount modeling yet. If `emit` is set without a `dir`
  output, the build fails with a named error rather than silently
  skipping the config.
- **A Kickstart ROM.** Looked up at
  `assets/roms/kickstart-{the base recipe's kickstart-version}.rom`,
  under the same `--assets` root recipes use for their own proprietary
  media. AROS ships its own ROM as part of the base build, so
  `manifests/aros68k.toml` needs nothing extra here; a real OS base
  (`wb1.3`, `os3.1.4`, `os3.2.2`) needs the matching real Kickstart ROM
  supplied at that path.

## What's actually in an emitted config

Real formats, grounded in real data rather than guessed: Copperline's
own `copperline.example.toml` plus hands-on boot verification;
Amiberry's via real `.uae` files pulled from a working install, and the
exact `chipmem_size`/`bogomem_size` scaling formulas (512K/256K units —
*not* raw megabytes, unlike `fastmem_size`/`z3mem_size`) read directly
out of Amiberry's own `cfgfile.cpp` and confirmed by round-tripping a
generated config through Amiberry's own parser. WinUAE reuses the same
UAE-derived writer but is unverified — no local WinUAE to check
against, flagged honestly rather than silently assumed correct.

Both real configs have been boot-verified end to end: built, loaded
into the real emulator against the real ROM, and confirmed to reach a
genuinely interactive desktop or CLI (not just a painted screen) — live
mouse-pointer movement or a scripted keypress-and-response, observed
over each emulator's own automation interface.

## Recipes contribute directives too

A recipe (base or package) can add its own literal config for a
specific emitter via `[emulator-config.<emitter>]` — this is how, for
example, `bsdsocket-emulation` turns on each emulator's own
bsdsocket-library emulation (`bsdsocket_emu=true` for Amiberry/WinUAE;
Copperline's `[hostsocket] net = "host"` HostSocket board), and how
`picasso96-3`'s `uaegfx` card option wires in the matching RTG board
config. Directives merge across the whole resolved plan — base first,
then packages in resolution order, later wins on a key collision — so
a manifest doesn't need to hand-assemble anything itself.

## Where to go next

- [Manifest Format](Manifest-Format.md) — the `output`/`emit` keys in
  full.
- [Writing a Recipe](Writing-Recipes.md) — how a recipe contributes its
  own `[emulator-config.*]` directives.
- [Recipe Library](Recipes.md) — `bsdsocket-emulation` and
  `picasso96-3` are the two real worked examples above.
