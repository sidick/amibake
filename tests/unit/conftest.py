from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def write(tmp_path):
    """Write TOML text to a temp file and return its path."""

    def _write(text: str, name: str = "test.toml", subdir: str | None = None) -> Path:
        directory = tmp_path / subdir if subdir else tmp_path
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_text(text)
        return path

    return _write


def fields_of(problems):
    return [p.field for p in problems]


def errors_of(problems):
    return [p for p in problems if p.severity == "error"]
