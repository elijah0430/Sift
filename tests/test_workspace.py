import os
import subprocess
import sys

from sift.cli import _page
from sift.lifecycle import create_exploration, preserve
from sift.promotion import prepare, seal
from sift.snapshots import create_run
from sift.util import read_json, write_json
from sift.workspace import compare_experiments, experiment_runs, resolve_run, workspace_status


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


def test_experiment_comparison_collects_configuration_inputs_and_json_results(project):
    exploration = create_exploration(project, "comparison")
    data = project.root / "data.json"
    data.write_text('{"rows": 3}', encoding="utf-8")
    command = f'"{sys.executable}" scratch/comparison/experiment.py'
    run_ids = []
    for method, accuracy in (("baseline", 0.71), ("calibrated", 0.78)):
        (exploration / "experiment.py").write_text(
            "from pathlib import Path\nimport json\n"
            "Path('results').mkdir(exist_ok=True)\n"
            f"Path('results/metrics.json').write_text(json.dumps({{'accuracy': {accuracy}}}))\n",
            encoding="utf-8",
        )
        run_id, exit_code = create_run(
            project,
            command,
            ["results/metrics.json"],
            inputs=["dataset=data.json"],
            seeds=[7],
            metadata=[f"method={method}", "model=small"],
            exploration="comparison",
        )
        assert exit_code == 0
        run_ids.append(run_id)

    preserve(project, "comparison", "comparison-study", run_ids[1])
    table = compare_experiments(project, tuple(run_ids))

    assert table["rows"][0]["metadata.method"] == "baseline"
    assert table["rows"][1]["metadata.method"] == "calibrated"
    assert table["rows"][1]["input.dataset"] == "data.json"
    assert table["rows"][1]["result.metrics.accuracy"] == 0.78
    assert table["rows"][1]["experiment"] == "comparison-study"
    assert table["rows"][1]["scratch"] == "comparison"

    # Runs can start in the same second; the most recently updated manifest remains first.
    for index, run_id in enumerate(run_ids, start=1):
        manifest_path = project.state_dir / "runs" / run_id / "manifest.json"
        manifest = read_json(manifest_path)
        manifest["started_at"] = "2026-01-01T00:00:00+00:00"
        write_json(manifest_path, manifest)
        timestamp = 1_800_000_000_000_000_000 + index * 1_000_000_000
        os.utime(manifest_path, ns=(timestamp, timestamp))
    assert experiment_runs(project, limit=1)["rows"][0]["run"] == run_ids[1]


def test_experiment_cli_runs_and_saves_the_linked_scratch_code(project):
    def cli(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "sift", *arguments],
            cwd=project.root,
            text=True,
            capture_output=True,
            check=False,
        )

    created = cli("experiment", "new", "sampler-study")
    assert created.returncode == 0, created.stderr
    script = project.root / "scratch" / "sampler-study" / "experiment.py"
    script.write_text(
        "from pathlib import Path\nimport json\n"
        "Path('results').mkdir(exist_ok=True)\n"
        "Path('results/metrics.json').write_text(json.dumps({'loss': 0.4}))\n",
        encoding="utf-8",
    )

    completed = cli(
        "experiment",
        "run",
        "sampler-study",
        "--artifact",
        "results/metrics.json",
        "--meta",
        "method=baseline",
    )
    assert completed.returncode == 0, completed.stderr
    run_id = completed.stdout.split()[0]
    assert (
        read_json(project.state_dir / "runs" / run_id / "manifest.json")["exploration"]
        == "sampler-study"
    )

    saved = cli("experiment", "save", run_id, "--name", "sampler-ablation")
    assert saved.returncode == 0, saved.stderr
    assert (project.root / "experiments" / "sampler-ablation" / "experiment.py").is_file()

    listed = cli("experiment", "list")
    assert listed.returncode == 0, listed.stderr
    assert "METHOD" in listed.stdout
    assert "LOSS" in listed.stdout
    assert "sampler-ablation" in listed.stdout

    proposed = cli(
        "core",
        "propose",
        "--title",
        "Share sampler",
        "--rationale",
        "The experiment now uses the same sampler twice",
        "--from-run",
        "sampler-ablation",
    )
    assert proposed.returncode == 0, proposed.stderr
    proposal_id = proposed.stdout.splitlines()[0]
    proposal = read_json(project.state_dir / "proposals" / proposal_id / "manifest.json")
    assert proposal["baseline_run"] == run_id


def test_primary_help_shows_the_small_research_interface(project):
    completed = subprocess.run(
        [sys.executable, "-m", "sift", "--help"],
        cwd=project.root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "experiment" in completed.stdout
    assert "core" in completed.stdout
    assert "cache" not in completed.stdout
    assert "promote" not in completed.stdout
