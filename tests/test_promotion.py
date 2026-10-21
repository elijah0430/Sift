import shutil
import subprocess
import sys

import pytest

from sift.cli import _review
from sift.errors import SiftError
from sift.promotion import (
    apply,
    approve,
    pending_proposals,
    prepare,
    proposal_feedback,
    request_changes,
    seal,
)
from sift.util import read_json, utc_now, write_json


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


@pytest.mark.parametrize("reviewer", [None, "Researcher"])
def test_review_approves_and_applies_the_displayed_change(project, monkeypatch, reviewer):
    target = project.root / "src" / "demo" / "scoring.py"
    target.write_text("def score(x):\n    return x\n", encoding="utf-8")
    proposal_id, candidate = prepare(project, "Share calibrated scoring", "Used by two studies.")
    (candidate / "src" / "demo" / "scoring.py").write_text(
        "def score(x):\n    return x * 2\n", encoding="utf-8"
    )
    seal(project, proposal_id, (f'"{sys.executable}" -c "print(\'ok\')"',))

    class Interactive:
        def isatty(self):
            return True

    pages = []
    answers = iter(["a"])
    monkeypatch.setattr(sys, "stdin", Interactive())
    monkeypatch.setattr("sift.cli.getpass.getuser", lambda: "local-user")
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr("sift.cli._page", pages.append)

    assert _review(project, proposal_id, None, reviewer, terminal=True) == 0
    assert "x * 2" in target.read_text(encoding="utf-8")
    assert "Share calibrated scoring" in pages[0]
    manifest = read_json(project.state_dir / "proposals" / proposal_id / "manifest.json")
    approval = read_json(project.state_dir / "proposals" / proposal_id / "approval.json")
    assert manifest["status"] == "applied"
    assert approval["reviewer"] == (reviewer or "local-user")
    assert approval["digest"] == manifest["digest"]


def test_review_rejects_changes_made_after_display(project, monkeypatch):
    proposal_id, candidate = prepare(project, "New value")
    target = candidate / "src" / "demo" / "value.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    seal(project, proposal_id, (f'"{sys.executable}" -c "print(\'ok\')"',))

    class Interactive:
        def isatty(self):
            return True

    def change_after_display(_text):
        target.write_text("VALUE = 2\n", encoding="utf-8")

    answers = iter(["a"])
    monkeypatch.setattr(sys, "stdin", Interactive())
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr("sift.cli._page", change_after_display)

    with pytest.raises(SiftError, match="changed.*review|Reseal"):
        _review(project, proposal_id, None, terminal=True)
    assert not (project.root / "src" / "demo" / "value.py").exists()


@pytest.mark.parametrize("already_approved", [False, True])
def test_review_cannot_apply_a_new_revision_approved_by_another_session(
    project, monkeypatch, already_approved
):
    from sift.promotion import approve_reviewed

    proposal_id, candidate = prepare(project, "New value")
    target = candidate / "src" / "demo" / "value.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    command = f'"{sys.executable}" -c "print(1)"'
    digest = seal(project, proposal_id, (command,))
    approval_path = project.state_dir / "proposals" / proposal_id / "approval.json"

    class Interactive:
        def isatty(self):
            return True

    def replace_and_approve():
        target.write_text("VALUE = 2\n", encoding="utf-8")
        changed_digest = seal(project, proposal_id, (command,))
        write_json(approval_path, {"digest": changed_digest, "reviewer": "other reviewer"})

    def approve_then_replace(*args):
        approve_reviewed(*args)
        replace_and_approve()

    if already_approved:
        write_json(approval_path, {"digest": digest, "reviewer": "earlier reviewer"})
        monkeypatch.setattr("sift.cli._page", lambda _text: replace_and_approve())
    else:
        monkeypatch.setattr("sift.cli._page", lambda _text: None)
        monkeypatch.setattr("sift.cli.approve_reviewed", approve_then_replace)

    monkeypatch.setattr(sys, "stdin", Interactive())
    monkeypatch.setattr("builtins.input", lambda _prompt: "a")
    with pytest.raises(SiftError, match="changed during review"):
        _review(project, proposal_id, None, terminal=True)
    assert not (project.root / "src" / "demo" / "value.py").exists()


def test_editor_cannot_silently_replace_the_displayed_revision(project, monkeypatch, capsys):
    proposal_id, candidate = prepare(project, "New value")
    target = candidate / "src" / "demo" / "value.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    command = f'"{sys.executable}" -c "print(1)"'
    seal(project, proposal_id, (command,))

    class Interactive:
        def isatty(self):
            return True

    def edit_and_reseal(_path, _editor):
        target.write_text("VALUE = 2\n", encoding="utf-8")
        seal(project, proposal_id, (command,))

    answers = iter(["e", "a"])
    monkeypatch.setattr(sys, "stdin", Interactive())
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr("sift.cli._page", lambda _text: None)
    monkeypatch.setattr("sift.cli._open_editor", edit_and_reseal)
    assert _review(project, proposal_id, None, terminal=True) == 0
    assert "changed during review" in capsys.readouterr().out
    assert not (project.root / "src" / "demo" / "value.py").exists()
    assert not (project.state_dir / "proposals" / proposal_id / "approval.json").exists()


def test_candidate_is_a_local_git_review_workspace(project):
    if not shutil.which("git"):
        pytest.skip("git is unavailable")
    _, candidate = prepare(project, "Review in editor")
    clean = subprocess.run(
        ["git", "status", "--short"],
        cwd=candidate,
        text=True,
        capture_output=True,
        check=True,
    )
    assert clean.stdout == ""
    (candidate / "src" / "demo" / "reviewed.py").write_text("VALUE = 1\n", encoding="utf-8")
    changed = subprocess.run(
        ["git", "status", "--short"],
        cwd=candidate,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "src/demo/reviewed.py" in changed.stdout.replace("\\", "/")


def test_requested_changes_return_the_proposal_to_the_agent(project):
    proposal_id, candidate = prepare(project, "Review feedback")
    target = candidate / "src" / "demo" / "reviewed.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    command = f'"{sys.executable}" -c "print(1)"'
    digest = seal(project, proposal_id, (command,))

    request_changes(
        project,
        proposal_id,
        digest,
        "Researcher",
        "# Requested changes\n\n- Rename VALUE to DEFAULT_VALUE.",
    )
    assert not pending_proposals(project)
    feedback = proposal_feedback(project, proposal_id)
    assert feedback["status"] == "open"
    assert "DEFAULT_VALUE" in feedback["feedback"]
    with pytest.raises(SiftError, match="Revise the candidate"):
        seal(project, proposal_id, (command,))

    target.write_text("DEFAULT_VALUE = 1\n", encoding="utf-8")
    seal(project, proposal_id, (command,))
    assert proposal_feedback(project, proposal_id)["status"] == "addressed"
    assert pending_proposals(project)[0]["id"] == proposal_id


def test_review_can_recheck_an_edit_before_approval(project, monkeypatch):
    proposal_id, candidate = prepare(project, "Edit during review")
    target = candidate / "src" / "demo" / "value.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    seal(project, proposal_id, (f'"{sys.executable}" -c "print(1)"',))

    class Interactive:
        def isatty(self):
            return True

    def edit_candidate(_path, _editor):
        target.write_text("VALUE = 2\n", encoding="utf-8")

    answers = iter(["e", "r", "a"])
    monkeypatch.setattr(sys, "stdin", Interactive())
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr("sift.cli._page", lambda _text: None)
    monkeypatch.setattr("sift.cli._open_editor", edit_candidate)

    assert _review(project, proposal_id, None, terminal=True) == 0
    applied = project.root / "src" / "demo" / "value.py"
    assert applied.read_text(encoding="utf-8") == "VALUE = 2\n"


def test_review_can_return_requested_changes_to_the_agent(project, monkeypatch):
    proposal_id, candidate = prepare(project, "Request revision")
    (candidate / "src" / "demo" / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    seal(project, proposal_id, (f'"{sys.executable}" -c "print(1)"',))

    class Interactive:
        def isatty(self):
            return True

    answers = iter(["f", "Add an edge-case test for an empty input."])
    monkeypatch.setattr(sys, "stdin", Interactive())
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr("sift.cli._page", lambda _text: None)

    assert _review(project, proposal_id, None, terminal=True) == 0
    assert proposal_feedback(project, proposal_id)["status"] == "open"
    assert not pending_proposals(project)
