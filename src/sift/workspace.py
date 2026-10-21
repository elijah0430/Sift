from __future__ import annotations

from pathlib import Path

from .config import ProjectConfig
from .errors import SiftError
from .util import contained_path, read_json, safe_id, slugify


def _directories(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    return sorted(item.name for item in path.iterdir() if item.is_dir())


def workspace_status(config: ProjectConfig) -> dict:
    run_counts: dict[str, int] = {}
    runs = config.state_dir / "runs"
    if runs.is_dir():
        for path in runs.glob("*/manifest.json"):
            status = read_json(path).get("status", "unknown")
            run_counts[status] = run_counts.get(status, 0) + 1

    proposal_counts: dict[str, int] = {}
    proposals = config.state_dir / "proposals"
    if proposals.is_dir():
        for path in proposals.glob("*/manifest.json"):
            status = read_json(path).get("status", "unknown")
            proposal_counts[status] = proposal_counts.get(status, 0) + 1

    active_runs = sum(run_counts.get(status, 0) for status in ("preparing", "running"))
    return {
        "root": str(config.root),
        "needs_review": sum(proposal_counts.get(status, 0) for status in ("ready", "applying")),
        "changes_requested": proposal_counts.get("changes_requested", 0),
        "draft_proposals": sum(
            proposal_counts.get(status, 0) for status in ("draft", "checking", "checks_failed")
        ),
        "explorations": _directories(config.root / config.scratch),
        "experiments": _directories(config.root / config.experiments),
        "runs": {
            "total": sum(run_counts.values()),
            "active": active_runs,
            "completed": run_counts.get("completed", 0),
            "failed": run_counts.get("failed", 0),
            "interrupted": run_counts.get("interrupted", 0),
        },
    }


def resolve_run(config: ProjectConfig, reference: str) -> str:
    try:
        run_id = safe_id(reference)
    except SiftError:
        run_id = ""
    if run_id and (config.state_dir / "runs" / run_id / "manifest.json").is_file():
        return run_id

    candidates = [reference, slugify(reference)]
    for relative in dict.fromkeys(candidates):
        try:
            experiment = contained_path(config.root / config.experiments, relative)
        except SiftError:
            continue
        record_path = experiment / "sift-record.json"
        if not record_path.is_file():
            continue
        run_id = read_json(record_path).get("run_id")
        if not run_id:
            raise SiftError(f"Experiment has no linked run: {reference}")
        read_json(config.state_dir / "runs" / safe_id(run_id) / "manifest.json")
        return run_id
    raise SiftError(f"Unknown experiment or run: {reference}")
