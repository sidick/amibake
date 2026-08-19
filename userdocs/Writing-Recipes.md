# Writing a Recipe

A recipe teaches AmiBake to install one package — one directory in the
recipe library containing one declarative `recipe.toml`, never a
change to AmiBake's own code:

```
recipes/amissl/
  recipe.toml
```

The full contract lives in
[`docs/recipe-contract.md`](https://github.com/sidick/amibake/blob/main/docs/recipe-contract.md)
in the repository, and is deliberately written to be **sufficient on
its own** — a real recipe (`recipes/reqtools`) was written by an agent
given only that document and `docs/limits.md`, no builder source, as
its own validation exercise. This page is a shorter on-ramp; head to
the contract for every field's exact rules.

## The shape of a recipe

```toml
[package]
name        = "amissl"
versions    = ["5.20", "5.18"]        # newest first
depends     = []                      # e.g. ["mui >= 3.8"] or ["bsdsocket"]
conflicts   = []
provides    = []                      # capabilities, e.g. ["bsdsocket"]

[requires]                            # per-recipe OS floor/ceiling
os          = ">= 3.0"
kickstart   = ">= 39"
cpu         = ">= 68020"

[source.aminet]
url         = "util/libs/AmiSSL-{version}.lha"
sha256      = { "5.20" = "...", "5.18" = "..." }

[install]
copy = [
  { from = "AmiSSL/Libs/#?",  to = "SYS:Libs/" },
  { from = "AmiSSL/Certs/#?", to = "SYS:Devs/AmiSSL/Certs/" },
]

[verify]
exists      = ["SYS:Libs/amisslmaster.library"]
```

- **`[package]`** — identity (`name` must equal the directory name),
  `versions` (newest first, always quoted strings — never floats), and
  the dependency graph (`depends`/`conflicts`/`provides`).
- **`[requires]`** — what this package needs from the chosen base and
  machine: OS/Kickstart version ranges, a CPU floor, FPU/MMU flags,
  which emulators. Entirely optional, and every key within it is
  independently optional — a package can assert only the axes that
  actually matter to it. Can be overridden per package **version**.
- **`[source.*]`** — where to fetch from: `[source.aminet]`,
  `[source.github]`, `[source.url]`, or `[source.assets]` for
  proprietary media you supply yourself under `assets/` (never fetched
  or committed by AmiBake). A recipe may declare more than one as
  alternates. Every non-`assets` source is checksum-verified; `assets`
  checksums, when known, only warn on mismatch rather than hard-failing
  — real proprietary media often has more than one legitimate dump.
- **`[install]`** — `copy` entries (`from`/`to`, AmigaDOS `#?`
  wildcards, optional `when` for option-gated copies), plus `assigns`,
  `envarc`, and literal `files` for anything that isn't a straight copy
  from the archive.
- **`[verify]`** — post-build sanity checks (`exists`) run automatically
  by `amibake build` before any output is written.
- **`[options]`** (not shown above) — typed parameters a manifest can
  answer inline (`{ name = "picasso96-3", card = "uaegfx" }`), each with
  its own `[requires]`-style validation.

## Workflow

1. Pick a real, freely-fetchable archive if you can (Aminet or a GitHub
   release) — `tools/ci_recipe_smoke.py` auto-discovers and builds any
   such recipe against the `aros68k` base in CI, so it gets a real
   regression test for free. Proprietary-media-only recipes
   (`[source.assets]`) are excluded from that automatic coverage, by
   design.
2. Download the real archive and look at its actual layout — recipe
   `copy` patterns should match what the archive really contains, not a
   guess. Several real bugs in AmiBake itself (case-sensitivity in
   pattern matching, `\`-separated paths from DOS-era archivers,
   CPU-variant sibling files) were only found this way.
3. `amibake lint recipes/<name>` to validate the schema.
4. `amibake resolve`/`build` a small manifest naming just this package
   (plus a base it's compatible with) to confirm it actually installs
   and `[verify]` passes.
5. If a real declarative `[install]` genuinely can't express what's
   needed, check [`docs/limits.md`](https://github.com/sidick/amibake/blob/main/docs/limits.md)
   first — it catalogs every real gap found so far (and the fenced
   `[hook]` escape hatch, for the rare case that needs arbitrary Python)
   before reaching for something ad hoc.

## Contributing it back

AmiBake's recipe library lives in this repository (`recipes/`), so a
new or fixed recipe is a normal pull request:

1. Fork the repo, and add your recipe under `recipes/<name>/recipe.toml`
   (or edit an existing one).
2. Run the same checks CI runs before opening the PR:
   ```sh
   .venv/bin/amibake lint recipes manifests
   python tools/ci_recipe_smoke.py   # if your recipe is network-fetchable
   ```
3. Open a PR. CI runs `amibake lint` and the smoke build automatically
   — a network-fetchable recipe (Aminet/GitHub/URL source) gets a real
   build-and-`[verify]` regression test with no extra configuration on
   your part; a `[source.assets]`-only recipe (proprietary media) is
   linted but can't be build-tested in CI, so say in the PR description
   what you *did* verify it against locally.
4. Say plainly in the PR what's confirmed vs. assumed — which archive
   you actually downloaded and inspected, whether you built and booted
   it, and what (if anything) is still unverified. Several existing
   recipes carry exactly this kind of honest caveat in their own header
   comment (e.g. `recipes/picasso96-3`'s "nobody here has a licensed
   archive to test against") rather than a false claim of a real check
   that didn't happen — do the same.

## Where to go next

- [`docs/recipe-contract.md`](https://github.com/sidick/amibake/blob/main/docs/recipe-contract.md) — the full field-by-field contract.
- [`docs/limits.md`](https://github.com/sidick/amibake/blob/main/docs/limits.md) — what the declarative schema can't express yet, and how real recipes that hit a limit handled it.
- [Recipe Library](Recipes.md) — existing recipes to use as real
  worked examples.
- [CLI Reference](CLI-Reference.md) — `lint`/`resolve`/`build`.
