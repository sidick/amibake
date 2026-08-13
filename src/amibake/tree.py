"""Internal build-time filesystem representation.

Paths are plain strings: full Amiga paths with a volume prefix
("SYS:Libs/amisslmaster.library") for the build target, or archive-
relative paths with none ("AmiSSL/Libs/amisslmaster.library") for
extracted archive contents. AmigaDOS filesystems are case-insensitive
but case-preserving, so lookups are case-insensitive while the stored
name keeps whatever case was written.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AmigaMeta:
    protection: int = 0
    comment: str = ""
    # (days, minutes, ticks) since 1978-01-01, the AmigaDOS DateStamp
    # convention. Builds are deterministic, so real wall-clock timestamps
    # are never used here — (0, 0, 0) means "unset".
    datestamp: tuple[int, int, int] = (0, 0, 0)


@dataclass(frozen=True)
class TreeFile:
    data: bytes
    meta: AmigaMeta = field(default_factory=AmigaMeta)


@dataclass(frozen=True)
class UserStartupFragment:
    order: int
    source: str  # package name; a stable tiebreak when order ties
    lines: tuple[str, ...]


@dataclass(frozen=True)
class Assign:
    source: str
    name: str
    path: str


class Tree:
    """A build-time Amiga filesystem tree, assembled layer by layer."""

    def __init__(self) -> None:
        self._files: dict[str, TreeFile] = {}  # lowercased path -> file
        self._names: dict[str, str] = {}  # lowercased path -> display-cased path
        self.user_startup: list[UserStartupFragment] = []
        self.assigns: list[Assign] = []

    @staticmethod
    def _key(path: str) -> str:
        return path.lower()

    def put(self, path: str, data: bytes, meta: AmigaMeta | None = None) -> None:
        key = self._key(path)
        self._files[key] = TreeFile(data=data, meta=meta or AmigaMeta())
        self._names[key] = path

    def get(self, path: str) -> TreeFile:
        return self._files[self._key(path)]

    def exists(self, path: str) -> bool:
        return self._key(path) in self._files

    def paths(self) -> list[str]:
        """Display-cased paths, in deterministic (case-insensitive) order."""
        return [self._names[k] for k in sorted(self._files)]

    def add_user_startup(self, order: int, source: str, lines: list[str]) -> None:
        if lines:
            self.user_startup.append(UserStartupFragment(order, source, tuple(lines)))

    def add_assign(self, source: str, name: str, path: str) -> None:
        self.assigns.append(Assign(source, name, path))

    def render_user_startup(self) -> bytes:
        """S:User-Startup content: assigns folded in as `Assign` lines at
        order 0, package fragments after, everything sorted by
        (order, source) so layering order never affects the result."""
        fragments = list(self.user_startup)
        if self.assigns:
            assign_lines = [
                f"Assign {a.name}: {a.path}"
                for a in sorted(self.assigns, key=lambda a: (a.name, a.source))
            ]
            fragments.append(UserStartupFragment(0, "", tuple(assign_lines)))
        fragments.sort(key=lambda f: (f.order, f.source))
        blocks = [
            f"; --- {frag.source or 'assigns'} ---\n" + "\n".join(frag.lines)
            for frag in fragments
        ]
        return ("\n\n".join(blocks) + "\n").encode("latin-1")

    def content_hash(self) -> str:
        """Deterministic hash of everything a byte-identical rebuild must
        reproduce: file contents and metadata, plus user-startup fragments
        and assigns (which aren't materialized into `files` until a
        finalize step chooses to call render_user_startup)."""
        h = hashlib.sha256()
        for key in sorted(self._files):
            f = self._files[key]
            h.update(key.encode())
            h.update(f.data)
            h.update(repr(f.meta).encode())
        for frag in sorted(self.user_startup, key=lambda f: (f.order, f.source, f.lines)):
            h.update(repr(frag).encode())
        for a in sorted(self.assigns, key=lambda a: (a.source, a.name, a.path)):
            h.update(repr(a).encode())
        return h.hexdigest()

    def materialize(self) -> Tree:
        """A clone with S:User-Startup written as a real file, if there are
        any startup fragments or assigns to render. Emitters call this once
        before writing files, so hdf/dir/archive outputs agree."""
        if not self.user_startup and not self.assigns:
            return self.clone()
        t = self.clone()
        t.put("S:User-Startup", t.render_user_startup())
        t._ensure_startup_sequence_sources_user_startup()
        return t

    # Recipes write Startup-Sequence via [install].copy/[install].files
    # using the physical "SYS:S/Startup-Sequence" path (same convention
    # as every other [install] destination); this class's own
    # materialize() writes S:User-Startup via the logical "S:"
    # volume-alias form. paths.py's to_physical_path() already treats
    # both as equivalent at emit time (S: -> physical S/), but at the
    # Tree-key level (pre-emit) they're different keys — so a lookup
    # here has to check both forms, not just one.
    _STARTUP_SEQUENCE_KEYS = ("SYS:S/Startup-Sequence", "S:Startup-Sequence")

    def _ensure_startup_sequence_sources_user_startup(self) -> None:
        """`EXECUTE S:User-Startup` from Startup-Sequence is a 2.0+
        convention (same generation as ENVARC:) — a base whose installed
        Startup-Sequence predates it (e.g. real Kickstart 1.3) never runs
        S:User-Startup at all, so every other package's user-startup
        fragments would be silently dead code on that base. When there's
        a Startup-Sequence to patch and it doesn't already reference
        User-Startup, append the sourcing stanza automatically. A no-op
        for any base whose real Startup-Sequence already sources it
        (harmless: the check below skips them)."""
        key = next((k for k in self._STARTUP_SEQUENCE_KEYS if self.exists(k)), None)
        if key is None:
            return
        current = self.get(key)
        if b"user-startup" in current.data.lower():
            return
        stanza = (
            b"\n; --- amibake: run S:User-Startup (appended automatically "
            b"-- this base's own Startup-Sequence doesn't source it) ---\n"
            b"IF EXISTS S:User-Startup\n"
            b"  EXECUTE S:User-Startup\n"
            b"ENDIF\n"
        )
        self.put(key, current.data + stanza, current.meta)

    def clone(self) -> Tree:
        t = Tree()
        t._files = dict(self._files)
        t._names = dict(self._names)
        t.user_startup = list(self.user_startup)
        t.assigns = list(self.assigns)
        return t
