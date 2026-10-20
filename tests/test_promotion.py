import sys

import pytest

from sift.errors import SiftError
from sift.promotion import apply, approve, prepare, seal
from sift.util import utc_now, write_json


def test_promotion_requires_exact_human_approval(project):
    target = project.root / "src" / "demo" / "scoring.py"
    target.write_text("def score(x):\n    return x\n", encoding="utf-8")
    proposal_id, candidate = prepare(project, "Calibrated scorer")
    candidate_target = candidate / "src" / "demo" / "scoring.py"
    candidate_target.write_text("def score(x):\n    return x * 2\n", encoding="utf-8")

    check = f'"{sys.executable}" -c "print(\'checked\')"'
    digest = seal(project, proposal_id, (check,))

    with pytest.raises(SiftError, match="approval"):
        apply(project, proposal_id)

    proposal = project.state_dir / "proposals" / proposal_id
    write_json(
        proposal / "approval.json",
        {"digest": digest, "reviewer": "human", "approved_at": utc_now()},
    )
    apply(project, proposal_id)
    assert "x * 2" in target.read_text(encoding="utf-8")


def test_reseal_invalidates_approval(project):
    proposal_id, candidate = prepare(project, "New utility")
    new_file = candidate / "src" / "demo" / "utility.py"
    new_file.write_text("VALUE = 1\n", encoding="utf-8")
    check = f'"{sys.executable}" -c "print(\'ok\')"'
    first = seal(project, proposal_id, (check,))
    proposal = project.state_dir / "proposals" / proposal_id
    write_json(proposal / "approval.json", {"digest": first})

    new_file.write_text("VALUE = 2\n", encoding="utf-8")
    second = seal(project, proposal_id, (check,))

    assert second != first
    assert not (proposal / "approval.json").exists()


def test_apply_rejects_changed_base(project):
    target = project.root / "src" / "demo" / "value.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    proposal_id, candidate = prepare(project, "Change value")
    (candidate / "src" / "demo" / "value.py").write_text("VALUE = 2\n", encoding="utf-8")
    check = f'"{sys.executable}" -c "print(\'ok\')"'
    digest = seal(project, proposal_id, (check,))
    proposal = project.state_dir / "proposals" / proposal_id
    write_json(proposal / "approval.json", {"digest": digest})
    target.write_text("VALUE = 3\n", encoding="utf-8")

    with pytest.raises(SiftError, match="changed since review"):
        apply(project, proposal_id)

    assert target.read_text(encoding="utf-8") == "VALUE = 3\n"


def test_approval_requires_human_terminal(project, monkeypatch):
    proposal_id, candidate = prepare(project, "New value")
    (candidate / "src" / "demo" / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    check = f'"{sys.executable}" -c "print(\'ok\')"'
    seal(project, proposal_id, (check,))

    class NonInteractive:
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", NonInteractive())
    with pytest.raises(SiftError, match="interactive human"):
        approve(project, proposal_id)
