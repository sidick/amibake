# Vendored AROS 68k ROM

`aros-rom.bin` (Kickstart replacement) and `aros-ext.bin` (extended ROM)
are `boot/amiga/` from the **AROS 20260930** m68k boot-iso nightly —
the same nightly `../recipe.toml` pins for the SYS: content, so the ROM
and the filesystem it boots always come from one build.

They are committed rather than fetched because the nightly they come
from is unfetchable within weeks: SourceForge prunes dated nightly
directories, so a URL pin 404s and every build that needs a ROM breaks
with it. At 512K each they cost the repo little, unlike the 115 MB
boot-iso zip (410 MB ISO) the SYS: content is cut from — which is why
only the ROM is vendored and the rest still comes from the pinned URL.

Without these, `amibake build` could emit no emulator config for the
AROS base at all: config emission looks for
`assets/roms/kickstart-<version>.rom`, and AROS has no Kickstart version
to look one up by — AROS *is* the ROM.

`tools/refresh_aros_nightly.py` rewrites these two files together with
the recipe's pin, so they never drift apart.

Licence: the AROS Public License (APL) v1.1, `LICENSE` here, copied
verbatim from the same nightly archive. Freely redistributable — the
reason AmiBake can commit this and not a Commodore Kickstart.

Checksums (`shasum -a 256`), for cross-checking against the upstream
nightly:

    97d1e6e6a5d73d4bae383fcb6ad1c4707d56fdeebcfb96905a0e00503a9b4cd7  aros-rom.bin
    b3458049872043009754c2114f441ff3977ec36efa0011b988c335d39de3d993  aros-ext.bin
