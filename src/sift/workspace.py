from __future__ import annotations

import json
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
    proposal_items = []
    proposals = config.state_dir / "proposals"
    if proposals.is_dir():
        for path in proposals.glob("*/manifest.json"):
            record = read_json(path)
            if record.get("agent_session"):
                continue
            status = record.get("status", "unknown")
            proposal_counts[status] = proposal_counts.get(status, 0) + 1
            if status in {
                "draft",
                "checking",
                "ready",
                "applying",
                "changes_requested",
                "checks_failed",
            }:
                proposal_items.append(
                    {"id": record["id"], "title": record["title"], "status": status}
                )

    active_runs = sum(run_counts.get(status, 0) for status in ("preparing", "running"))
    return {
        "root": str(config.root),
        "needs_review": sum(proposal_counts.get(status, 0) for status in ("ready", "applying")),
        "changes_requested": proposal_counts.get("changes_requested", 0),
        "checks_failed": proposal_counts.get("checks_failed", 0),
        "proposals": proposal_items,
        "draft_proposals": sum(proposal_counts.get(status, 0) for status in ("draft", "checking")),
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
    matches = set()
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
        if not (config.state_dir / "runs" / safe_id(run_id) / "manifest.json").is_file():
            raise SiftError(
                f"Saved experiment '{reference}' needs its original run data ({run_id}).\n"
                f"In the original project: sift experiment export {run_id} BUNDLE\n"
                "Here: sift experiment import BUNDLE\n"
                "To extend saved code with current inputs: "
                f"sift experiment new NAME --from-run {reference}"
            )
        matches.add(run_id)
    run_root = config.state_dir / "runs"
    matches.update(
        path.parent.name
        for path in run_root.glob("*/manifest.json")
        if path.parent.name.startswith(reference)
        or (
            reference.startswith("run-")
            and path.parent.name.rsplit("-", 1)[-1].startswith(reference[4:])
        )
    )
    if len(matches) == 1:
        return next(iter(matches))
    if matches:
        raise SiftError("Ambiguous run reference; use one of: " + ", ".join(sorted(matches)))
    raise SiftError(
        f"Unknown experiment or run: {reference}. Run sift experiment list to find its ID."
    )


def run_aliases(config: ProjectConfig) -> dict[str, str]:
    identifiers = [path.parent.name for path in (config.state_dir / "runs").glob("*/manifest.json")]
    aliases = {}
    for identifier in identifiers:
        suffix = identifier.rsplit("-", 1)[-1]
        aliases[identifier] = (
            f"run-{suffix}"
            if sum(item.rsplit("-", 1)[-1] == suffix for item in identifiers) == 1
            and not (config.root / config.experiments / f"run-{suffix}").exists()
            else identifier
        )
    return aliases


def _flatten_json(value: object, prefix: str = "") -> dict[str, object]:
    if isinstance(value, dict):
        flattened: dict[str, object] = {}
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_json(child, name))
        return flattened
    if isinstance(value, list):
        if all(item is None or isinstance(item, (str, int, float, bool)) for item in value):
            return {prefix: value}
        return {}
    if value is None or isinstance(value, (str, int, float, bool)):
        return {prefix: value}
    return {}


def _preserved_run_names(config: ProjectConfig) -> dict[str, list[str]]:
    names: dict[str, list[str]] = {}
    root = config.root / config.experiments
    if not root.is_dir():
        return names
    for record_path in root.rglob("sift-record.json"):
        record = read_json(record_path)
        run_id = record.get("run_id")
        if not run_id:
            continue
        name = record_path.parent.relative_to(root).as_posix()
        names.setdefault(run_id, []).append(name)
    return names


def _run_values(config: ProjectConfig, manifest: dict, preserved: dict[str, list[str]]) -> dict:
    run_id = manifest["id"]
    values: dict[str, object] = {
        "run": run_id,
        "scratch": manifest.get("exploration") or "",
        "experiment": ",".join(sorted(preserved.get(run_id, []))),
        "status": manifest.get("status", "unknown"),
        "parent": manifest.get("parent") or "",
        "seed": ",".join(map(str, manifest.get("seeds", []))),
    }
    for name, value in sorted(manifest.get("metadata", {}).items()):
        values[f"metadata.{name}"] = value
    for item in manifest.get("inputs", []):
        values[f"input.{item['name']}"] = item.get("value", "")
        values[f"input_sha256.{item['name']}"] = item.get("sha256")
    run_dir = config.state_dir / "runs" / safe_id(run_id)
    for artifact in manifest.get("artifacts", []):
        relative = artifact.get("path", "")
        path = contained_path(run_dir / "artifacts", relative)
        if path.suffix.lower() != ".json" or not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        artifact_name = Path(relative).with_suffix("").as_posix()
        for name, value in _flatten_json(content).items():
            key = f"result.{artifact_name}" + (f".{name}" if name else "")
            values[key] = value
    return values


def experiment_runs(
    config: ProjectConfig,
    references: tuple[str, ...] = (),
    limit: int | None = None,
) -> dict:
    """Return comparable, researcher-facing rows for experiment runs."""
    run_root = config.state_dir / "runs"
    if references:
        manifests = [
            read_json(run_root / resolve_run(config, item) / "manifest.json") for item in references
        ]
    elif run_root.is_dir():
        records = [
            (path.stat().st_mtime_ns, read_json(path)) for path in run_root.glob("*/manifest.json")
        ]
        records.sort(key=lambda item: (item[1].get("started_at", ""), item[0]), reverse=True)
        manifests = [manifest for _, manifest in records]
    else:
        manifests = []
    if limit is not None:
        if limit < 1:
            raise SiftError("Experiment list limit must be at least 1.")
        manifests = manifests[:limit]

    preserved = _preserved_run_names(config)
    rows = [_run_values(config, manifest, preserved) for manifest in manifests]
    fixed = ["run", "scratch", "experiment", "status", "parent", "seed"]
    dynamic = sorted(
        {key for row in rows for key in row if key not in fixed},
        key=lambda key: (
            {"metadata": 0, "input": 1, "input_sha256": 2, "result": 3}.get(
                key.split(".", 1)[0], 4
            ),
            key,
        ),
    )
    warnings = []
    for key in (key for key in dynamic if key.startswith("input.")):
        hash_key = "input_sha256." + key[6:]
        hashes_by_path: dict[str, set[str]] = {}
        for row in rows:
            if row.get(hash_key):
                hashes_by_path.setdefault(str(row.get(key)), set()).add(str(row[hash_key]))
        if any(len(hashes) > 1 for hashes in hashes_by_path.values()):
            warnings.append(f"Input {key[6:]} changed: the same path contains different data.")
    return {
        "columns": [*fixed, *dynamic],
        "rows": rows,
        "history_count": len(manifests),
        "saved_experiments": [
            {"name": name, "run": run_id} for run_id, names in preserved.items() for name in names
        ],
        "aliases": run_aliases(config),
        "warnings": warnings,
    }


def compare_experiments(config: ProjectConfig, references: tuple[str, ...]) -> dict:
    if len(references) < 2:
        raise SiftError("Compare at least two experiment runs.")
    return experiment_runs(config, references)


def select_runs(
    table: dict,
    columns: str | None = None,
    where: tuple[str, ...] = (),
    sort: str | None = None,
    descending: bool = False,
    limit: int | None = None,
) -> dict:
    """Select columns and rows without changing the underlying run records."""
    available = table["columns"]

    def column(name: str) -> str:
        if name in available:
            return name
        for prefix in ("metadata.", "input."):
            if prefix + name in available:
                return prefix + name
        matches = [key for key in available if key.rsplit(".", 1)[-1] == name]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise SiftError(f"Ambiguous column '{name}'; use one of: {', '.join(matches)}")
        raise SiftError(f"Unknown column '{name}'. Available: {', '.join(available)}")

    rows = list(table["rows"])
    for expression in where:
        if "=" not in expression:
            raise SiftError("Expected --where COLUMN=VALUE.")
        name, value = expression.split("=", 1)
        key = column(name)
        rows = [
            row
            for row in rows
            if str(row.get(key, "")) == value
            or (key == "run" and table.get("aliases", {}).get(row.get(key)) == value)
        ]
    if sort:
        key = column(sort)
        present = [row for row in rows if row.get(key) is not None]
        missing = [row for row in rows if row.get(key) is None]
        numeric = all(isinstance(row[key], (int, float)) for row in present)
        rows = (
            sorted(
                present, key=lambda row: row[key] if numeric else str(row[key]), reverse=descending
            )
            + missing
        )
    if limit is not None:
        if limit < 1:
            raise SiftError("Experiment list limit must be at least 1.")
        rows = rows[:limit]
    result = {**table, "rows": rows}
    if columns:
        names = [item.strip() for item in columns.split(",") if item.strip()]
        if not names:
            raise SiftError("Select at least one column.")
        result.update(
            columns=list(dict.fromkeys(["run", *(column(name) for name in names)])),
            selected_columns=True,
        )
    return result


def comparison_columns(table: dict) -> list[str]:
    if table.get("selected_columns"):
        return table["columns"]
    results = [
        key for key in table["columns"] if key.startswith("result.") and ".config." not in key
    ]
    metrics = [
        key
        for key in results
        if any(
            isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)
            for row in table["rows"]
        )
    ]
    return [
        key
        for key in table["columns"]
        if key in {"run", "status", "scratch", "experiment", "seed"}
        or key.startswith(("metadata.", "input."))
        or key in (metrics or results)[:4]
    ]


def archive_records(config: ProjectConfig) -> list[dict]:
    return sorted(
        (read_json(path) for path in (config.state_dir / "archive").glob("*/manifest.json")),
        key=lambda record: record.get("archived_at", ""),
        reverse=True,
    )


def archive_path(config: ProjectConfig, reference: str) -> str:
    candidate = Path(reference)
    if candidate.is_relative_to(config.scratch) or candidate.is_relative_to(config.experiments):
        return reference
    paths = [area / slugify(reference) for area in (config.scratch, config.experiments)]
    matches = [path for path in paths if (config.root / path).is_dir()]
    if len(matches) == 1:
        return matches[0].as_posix()
    if matches:
        raise SiftError(
            "Ambiguous experiment name; use a path: "
            + ", ".join(path.as_posix() for path in matches)
        )
    raise SiftError(
        f"No scratch or saved experiment named '{reference}'. Use sift status to find current work."
    )
