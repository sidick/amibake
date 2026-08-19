# Manifest Format

A manifest is a TOML file describing one complete Amiga setup: a base
OS, a machine, a set of packages, and what to emit. One manifest = one
setup; a test matrix is a directory of manifests.

TOML is deliberate: it has no implicit typing, so `version = "5.20"`
can never silently become the float `5.2`. Every version value in a
manifest or recipe is a string, always.

```toml
# manifests/os32-p96-amissl.toml
base     = "os3.2.2"
machine  = { cpu = "68030", fpu = true, mmu = true, ram = "fast:8M", rtg = true }
packages = [
  "picasso96-3 >= 3.2",
  "amissl = 5.20",
  "classact = 3.3",
]
output   = ["hdf", "dir"]
emit     = ["copperline", "amiberry"]
```

This is the full authoritative reference:
[`docs/manifest.md`](https://github.com/sidick/amibake/blob/main/docs/manifest.md)
in the repository — the exact schema the codebase itself is tested
against. This page is a task-oriented walkthrough of the same ground.

## `base`

Names a base recipe — `aros68k`, `wb1.3`, `os3.1.4`, `os3.2.2` (see the
[Recipe Library](Recipes.md) for what each needs). A base with its own
options (e.g. `wb1.3`'s `boot` choice between a full Workbench desktop
and a minimal CLI-only Startup-Sequence) takes a table instead of a
bare string:

```toml
base = { name = "wb1.3", boot = "cli" }
```

A base always resolves to the newest version it declares — there's no
`version =` on a base entry the way there is on a package.

## `machine`

An optional table asserting hardware floors/features; the resolver
validates every package's `[requires]` against it.

```toml
machine = { cpu = "68030", fpu = true, mmu = true, ram = "fast:8M", rtg = true, chipset = "aga" }
```

| Key | Type | Notes |
|---|---|---|
| `cpu` | string | `68000` .. `68060` |
| `fpu` | bool | Independent axis — an EC030 is `cpu = "68030", fpu = false` |
| `mmu` | bool | Independent axis — required by Enforcer/MuForce-style setups |
| `ram` | string | `<kind>:<size>`, kind ∈ `chip`/`fast`/`slow`/`z3`; comma-separated for several: `"chip:2M,fast:8M"` |
| `rtg` | bool | RTG board present |
| `chipset` | string | `ocs`, `ecs`, `aga` |

Omitting `machine` entirely means no hardware constraints are asserted
— fine for a base-only smoke build, not for anything that needs a
specific CPU floor or RTG board.

## `packages`

Each entry is either a plain constraint string or a table (for a
package with options to answer):

```toml
packages = [
  "amissl = 5.20",                       # exact version
  "picasso96-3 >= 3.2",                  # constraint: =, >=, <=, >, <
  "mui >= 3.8, < 4.0",                   # conjunction
  { name = "picasso96-3", version = ">= 3.2", card = "uaegfx" },  # + option answers
]
```

Package names are lower-case slugs (`amissl`, `picasso96-3`,
`bsdsocket-emulation`). Version strings are dotted decimal
(`3.2.2.1`, `5.20`, `2.9a`) compared as real Amiga versions, never as
floats — `5.20` is greater than `5.3`.

## `output`

Which build artifact formats to write. Default `["hdf"]`.

| Value | What it is |
|---|---|
| `hdf` | A bootable RDB/partitioned hard-disk image. |
| `dir` | A plain host directory tree (with `.uaem` sidecars for Amiga metadata a host filesystem can't represent). |
| `tgz` | A deterministic tarball. |
| `zip` | A deterministic zip. |

## `emit`

Which emulator configs to write alongside the build, once `[verify]`
passes. Default: none.

```toml
emit = ["copperline", "amiberry"]   # also: "winuae"
```

Needs a `dir` entry in `output` and a Kickstart ROM at
`assets/roms/kickstart-{the base's kickstart-version}.rom` — see
[Emulator Configs](Emulator-Configs.md) for the full picture, including
what a recipe can itself contribute to an emitted config (the
`bsdsocket-emulation` and `picasso96-3` recipes both do).

## `providers`

Resolves ambiguity when more than one installed package could satisfy
the same capability (e.g. two different `bsdsocket` providers):

```toml
providers = { bsdsocket = "roadshow" }
```

## Validation: lint time vs. resolve time

`amibake lint` checks shape, types, known keys, and constraint syntax —
purely local to the manifest file, no recipe library needed to be
consistent. `amibake resolve` (and `build`, which calls it internally)
does the cross-document checks: do the named packages actually exist,
does their `[requires]` accept this base and machine, is every
capability provided exactly once. Resolve-time errors always name the
package, the requirement that failed, and the remedy — never a bare
stack trace.

## Where to go next

- [Recipe Library](Recipes.md) — every package and base you can name in
  a manifest today.
- [Writing a Recipe](Writing-Recipes.md) — add support for a package
  that isn't there yet.
- [CLI Reference](CLI-Reference.md) — `lint`/`resolve`/`build` flags.
