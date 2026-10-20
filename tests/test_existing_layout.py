from dataclasses import replace

from sift.boundaries import check_boundaries, dependency_graph


def test_existing_flat_core_modules_are_supported(project):
    path = project.root / "metrics.py"
    path.write_text("import scratch.idea\n")
    config = replace(project, core=(path.relative_to(project.root),))
    graph, errors = dependency_graph(config)
    assert not errors
    assert "metrics" in graph
    assert any("core cannot import" in violation.rule for violation in check_boundaries(config))


def test_existing_package_root_is_not_mistaken_for_a_source_root(project):
    package = project.root / "library"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "method.py").write_text("VALUE=1\n")
    config = replace(project, core=(package.relative_to(project.root),))
    graph, errors = dependency_graph(config)
    assert not errors
    assert "library.method" in graph
