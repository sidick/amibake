"""Typed error taxonomy.

Every user-facing failure names the file, the field, the problem, and the
remedy. Tests assert on these fields, not on formatted strings.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Problem:
    file: str
    field: str  # dotted location, e.g. "[package].versions" or "packages[2]"
    problem: str
    remedy: str
    severity: str = "error"  # "error" | "warning"

    def __str__(self) -> str:
        tag = "warning: " if self.severity == "warning" else ""
        return f"{self.file}: {self.field}: {tag}{self.problem} — {self.remedy}"


class AmiBakeError(Exception):
    """Raised when a single Problem must abort immediately (unreadable file,
    unparseable TOML). Validators otherwise collect Problems."""

    def __init__(self, problem: Problem):
        self.problem = problem
        super().__init__(str(problem))
