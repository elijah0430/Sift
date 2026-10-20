from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

from .config import ProjectConfig
from .errors import SiftError
from .util import copy_tree, python_runtime, sha256_file, short_id, tree_hash, utc_now, write_json


def _git_metadata(root: Path) -> dict[str, object]:
    def output(*args: str) -> str | None:
        result = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    return {
        "commit": output("rev-parse", "HEAD"),
        "branch": output("branch", "--show-current"),
        "dirty": bool(output("status", "--porcelain")),
    }


def create_run(
    config: ProjectConfig,
    command: str,
    artifacts: Iterable[str] = (),
    parent: str | None = None,
    change: str | None = None,
) -> tuple[str, int]:
    run_id = short_id("run")
    run_dir = config.state_dir / "runs" / run_id
    source = run_dir / "source"
    run_dir.mkdir(parents=True)
    copy_tree(config.root, source)
    started = utc_now()
    stdout = run_dir / "stdout.log"
    stderr = run_dir / "stderr.log"
    completed = subprocess.run(
        command,
        cwd=source,
        shell=True,
        text=True,
        stdout=stdout.open("w", encoding="utf-8"),
        stderr=stderr.open("w", encoding="utf-8"),
        check=False,
    )
    registered: list[dict[str, str]] = []
    artifact_dir = run_dir / "artifacts"
    for value in artifacts:
        source_path = (source / value).resolve()
        try:
            relative = source_path.relative_to(source.resolve())
        except ValueError as exc:
            raise SiftError(f"Artifact must be inside the project: {value}") from exc
        if not source_path.exists() or not source_path.is_file():
            raise SiftError(f"Artifact was not produced: {value}")
        destination = artifact_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        registered.append({"path": relative.as_posix(), "sha256": sha256_file(destination)})
    manifest = {
        "schema": 1,
        "id": run_id,
        "status": "completed" if completed.returncode == 0 else "failed",
        "started_at": started,
        "finished_at": utc_now(),
        "command": command,
        "exit_code": completed.returncode,
        "parent": parent,
        "change": change,
        "source_hash": tree_hash(source),
        "git": _git_metadata(config.root),
        "runtime": python_runtime(),
        "environment": {
            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
        },
        "artifacts": registered,
        "replay_verified": False,
    }
    write_json(run_dir / "manifest.json", manifest)
    return run_id, completed.returncode


def replay_run(config: ProjectConfig, run_id: str) -> tuple[str, int, bool]:
    original = config.state_dir / "runs" / run_id
    manifest_path = original / "manifest.json"
    if not manifest_path.exists():
        raise SiftError(f"Unknown run: {run_id}")
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    replay_id = short_id("replay")
    replay_dir = config.state_dir / "replays" / replay_id
    source = replay_dir / "source"
    replay_dir.mkdir(parents=True)
    copy_tree(original / "source", source)
    completed = subprocess.run(
        manifest["command"],
        cwd=source,
        shell=True,
        stdout=(replay_dir / "stdout.log").open("w", encoding="utf-8"),
        stderr=(replay_dir / "stderr.log").open("w", encoding="utf-8"),
        check=False,
    )
    matches = completed.returncode == manifest["exit_code"]
    artifact_results: list[dict[str, object]] = []
    for artifact in manifest.get("artifacts", []):
        path = source / artifact["path"]
        same = path.is_file() and sha256_file(path) == artifact["sha256"]
        matches = matches and same
        artifact_results.append({"path": artifact["path"], "matches": same})
    write_json(
        replay_dir / "manifest.json",
        {
            "schema": 1,
            "id": replay_id,
            "original_run": run_id,
            "created_at": utc_now(),
            "exit_code": completed.returncode,
            "exact_match": matches,
            "artifacts": artifact_results,
        },
    )
    if matches:
        manifest["replay_verified"] = True
        manifest["last_verified_at"] = utc_now()
        write_json(manifest_path, manifest)
    return replay_id, completed.returncode, matches
