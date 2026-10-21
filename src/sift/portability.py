"""Validated transport of experiment runs between projects and agent workspaces."""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import ProjectConfig
from .errors import SiftError
from .util import (
    contained_path,
    copy_file,
    copy_tree,
    fs_path,
    project_lock,
    read_json,
    safe_id,
    sha256_file,
    tree_hash,
)


def validate_run(path: Path, expected_id: str | None = None) -> dict:
    manifest = read_json(path / "manifest.json")
    run_id = safe_id(manifest["id"])
    if expected_id and run_id != expected_id:
        raise SiftError("Run ID does not match its directory.")
    if manifest.get("status") not in {"completed", "failed", "interrupted"}:
        raise SiftError(f"Run is still active: {run_id}")
    if manifest.get("source_hash"):
        if tree_hash(path / "source", ignores=()) != manifest["source_hash"]:
            raise SiftError(f"Run source snapshot is corrupted: {run_id}")
    elif manifest.get("status") == "completed" or manifest.get("artifacts"):
        raise SiftError(f"Run has no source snapshot hash: {run_id}")
    for item in manifest.get("artifacts", []):
        output = contained_path(path / "artifacts", item["path"])
        if not output.is_file() or sha256_file(output) != item["sha256"]:
            raise SiftError(f"Run artifact is corrupted: {item['path']}")
    for item in manifest.get("inputs", []):
        if not item.get("captured"):
            continue
        source = contained_path(path, item["captured"])
        digest = tree_hash(source, ignores=()) if source.is_dir() else sha256_file(source)
        if digest != item["sha256"]:
            raise SiftError(f"Run input is corrupted: {item['name']}")
    return manifest


def import_run(config: ProjectConfig, source: Path) -> tuple[str, bool]:
    """Import immutable history, without a work copy, approvals, or project code writes."""
    source = fs_path(source)
    record = validate_run(source)
    run_id = record["id"]
    destination = config.state_dir / "runs" / run_id
    # Only canonical run records are compared: bundles may also carry a README.
    parts = [
        "manifest.json",
        "source",
        "inputs",
        "artifacts",
        "stdout.log",
        "stderr.log",
        "environment.log",
        "managed-environment.json",
        "process.json",
        "verify.stdout.log",
        "verify.stderr.log",
    ]

    def signature(path: Path) -> dict:
        return {
            name: tree_hash(path / name, ignores=())
            if (path / name).is_dir()
            else sha256_file(path / name)
            for name in parts
            if (path / name).exists()
        }

    with project_lock(config.state_dir):
        if destination.exists():
            validate_run(destination, run_id)
            if signature(source) != signature(destination):
                raise SiftError(f"Run ID collision while importing history: {run_id}")
            return run_id, False
        staging = config.state_dir / f"incoming-{run_id}"
        if staging.exists():
            raise SiftError(f"An interrupted import exists: {staging}")
        staging.mkdir()
        try:
            for name in parts:
                item = source / name
                if item.is_dir():
                    copy_tree(item, staging / name, ignores=())
                elif item.is_file():
                    copy_file(item, staging / name)
            validate_run(staging, run_id)
            if signature(source) != signature(staging):
                raise SiftError("Run changed during import.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging.rename(destination)
        except BaseException:
            shutil.rmtree(staging)
            raise
    return run_id, True
