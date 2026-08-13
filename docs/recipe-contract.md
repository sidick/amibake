# The AmiBake recipe contract (v1)

A recipe teaches AmiBake to install one package. It is **one directory in
the recipe library containing one declarative file** — never a builder
change:

```
recipes/amissl/
  recipe.toml
```

This document is the contract: it must be sufficient to write a recipe
without reading builder source. If you find yourself needing the source,
that is a documentation bug — file it.

## Complete example

```toml
[package]
name        = "amissl"
versions    = ["5.20", "5.18"]        # newest first
depends     = []                      # e.g. ["mui >= 3.8"] or ["bsdsocket"]
conflicts   = []
provides    = []                      # capabilities, e.g. ["bsdsocket"]

[requires]                            # per-recipe OS floor/ceiling — they vary
os          = ">= 3.0"                # Workbench/OS version range
kickstart   = ">= 39"                 # KS version, where it differs from os
cpu         = ">= 68020"              # optional floor

[source.aminet]
url         = "util/libs/AmiSSL-{version}.lha"
sha256      = { "5.20" = "0000000000000000000000000000000000000000000000000000000000000000",
                "5.18" = "0000000000000000000000000000000000000000000000000000000000000000" }

[install]
copy = [
  { from = "AmiSSL/Libs/#?",  to = "SYS:Libs/", cpu-variant = true },
  { from = "AmiSSL/Certs/#?", to = "SYS:Devs/AmiSSL/Certs/" },
]

[verify]
exists      = ["SYS:Libs/amisslmaster.library"]
```

## `[package]` — identity and graph position

| Key | Type | Required | Notes |
|---|---|---|---|
| `name` | slug string | yes | Must equal the recipe's directory name. Lower-case, `[a-z0-9]` with interior `-` or `.`. |
| `versions` | array of version strings | yes, non-empty | Dotted decimal strings, newest first. Always quoted — `5.20` unquoted would be a float. |
| `depends` | array of package specs | no | `"name"` or `"name >= 3.8"`. Capabilities may be depended on by name (`"bsdsocket"`). |
| `conflicts` | array of package specs | no | Resolver refuses manifests containing both. |
| `provides` | array of slugs | no | Capabilities this recipe satisfies. One provider per capability per manifest; ambiguity is a resolve-time error and the manifest picks via its `providers` table. |
| `strategy` | string | base recipes only | `extract` (declarative, preferred) or `installer` (drives the real Installer; not yet implemented). |

## `[requires]` — what the package needs from base, machine, emulator

Every recipe declares its own requirements, because they all differ.
Validated at resolve time against the manifest's base and machine —
pairing a `>= 3.0` package with a 1.3 base is a hard, early error naming
the package, the requirement, and the remedy.

| Key | Type | Example |
|---|---|---|
| `os` | constraint string | `">= 3.0"`, `">= 2.0, < 4.0"` |
| `kickstart` | constraint string | `">= 39"` |
| `cpu` | constraint string | `">= 68020"` |
| `fpu` | bool | `true` = needs an FPU |
| `mmu` | bool | `true` = needs an MMU (Enforcer-style tools, VMM) |
| `emulator` | array of strings | `["amiberry", "winuae"]` — for functionality that only exists on some emulators (the no-op bsdsocket provider) |

Requirements may differ per package **version**: use a sub-table keyed by
version to override, so a 1.3-capable 4.x can coexist with a 3.0+ 5.x:

```toml
[requires]
os = ">= 3.0"
[requires.per-version."4.12"]
os = ">= 1.3"
```

## `[source.*]` — where the archive comes from

A source table is required whenever `[install].copy` names files to
fetch. A recipe with no `copy` entries — a pure capability provider that
only contributes machine-config directives, like the no-op
`bsdsocket-emulation` provider described below — needs no `[source]` at
all, since it has nothing to download.

- **`[source.aminet]`** — freely-redistributable path. `url` is the
  Aminet-relative path with `{version}` substituted (required in the URL
  when the recipe lists more than one version); `sha256` maps **every**
  listed version to its 64-hex-digit archive checksum. Fetches verify the
  checksum; mirrors are a builder configuration, not a recipe concern.
  **Caveat:** Aminet often hosts only the current release under a rolling,
  unversioned filename (e.g. `AmiSSL-v5-OS3.lha`, replacing prior
  releases in place) — fine for a single-version recipe pinned by
  checksum, but it cannot express multiple installable versions. Prefer
  `[source.github]` when the upstream project publishes tagged releases.
- **`[source.github]`** — freely-redistributable path, for upstreams that
  publish versioned GitHub Releases (common for actively maintained
  packages, e.g. AmiSSL at github.com/jens-maus/amissl). `repo` is
  `"owner/name"`; `asset` is the release asset filename template with
  `{version}` substituted (required when the recipe lists more than one
  version, e.g. `"AmiSSL-{version}-OS3.lha"`); `tag` is the release tag
  template, default `"{version}"` (override when a project prefixes tags,
  e.g. `"v{version}"`); `sha256` maps every listed version to its archive
  checksum, same rule as `[source.aminet]`. The download URL is built as
  `https://github.com/{repo}/releases/download/{tag}/{asset}`.
- **`[source.url]`** — freely-redistributable path, for anything not
  Aminet or GitHub (SourceForge, a project's own site, …). `url` is the
  full fetch URL with `{version}` substituted (required when the recipe
  lists more than one version); `sha256` maps every listed version to
  its archive checksum, same rule as the other sources. `filename` is
  optional and used **only** to detect the archive format (`.lha`/
  `.zip`/`.iso`) — needed when the fetch URL itself doesn't end in the
  real extension (e.g. SourceForge's download links end in `/download`),
  in which case set it to the real filename (`{version}` substituted the
  same way). Defaults to `url` when omitted.
- **`[source.assets]`** — proprietary path. `path` names a file the user
  supplies in their `assets/` directory (with `{version}`, same rule).
  Absent asset = clear error naming the missing file. Nothing proprietary
  is ever fetched or cached publicly. `sha256` is optional here (unlike
  every other source) and, when given, only needs to cover the versions
  the recipe author actually knows a checksum for — partial coverage is
  fine. A mismatch at build time is a *warning*, never a build failure:
  older media especially has no single canonical dump, and a different
  (but equally valid) backup or re-dump of the same official disk
  shouldn't be rejected as if it were wrong. `path`'s extension picks
  the extraction format — `.adf` (a raw Amiga floppy disk image, OFS or
  FFS) is supported alongside `.lha`/`.zip`/`.iso`, the format real
  pre-CD-ROM install media (e.g. Workbench 1.3) ships as.

A recipe may declare more than one non-assets source (e.g. `aminet` and
`github` both freely redistributable) as alternates for the fetcher to
try; `assets` always wins when the file is present, since a user-supplied
asset is authoritative.

## `[install]` — the declarative install

Most Amiga installs are copies + config lines + assigns. The schema
expresses exactly that.

- `copy` — array of `{ from, to }` tables. `from` is a path inside the
  extracted archive and may use AmigaDOS patterns (`#?`, `?`, `(a|b)`);
  `to` is an Amiga path on the target (`SYS:`, `ENVARC:`, …) — an
  into-directory copy either ends in `/` (`SYS:Libs/`) or is a bare
  volume with no sub-path (`SYS:`, its own root directory); anything
  else names an exact single destination file, valid only when `from`
  matches exactly one archive path. Optional keys:
  - `cpu-variant = true` — select the 000/020/040/060 binary variant
    matching the machine block from archives that ship them.
  - `when = "<option> = <value>"` — apply only when the manifest's option
    answer matches (see `[options]`).
- `envarc` — array of `{ name, content }`: files created under `ENVARC:`.
- `files` — array of `{ to, content }`: literal-content files at an
  arbitrary Amiga destination path (like `envarc`, but not limited to
  `ENVARC:`). For a base recipe that needs to author its own
  Startup-Sequence rather than copy one verbatim from its source media
  (real pre-2.0 media has no `EXECUTE S:User-Startup` line at all — see
  `[install].user-startup` below).
- `user-startup` — array of `{ order, lines }`: fragments merged into
  `S:User-Startup` sorted by `order` (integer; house convention 0–99,
  50 = "doesn't matter"). Explicit ordering keys make layers compose
  deterministically. Relies on the base's Startup-Sequence actually
  running `EXECUTE S:User-Startup` — a 2.0+ convention; on a pre-2.0
  base (Kickstart 1.3), the builder appends that line automatically to
  whatever Startup-Sequence the base installed (via `copy` or `files`)
  if it isn't already present, so fragments still run. A base with no
  Startup-Sequence file at all has nothing to append to — its own
  recipe must ship one (`files` is the tool for that).
- `assigns` — array of `{ name, path }`: assigns added at boot, e.g.
  `{ name = "AmiSSL", path = "SYS:Devs/AmiSSL" }`.

## `[verify]` — post-install checks

- `exists` — array of Amiga paths that must exist in the built tree.
  Runs after assembly on every build; a recipe PR's fixture build must
  pass it in CI.

## `[options.*]` — typed parameters (the P96 case)

Where a real installer asks questions, the recipe declares them and the
manifest answers them:

```toml
[options.card]
type     = "enum"
values   = ["uaegfx", "picasso-iv", "cybervision64-3d", "zz9000"]
required = true
```

| Key | Type | Notes |
|---|---|---|
| `type` | string | `enum`, `bool`, or `string` |
| `values` | array of strings | required for `enum` |
| `required` | bool | default `false` |
| `default` | matches type | for `enum` must be one of `values`; the literal manifest answer `"auto"` opts into a per-emulator default the recipe declares — never silently applied, and the resolved choice always lands in the lockfile |

Option values may carry their own requirements, validated cross-axis like
any other:

```toml
[options.card.requires.uaegfx]
emulator = ["amiberry", "winuae"]
```

Options are part of the layer cache key: "P96 with uaegfx" and "P96 with
zz9000" are distinct cached layers.

## `[base]` — base-recipe version identity (base recipes only)

A base recipe (one named by a manifest's `base` key, e.g. `os3.2.2`,
`wb1.3`, `aros68k`) declares its OS and Kickstart identity so the
resolver can validate other recipes' `[requires]` against it:

```toml
[base]
os-version        = "3.2.2"
kickstart-version = "47.102"        # optional — only needed if some recipe's
                                     # [requires].kickstart differs from os
dos-type          = "ffs-intl"      # optional — default "ffs-intl"
```

Without `[base].os-version`, any recipe declaring `[requires].os` cannot
be validated against this base and the resolver reports that plainly
(naming the base recipe that's missing the metadata) rather than silently
skipping the check. `kickstart-version` is optional: recipes whose
Kickstart requirement is implied by their OS requirement don't need it,
and the resolver skips the Kickstart check when a base omits it.

`dos-type` picks the hdf output's filesystem: one of `ofs`, `ffs`,
`ofs-intl`, `ffs-intl` (the default), `ofs-intl-dircache`,
`ffs-intl-dircache`, `ofs-intl-longname`, `ffs-intl-longname`.
`international` mode is a 2.0+ FFS extension — a Kickstart 1.3 base
needs plain `ofs` or `ffs`, never an `-intl` variant. `-longname`
variants (DOS6/DOS7) allow filenames past the classic 30-character
limit; pick one when the base's own content needs it (AROS's bundled
fonts are the first real example found).

## `[hook]` — the fenced escape hatch

A recipe *may* declare `script = "hook.py"` for the genuinely
scripted-installer minority. Hooks are flagged by the linter, reviewed
harder, and a package whose installer makes decisions a recipe can't
express stays in the honest-limits table rather than being half-supported.
(Hook execution is not yet implemented; declaring one is legal and lints
with a warning.)

## Contributing a recipe

1. One directory, one `recipe.toml`, directory name = package name.
2. `amibake lint recipes/<name>` must pass.
3. Add a fixture manifest using the recipe; CI builds it and runs the
   recipe's `[verify]` block.
4. No builder changes. If the schema can't express the install, open an
   issue rather than a hook, unless the hook is genuinely unavoidable.
