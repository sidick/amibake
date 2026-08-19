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

**Status:** `lint`, `resolve`, and `build` all work end-to-end. Bases
include AROS 68k, Workbench 1.3, AmigaOS 3.1.4, and AmigaOS 3.2.2 (the
last two need your own licensed install media under `assets/`, which is
never committed — see [docs/limits.md](docs/limits.md)); AROS builds
from freely-available nightlies, so it's the base CI exercises directly.
Package recipes cover AmiSSL, Picasso96, ClassAct, MUI (3.8 and 5.0),
BGUI, ReqTools, xfdMaster, XPK, and more under `recipes/`. Emitted
output boots interactively under both Copperline and Amiberry. See
[PLAN.md](PLAN.md) for milestone-by-milestone status and what's next
(a CI action for consuming projects).

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

## License

[MIT](LICENSE)
