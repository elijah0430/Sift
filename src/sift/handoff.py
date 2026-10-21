"""Validate and publish an isolated agent session's experiment history."""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import ProjectConfig
from .errors import SiftError
from .lifecycle import preserve
from .util import (
    contained_path,
    copy_tree,
    project_lock,
    read_json,
    safe_id,
    sha256_file,
    tree_hash,
)


def _validate_run(path: Path, expected_id: str | None = None) -> dict:
    manifest = read_json(path / "manifest.json")
    if safe_id(manifest["id"]) != (expected_id or path.name):
        raise SiftError("Agent run ID does not match its directory.")
    if manifest.get("source_hash"):
        if tree_hash(path / "source", ignores=()) != manifest["source_hash"]:
            raise SiftError(f"Agent source snapshot is corrupted: {path.name}")
    elif manifest.get("status") == "completed" or manifest.get("artifacts"):
        raise SiftError(f"Agent run has no source snapshot hash: {path.name}")
    for item in manifest.get("artifacts", []):
        output = contained_path(path / "artifacts", item["path"])
        if not output.is_file() or sha256_file(output) != item["sha256"]:
            raise SiftError(f"Agent artifact is corrupted: {item['path']}")
    for item in manifest.get("inputs", []):
        if not item.get("captured"):
            continue
        source = contained_path(path, item["captured"])
        digest = tree_hash(source, ignores=()) if source.is_dir() else sha256_file(source)
        if digest != item["sha256"]:
            raise SiftError(f"Agent input is corrupted: {item['name']}")
    return manifest


def publish_research(config: ProjectConfig, candidate: Path) -> dict:
    """Copy finalized runs and their saved experiments, never core or approval files."""
    isolated = ProjectConfig.load(candidate)
    if isolated.scratch != config.scratch or isolated.experiments != config.experiments:
        raise SiftError("Review research directory changes before publishing agent experiments.")
    report: dict[str, list] = {"runs": [], "experiments": [], "pending_runs": []}
    for manifest_path in sorted((isolated.state_dir / "runs").glob("*/manifest.json")):
        record = read_json(manifest_path)
        run_id = safe_id(record["id"])
        if record.get("status") not in {"completed", "failed", "interrupted"}:
            report["pending_runs"].append(run_id)
            continue
        source = contained_path(isolated.state_dir / "runs", run_id)
        _validate_run(source)
        destination = contained_path(config.state_dir / "runs", run_id)
        with project_lock(config.state_dir):
            if destination.exists():
                if tree_hash(source, ignores=("work/*",)) != tree_hash(
                    destination, ignores=("work/*",)
                ):
                    raise SiftError(f"Run ID collision while importing agent history: {run_id}")
                continue
            staging = contained_path(config.state_dir, f"incoming-{run_id}")
            if staging.exists():
                raise SiftError(f"An interrupted import exists: {staging}")
            try:
                copy_tree(source, staging, ignores=("work/*",))
                _validate_run(staging, run_id)
                if tree_hash(staging, ignores=()) != tree_hash(source, ignores=("work/*",)):
                    raise SiftError("Agent run changed during import.")
                destination.parent.mkdir(parents=True, exist_ok=True)
                staging.rename(destination)
            except BaseException:
                if staging.exists():
                    shutil.rmtree(staging)
                raise
        report["runs"].append(run_id)

    for record_path in (candidate / isolated.experiments).rglob("sift-record.json"):
        record = read_json(record_path)
        run_id = record.get("run_id")
        if (
            not run_id
            or not (config.state_dir / "runs" / safe_id(run_id) / "manifest.json").is_file()
        ):
            continue
        source_relative = Path(record["source"])
        if not source_relative.is_relative_to(isolated.scratch):
            raise SiftError("Saved agent experiment source must be inside scratch.")
        scratch_name = source_relative.relative_to(isolated.scratch).as_posix()
        name = record_path.parent.relative_to(candidate / isolated.experiments).as_posix()
        destination = contained_path(config.root / config.experiments, name)
        if destination.exists():
            existing = destination / "sift-record.json"
            if existing.is_file() and read_json(existing).get("run_id") == run_id:
                continue
            name = f"{name}-{run_id.rsplit('-', 1)[-1]}"
        saved = preserve(config, scratch_name, name, run_id)
        report["experiments"].append(saved.relative_to(config.root).as_posix())
    return report
