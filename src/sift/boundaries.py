from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .config import ProjectConfig


@dataclass(frozen=True)
class Violation:
    file: Path
    line: int
    imported: str
    rule: str


def _imports(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    result: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append((node.lineno, node.module))
    return result


def check_boundaries(config: ProjectConfig) -> list[Violation]:
    forbidden = {
        config.scratch.parts[0].replace("-", "_"),
        config.experiments.parts[0].replace("-", "_"),
    }
    violations: list[Violation] = []
    for relative_root in config.core:
        root = config.root / relative_root
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            for line, imported in _imports(path):
                top = imported.split(".", 1)[0]
                if top in forbidden:
                    violations.append(
                        Violation(
                            file=path.relative_to(config.root),
                            line=line,
                            imported=imported,
                            rule="core cannot import scratch or experiments",
                        )
                    )
    return violations
