# CLI Reference

```
amibake lint <paths>...
amibake resolve <manifest> [--recipes DIR] [--lockfile FILE] [--print]
amibake build <manifest> [--recipes DIR] [--out DIR] [--cache DIR]
              [--assets DIR] [--no-cache] [--allow-hooks]
amibake --version
```

`amibake --version` prints the installed version and exits.
`amibake <command> --help` prints that subcommand's own flags.

## Exit codes

Every subcommand returns `0` on success. `lint` returns `1` if any
`error`-severity problem was found (warnings alone still exit `0`).
`resolve` and `build` return `1` on any lint failure, resolve failure,
fetch/extract error, `[hook]` refusal, `[verify]` failure, or emitter
error — in every case, a diagnostic is printed to stderr naming exactly
what went wrong before exiting.

## `amibake lint <paths>...`

Validates recipes and manifests against the schema, without resolving
or building anything. Each path is either:

- a directory — every `recipe.toml` beneath it is checked (recursively);
  if none are found, every `*.toml` beneath it is checked as a manifest
  instead;
- a `recipe.toml` file — checked as a recipe;
- any other `.toml` file — checked as a manifest.

```console
$ amibake lint recipes manifests
30 file(s) checked: 0 error(s), 0 warning(s)
```

Every problem is printed as it's found (file, field, what's wrong, and
the fix), then a one-line summary. This is the fast, no-network check —
run it before `resolve`/`build`, and it's exactly what CI runs first
(see the shipped `.github/workflows/ci.yml`).

## `amibake resolve <manifest>`

Lints the manifest and every recipe in the library, then resolves
package versions, dependencies, and `[requires]` (OS/Kickstart/CPU/
FPU/MMU/emulator) against the chosen base and machine — producing a
deterministic build plan and a lockfile. Does not fetch, extract, or
build anything.

```console
$ amibake resolve manifests/aros68k.toml
resolved manifests/aros68k.toml: base=aros68k, packages=[(none)]
wrote manifests/aros68k.lock.toml
```

| Flag | Default | Meaning |
|---|---|---|
| `--recipes DIR` | `./recipes` | Recipe library root. |
| `--lockfile FILE` | `<manifest>.lock.toml` | Lockfile output path. |
| `--print` | off | Print the lockfile to stdout instead of writing it. |

## `amibake build <manifest>`

Runs `resolve` internally, then fetches every source (verifying
checksums, using the content-addressed cache), extracts and layers it
into an internal tree, runs the recipe's `[verify]` checks, and emits
every requested output format and emulator config.

```console
$ amibake build manifests/aros68k.toml --assets assets
built manifests/aros68k.toml: base=aros68k, packages=[(none)]
wrote manifests/aros68k.hdf
wrote manifests/aros68k
```

| Flag | Default | Meaning |
|---|---|---|
| `--recipes DIR` | `./recipes` | Recipe library root. |
| `--out DIR` | alongside the manifest | Output directory for built images/configs. |
| `--cache DIR` | `./.amibake-cache` | Layer/archive cache root. |
| `--assets DIR` | none | `assets/` directory for proprietary sources (OS media, ROMs) — never fetched or committed by AmiBake itself. |
| `--no-cache` | off | Bypass the layer cache (always re-fetch/re-extract/re-layer). |
| `--allow-hooks` | off | Run a recipe's `[hook]` script (arbitrary Python executed during the build — review it first). Without this flag, a build needing a hook fails, naming which recipe declared it. |

See [Getting Started](Getting-Started.md) for a full walkthrough, and
[Manifest Format](Manifest-Format.md) for what `output`/`emit` in the
manifest control.
