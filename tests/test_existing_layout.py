import os
import subprocess
from dataclasses import replace

import pytest

from sift.boundaries import check_boundaries, dependency_graph
from sift.errors import SiftError
from sift.util import copy_tree


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


@pytest.mark.skipif(os.name != "nt", reason="Windows directory junction")
def test_windows_junctions_cannot_capture_external_source(project, tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    (external / "private.txt").write_text("not part of this research")
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(project.root / "linked"), str(external)],
        check=True,
        capture_output=True,
    )
    with pytest.raises(SiftError, match="junction"):
        copy_tree(project.root, tmp_path / "snapshot")


@pytest.mark.skipif(os.name == "nt", reason="POSIX symbolic link")
def test_posix_links_cannot_capture_external_source(project, tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    (project.root / "linked").symlink_to(external, target_is_directory=True)
    with pytest.raises(SiftError, match="symlink"):
        copy_tree(project.root, tmp_path / "snapshot")
