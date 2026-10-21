import json
import subprocess
import sys

import pytest

from sift.cli import _choose_proposal, _parser, _print_experiment_runs, execute
from sift.config import initialize_project
from sift.errors import SiftError
from sift.handoff import publish_research
from sift.harness import launch
from sift.lifecycle import create_exploration, preserve
from sift.promotion import prepare, request_changes, review_material, seal
from sift.snapshots import create_run, replay_run
from sift.util import read_json, write_json
from sift.workspace import compare_experiments, experiment_runs, resolve_run


def test_split_results_and_changed_input_identity_survive_comparison(project, capsys):
    scratch = create_exploration(project, "evaluation")
    script = scratch / "experiment.py"
    script.write_text(
        "from pathlib import Path\n"
        "for split, value in [('train', 0.99), ('test', 0.75)]:\n"
        "    p=Path('results')/split/'metrics.json'\n"
        "    p.parent.mkdir(parents=True, exist_ok=True)\n"
        "    p.write_text('{\"accuracy\":'+str(value)+'}')\n",
        encoding="utf-8",
    )
    data = project.root / "data.json"
    runs = []
    for value in ("v1", "v2"):
        data.write_text(value, encoding="utf-8")
        run_id, code = create_run(
            project,
            f'"{sys.executable}" scratch/evaluation/experiment.py',
            ["results"],
            inputs=["dataset=data.json"],
            exploration="evaluation",
        )
        assert code == 0
        runs.append(run_id)
    table = compare_experiments(project, tuple(runs))
    row = table["rows"][0]
    assert row["result.results/train/metrics.accuracy"] == 0.99
    assert row["result.results/test/metrics.accuracy"] == 0.75
    assert row["input_sha256.dataset"] != table["rows"][1]["input_sha256.dataset"]
    assert table["warnings"]
    for run_id in runs:
        assert resolve_run(project, table["aliases"][run_id]) == run_id
    conflicting_name = table["aliases"][runs[0]]
    preserve(project, "evaluation", conflicting_name, runs[1])
    with pytest.raises(SiftError, match="Ambiguous"):
        resolve_run(project, conflicting_name)
    assert experiment_runs(project)["aliases"][runs[0]] == runs[0]
    _print_experiment_runs(table)
    output = capsys.readouterr().out
    assert "..." not in output
    assert "0.99" in output and "0.75" in output and "changed" in output
    assert replay_run(project, runs[0])[2]


def test_ambiguous_short_reference_lists_candidates(project):
    identifiers = ("run-20260101-010101-abcdef", "run-20260102-010101-abcdef")
    for identifier in identifiers:
        write_json(project.state_dir / "runs" / identifier / "manifest.json", {"id": identifier})
    with pytest.raises(SiftError, match="Ambiguous"):
        resolve_run(project, "run-abcdef")
    assert resolve_run(project, "run-20260101") == identifiers[0]
    assert experiment_runs(project)["aliases"][identifiers[0]] == identifiers[0]


def test_followup_copies_code_and_inherits_inputs_outputs_and_parent(project, monkeypatch):
    scratch = create_exploration(project, "original")
    (scratch / "experiment.py").write_text(
        "from pathlib import Path\nPath('answer.txt').write_text('42')\n", encoding="utf-8"
    )
    run_id, code = create_run(
        project,
        f'"{sys.executable}" scratch/original/experiment.py',
        ["answer.txt"],
        seeds=[7],
        metadata=["method=baseline"],
        exploration="original",
    )
    assert code == 0
    preserve(project, "original", "baseline", run_id)
    followup = create_exploration(project, "extension", from_run="baseline")
    assert "write_text('42')" in (followup / "experiment.py").read_text()
    assert not (followup / "baseline").exists()
    monkeypatch.chdir(project.root)
    args = _parser().parse_args(["--json", "experiment", "run", "extension"])
    assert execute(args) == 0
    table = experiment_runs(project)
    new_id = next(row["run"] for row in table["rows"] if row["scratch"] == "extension")
    manifest = read_json(project.state_dir / "runs" / new_id / "manifest.json")
    assert manifest["parent"] == run_id
    assert manifest["seeds"] == [7]
    assert manifest["metadata"] == {"method": "baseline"}
    assert manifest["artifacts"][0]["path"] == "answer.txt"
    first = preserve(project, "extension", run_id=new_id)
    assert preserve(project, "extension", run_id=new_id) == first
    second_id, code = create_run(
        project,
        f'"{sys.executable}" scratch/extension/experiment.py',
        ["answer.txt"],
        exploration="extension",
    )
    assert code == 0
    second = preserve(project, "extension", run_id=second_id)
    assert second != first and second.is_dir()


def test_explicit_custom_command_does_not_require_experiment_py(project, monkeypatch):
    scratch = project.root / "scratch" / "custom"
    scratch.mkdir()
    (scratch / "train.py").write_text("print('custom command executed')\n", encoding="utf-8")
    monkeypatch.chdir(project.root)
    args = _parser().parse_args(
        [
            "--json",
            "experiment",
            "run",
            "custom",
            "--command",
            f'"{sys.executable}" scratch/custom/train.py',
        ]
    )
    assert execute(args) == 0


def test_missing_core_mapping_is_reported_before_passed(tmp_path, monkeypatch, capsys):
    root = tmp_path / "flat"
    initialize_project(root)
    (root / "models.py").write_text("import scratch.idea\n", encoding="utf-8")
    monkeypatch.chdir(root)
    assert execute(_parser().parse_args(["check"])) == 1
    output = capsys.readouterr().out
    assert "not found" in output and "research.toml" in output
    assert "passed" not in output


def test_agent_handoff(project):
    script = project.root / "scratch" / "agent.py"
    script.write_text(
        "import json,subprocess,sys\nfrom pathlib import Path\n"
        "def sift(*args):\n"
        "    p=subprocess.run([sys.executable,'-m','sift','--json',*args],"
        "capture_output=True,text=True,check=True)\n"
        "    return json.loads(p.stdout)['result']\n"
        "sift('experiment','new','agent-study')\n"
        "Path('scratch/agent-study/experiment.py').write_text("
        "\"from pathlib import Path\\nPath('answer.txt').write_text('42')\\n\")\n"
        "r=sift('experiment','run','agent-study','--artifact','answer.txt')\n"
        "sift('experiment','save',r['id'],'--name','agent-result')\n",
        encoding="utf-8",
    )
    report = launch(project, [sys.executable, "scratch/agent.py"])
    assert report["exit_code"] == 0 and report["original_core_unchanged"]
    assert len(report["research"]["runs"]) == 1
    run_id = resolve_run(project, "agent-result")
    assert replay_run(project, run_id)[2]
    assert not (project.state_dir / "runs" / run_id / "work").exists()
    assert not list(project.state_dir.glob("proposals/*/approval.json"))


def test_corrupt_agent_output(project):
    _, candidate = prepare(project, "Agent session")
    from sift.config import ProjectConfig

    isolated = ProjectConfig.load(candidate)
    run_id, code = create_run(
        isolated,
        f"\"{sys.executable}\" -c \"open('answer.txt','w').write('42')\"",
        ["answer.txt"],
    )
    assert code == 0
    artifact = isolated.state_dir / "runs" / run_id / "artifacts/answer.txt"
    artifact.write_text("changed", encoding="utf-8")
    with pytest.raises(SiftError, match="corrupted"):
        publish_research(project, candidate)
    assert not (project.state_dir / "runs" / run_id).exists()


def test_revised_review_includes_feedback_and_only_changes_since_review(project):
    proposal_id, candidate = prepare(project, "Reusable utility")
    target = candidate / "src/demo/utility.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    command = f'"{sys.executable}" -c "print(1)"'
    digest = seal(project, proposal_id, (command,))
    request_changes(project, proposal_id, digest, "reviewer", "Rename the constant.")
    target.write_text("DEFAULT_VALUE = 1\n", encoding="utf-8")
    seal(project, proposal_id, (command,))
    material = review_material(project, proposal_id)
    assert material["revision"]["feedback"].strip() == "Rename the constant."
    assert "-VALUE = 1" in material["revision"]["diff"]
    assert "+DEFAULT_VALUE = 1" in material["revision"]["diff"]


def test_invalid_review_selection_can_be_corrected(project, monkeypatch):
    for number in (1, 2):
        proposal_id, candidate = prepare(project, f"Change {number}")
        (candidate / "src/demo/value.py").write_text(f"VALUE = {number}\n", encoding="utf-8")
        seal(project, proposal_id, (f'"{sys.executable}" -c "print(1)"',))
    answers = iter(["99", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert _choose_proposal(project, None) is not None


def test_json_flag_at_end_and_failure_details_are_machine_readable(project):
    create_exploration(project, "failure")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sift",
            "experiment",
            "run",
            "failure",
            "--command",
            f'"{sys.executable}" -c "raise ValueError(\'missing labels\')"',
            "--json",
        ],
        cwd=project.root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)["result"]
    assert "missing labels" in report["stderr_tail"]
    assert report["logs"]["stderr"].endswith("stderr.log")
