
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


def test_build_end_to_end(tmp_path, capsys):
    recipes = tmp_path / "recipes"
    base_dir = recipes / "os32-fixture"
    base_dir.mkdir(parents=True)
    (base_dir / "recipe.toml").write_text(
        '[package]\nname = "os32-fixture"\nversions = ["3.2.2"]\n'
        'strategy = "extract"\n\n[base]\nos-version = "3.2.2"\n'
    )
    manifest = tmp_path / "m.toml"
    manifest.write_text('base = "os32-fixture"\noutput = ["dir"]\n')

    rc = main(["build", str(manifest), "--recipes", str(recipes),
              "--cache", str(tmp_path / "cache")])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "built" in captured.out
    assert (tmp_path / "m").is_dir()


def test_resolve_end_to_end(tmp_path, capsys):
    recipes = tmp_path / "recipes"
    base_dir = recipes / "os32-fixture"
    base_dir.mkdir(parents=True)
    (base_dir / "recipe.toml").write_text(
        '[package]\nname = "os32-fixture"\nversions = ["3.2.2"]\n'
        'strategy = "extract"\n\n[base]\nos-version = "3.2.2"\n'
    )
    manifest = tmp_path / "m.toml"
    manifest.write_text('base = "os32-fixture"\n')

    rc = main(["resolve", str(manifest), "--recipes", str(recipes)])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "resolved" in captured.out
    lockfile = tmp_path / "m.lock.toml"
    assert lockfile.is_file()
    assert 'name = "os32-fixture"' in lockfile.read_text()


def test_resolve_reports_named_errors(tmp_path, capsys):
    recipes = tmp_path / "recipes"
    recipes.mkdir()
    manifest = tmp_path / "m.toml"
    manifest.write_text('base = "nope"\n')
    rc = main(["resolve", str(manifest), "--recipes", str(recipes)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "nope" in captured.err


def test_resolve_aborts_on_dirty_manifest(tmp_path, capsys):
    recipes = tmp_path / "recipes"
    recipes.mkdir()
    manifest = tmp_path / "m.toml"
    manifest.write_text('base = "os32-fixture"\noutput = ["floppy"]\n')
    rc = main(["resolve", str(manifest), "--recipes", str(recipes)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "output[0]" in captured.err
    assert "aborted" in captured.err
