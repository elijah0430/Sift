from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import SiftError

DEFAULT_IGNORES = {
    ".git",
    ".research",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".venv",
    "__pycache__",
    "dist",
    "build",
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise SiftError("Name must contain at least one letter or number.")
    return slug


def short_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{os.urandom(3).hex()}"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SiftError(f"Missing record: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SiftError(f"Could not read {path}: {exc}") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_files(root: Path, ignores: Iterable[str] = DEFAULT_IGNORES) -> list[Path]:
    ignored = set(ignores)
    result: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in ignored for part in relative.parts):
            continue
        if path.is_file():
            result.append(relative)
    return sorted(result, key=lambda item: item.as_posix())


def tree_hash(root: Path, ignores: Iterable[str] = DEFAULT_IGNORES) -> str:
    digest = hashlib.sha256()
    for relative in relative_files(root, ignores):
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(sha256_file(root / relative).encode())
        digest.update(b"\0")
    return digest.hexdigest()


def copy_tree(source: Path, destination: Path, ignores: Iterable[str] = DEFAULT_IGNORES) -> None:
    if destination.exists():
        raise SiftError(f"Destination already exists: {destination}")
    ignored = set(ignores)

    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in ignored}

    shutil.copytree(source, destination, ignore=ignore)


def find_project(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "research.toml").exists():
            return candidate
    raise SiftError("No research.toml found. Run `sift init` at the project root.")


def run_process(
    command: list[str] | str,
    *,
    cwd: Path,
    shell: bool = False,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> int:
    stdout_handle = stdout_path.open("w", encoding="utf-8") if stdout_path else None
    stderr_handle = stderr_path.open("w", encoding="utf-8") if stderr_path else None
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=shell,
            stdout=stdout_handle,
            stderr=stderr_handle,
            check=False,
        )
        return completed.returncode
    finally:
        if stdout_handle:
            stdout_handle.close()
        if stderr_handle:
            stderr_handle.close()


def python_runtime() -> dict[str, str]:
    return {
        "executable": sys.executable,
        "implementation": sys.implementation.name,
        "version": sys.version,
        "platform": sys.platform,
    }
