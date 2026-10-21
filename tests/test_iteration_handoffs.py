import json
import sys
from dataclasses import replace

import pytest

from sift.cli import _parser, _print_experiment_runs, execute
from sift.config import ProjectConfig
from sift.diagnostics import export_run
from sift.errors import SiftError
from sift.handoff import publish_research, seed_research
from sift.harness import launch
from sift.lifecycle import create_exploration, preserve
from sift.portability import import_run
from sift.promotion import prepare, review_material, seal
from sift.snapshots import create_run, replay_run
from sift.util import copy_tree, read_json, tree_hash, write_json
from sift.workspace import (
    archive_path,
    comparison_columns,
    resolve_run,
    select_runs,
    workspace_status,
)


def test_repeat_run_keeps_options_and_allows_an_explicit_reset(project, monkeypatch):
    scratch = create_exploration(project, "study")
    (scratch / "experiment.py").write_text(
        "from pathlib import Path\nPath('answer.txt').write_text(Path('data.txt').read_text())\n",
        encoding="utf-8",
    )
    (project.root / "data.txt").write_text("42", encoding="utf-8")
    monkeypatch.chdir(project.root)
    parse = _parser().parse_args
    assert (
        execute(
            parse(
                [
                    "--json",
                    "experiment",
                    "run",
                    "study",
                    "--input",
                    "data=data.txt",
                    "--artifact",
                    "answer.txt",
                    "--seed",
                    "7",
                    "--meta",
                    "method=baseline",
                ]
            )
        )
        == 0
    )
    assert execute(parse(["--json", "experiment", "run", "study"])) == 0
    manifests = [read_json(path) for path in (project.state_dir / "runs").glob("*/manifest.json")]
    assert len(manifests) == 2
    assert all(
        item["declared_artifacts"] == ["answer.txt"]
        and item["inputs"][0]["name"] == "data"
        and item["seeds"] == [7]
        and item["metadata"]["method"] == "baseline"
        for item in manifests
    )
    assert execute(parse(["--json", "experiment", "run", "study", "--reset-options"])) == 0
    recipe = read_json(scratch / "sift-record.json")
    assert recipe["inputs"] == recipe["artifacts"] == recipe["seeds"] == []


def test_ignored_inputs_keep_relative_paths_and_replay_uses_original_data(project):
    config = replace(project, ignores=("data",))
    data = project.root / "data"
    data.mkdir()
    (data / "eval.json").write_text('{"score": 42}', encoding="utf-8")
    script = project.root / "experiment.py"
    script.write_text(
        "from pathlib import Path\n"
        "Path('answer.json').write_text(Path('data/eval.json').read_text())\n",
        encoding="utf-8",
    )
    run_id, code = create_run(
        config, f'"{sys.executable}" experiment.py', ["answer.json"], inputs=["eval=data/eval.json"]
    )
    assert code == 0
    assert not (config.state_dir / "runs" / run_id / "source/data").exists()
    (data / "eval.json").write_text('{"score": 99}', encoding="utf-8")
    assert replay_run(config, run_id)[2]
    with pytest.raises(SiftError, match="Input file does not exist"):
        create_run(config, f'"{sys.executable}" experiment.py', inputs=["eval=data/typo.json"])


def test_experiment_bundle_round_trip_and_saved_code_extension_without_state(project, tmp_path):
    scratch = create_exploration(project, "study")
    (scratch / "experiment.py").write_text(
        "from pathlib import Path\nPath('answer.txt').write_text('42')\n", encoding="utf-8"
    )
    run_id, code = create_run(
        project,
        f'"{sys.executable}" scratch/study/experiment.py',
        ["answer.txt"],
        exploration="study",
    )
    assert code == 0
    preserve(project, "study", "baseline", run_id)
    clone = tmp_path / "clone"
    copy_tree(project.root, clone, project.snapshot_ignores)
    consumer = ProjectConfig.load(clone)
    with pytest.raises(SiftError, match="experiment import BUNDLE"):
        resolve_run(consumer, "baseline")
    extension = create_exploration(consumer, "extension", from_run="baseline")
    assert "scratch/extension/experiment.py" in read_json(extension / "sift-record.json")["command"]
    assert read_json(extension / "sift-record.json")["parent_run"] is None
    bundle = export_run(project, "run-" + run_id.rsplit("-", 1)[-1], tmp_path / "bundle")
    assert (bundle / "README.md").is_file() and not (bundle / "work").exists()
    assert import_run(consumer, bundle) == (run_id, True)
    assert import_run(consumer, bundle) == (run_id, False)
    assert resolve_run(consumer, "baseline") == run_id
    assert replay_run(consumer, run_id)[2]
    (bundle / "artifacts/answer.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(SiftError, match="corrupted"):
        import_run(consumer, bundle)


def test_agent_inherits_history_and_publishes_rechecked_unapproved_proposal(project):
    scratch = create_exploration(project, "baseline")
    (scratch / "experiment.py").write_text(
        "from pathlib import Path\nPath('answer.txt').write_text('42')\n", encoding="utf-8"
    )
    run_id, _ = create_run(
        project,
        f'"{sys.executable}" scratch/baseline/experiment.py',
        ["answer.txt"],
        exploration="baseline",
    )
    preserve(project, "baseline", "baseline-result", run_id)
    before = tree_hash(project.root / "src", ignores=())
    actor = project.root / "scratch/agent.py"
    actor.write_text(
        "import json,subprocess,sys\nfrom pathlib import Path\n"
        "def sift(*args):\n"
        "    p=subprocess.run([sys.executable,'-m','sift','--json',*args],"
        "capture_output=True,text=True,check=True)\n"
        "    return json.loads(p.stdout)['result']\n"
        "sift('experiment','new','extension','--from-run','baseline-result')\n"
        "p=sift('core','propose','--title','Reusable helper','--from-run','baseline-result')\n"
        "Path(p['candidate'],'src/demo/helper.py').write_text('VALUE = 42\\n')\n"
        "sift('core','propose',p['id'],'--ready','--check',"
        'f\'"{sys.executable}" -c "print(42)"\')\n',
        encoding="utf-8",
    )
    report = launch(project, [sys.executable, "scratch/agent.py"])
    assert report["exit_code"] == 0
    assert run_id in report["inherited_runs"]
    assert len(report["research"]["proposals"]) == 1
    proposal = report["research"]["proposals"][0]
    material = review_material(project, proposal["id"])
    assert material["status"] == "ready"
    assert material["baseline_run"] == run_id
    assert not (project.state_dir / "proposals" / proposal["id"] / "approval.json").exists()
    assert tree_hash(project.root / "src", ignores=()) == before
    status = workspace_status(project)
    assert status["needs_review"] == 1 and status["draft_proposals"] == 0


def test_modified_inherited_history_is_rejected(project):
    run_id, _ = create_run(project, f'"{sys.executable}" -c "print(42)"')
    _, candidate = prepare(project, "Session")
    seed_research(project, candidate)
    isolated = ProjectConfig.load(candidate)
    manifest = read_json(isolated.state_dir / "runs" / run_id / "manifest.json")
    manifest["metadata"]["method"] = "changed"
    write_json(isolated.state_dir / "runs" / run_id / "manifest.json", manifest)
    with pytest.raises(SiftError, match="collision"):
        publish_research(project, candidate)


def test_agent_receives_current_declared_data_excluded_from_snapshots(project):
    data = project.root / "data"
    data.mkdir()
    (data / "eval.json").write_text('{"value": 1}', encoding="utf-8")
    project = replace(project, ignores=("data",))
    _, code = create_run(
        project, f'"{sys.executable}" -c "print(42)"', inputs=["eval=data/eval.json"]
    )
    assert code == 0
    (data / "eval.json").write_text('{"value": 2}', encoding="utf-8")
    _, candidate = prepare(project, "Session")
    assert not (candidate / "data").exists()
    seed_research(project, candidate)
    assert json.loads((candidate / "data/eval.json").read_text())["value"] == 2


def test_external_input_path_is_stable_in_results_and_captured_data_stays_immutable(
    project, tmp_path
):
    external = tmp_path / "external.json"
    external.write_text('{"value": 42}', encoding="utf-8")
    (project.root / "experiment.py").write_text(
        "import json,os\nfrom pathlib import Path\n"
        "path=Path(os.environ['SIFT_INPUT_DATA'])\n"
        "Path('answer.json').write_text(json.dumps({'input':str(path),'data':json.loads(path.read_text())}))\n"
        "path.write_text('changed working copy')\n",
        encoding="utf-8",
    )
    run_id, code = create_run(
        project, f'"{sys.executable}" experiment.py', ["answer.json"], inputs=[f"data={external}"]
    )
    assert code == 0 and replay_run(project, run_id)[2]
    assert external.read_text() == '{"value": 42}'
    assert (project.state_dir / "runs" / run_id / "inputs/data").read_text() == '{"value": 42}'


def test_long_workspace_proposal_can_be_copied_and_sealed(project):
    _, candidate = prepare(project, "Session")
    nested = ProjectConfig.load(candidate)
    identifier, deeper = prepare(nested, "Helper")
    target = deeper / "src/demo" / ("nested" * 10) / "helper.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 42\n", encoding="utf-8")
    seal(nested, identifier, (f'"{sys.executable}" -c "print(42)"',))
    assert (
        read_json(nested.state_dir / "proposals" / identifier / "manifest.json")["status"]
        == "ready"
    )


def test_comparison_is_compact_filterable_and_sorted(capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "100")
    rows = [
        {
            "run": f"run-{index}",
            "status": "completed",
            "scratch": "study",
            "seed": str(index % 3),
            "metadata.method": "baseline" if index < 3 else "new",
            "result.results/metrics.accuracy": index / 10,
            "result.results/metrics.config.method": "baseline" if index < 3 else "new",
        }
        for index in range(6)
    ]
    table = {"columns": list(rows[0]), "rows": rows}
    assert "result.results/metrics.config.method" not in comparison_columns(table)
    _print_experiment_runs(table)
    text = capsys.readouterr().out
    assert len(text.splitlines()) < 16
    selected = select_runs(table, "method,seed,accuracy", ("method=new",), "accuracy", True)
    assert [row["run"] for row in selected["rows"]] == ["run-5", "run-4", "run-3"]
    assert len(selected["columns"]) == 4
    with pytest.raises(SiftError, match="Unknown column"):
        select_runs(table, "missing")


def test_draft_and_archive_are_discoverable(project, monkeypatch, capsys):
    identifier, _ = prepare(project, "Share the scorer")
    monkeypatch.chdir(project.root)
    assert execute(_parser().parse_args(["status"])) == 0
    assert "Share the scorer" in capsys.readouterr().out
    assert execute(_parser().parse_args(["core", "list"])) == 0
    assert identifier in capsys.readouterr().out
    create_exploration(project, "old-study")
    assert archive_path(project, "old-study") == "scratch/old-study"
    assert execute(_parser().parse_args(["experiment", "archive", "old-study"])) == 0
    assert execute(_parser().parse_args(["experiment", "archive", "--list"])) == 0
    assert "--restore" in capsys.readouterr().out
