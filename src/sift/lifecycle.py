from __future__ import annotations

import shutil
from pathlib import Path

from .boundaries import dependency_graph
from .config import ProjectConfig
from .errors import SiftError
from .util import (
    contained_path,
    copy_tree,
    project_lock,
    read_json,
    safe_id,
    short_id,
    slugify,
    tree_hash,
    utc_now,
    write_json,
)


def create_exploration(
    config: ProjectConfig,
    name: str,
    question: str = "",
    from_run: str | None = None,
    notebook: bool = False,
) -> Path:
    path = contained_path(config.root, config.scratch / slugify(name))
    if path.exists():
        raise SiftError(f"Exploration already exists: {path}")
    if from_run:
        run = config.state_dir / "runs" / safe_id(from_run)
        manifest = read_json(run / "manifest.json")
        if tree_hash(run / "source", ignores=()) != manifest["source_hash"]:
            raise SiftError("The baseline source snapshot is corrupted.")
        path.mkdir(parents=True)
        copy_tree(run / "source", path / "baseline", ignores=())
        write_json(path / "sift-record.json", {"parent_run": from_run, "question": question})
    else:
        path.mkdir(parents=True)
    (path / "README.md").write_text(
        f"# {name}\n\nQuestion: {question or 'Describe the research question.'}\n",
        encoding="utf-8",
    )
    (path / "experiment.py").write_text(
        '"""Exploratory code; import reusable functions and modules from core."""\n',
        encoding="utf-8",
    )
    if notebook:
        template = Path(__file__).parent / "templates" / "notebook.py.txt"
        (path / "notebook.py").write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def preserve(
    config: ProjectConfig,
    source_name: str,
    experiment_name: str | None = None,
    run_id: str | None = None,
) -> Path:
    source = contained_path(config.root / config.scratch, source_name)
    original_relative = source.relative_to(config.root).as_posix()
    run_record = None
    if run_id:
        run_record = read_json(config.state_dir / "runs" / safe_id(run_id) / "manifest.json")
        recorded_source = config.state_dir / "runs" / run_id / "source"
        if tree_hash(recorded_source, ignores=()) != run_record["source_hash"]:
            raise SiftError("Recorded source is corrupted.")
        source = contained_path(recorded_source, original_relative)
    if not source.is_dir():
        raise SiftError(f"Exploration does not exist: {source_name}")
    with project_lock(config.state_dir):
        destination = contained_path(
            config.root,
            config.experiments / slugify(experiment_name or source.name),
        )
        copy_tree(source, destination)
        write_json(
            destination / "sift-record.json",
            {
                "schema": 1,
                "preserved_at": utc_now(),
                "source": original_relative,
                "source_hash": tree_hash(source),
                "status": "preserved",
                "run_id": run_id,
                "core_source_hash": run_record.get("source_hash") if run_record else None,
                "reproduction": (
                    f"sift reproduce {run_id}" if run_id else "No experiment run linked."
                ),
            },
        )
        return destination


def retire(config: ProjectConfig, relative_path: str) -> str:
    target = contained_path(config.root, relative_path)
    roots = [config.root / config.scratch, config.root / config.experiments]
    if not any(target != root and root in target.parents for root in roots):
        raise SiftError("Retirement is limited to individual scratch or experiment paths.")
    if not target.is_dir():
        raise SiftError(f"Nothing to retire: {relative_path}")
    with project_lock(config.state_dir):
        for record_path in (config.state_dir / "runs").glob("*/manifest.json"):
            if read_json(record_path).get("status") in {"preparing", "running"}:
                raise SiftError("An active run must finish or be reconciled before retirement.")
        graph, errors = dependency_graph(config)
        if any(
            any(item.file.is_relative_to(path) for path in (*config.core, config.experiments))
            and not (config.root / item.file).is_relative_to(target)
            for item in errors
        ):
            raise SiftError("Resolve source analysis errors before dependency-aware retirement.")
        module = ".".join(target.relative_to(config.root).parts).replace("-", "_")
        for node in graph.values():
            if (config.root / node["path"]).is_relative_to(target):
                continue
            if not any(
                node["path"].is_relative_to(path) for path in (*config.core, config.experiments)
            ):
                continue
            if any(
                imported == module or imported.startswith(module + ".")
                for _, imported in node["imports"]
            ):
                raise SiftError(f"Maintained code still depends on this path: {node['path']}")
        retirement_id = short_id("retired")
        archive = config.state_dir / "archive" / retirement_id
        copy_tree(target, archive / "payload", ignores=())
        digest = tree_hash(archive / "payload", ignores=())
        if digest != tree_hash(target, ignores=()):
            raise SiftError("Archive verification failed; active files were left in place.")
        write_json(
            archive / "manifest.json",
            {
                "schema": 1,
                "id": retirement_id,
                "original_path": target.relative_to(config.root).as_posix(),
                "archived_at": utc_now(),
                "payload_hash": digest,
                "status": "archived",
            },
        )
        shutil.rmtree(target)
        return retirement_id


def restore_retirement(config: ProjectConfig, retirement_id: str) -> Path:
    archive = config.state_dir / "archive" / safe_id(retirement_id)
    manifest = read_json(archive / "manifest.json")
    destination = contained_path(config.root, manifest["original_path"])
    if not any(
        destination != config.root / root and destination.is_relative_to(config.root / root)
        for root in (config.scratch, config.experiments)
    ):
        raise SiftError("Archive destination must remain within scratch or experiments.")
    if destination.exists():
        raise SiftError(f"Restore destination already exists: {destination}")
    if tree_hash(archive / "payload", ignores=()) != manifest["payload_hash"]:
        raise SiftError("Archived payload is corrupted.")
    copy_tree(archive / "payload", destination, ignores=())
    return destination
