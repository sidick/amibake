# The AmiBake manifest format

A manifest is a TOML file describing one complete Amiga setup: a base OS,
a machine, a set of packages, and what to emit. One manifest = one setup;
a test matrix is a directory of manifests.

TOML is deliberate: it has no implicit typing, so `version = "5.20"` can
never silently become the float 5.2. All version values are strings.

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

## Top-level keys

| Key | Type | Required | Meaning |
|---|---|---|---|
| `base` | string or table | yes | Name of a base recipe (e.g. `os3.2.2`, `wb1.3`, `aros68k`). A base recipe with its own `[options]` (e.g. `wb1.3`'s `boot`) takes a table instead: `base = { name = "wb1.3", boot = "cli" }` — same shape as a `packages[]` table entry, minus `version` (a base always resolves to its newest declared version). |
| `machine` | table | no | Machine variant; see below. Defaults are recipe-visible, so omitting it means "no machine constraints asserted". |
| `packages` | array | no | Packages to install; see below. |
| `output` | array of string | no | Output formats, any of `hdf`, `dir`, `tgz`, `zip`. Default: `["hdf"]`. |
| `emit` | array of string | no | Emulator configurations to emit, any of `copperline`, `amiberry`, `winuae`. Default: none. `amibake build` writes `<manifest-stem>.copperline.toml` / `<manifest-stem>-amiberry.uae` / `<manifest-stem>-winuae.uae` alongside the build outputs, once `[verify]` passes. Needs something bootable in `output` — `copperline` takes an `hdf` (attached to `[lide]`, preferred when present) or a `dir` (`[[filesys]]` HOSTFS); `amiberry`/`winuae` still need a `dir` (`filesystem2=`), their hardfile path not being grounded yet — and a Kickstart ROM at `assets/roms/kickstart-{the base recipe's [base].kickstart-version}.rom`, under the same `--assets` root recipes use for their own proprietary media. |
| `providers` | table | no | Capability → package name, resolving provider ambiguity (e.g. `bsdsocket = "roadshow"`). |
| `run` | array of tables | no | Programs the built image runs at boot; see `[[run]]` below. |

Unknown top-level keys are an error, not ignored — a typo must fail, not
silently change the build.

## The `machine` table

| Key | Type | Values |
|---|---|---|
| `cpu` | string | `68000`, `68010`, `68020`, `68030`, `68040`, `68060` |
| `fpu` | bool | independent axis — an EC030 is `cpu = "68030", fpu = false` |
| `mmu` | bool | independent axis — required by Enforcer/MuForce-style setups |
| `ram` | string | `<kind>:<size>`, kind ∈ `chip`/`fast`/`slow`/`z3`, size like `512K`, `8M`, `1G`. Multiple specs comma-separated: `"chip:2M,fast:8M"`. |
| `rtg` | bool | RTG board present (drives P96-style recipe validation). |
| `chipset` | string | `ocs`, `ecs`, `aga` |

`cpu` is structured (family + explicit `fpu`/`mmu` flags), never a packed
string like `68030/68882`: the flags are real independent hardware axes
and recipes validate against each separately.

## Package entries

Each element of `packages` is either:

- **A string**: `"name"` or `"name <constraint>"`, e.g. `"amissl = 5.20"`,
  `"picasso96-3 >= 3.2"`. Constraint operators: `=`, `>=`, `<=`, `>`, `<`;
  conjunctions comma-separated: `"mui >= 3.8, < 4.0"`.
- **A table**: when a recipe declares options, the manifest answers them
  inline: `{ name = "picasso96-3", version = ">= 3.2", card = "uaegfx" }`.
  `name` is required; `version` is a constraint string; every other key
  is an option answer (string, integer, or boolean) validated against the
  recipe's `[options]` declarations at resolve time.

Package names are lower-case slugs: `[a-z0-9]` with interior `-` or `.`
(e.g. `p96`, `bsdsocket-emulation`, `wb1.3`).

Version strings are dotted decimal (`3.2.2.1`, `5.20`, `45.1`) and are
compared as Amiga versions, never as floats: `5.20` > `5.3`.

## `[[run]]` — programs the image runs at boot

What to run is a property of a *test setup*, so it lives in the
manifest, not in recipes (a recipe's own `[install].user-startup` is for
things that are genuinely part of an install — SegTracker's semaphore,
xfdPatch). Each `[[run]]` entry names an installed program by its
destination Amiga path; the build fails if nothing installed it.

```toml
[[run]]
command = "C:devsoak"
args    = "copperhf.device 0 -d -r 0,8M -t 30s -y"
stack   = 65536
output  = "SER:"

[[run]]
mode      = "wbstartup"
command   = "SYS:Tools/AmiInspect"
tooltypes = { CX_POPUP = "NO" }
```

| Key | Type | Modes | Meaning |
|---|---|---|---|
| `command` | Amiga path | both | The installed program. Alias-insensitive: `C:devsoak` finds a file installed as `SYS:C/devsoak`. |
| `mode` | string | — | `cli` (default): a line in the generated `S:AmiBake-Startup`. `wbstartup`: copied into `SYS:WBStartup/` for Workbench to start after LoadWB (needs OS 2.0+, and an icon — see below). |
| `stack` | int | both | Stack bytes: a `Stack` line (`cli`) or the icon's `STACK=` tool type (`wbstartup`). Defaults from the recipe's `[install].commands` declaration when one names this path; overriding *below* the declared value warns but proceeds — deliberately undersizing a stack is a legitimate test setup. |
| `args` | string | cli | Command-line arguments, verbatim. |
| `output` | Amiga path | cli | Appends `><path>` — e.g. `T:log` or `SER:` (pairs with an emulator's serial capture for output-asserting boot tests). |
| `detach` | bool | cli | `Run >NIL:` prefix — don't block the script (default false). |
| `startpri` | int | wbstartup | `STARTPRI=` tool type. |
| `donotwait` | bool | wbstartup | `DONOTWAIT` tool type, default **true** — a waiting WBStartup tool hangs boot. |
| `tooltypes` | table | wbstartup | Tool types set on the `SYS:WBStartup/` icon. A string sets `NAME=value`; `true` the bare valueless name; `false` removes one (e.g. unsetting a recipe-declared `CX_POPUP`). Merged per-key over the recipe's `[install].commands` tool types, which sit over the sugar keys above; setting one tool type via both a sugar key and `tooltypes` in the same entry is a lint error (a contradiction, not an override). |

Mechanics worth knowing:

- `cli` entries render into one generated `S:AmiBake-Startup`, run from
  `S:User-Startup` by a fragment at order 95 — after every package's own
  startup fragments. It's a separate file on purpose: inspecting the
  image separates "what AmiBake was told to run" from "what packages
  installed", and `Execute S:AmiBake-Startup` re-runs just the workload.
- A `Stack` line persists for subsequent entries (`Execute` runs the
  script in the calling Shell's process, and the base's own default
  isn't knowable portably) — an entry that needs a specific stack should
  set it explicitly rather than rely on position.
- `wbstartup` requires the program's icon (`<command>.info`) to already
  be installed — Workbench only starts what has an icon, and AmiBake
  doesn't generate icons from nothing yet (see `docs/limits.md`). It
  also assumes the base actually runs `LoadWB` (a `boot = "cli"` wb1.3
  build never scans WBStartup).

## What validation happens when

Manifest **linting** (`amibake lint`) checks everything above: shape,
types, known keys, spec syntax. Cross-document validation — do the named
packages exist, do their `[requires]` blocks accept this base and
machine, is every capability provided exactly once — happens at
**resolve** time (`amibake resolve`), where errors name the package, the
requirement, and the remedy.
