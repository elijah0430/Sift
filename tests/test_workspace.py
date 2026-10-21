import sys

from sift.cli import _page
from sift.lifecycle import create_exploration, preserve
from sift.promotion import prepare, seal
from sift.snapshots import create_run
from sift.workspace import resolve_run, workspace_status


def test_status_describes_the_research_lifecycle(project):
    exploration = create_exploration(project, "sampler study")
    (exploration / "experiment.py").write_text(
        "from pathlib import Path\nPath('result.txt').write_text('ok')\n",
        encoding="utf-8",
    )
    command = f'"{sys.executable}" scratch/sampler-study/experiment.py'
    run_id, exit_code = create_run(project, command, ["result.txt"])
    assert exit_code == 0
    preserve(project, "sampler-study", "sampler-ablation", run_id)

    proposal_id, candidate = prepare(project, "Share sampler")
    (candidate / "src" / "demo" / "sampler.py").write_text("VALUE = 1\n", encoding="utf-8")
    seal(project, proposal_id, (f'"{sys.executable}" -c "print(1)"',))

    status = workspace_status(project)
    assert status["needs_review"] == 1
    assert status["explorations"] == ["sampler-study"]
    assert status["experiments"] == ["sampler-ablation"]
    assert status["runs"]["completed"] == 1
    assert resolve_run(project, "sampler-ablation") == run_id
    assert resolve_run(project, run_id) == run_id


def test_terminal_diff_falls_back_when_the_configured_pager_is_unavailable(monkeypatch, capsys):
    monkeypatch.setenv("PAGER", "definitely-not-a-real-pager")
    _page("review text")
    assert capsys.readouterr().out == "review text\n"
