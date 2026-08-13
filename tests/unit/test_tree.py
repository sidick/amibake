from amibake.tree import AmigaMeta, Tree


def test_put_get_case_insensitive_lookup_case_preserving_display():
    tree = Tree()
    tree.put("SYS:Libs/AmiSSL.library", b"data")
    assert tree.exists("sys:libs/amissl.library")
    assert tree.get("sys:libs/amissl.library").data == b"data"
    assert tree.paths() == ["SYS:Libs/AmiSSL.library"]


def test_paths_sorted_case_insensitively():
    tree = Tree()
    tree.put("SYS:b", b"1")
    tree.put("SYS:A", b"2")
    assert tree.paths() == ["SYS:A", "SYS:b"]


def test_meta_round_trips():
    tree = Tree()
    meta = AmigaMeta(protection=0x0F, comment="hi", datestamp=(1, 2, 3))
    tree.put("SYS:x", b"1", meta)
    assert tree.get("SYS:x").meta == meta


def test_content_hash_stable_across_equivalent_trees():
    a, b = Tree(), Tree()
    a.put("SYS:x", b"1")
    a.put("SYS:y", b"2")
    b.put("SYS:y", b"2")
    b.put("SYS:x", b"1")
    assert a.content_hash() == b.content_hash()


def test_content_hash_changes_with_data():
    a, b = Tree(), Tree()
    a.put("SYS:x", b"1")
    b.put("SYS:x", b"2")
    assert a.content_hash() != b.content_hash()


def test_content_hash_changes_with_user_startup_and_assigns():
    base = Tree()
    base.put("SYS:x", b"1")

    with_startup = base.clone()
    with_startup.add_user_startup(50, "pkg", ["Run Foo"])
    assert with_startup.content_hash() != base.content_hash()

    with_assign = base.clone()
    with_assign.add_assign("pkg", "Foo", "SYS:Foo")
    assert with_assign.content_hash() != base.content_hash()


def test_clone_is_independent():
    a = Tree()
    a.put("SYS:x", b"1")
    b = a.clone()
    b.put("SYS:y", b"2")
    assert not a.exists("SYS:y")
    assert b.exists("SYS:x")


def test_render_user_startup_deterministic_order_and_assigns_folded_in():
    tree = Tree()
    tree.add_user_startup(50, "zpkg", ["Run Z"])
    tree.add_user_startup(10, "apkg", ["Run A"])
    tree.add_assign("apkg", "Foo", "SYS:Foo")
    text = tree.render_user_startup().decode("latin-1")
    # assigns (order 0) come first, then ascending order, "apkg" before "zpkg"
    assign_pos = text.index("Assign Foo: SYS:Foo")
    a_pos = text.index("Run A")
    z_pos = text.index("Run Z")
    assert assign_pos < a_pos < z_pos


def test_render_user_startup_is_deterministic_across_calls():
    tree = Tree()
    tree.add_user_startup(50, "pkg", ["Run Foo"])
    assert tree.render_user_startup() == tree.render_user_startup()
