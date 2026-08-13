
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


def _hook_recipes(tmp_path, hook_body):
    recipes = tmp_path / "recipes"
    base_dir = recipes / "basefix"
    base_dir.mkdir(parents=True)
    (base_dir / "recipe.toml").write_text(
        '[package]\nname = "basefix"\nversions = ["1.0"]\n'
        'strategy = "extract"\n\n[base]\nos-version = "3.1"\n'
    )
    hook_dir = recipes / "hooktest"
    hook_dir.mkdir(parents=True)
    (hook_dir / "recipe.toml").write_text(
        '[package]\nname = "hooktest"\nversions = ["1.0"]\n\n'
        '[hook]\nscript = "hook.py"\n'
    )
    (hook_dir / "hook.py").write_text(hook_body)
    manifest = tmp_path / "m.toml"
    manifest.write_text('base = "basefix"\npackages = ["hooktest"]\noutput = ["dir"]\n')
    return recipes, manifest


def test_build_warning_only_recipe_still_builds(tmp_path, capsys):
    """A lint *warning* (e.g. a declared hook) must not abort build/resolve
    the way an *error* does — real bug found wiring up hook execution:
    _lint_then_resolve treated any problem, including warnings, as fatal."""
    recipes, manifest = _hook_recipes(
        tmp_path, "def apply(tree, archive, options):\n    return tree\n")
    rc = main(["build", str(manifest), "--recipes", str(recipes),
              "--cache", str(tmp_path / "cache")])
    captured = capsys.readouterr()
    assert rc == 1  # blocked, but by the *hook* gate, not the lint warning
    assert "declares a Python hook" in captured.err
    assert "does not lint clean" not in captured.err


def test_build_hook_requires_allow_hooks_flag(tmp_path, capsys):
    recipes, manifest = _hook_recipes(
        tmp_path, "def apply(tree, archive, options):\n    return tree\n")
    rc = main(["build", str(manifest), "--recipes", str(recipes),
              "--cache", str(tmp_path / "cache")])
    assert rc == 1
    assert "--allow-hooks" in capsys.readouterr().err


def test_build_hook_runs_with_allow_hooks_flag(tmp_path, capsys):
    recipes, manifest = _hook_recipes(tmp_path, (
        'def apply(tree, archive, options):\n'
        '    tree.put("SYS:HookProof", b"it ran")\n'
        '    return tree\n'
    ))
    rc = main(["build", str(manifest), "--recipes", str(recipes),
              "--cache", str(tmp_path / "cache"), "--allow-hooks"])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert (tmp_path / "m" / "HookProof").read_bytes() == b"it ran"


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


def test_build_emits_configs_for_every_emit_target(tmp_path, capsys):
    recipes = tmp_path / "recipes"
    base_dir = recipes / "os32-fixture"
    base_dir.mkdir(parents=True)
    (base_dir / "recipe.toml").write_text(
        '[package]\nname = "os32-fixture"\nversions = ["3.2.2"]\n'
        'strategy = "extract"\n\n[base]\nos-version = "3.2.2"\n'
        'kickstart-version = "34.5"\n'
    )
    assets = tmp_path / "assets"
    (assets / "roms").mkdir(parents=True)
    (assets / "roms" / "kickstart-34.5.rom").write_bytes(b"rom")
    manifest = tmp_path / "m.toml"
    manifest.write_text(
        'base = "os32-fixture"\nmachine = { cpu = "68030" }\n'
        'output = ["dir"]\nemit = ["copperline", "amiberry"]\n'
    )

    rc = main(["build", str(manifest), "--recipes", str(recipes),
              "--cache", str(tmp_path / "cache"), "--assets", str(assets)])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert (tmp_path / "m.copperline.toml").is_file()
    assert (tmp_path / "m-amiberry.uae").is_file()
    assert "cpu_model=68030" in (tmp_path / "m-amiberry.uae").read_text()


def test_build_emit_without_rom_fails_named_error(tmp_path, capsys):
    recipes = tmp_path / "recipes"
    base_dir = recipes / "os32-fixture"
    base_dir.mkdir(parents=True)
    (base_dir / "recipe.toml").write_text(
        '[package]\nname = "os32-fixture"\nversions = ["3.2.2"]\n'
        'strategy = "extract"\n\n[base]\nos-version = "3.2.2"\n'
        'kickstart-version = "34.5"\n'
    )
    manifest = tmp_path / "m.toml"
    manifest.write_text('base = "os32-fixture"\noutput = ["dir"]\nemit = ["amiberry"]\n')

    rc = main(["build", str(manifest), "--recipes", str(recipes),
              "--cache", str(tmp_path / "cache")])
    captured = capsys.readouterr()
    assert rc == 1
    assert "kickstart-34.5.rom" in captured.err


def test_build_emit_without_dir_output_fails_named_error(tmp_path, capsys):
    recipes = tmp_path / "recipes"
    base_dir = recipes / "os32-fixture"
    base_dir.mkdir(parents=True)
    (base_dir / "recipe.toml").write_text(
        '[package]\nname = "os32-fixture"\nversions = ["3.2.2"]\n'
        'strategy = "extract"\n\n[base]\nos-version = "3.2.2"\n'
        'kickstart-version = "34.5"\ndos-type = "ffs-intl"\n'
    )
    assets = tmp_path / "assets"
    (assets / "roms").mkdir(parents=True)
    (assets / "roms" / "kickstart-34.5.rom").write_bytes(b"rom")
    manifest = tmp_path / "m.toml"
    manifest.write_text('base = "os32-fixture"\noutput = ["hdf"]\nemit = ["amiberry"]\n')

    rc = main(["build", str(manifest), "--recipes", str(recipes),
              "--cache", str(tmp_path / "cache"), "--assets", str(assets)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "'dir' build output" in captured.err


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
