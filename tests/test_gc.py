from datetime import UTC, datetime, timedelta

import pytest

from sift.cache import drop, put
from sift.errors import SiftError
from sift.gc import apply, plan, set_pin
from sift.lifecycle import create_exploration, retire


def _retired(project, name):
    create_exploration(project, name)
    return retire(project, f"scratch/{name}")


def test_gc_plan_respects_pins_and_requires_exact_digest(project):
    removable = _retired(project, "old-one")
    pinned = _retired(project, "old-two")
    set_pin(project, pinned, True)
    future = datetime.now(UTC) + timedelta(days=project.archive_days + 1)

    plan_id, digest, candidates = plan(project, now=future)

    assert [item["id"] for item in candidates] == [removable]
    with pytest.raises(SiftError, match="confirmation"):
        apply(project, plan_id, "wrong")
    assert apply(project, plan_id, digest[:12]) == 1
    assert not (project.state_dir / "archive" / removable).exists()
    assert (project.state_dir / "archive" / pinned).exists()


def test_gc_rejects_archive_changed_after_review(project):
    retirement_id = _retired(project, "old-one")
    future = datetime.now(UTC) + timedelta(days=project.archive_days + 1)
    plan_id, digest, _ = plan(project, now=future)
    payload = project.state_dir / "archive" / retirement_id / "payload" / "extra.txt"
    payload.write_text("changed", encoding="utf-8")

    with pytest.raises(SiftError, match="changed after planning"):
        apply(project, plan_id, digest[:12])


def test_gc_only_collects_unreferenced_cache_objects(project, tmp_path):
    kept_file = tmp_path / "kept.txt"
    dropped_file = tmp_path / "dropped.txt"
    kept_file.write_text("keep", encoding="utf-8")
    dropped_file.write_text("drop", encoding="utf-8")
    kept = put(project, "kept", kept_file)
    dropped = put(project, "dropped", dropped_file)
    drop(project, "dropped")

    plan_id, digest, candidates = plan(project)

    assert [item["id"] for item in candidates] == [dropped["sha256"]]
    assert apply(project, plan_id, digest[:12]) == 1
    objects = project.state_dir / "cache" / "objects"
    assert (objects / kept["sha256"]).exists()
    assert not (objects / dropped["sha256"]).exists()
