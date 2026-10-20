from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import SiftError

DEFAULT_CONFIG = """# Sift project configuration
[paths]
core = ["src"]
experiments = "experiments"
scratch = "scratch"
tests = "tests"
state = ".research"

[checks]
commands = ["python -m pytest"]

[retention]
archive_days = 90
"""


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    core: tuple[Path, ...]
    experiments: Path
    scratch: Path
    tests: Path
    state: Path
    checks: tuple[str, ...]
    archive_days: int

    @classmethod
    def load(cls, root: Path) -> ProjectConfig:
        path = root / "research.toml"
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise SiftError(f"Could not read {path}: {exc}") from exc
        paths = data.get("paths", {})
        try:
            core_values = paths.get("core", ["src"])
            if isinstance(core_values, str):
                core_values = [core_values]
            return cls(
                root=root,
                core=tuple(Path(value) for value in core_values),
                experiments=Path(paths.get("experiments", "experiments")),
                scratch=Path(paths.get("scratch", "scratch")),
                tests=Path(paths.get("tests", "tests")),
                state=Path(paths.get("state", ".research")),
                checks=tuple(data.get("checks", {}).get("commands", [])),
                archive_days=int(data.get("retention", {}).get("archive_days", 90)),
            )
        except (TypeError, ValueError) as exc:
            raise SiftError(f"Invalid configuration in {path}: {exc}") from exc

    @property
    def state_dir(self) -> Path:
        return self.root / self.state


def initialize_project(root: Path, package_name: str | None = None) -> ProjectConfig:
    config_path = root / "research.toml"
    if config_path.exists():
        raise SiftError(f"Already initialized: {config_path}")
    config_path.write_text(DEFAULT_CONFIG, encoding="utf-8", newline="\n")
    for directory in ("experiments", "scratch", "tests", ".research"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    if package_name:
        (root / "src" / package_name.replace("-", "_")).mkdir(parents=True, exist_ok=True)
    gitignore = root / ".gitignore"
    additions = [".research/runs/", ".research/proposals/", ".research/archive/"]
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    missing = [line for line in additions if line not in existing.splitlines()]
    if missing:
        with gitignore.open("a", encoding="utf-8", newline="\n") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write("\n".join(missing) + "\n")
    return ProjectConfig.load(root)
