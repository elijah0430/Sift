from sift.boundaries import check_boundaries


def test_core_cannot_import_scratch(project):
    module = project.root / "src" / "demo" / "bad.py"
    module.write_text("from scratch.idea import method\n", encoding="utf-8")

    violations = check_boundaries(project)

    assert len(violations) == 1
    assert violations[0].imported == "scratch.idea"


def test_scratch_may_import_core(project):
    module = project.root / "scratch" / "idea.py"
    module.write_text("from demo import useful\n", encoding="utf-8")

    assert check_boundaries(project) == []


def test_scratch_explorations_cannot_import_each_other(project):
    first = project.root / "scratch" / "first"
    first.mkdir()
    (first / "idea.py").write_text("from scratch.second.method import run\n", encoding="utf-8")

    violations = check_boundaries(project)

    assert len(violations) == 1
    assert "cannot import each other" in violations[0].rule
