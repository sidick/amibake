# Installation

## Requirements

- **Python 3.11 or later** (AmiBake uses the stdlib `tomllib`, added in
  3.11). Tested on macOS and Linux; Windows hasn't been tried.
- **No Amiga hardware, ROM image, or emulator required to build.**
  AmiBake resolves and builds entirely on the host — an emulator only
  comes into play if you actually want to boot the result, and even
  then only a Kickstart ROM (for `emit`'s emulator configs) is needed,
  not a full install of one.

## Getting the CLI

AmiBake has not yet had a tagged PyPI release (see
[the index page](index.md)'s note on project status) — install it from
source, into a virtualenv:

```sh
git clone https://github.com/sidick/amibake.git
cd amibake
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

This installs the `amibake` console script into `.venv/bin/`, along
with the `pytest`/`ruff` dev toolchain. See
[Building from Source](Building-from-Source.md) for running the test
suite and linting the shipped recipe library.

## Checking it works

```console
$ .venv/bin/amibake --version
amibake 0.1.0.dev0
$ .venv/bin/amibake lint recipes manifests
30 file(s) checked: 0 error(s), 0 warning(s)
```

`amibake lint` validates every shipped recipe and manifest against the
schema — a clean run (`0 error(s)`) confirms the CLI is installed and
working, and the recipe library it ships with is internally consistent.

## Next steps

- [Getting Started](Getting-Started.md) — resolve and build a real
  manifest, starting from the AROS 68k base (no licensed media needed).
- [CLI Reference](CLI-Reference.md) — every `amibake` subcommand and
  flag.
