"""Validate and publish an isolated agent session's experiment history."""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import ProjectConfig
from .errors import SiftError
from .lifecycle import preserve
from .portability import import_run, validate_run
from .promotion import _initialize_review_repository, _protected_hash, _validate_seal, seal
from .util import (
    contained_path,
    copy_file,
    copy_tree,
    project_lock,
    read_json,
    safe_id,
    tree_hash,
    write_json,
)


def _validate_run(path: Path, expected_id: str | None = None) -> dict:
    return validate_run(path, expected_id or path.name)


def seed_research(config: ProjectConfig, candidate: Path) -> list[str]:
    """Give the session its own validated copies of existing finalized run history."""
    isolated = ProjectConfig.load(candidate)
    identifiers = []
    for path in sorted((config.state_dir / "runs").glob("*/manifest.json")):
        record = read_json(path)
        if record.get("status") in {"completed", "failed", "interrupted"}:
            run_id, _ = import_run(isolated, path.parent)
            identifiers.append(run_id)
            for item in record.get("inputs", []):
                relative = item.get("source_relative")
                if not relative:
                    continue
                source = contained_path(config.root, relative)
                target = contained_path(candidate, relative)
                if target.exists() or not source.exists():
                    continue
                # Carry current declared data, rather than substituting the old captured version.
                if source.is_dir():
                    copy_tree(source, target, ignores=())
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    copy_file(source, target)
    return identifiers


def _publish_proposals(config: ProjectConfig, isolated: ProjectConfig) -> list[dict]:
    imported = []
    for path in sorted((isolated.state_dir / "proposals").glob("*/manifest.json")):
        record = read_json(path)
        if record.get("status") not in {"draft", "ready", "checks_failed", "changes_requested"}:
            continue
        identifier = safe_id(record["id"])
        source = contained_path(isolated.state_dir / "proposals", identifier)
        if record.get("status") == "ready":
            _validate_seal(isolated, source, record)
        base_config = ProjectConfig.load(source / "base")
        if _protected_hash(base_config) != _protected_hash(config):
            raise SiftError(
                f"Core changed since agent proposal {identifier} began. "
                f"Rebase its candidate at {source / 'candidate'} before requesting review."
            )
        if tree_hash(source / "base", ignores=()) != record["base_tree_hash"]:
            raise SiftError(f"Agent proposal reference snapshot is corrupted: {identifier}")
        destination = config.state_dir / "proposals" / identifier
        with project_lock(config.state_dir):
            if destination.exists():
                existing = read_json(destination / "manifest.json")
                if existing.get("imported_digest") == record.get("digest") and existing.get(
                    "imported_from"
                ) == str(source):
                    continue
                raise SiftError(f"Proposal ID collision: {identifier}")
            staging = config.state_dir / f"incoming-{identifier}"
            staging.mkdir()
            try:
                copy_tree(source / "base", staging / "base", ignores=())
                copy_tree(source / "candidate", staging / "candidate", isolated.snapshot_ignores)
                if tree_hash(staging / "candidate", ignores=()) != tree_hash(
                    source / "candidate", isolated.snapshot_ignores
                ):
                    raise SiftError("Agent proposal changed during import.")
                manifest = {
                    key: record[key]
                    for key in (
                        "schema",
                        "id",
                        "title",
                        "rationale",
                        "baseline_run",
                        "run_refs",
                        "created_at",
                        "base_tree_hash",
                    )
                }
                manifest.update(
                    status="draft",
                    protected_hash=_protected_hash(config),
                    review_repository=_initialize_review_repository(staging / "candidate"),
                    imported_from=str(source),
                    imported_digest=record.get("digest"),
                )
                write_json(staging / "manifest.json", manifest)
                staging.rename(destination)
            except BaseException:
                shutil.rmtree(staging)
                raise
        # New checks, diff, and seal are produced in the receiving project. No approval is copied.
        if record.get("status") in {"ready", "checks_failed"}:
            seal(config, identifier, tuple(record.get("check_commands", ())))
        summary = read_json(destination / "manifest.json")
        imported.append({"id": identifier, "title": summary["title"], "status": summary["status"]})
    return imported


def publish_research(config: ProjectConfig, candidate: Path) -> dict:
    """Import history and unapproved proposals; never apply core or transfer approvals."""
    isolated = ProjectConfig.load(candidate)
    if isolated.scratch != config.scratch or isolated.experiments != config.experiments:
        raise SiftError("Review research directory changes before publishing agent experiments.")
    report: dict[str, list] = {"runs": [], "experiments": [], "pending_runs": [], "proposals": []}
    for manifest_path in sorted((isolated.state_dir / "runs").glob("*/manifest.json")):
        record = read_json(manifest_path)
        run_id = safe_id(record["id"])
        if record.get("status") not in {"completed", "failed", "interrupted"}:
            report["pending_runs"].append(run_id)
            continue
        source = contained_path(isolated.state_dir / "runs", run_id)
        _, created = import_run(config, source)
        if created:
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
    report["proposals"] = _publish_proposals(config, isolated)
    return report
