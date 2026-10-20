from __future__ import annotations

import shutil
from pathlib import Path

from .config import ProjectConfig
from .errors import SiftError
from .util import copy_tree, short_id, tree_hash, utc_now, write_json


def create_exploration(config: ProjectConfig, name: str, question: str = "") -> Path:
    from .util import slugify

    path = config.root / config.scratch / slugify(name)
    if path.exists():
        raise SiftError(f"Exploration already exists: {path}")
    path.mkdir(parents=True)
    (path / "README.md").write_text(
        f"# {name}\n\n## Question\n\n{question or 'Describe the question being explored.'}\n\n"
        "## Status\n\nActive exploration.\n",
        encoding="utf-8",
        newline="\n",
    )
    (path / "experiment.py").write_text(
        '"""Exploratory code. Import maintained capabilities from the project core."""\n\n'
        '\nif __name__ == "__main__":\n    pass\n',
        encoding="utf-8",
        newline="\n",
    )
    return path


def preserve(config: ProjectConfig, source_name: str, experiment_name: str | None = None) -> Path:
    from .util import slugify

    source = (config.root / config.scratch / source_name).resolve()
    scratch_root = (config.root / config.scratch).resolve()
    try:
        source.relative_to(scratch_root)
    except ValueError as exc:
        raise SiftError("Only scratch explorations can be preserved with this command.") from exc
    if not source.is_dir():
        raise SiftError(f"Exploration does not exist: {source_name}")
    destination = config.root / config.experiments / slugify(experiment_name or source.name)
    copy_tree(source, destination, ignores=())
    write_json(
        destination / "sift-record.json",
        {
            "schema": 1,
            "preserved_at": utc_now(),
            "source": str(source.relative_to(config.root)).replace("\\", "/"),
            "source_hash": tree_hash(destination, ignores=()),
            "status": "preserved",
        },
    )
    return destination


def retire(config: ProjectConfig, relative_path: str) -> str:
    target = (config.root / relative_path).resolve()
    allowed = [
        (config.root / config.scratch).resolve(),
        (config.root / config.experiments).resolve(),
    ]
    if not any(target != root and root in target.parents for root in allowed):
        raise SiftError("Retirement is limited to individual scratch or experiment paths.")
    if not target.exists():
        raise SiftError(f"Nothing to retire: {relative_path}")
    if not target.is_dir():
        raise SiftError("Retirement currently accepts directories, not individual files.")
    retirement_id = short_id("retired")
    archive = config.state_dir / "archive" / retirement_id
    archive.mkdir(parents=True)
    payload = archive / "payload"
    copy_tree(target, payload, ignores=())
    digest = tree_hash(payload, ignores=())
    write_json(
        archive / "manifest.json",
        {
            "schema": 1,
            "id": retirement_id,
            "original_path": str(target.relative_to(config.root)).replace("\\", "/"),
            "archived_at": utc_now(),
            "payload_hash": digest,
        },
    )
    shutil.rmtree(target)
    return retirement_id


def restore_retirement(config: ProjectConfig, retirement_id: str) -> Path:
    from .util import read_json

    archive = config.state_dir / "archive" / retirement_id
    manifest = read_json(archive / "manifest.json")
    destination = config.root / manifest["original_path"]
    if destination.exists():
        raise SiftError(f"Restore destination already exists: {destination}")
    payload = archive / "payload"
    copy_tree(payload, destination, ignores=())
    return destination
