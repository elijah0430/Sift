from pathlib import Path

import pytest

from sift.config import ProjectConfig, initialize_project


@pytest.fixture
def project(tmp_path: Path) -> ProjectConfig:
    root = tmp_path / "project"
    root.mkdir()
    config = initialize_project(root, "demo")
    (root / "src" / "demo" / "__init__.py").write_text("", encoding="utf-8")
    return config
