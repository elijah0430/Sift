from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from fnmatch import fnmatch
from functools import wraps
from pathlib import Path
from typing import Any

from .errors import SiftError

DEFAULT_IGNORES = {
    ".git",
    ".research",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".import_linter_cache",
    ".tach",
    ".tach_cache",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".coverage",
    "htmlcov",
    ".pytest-local*",
    ".package-smoke*",
    ".smoke*",
    ".env",
    ".env.*",
    "*.egg-info",
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
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise SiftError(f"Expected a JSON object: {path}")
        return value
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


def is_link(path: Path) -> bool:
    try:
        information = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(information.st_mode) or (
        getattr(information, "st_reparse_tag", 0)
        == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", None)
    )


def relative_files(root: Path, ignores: Iterable[str] = DEFAULT_IGNORES) -> list[Path]:
    if not root.is_dir() or is_link(root):
        raise SiftError(f"Expected a real directory, not a symlink or junction: {root}")
    ignored = tuple(ignores)

    def excluded(path: Path) -> bool:
        relative = path.relative_to(root).as_posix()
        return any(fnmatch(relative if "/" in item else path.name, item) for item in ignored)

    result: list[Path] = []
    for directory, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if not excluded(Path(directory) / name)]
        for name in [*directories, *files]:
            path = Path(directory) / name
            if excluded(path):
                continue
            if is_link(path):
                raise SiftError(f"Snapshot paths must not be symlinks or junctions: {path}")
            if path.is_file():
                result.append(path.relative_to(root))
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
    files = relative_files(source, ignores)
    destination.mkdir(parents=True)
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)


def safe_id(value: str) -> str:
    if value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise SiftError(f"Invalid record identifier: {value}")
    return value


def contained_path(root: Path, relative: str | Path) -> Path:
    relative = Path(relative)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise SiftError(f"Expected a non-empty project-relative path: {relative}")
    if any(":" in part for part in relative.parts):
        raise SiftError(f"Invalid relative path: {relative}")
    path = root
    for part in relative.parts:
        path = path / part
        if is_link(path):
            raise SiftError(f"Symlink or junction is not allowed: {path}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise SiftError(f"Path escapes its root: {relative}")
    return path


def canonical_hash(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


@contextmanager
def project_lock(state: Path):
    state.mkdir(parents=True, exist_ok=True)
    path = state / "transaction.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise SiftError(
            "A transaction is locked. Use sift doctor to inspect interrupted work."
        ) from exc
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def state_locked(function):
    @wraps(function)
    def locked(config, *args, **kwargs):
        with project_lock(config.state_dir):
            return function(config, *args, **kwargs)

    return locked


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
