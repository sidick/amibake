from amibake.tree import Tree
from amibake.verify import verify_exists


def test_verify_passes_when_paths_exist():
    tree = Tree()
    tree.put("SYS:Libs/amisslmaster.library", b"data")
    doc = {"verify": {"exists": ["SYS:Libs/amisslmaster.library"]}}
    assert verify_exists(tree, "amissl", doc) == []


def test_verify_fails_with_named_problem():
    tree = Tree()
    doc = {"verify": {"exists": ["SYS:Libs/amisslmaster.library"]}}
    problems = verify_exists(tree, "amissl", doc)
    assert len(problems) == 1
    assert "amissl" in problems[0]
    assert "SYS:Libs/amisslmaster.library" in problems[0]


def test_verify_no_verify_block_is_a_pass():
    tree = Tree()
    assert verify_exists(tree, "amissl", {}) == []
