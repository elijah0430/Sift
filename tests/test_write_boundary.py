import pytest

from sift.cache import get, put
from sift.errors import SiftError
from sift.promotion import prepare


def test_cache_cannot_write_into_core(project, tmp_path):
    source = tmp_path / "component.py"
    source.write_text("VALUE=1")
    put(project, "component", source)
    target = project.root / "src/demo/unreviewed.py"
    with pytest.raises(SiftError, match="reviewed promotion"):
        get(project, "component", target)
    assert not target.exists()


def test_materialization_cannot_forge_a_promotion_approval(project):
    proposal_id, _ = prepare(project, "Candidate")
    target = project.state_dir / "proposals" / proposal_id / "approval.json"
    with pytest.raises(SiftError, match="protected Sift state"):
        project.check_output_destination(target)


def test_candidate_materialization_remains_available_for_review(project, tmp_path):
    source = tmp_path / "component.py"
    source.write_text("VALUE=1")
    put(project, "component", source)
    _, candidate = prepare(project, "Candidate")
    target = candidate / "src/demo/proposed.py"
    get(project, "component", target)
    assert target.read_text() == "VALUE=1"
