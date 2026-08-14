# amibake

Manifest-driven Amiga test setup builder: pick a base OS, list packages
and versions, name a machine variant, get back a ready-to-boot disk image
plus matching emulator configuration — a Dockerfile for Amiga setups.

```toml
base     = "os3.2.2"
machine  = { cpu = "68030", fpu = true, mmu = true, ram = "fast:8M", rtg = true }
packages = ["picasso96-3 >= 3.2", "amissl = 5.27", "classact = 3.3"]
emit     = ["copperline", "amiberry"]
```

**Status: early development.** `amibake lint` (manifest and recipe
validation) works; resolve/build arrive per [PLAN.md](PLAN.md).

## Documentation

- [docs/manifest.md](docs/manifest.md) — the manifest format
- [docs/recipe-contract.md](docs/recipe-contract.md) — the recipe contract:
  everything needed to add support for a package, without reading builder
  source
- [docs/limits.md](docs/limits.md) — what the declarative schema can't
  express yet, and how real recipes that hit a limit handled it
- [PLAN.md](PLAN.md) — implementation plan and milestones

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/amibake lint recipes manifests
```
