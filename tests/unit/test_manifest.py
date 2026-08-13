import pytest

from amibake.errors import AmiBakeError
from amibake.manifest import validate_manifest

from .conftest import REPO_ROOT, errors_of

VALID = '''
base     = "os3.2.2"
machine  = { cpu = "68030", fpu = true, mmu = true, ram = "chip:2M,fast:8M", rtg = true }
packages = [
  "p96 >= 3.2",
  "amissl = 5.20",
  { name = "p96", version = ">= 3.2", card = "uaegfx" },
]
output   = ["hdf", "dir"]
emit     = ["copperline", "amiberry"]

[providers]
bsdsocket = "roadshow"
'''


def test_valid_manifest(write):
    assert validate_manifest(write(VALID)) == []


def test_shipped_exemplar_manifests_lint_clean():
    manifests = sorted((REPO_ROOT / "manifests").glob("*.toml"))
    assert manifests, "no exemplar manifests found"
    for m in manifests:
        assert validate_manifest(m) == [], f"{m} should lint clean"


# Each case: (toml text, substring expected in some problem's field)
INVALID = [
    ("", "base"),  # missing base
    ('base = "os3.2.2"\nbogus = 1\n', "bogus"),  # unknown top-level key
    ('base = "OS3.2"\n', "base"),  # bad base name
    ('base = "os3.2.2"\nmachine = { cpu = "68030/68882" }\n', "machine.cpu"),
    ('base = "os3.2.2"\nmachine = { cpu = "68030", fpu = 1 }\n', "machine.fpu"),
    ('base = "os3.2.2"\nmachine = { ram = "fast:8MB" }\n', "machine.ram"),
    ('base = "os3.2.2"\nmachine = { chipset = "aaa" }\n', "machine.chipset"),
    ('base = "os3.2.2"\nmachine = { turbo = true }\n', "machine.turbo"),
    ('base = "os3.2.2"\npackages = ["amissl == 5.20"]\n', "packages[0]"),
    ('base = "os3.2.2"\npackages = [5.20]\n', "packages[0]"),
    ('base = "os3.2.2"\npackages = [{ version = "= 5.20" }]\n', "packages[0].name"),
    ('base = "os3.2.2"\npackages = [{ name = "p96", version = "3.2" }]\n',
     "packages[0].version"),
    ('base = "os3.2.2"\npackages = [{ name = "p96", card = 5.2 }]\n',
     "packages[0].card"),
    ('base = "os3.2.2"\noutput = ["floppy"]\n', "output[0]"),
    ('base = "os3.2.2"\nemit = ["fs-uae"]\n', "emit[0]"),
    ('base = "os3.2.2"\n[providers]\nbsdsocket = 3\n', "providers.bsdsocket"),
]


@pytest.mark.parametrize(("text", "field"), INVALID,
                         ids=[f[1] for f in INVALID])
def test_invalid_manifests(write, text, field):
    problems = errors_of(validate_manifest(write(text)))
    assert problems, "expected at least one error"
    assert any(field in p.field for p in problems), (
        f"no problem mentioning {field!r} in {[p.field for p in problems]}")
    for p in problems:
        assert p.remedy, "every error carries a remedy"


def test_unparseable_toml_aborts(write):
    with pytest.raises(AmiBakeError) as exc:
        validate_manifest(write("base = os3.2.2\n"))
    assert "quoted" in exc.value.problem.remedy
