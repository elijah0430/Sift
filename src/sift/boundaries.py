from __future__ import annotations

import ast
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import ProjectConfig
from .util import relative_files


@dataclass(frozen=True)
class Violation:
    file: Path
    line: int
    imported: str
    rule: str


def run_boundary_engine(config: ProjectConfig, engine: str | None = None) -> dict | None:
    selected = engine or config.boundary_engine
    if selected == "builtin":
        return None
    from .snapshots import execution_environment

    command = {"import-linter": ["lint-imports"], "tach": ["tach", "check"]}.get(selected)
    if not command:
        raise ValueError(f"Unknown boundary engine: {selected}")
    env = execution_environment(config, config.root)
    executable = shutil.which(command[0], path=env.get("PATH"))
    if not executable:
        from .errors import SiftError

        raise SiftError(f"Install the optional {selected} tool in the selected environment.")
    command[0] = executable
    result = subprocess.run(
        command,
        cwd=config.root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": " ".join(command),
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _module(path: Path, config: ProjectConfig) -> str:
    for core in config.core:
        if path.is_relative_to(core):
            if path == core and path.suffix == ".py":
                path = Path(path.name)
            elif (config.root / core / "__init__.py").is_file():
                path = path.relative_to(core.parent)
            else:
                path = path.relative_to(core)
            break
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(part.replace("-", "_") for part in parts)


def _imports(path: Path, module: str = "") -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = []
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = node.module or ""
            if node.level:
                parents = package.split(".") if package else []
                parents = parents[: len(parents) - node.level + 1]
                prefix = ".".join([*parents, *([prefix] if prefix else [])])
            result.append((node.lineno, prefix))
            result.extend(
                (node.lineno, f"{prefix}.{alias.name}".strip("."))
                for alias in node.names
                if alias.name != "*"
            )
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            function = node.func
            name = (
                function.id
                if isinstance(function, ast.Name)
                else (function.attr if isinstance(function, ast.Attribute) else "")
            )
            if name in {"__import__", "import_module"} and isinstance(node.args[0].value, str):
                result.append((node.lineno, node.args[0].value))
    return result


def dependency_graph(config: ProjectConfig) -> tuple[dict, list[Violation]]:
    graph = {}
    violations = []
    for relative in relative_files(config.root, config.snapshot_ignores):
        if relative.suffix != ".py":
            continue
        module = _module(relative, config)
        try:
            imports = _imports(config.root / relative, module)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            violations.append(
                Violation(
                    relative,
                    getattr(exc, "lineno", 1) or 1,
                    "",
                    f"cannot analyze Python source: {exc}",
                )
            )
            graph[module] = {"path": relative, "imports": [], "analysis_error": str(exc)}
            continue
        graph[module] = {"path": relative, "imports": imports}
    return graph, violations


def _under(value: str, prefix: str) -> bool:
    return value == prefix or value.startswith(prefix + ".")


def check_boundaries(config: ProjectConfig) -> list[Violation]:
    graph, errors = dependency_graph(config)
    violations = [
        item
        for item in errors
        if any(item.file.is_relative_to(path) for path in (*config.core, config.experiments))
    ]
    scratch = ".".join(config.scratch.parts).replace("-", "_")
    experiments = ".".join(config.experiments.parts).replace("-", "_")
    core_modules = {
        module
        for module, node in graph.items()
        if any(node["path"].is_relative_to(path) for path in config.core)
    }
    for module, node in graph.items():
        own_scratch = ".".join(module.split(".")[: len(scratch.split(".")) + 1])
        own_experiment = ".".join(module.split(".")[: len(experiments.split(".")) + 1])
        for line, imported in node["imports"]:
            rule = None
            if module in core_modules and (
                _under(imported, scratch) or _under(imported, experiments)
            ):
                rule = "core cannot import scratch or experiments"
            elif _under(module, experiments) and _under(imported, scratch):
                rule = "maintained experiments cannot depend on scratch"
            elif (
                _under(module, scratch)
                and _under(imported, scratch)
                and imported != scratch
                and not _under(imported, own_scratch)
            ):
                rule = "scratch explorations cannot import each other"
            elif (
                _under(module, experiments)
                and _under(imported, experiments)
                and imported != experiments
                and not _under(imported, own_experiment)
            ):
                rule = "experiments cannot import each other"
            if config.public_api and module not in core_modules:
                if any(_under(imported, core_module) for core_module in core_modules) and not any(
                    _under(imported, public) or _under(public, imported)
                    for public in config.public_api
                ):
                    rule = "import is outside the declared public API"
            if rule:
                violation = Violation(node["path"], line, imported, rule)
                if violation not in violations:
                    violations.append(violation)
    for start in core_modules:
        pending = [(start, [])]
        seen = set()
        while pending:
            current, trail = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            if graph.get(current, {}).get("analysis_error") and current != start:
                violations.append(
                    Violation(
                        graph[start]["path"],
                        1,
                        current,
                        "core dependency has invalid Python source",
                    )
                )
            for line, imported in graph.get(current, {}).get("imports", []):
                chain = [*trail, imported]
                if config.acyclic and imported == start and current != start:
                    violations.append(
                        Violation(
                            graph[start]["path"],
                            line,
                            " -> ".join([start, *chain]),
                            "core dependency cycle",
                        )
                    )
                source_group = next(
                    (group for group in config.independent if _under(start, group)),
                    None,
                )
                target_group = next(
                    (group for group in config.independent if _under(imported, group)),
                    None,
                )
                if source_group and target_group and source_group != target_group:
                    violations.append(
                        Violation(
                            graph[start]["path"],
                            line,
                            imported,
                            "core modules declared independent depend on each other",
                        )
                    )
                if current != start and (
                    _under(imported, scratch) or _under(imported, experiments)
                ):
                    violations.append(
                        Violation(
                            graph[start]["path"],
                            line,
                            " -> ".join(chain),
                            "core cannot indirectly import scratch or experiments",
                        )
                    )
                if imported in graph:
                    pending.append((imported, chain))
    unique = {}
    for violation in violations:
        unique.setdefault((violation.file, violation.line, violation.rule), violation)
    return list(unique.values())
