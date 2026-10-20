from pathlib import Path

import pytest

from sift.config import ProjectConfig, initialize_project


@pytest.fixture
def project(tmp_path: Path) -> ProjectConfig:
    root = tmp_path / "project"
    root.mkdir()
    config = initialize_project(root, "demo")
    config_path = root / "research.toml"
    config_path.write_text(
        config_path.read_text().replace('commands = ["python -m pytest"]', "commands = []"),
        encoding="utf-8",
    )
    config = ProjectConfig.load(root)
    (root / "src" / "demo" / "__init__.py").write_text("", encoding="utf-8")
    return config
