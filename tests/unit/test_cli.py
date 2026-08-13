import pytest

from amibake.cli import main

from .conftest import REPO_ROOT


def test_lint_shipped_tree_is_green(capsys):
    rc = main(["lint", str(REPO_ROOT / "recipes"), str(REPO_ROOT / "manifests")])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "0 error(s)" in captured.out


def test_lint_bad_manifest_fails(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text('base = "os3.2.2"\noutput = ["floppy"]\n')
    rc = main(["lint", str(bad)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "output[0]" in captured.err
    assert "1 error(s)" in captured.out


def test_lint_unparseable_toml_fails(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text("base = os3.2.2\n")
    rc = main(["lint", str(bad)])
    assert rc == 1
    assert "not valid TOML" in capsys.readouterr().err


def test_lint_missing_path_fails(tmp_path, capsys):
    rc = main(["lint", str(tmp_path / "nope.toml")])
    assert rc == 1
    assert "no such file" in capsys.readouterr().err


def test_lint_warnings_do_not_fail(tmp_path, capsys):
    recipe_dir = tmp_path / "pkg"
    recipe_dir.mkdir()
    (recipe_dir / "recipe.toml").write_text(
        '[package]\nname = "pkg"\nversions = ["1.0"]\n\n'
        '[source.assets]\npath = "pkg.lha"\n\n'
        '[hook]\nscript = "hook.py"\n'
    )
    rc = main(["lint", str(recipe_dir)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "1 warning(s)" in captured.out


@pytest.mark.parametrize("command", ["build", "resolve"])
def test_unimplemented_commands_exit_2(tmp_path, capsys, command):
    manifest = tmp_path / "m.toml"
    manifest.write_text('base = "aros68k"\n')
    rc = main([command, str(manifest)])
    assert rc == 2
    assert "not implemented" in capsys.readouterr().err
