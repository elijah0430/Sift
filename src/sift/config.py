from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import SiftError
from .util import DEFAULT_IGNORES, contained_path

PROTECTED_FILES = (
    "research.toml",
    "pyproject.toml",
    "uv.lock",
    "requirements.txt",
    "environment.yml",
    "poetry.lock",
    "Dockerfile",
    ".python-version",
    "AGENTS.md",
)

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
    ignores: tuple[str, ...] = ()
    public_api: tuple[str, ...] = ()
    independent: tuple[str, ...] = ()
    acyclic: bool = True
    boundary_engine: str = "builtin"

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
            config = cls(
                root=root,
                core=tuple(Path(value) for value in core_values),
                experiments=Path(paths.get("experiments", "experiments")),
                scratch=Path(paths.get("scratch", "scratch")),
                tests=Path(paths.get("tests", "tests")),
                state=Path(paths.get("state", ".research")),
                checks=tuple(data.get("checks", {}).get("commands", [])),
                archive_days=int(data.get("retention", {}).get("archive_days", 90)),
                ignores=tuple(data.get("snapshot", {}).get("ignore", [])),
                public_api=tuple(data.get("boundaries", {}).get("public_api", [])),
                independent=tuple(data.get("boundaries", {}).get("independent", [])),
                acyclic=bool(data.get("boundaries", {}).get("acyclic", True)),
                boundary_engine=data.get("boundaries", {}).get("engine", "builtin"),
            )
            configured = [
                *config.core,
                config.experiments,
                config.scratch,
                config.tests,
                config.state,
            ]
            for relative in configured:
                if relative == Path("."):
                    raise SiftError("Configured directories must not be the project root.")
                contained_path(root, relative)
            for index, left in enumerate(configured):
                for right in configured[index + 1 :]:
                    if left == right or left in right.parents or right in left.parents:
                        raise SiftError(f"Configured paths overlap: {left} and {right}")
            if config.archive_days < 0:
                raise SiftError("archive_days must be nonnegative.")
            if config.boundary_engine not in {"builtin", "import-linter", "tach"}:
                raise SiftError("Boundary engine must be builtin, import-linter, or tach.")
            return config
        except (TypeError, ValueError) as exc:
            raise SiftError(f"Invalid configuration in {path}: {exc}") from exc

    @property
    def state_dir(self) -> Path:
        return self.root / self.state

    @property
    def snapshot_ignores(self) -> set[str]:
        return {*DEFAULT_IGNORES, self.state.as_posix(), *self.ignores}

    def check_output_destination(self, destination: Path) -> None:
        target = destination.resolve()
        protected = [
            *self.core,
            self.tests,
            self.experiments,
            Path(".git"),
            *(Path(name) for name in PROTECTED_FILES),
        ]
        if any(target.is_relative_to((self.root / path).resolve()) for path in protected):
            raise SiftError("Writes to maintained code or policy require a reviewed promotion.")
        if target.is_relative_to(self.state_dir.resolve()):
            parts = target.relative_to(self.state_dir.resolve()).parts
            if not (len(parts) >= 3 and parts[0] == "proposals" and parts[2] == "candidate"):
                raise SiftError(
                    "This destination is protected Sift state, not a candidate workspace."
                )


def initialize_project(root: Path, package_name: str | None = None) -> ProjectConfig:
    root.mkdir(parents=True, exist_ok=True)
    if package_name and not package_name.replace("-", "_").isidentifier():
        raise SiftError("Package name must be a Python identifier.")
    config_path = root / "research.toml"
    if config_path.exists():
        raise SiftError(f"Already initialized: {config_path}")
    config_path.write_text(DEFAULT_CONFIG, encoding="utf-8", newline="\n")
    for directory in ("experiments", "scratch", "tests", ".research"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    if package_name:
        (root / "src" / package_name.replace("-", "_")).mkdir(parents=True, exist_ok=True)
    gitignore = root / ".gitignore"
    additions = [".research/"]
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    missing = [line for line in additions if line not in existing.splitlines()]
    if missing:
        with gitignore.open("a", encoding="utf-8", newline="\n") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write("\n".join(missing) + "\n")
    return ProjectConfig.load(root)
