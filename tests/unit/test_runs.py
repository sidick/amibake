"""Manifest [[run]] entries: lint shape (manifest.py), cross-document
resolution (resolver.py — stack/tooltype merge against a recipe's
[install].commands), and application to a built Tree (runs.py)."""

import struct

import pytest

from amibake._validate import load_toml
from amibake.icon import read_tool_types
from amibake.manifest import validate_manifest
from amibake.plan import RunEntry, format_lockfile
from amibake.resolver import load_recipe_library, resolve
from amibake.runs import RUN_SCRIPT_PATH, RunError, apply_runs
from amibake.tree import Tree

SHA = "0" * 64


# --- fixtures -----------------------------------------------------------

def _lib(tmp_path, recipes: dict[str, str]):
    root = tmp_path / "recipes"
    for name, text in recipes.items():
        d = root / name
        d.mkdir(parents=True)
        (d / "recipe.toml").write_text(text)
    return load_recipe_library(root)


def _manifest(tmp_path, text: str):
    path = tmp_path / "manifest.toml"
    path.write_text(text)
    return path, load_toml(path)


BASE_32 = '''
[package]
name     = "base-fixture"
versions = ["3.2.2"]
strategy = "extract"

[base]
os-version        = "3.2.2"
kickstart-version = "47.102"
'''

BASE_13 = '''
[package]
name     = "base13-fixture"
versions = ["1.3"]
strategy = "extract"

[base]
os-version        = "1.3"
kickstart-version = "34.5"
'''

SOAK = f'''
[package]
name     = "soak-fixture"
versions = ["1.0"]

[source.aminet]
url    = "dev/misc/soak.lha"
sha256 = {{ "1.0" = "{SHA}" }}

[install]
copy     = [{{ from = "soak/soak", to = "SYS:C/soak" }}]
commands = [{{ path = "SYS:C/soak", stack = 65536 }}]
'''

WBTOOL = f'''
[package]
name     = "wbtool-fixture"
versions = ["1.0"]

[source.aminet]
url    = "util/wbtool.lha"
sha256 = {{ "1.0" = "{SHA}" }}

[install]
copy     = [{{ from = "wbtool/#?", to = "SYS:Tools/" }}]
commands = [{{ path = "SYS:Tools/WbTool", stack = 16384, tooltypes = {{ CX_POPUP = "NO" }} }}]
'''


def _resolve(tmp_path, manifest_text, recipes):
    library = _lib(tmp_path, recipes)
    path, manifest = _manifest(tmp_path, manifest_text)
    return resolve(path, manifest, library)


# A minimal structurally-real icon (same layout test_icon.py builds).
def _icon(tool_types=()):
    header = bytearray(78)
    struct.pack_into(">HH", header, 0, 0xE310, 1)
    struct.pack_into(">I", header, 54, 0x401DE130 if tool_types else 0)
    header[48] = 3
    body = bytes(header)
    if tool_types:
        body += struct.pack(">I", (len(tool_types) + 1) * 4)
        for entry in tool_types:
            raw = entry.encode("latin-1") + b"\0"
            body += struct.pack(">I", len(raw)) + raw
    return body


# --- manifest lint ------------------------------------------------------

class TestManifestLint:
    def _problems(self, tmp_path, run_toml):
        path = tmp_path / "m.toml"
        path.write_text(f'base = "b"\n{run_toml}')
        return validate_manifest(path)

    def test_minimal_cli_entry_lints_clean(self, tmp_path):
        assert self._problems(tmp_path, '[[run]]\ncommand = "C:soak"\n') == []

    def test_command_must_be_an_amiga_path(self, tmp_path):
        problems = self._problems(tmp_path, '[[run]]\ncommand = "soak"\n')
        assert any("not an Amiga path" in p.problem for p in problems)

    def test_unknown_mode_is_an_error(self, tmp_path):
        problems = self._problems(
            tmp_path, '[[run]]\ncommand = "C:x"\nmode = "startup"\n')
        assert any("unknown run mode" in p.problem for p in problems)

    def test_wbstartup_keys_rejected_on_cli_entries(self, tmp_path):
        problems = self._problems(
            tmp_path, '[[run]]\ncommand = "C:x"\nstartpri = 5\n')
        assert any("only applies to" in p.problem for p in problems)

    def test_cli_keys_rejected_on_wbstartup_entries(self, tmp_path):
        problems = self._problems(
            tmp_path,
            '[[run]]\ncommand = "SYS:T/x"\nmode = "wbstartup"\ndetach = true\n')
        assert any("only applies to" in p.problem for p in problems)

    def test_sugar_and_explicit_tooltype_conflict_is_an_error(self, tmp_path):
        problems = self._problems(
            tmp_path,
            '[[run]]\ncommand = "SYS:T/x"\nmode = "wbstartup"\n'
            'stack = 8192\ntooltypes = { STACK = "16384" }\n')
        assert any("also set via" in p.problem for p in problems)

    def test_tooltype_values_may_be_bool(self, tmp_path):
        assert self._problems(
            tmp_path,
            '[[run]]\ncommand = "SYS:T/x"\nmode = "wbstartup"\n'
            'tooltypes = { DONOTWAIT = true, CX_POPUP = false }\n') == []


# --- resolver -----------------------------------------------------------

class TestResolveRuns:
    def test_stack_defaults_from_recipe_commands(self, tmp_path):
        result = _resolve(tmp_path, (
            'base = "base-fixture"\npackages = ["soak-fixture"]\n'
            '[[run]]\ncommand = "C:soak"\nargs = "-y"\n'
        ), {"base-fixture": BASE_32, "soak-fixture": SOAK})
        assert result.ok and result.problems == []
        (run,) = result.plan.runs
        assert run.stack == 65536  # C:soak matched SYS:C/soak's declaration
        assert run.args == "-y"

    def test_manifest_stack_wins_with_a_warning_when_lower(self, tmp_path):
        result = _resolve(tmp_path, (
            'base = "base-fixture"\npackages = ["soak-fixture"]\n'
            '[[run]]\ncommand = "SYS:C/soak"\nstack = 4096\n'
        ), {"base-fixture": BASE_32, "soak-fixture": SOAK})
        assert result.ok
        (run,) = result.plan.runs
        assert run.stack == 4096
        assert [p.severity for p in result.problems] == ["warning"]
        assert "below the 65536" in result.problems[0].problem

    def test_higher_override_gets_no_warning(self, tmp_path):
        result = _resolve(tmp_path, (
            'base = "base-fixture"\npackages = ["soak-fixture"]\n'
            '[[run]]\ncommand = "SYS:C/soak"\nstack = 131072\n'
        ), {"base-fixture": BASE_32, "soak-fixture": SOAK})
        assert result.ok and result.problems == []
        assert result.plan.runs[0].stack == 131072

    def test_wbstartup_tooltypes_merge_and_override(self, tmp_path):
        result = _resolve(tmp_path, (
            'base = "base-fixture"\npackages = ["wbtool-fixture"]\n'
            '[[run]]\ncommand = "SYS:Tools/WbTool"\nmode = "wbstartup"\n'
            'startpri = 5\ntooltypes = { CX_POPUP = "YES" }\n'
        ), {"base-fixture": BASE_32, "wbtool-fixture": WBTOOL})
        assert result.ok and result.problems == []
        tooltypes = dict(result.plan.runs[0].tooltypes)
        assert tooltypes == {
            "STACK": "16384",       # from the recipe's commands.stack
            "STARTPRI": "5",        # sugar
            "DONOTWAIT": True,      # default
            "CX_POPUP": "YES",      # manifest override of the recipe's NO
        }

    def test_donotwait_false_resolves_to_removal(self, tmp_path):
        result = _resolve(tmp_path, (
            'base = "base-fixture"\npackages = ["wbtool-fixture"]\n'
            '[[run]]\ncommand = "SYS:Tools/WbTool"\nmode = "wbstartup"\n'
            'donotwait = false\n'
        ), {"base-fixture": BASE_32, "wbtool-fixture": WBTOOL})
        assert result.ok
        assert dict(result.plan.runs[0].tooltypes)["DONOTWAIT"] is False

    def test_wbstartup_on_a_kickstart_13_base_is_an_error(self, tmp_path):
        result = _resolve(tmp_path, (
            'base = "base13-fixture"\npackages = ["wbtool-fixture"]\n'
            '[[run]]\ncommand = "SYS:Tools/WbTool"\nmode = "wbstartup"\n'
        ), {"base13-fixture": BASE_13, "wbtool-fixture": WBTOOL})
        assert not result.ok
        assert any("Kickstart 36+" in p.problem for p in result.problems)

    def test_runs_serialize_into_the_lockfile(self, tmp_path):
        result = _resolve(tmp_path, (
            'base = "base-fixture"\npackages = ["soak-fixture"]\n'
            '[[run]]\ncommand = "C:soak"\nargs = "-y"\noutput = "SER:"\n'
        ), {"base-fixture": BASE_32, "soak-fixture": SOAK})
        text = format_lockfile(result.plan)
        assert '[[run]]' in text
        assert 'command = "C:soak"' in text
        assert 'stack = 65536' in text
        assert 'output = "SER:"' in text


# --- apply_runs ---------------------------------------------------------

def _tree_with_soak():
    tree = Tree()
    tree.put("SYS:C/soak", b"BIN")
    tree.put("SYS:S/Startup-Sequence", b"EXECUTE S:User-Startup\n")
    return tree


class TestApplyCli:
    def test_renders_script_and_user_startup_fragment(self):
        tree = apply_runs(_tree_with_soak(), (
            RunEntry(command="C:soak", args="-d -y", stack=65536,
                     output="T:soak.log"),
        ))
        script = tree.get(RUN_SCRIPT_PATH).data.decode("latin-1")
        assert "Stack 65536\n" in script
        assert "C:soak -d -y >T:soak.log\n" in script
        assert any(f.order == 95 and f.lines == (f"Execute {RUN_SCRIPT_PATH}",)
                   for f in tree.user_startup)

    def test_detach_prefixes_run(self):
        tree = apply_runs(_tree_with_soak(),
                          (RunEntry(command="C:soak", detach=True),))
        script = tree.get(RUN_SCRIPT_PATH).data.decode("latin-1")
        assert "Run >NIL: C:soak\n" in script

    def test_no_stack_means_no_stack_line(self):
        tree = apply_runs(_tree_with_soak(), (RunEntry(command="C:soak"),))
        assert b"Stack " not in tree.get(RUN_SCRIPT_PATH).data

    def test_missing_command_names_the_entry_and_path(self):
        with pytest.raises(RunError, match=r"\[\[run\]\] entry 0.*C:nope"):
            apply_runs(_tree_with_soak(), (RunEntry(command="C:nope"),))

    def test_original_tree_is_not_mutated(self):
        tree = _tree_with_soak()
        apply_runs(tree, (RunEntry(command="C:soak"),))
        assert not tree.exists(RUN_SCRIPT_PATH)
        assert tree.user_startup == []

    def test_no_entries_is_a_no_op(self):
        tree = _tree_with_soak()
        assert apply_runs(tree, ()) is tree


class TestApplyWbstartup:
    def _tree(self, icon=True):
        tree = Tree()
        tree.put("SYS:Tools/WbTool", b"BIN")
        if icon:
            tree.put("SYS:Tools/WbTool.info", _icon(["CX_POPUP=NO"]))
        return tree

    def test_copies_tool_and_patched_icon(self):
        tree = apply_runs(self._tree(), (
            RunEntry(command="SYS:Tools/WbTool", mode="wbstartup",
                     tooltypes=(("CX_POPUP", "YES"), ("DONOTWAIT", True),
                                ("STACK", "16384"))),
        ))
        assert tree.get("SYS:WBStartup/WbTool").data == b"BIN"
        tool_types = read_tool_types(tree.get("SYS:WBStartup/WbTool.info").data)
        assert tool_types == ["CX_POPUP=YES", "DONOTWAIT", "STACK=16384"]
        # No S:AmiBake-Startup for a wbstartup-only manifest.
        assert not tree.exists(RUN_SCRIPT_PATH)
        assert tree.user_startup == []

    def test_false_tooltype_removes_from_shipped_icon(self):
        tree = apply_runs(self._tree(), (
            RunEntry(command="SYS:Tools/WbTool", mode="wbstartup",
                     tooltypes=(("CX_POPUP", False), ("DONOTWAIT", True))),
        ))
        tool_types = read_tool_types(tree.get("SYS:WBStartup/WbTool.info").data)
        assert tool_types == ["DONOTWAIT"]

    def test_missing_icon_is_a_named_error(self):
        with pytest.raises(RunError, match=r"WbTool\.info.*not in this build"):
            apply_runs(self._tree(icon=False), (
                RunEntry(command="SYS:Tools/WbTool", mode="wbstartup"),))
