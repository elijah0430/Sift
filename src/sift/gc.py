from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta

from .config import ProjectConfig
from .errors import SiftError
from .util import (
    canonical_hash,
    contained_path,
    project_lock,
    read_json,
    safe_id,
    sha256_file,
    short_id,
    tree_hash,
    utc_now,
    write_json,
)


def _pins(config: ProjectConfig) -> set[str]:
    path = config.state_dir / "pins.json"
    return set(read_json(path).get("ids", [])) if path.exists() else set()


def set_pin(config: ProjectConfig, identifier: str, pinned: bool) -> None:
    safe_id(identifier)
    with project_lock(config.state_dir):
        values = _pins(config)
        values.add(identifier) if pinned else values.discard(identifier)
        write_json(config.state_dir / "pins.json", {"ids": sorted(values)})


def references(config: ProjectConfig) -> set[str]:
    result = _pins(config)
    paths = list((config.root / config.experiments).rglob("sift-record.json"))
    for category in ("runs", "replays", "proposals"):
        paths.extend((config.state_dir / category).glob("*/manifest.json"))
    for path in paths:
        record = read_json(path)
        for key in ("run_id", "parent", "parent_run", "original_run"):
            if record.get(key):
                result.add(record[key])
        result.update(record.get("archive_refs", []))
        result.update(record.get("run_refs", []))
        if record.get("status") in {
            "preparing",
            "running",
            "checking",
            "draft",
            "ready",
            "applying",
        }:
            result.add(record["id"])
    entries = config.state_dir / "cache" / "entries"
    for path in entries.glob("*.json"):
        entry = read_json(path)
        result.add(entry["sha256"])
    return result


def _eligible(timestamp: str, days: int, now: datetime) -> bool:
    return datetime.fromisoformat(timestamp) <= now - timedelta(days=days)


def plan(config: ProjectConfig, now: datetime | None = None) -> tuple[str, str, list[dict]]:
    now = now or datetime.now(UTC)
    retained = references(config)
    candidates = []
    for category, timestamp in (("archive", "archived_at"), ("runs", "finished_at")):
        for directory in sorted((config.state_dir / category).glob("*")):
            manifest_path = directory / "manifest.json"
            if not manifest_path.exists() or directory.name in retained:
                continue
            record = read_json(manifest_path)
            if record.get(timestamp) and _eligible(record[timestamp], config.archive_days, now):
                candidates.append(
                    {
                        "kind": category,
                        "id": directory.name,
                        "relative_path": directory.relative_to(config.root).as_posix(),
                        "tree_hash": tree_hash(directory, ignores=()),
                    }
                )
    for path in sorted((config.state_dir / "cache" / "objects").glob("*")):
        if path.is_file() and path.name not in retained:
            candidates.append(
                {
                    "kind": "cache-object",
                    "id": path.name,
                    "relative_path": path.relative_to(config.root).as_posix(),
                    "tree_hash": sha256_file(path),
                }
            )
    plan_id = short_id("gc")
    digest = canonical_hash(candidates)
    write_json(
        config.state_dir / "gc" / plan_id / "plan.json",
        {
            "schema": 1,
            "id": plan_id,
            "created_at": utc_now(),
            "retention_days": config.archive_days,
            "digest": digest,
            "candidates": candidates,
            "status": "planned",
        },
    )
    return plan_id, digest, candidates


def apply(config: ProjectConfig, plan_id: str, confirmation: str) -> int:
    with project_lock(config.state_dir):
        path = config.state_dir / "gc" / safe_id(plan_id) / "plan.json"
        record = read_json(path)
        if record["status"] not in {"planned", "applying"}:
            raise SiftError("GC plan has already been applied.")
        if canonical_hash(record["candidates"]) != record["digest"]:
            raise SiftError("GC plan changed after review.")
        if confirmation != record["digest"][:12]:
            raise SiftError("GC confirmation did not match the reviewed plan digest.")
        if config.archive_days != record["retention_days"]:
            raise SiftError("Retention policy changed; prepare a new cleanup plan.")
        retained = references(config)
        targets = []
        for item in record["candidates"]:
            if item["id"] in retained:
                raise SiftError(f"GC target gained a pin or reference: {item['id']}")
            target = contained_path(config.root, item["relative_path"])
            category = {"archive": "archive", "runs": "runs", "cache-object": "cache/objects"}.get(
                item["kind"]
            )
            if not category or target.parent != (config.state_dir / category).resolve():
                raise SiftError(f"Unsafe GC target: {target}")
            if not target.exists() and record["status"] == "applying":
                continue
            actual = (
                tree_hash(target, ignores=())
                if target.is_dir()
                else (sha256_file(target) if target.is_file() else None)
            )
            if actual != item["tree_hash"]:
                raise SiftError(f"GC target changed after planning: {item['id']}")
            targets.append(target)
        record["status"] = "applying"
        write_json(path, record)
        for target in targets:
            shutil.rmtree(target) if target.is_dir() else target.unlink()
        record.update(status="applied", applied_at=utc_now())
        write_json(path, record)
        return len(targets)
