import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from sift.adapters import CommandArtifactStore
from sift.boundaries import check_boundaries
from sift.config import ProjectConfig, initialize_project
from sift.diagnostics import export_run
from sift.errors import SiftError
from sift.lifecycle import create_exploration, preserve, retire
from sift.promotion import apply, prepare, seal
from sift.snapshots import create_run, replay_run
from sift.util import read_json, safe_id, write_json


def python(script):
    return f'"{sys.executable}" -c "{script}"'


def test_scratch_may_be_incomplete_without_blocking_core(project):
    scratch = create_exploration(project, "unfinished")
    (scratch / "experiment.py").write_text("def still_working(:\n")
    assert not check_boundaries(project)
    retire(project, "scratch/unfinished")


def test_public_interfaces_and_independent_capabilities(project):
    core = project.root / "src" / "demo"
    (core / "first.py").write_text("import demo.second\n")
    (core / "second.py").write_text("VALUE=1\n")
    config = replace(project, independent=("demo.first", "demo.second"))
    assert any("independent" in item.rule for item in check_boundaries(config))
    scratch = create_exploration(project, "client")
    (scratch / "experiment.py").write_text("from demo.second import VALUE\n")
    config = replace(project, public_api=("demo.first",))
    assert any("public API" in item.rule for item in check_boundaries(config))


def test_core_cycles_are_detected(project):
    core = project.root / "src" / "demo"
    (core / "first.py").write_text("import demo.second\n")
    (core / "second.py").write_text("import demo.first\n")
    assert any("cycle" in item.rule for item in check_boundaries(project))


def test_preservation_uses_recorded_source_even_after_live_edits(project):
    scratch = create_exploration(project, "idea")
    experiment = scratch / "experiment.py"
    experiment.write_text("VALUE = 'recorded'\n")
    run_id, status = create_run(project, python("print('done')"))
    assert status == 0
    experiment.write_text("VALUE = 'changed later'\n")
    recipe = preserve(project, "idea", run_id=run_id)
    assert "recorded" in (recipe / "experiment.py").read_text()


def test_export_and_replay_from_another_project(project, tmp_path):
    script = project.root / "experiment.py"
    script.write_text("from pathlib import Path\nPath('metric.txt').write_text('42')\n")
    run_id, status = create_run(project, f'"{sys.executable}" experiment.py', ["metric.txt"])
    assert status == 0
    consumer = initialize_project(tmp_path / "another-project")
    destination = consumer.state_dir / "runs" / run_id
    export_run(project, run_id, destination)
    record = read_json(destination / "manifest.json")
    assert record["source_hash"]
    assert (destination / "source" / "experiment.py").exists()
    assert replay_run(consumer, run_id)[2]


def test_command_artifact_adapter_executes_real_transport_commands(tmp_path):
    remote = tmp_path / "remote"
    remote.mkdir()
    upload = [
        sys.executable,
        "-c",
        "import shutil,sys; shutil.copyfile(sys.argv[1],sys.argv[2])",
        "{source}",
        str(remote) + "/{sha256}",
    ]
    download = [
        sys.executable,
        "-c",
        "import shutil,sys; shutil.copyfile(sys.argv[1],sys.argv[2])",
        str(remote) + "/{sha256}",
        "{destination}",
    ]
    source = tmp_path / "input"
    source.write_text("transport")
    store = CommandArtifactStore(upload, download)
    reference = store.put(source)
    restored = store.get(reference, tmp_path / "output")
    assert restored.read_text() == "transport"


def test_shared_filesystem_launcher_and_replay(project):
    launcher = project.root / "launcher.py"
    launcher.write_text("import subprocess,sys\nraise SystemExit(subprocess.call(sys.argv[1:]))\n")
    prefix = f'"{sys.executable}" "{launcher}"'
    run_id, status = create_run(
        project,
        python("from pathlib import Path; Path('metric.txt').write_text('1')"),
        ["metric.txt"],
        launcher=prefix,
    )
    assert status == 0
    assert replay_run(project, run_id)[2]


def test_candidate_requires_revalidation_if_an_unmodified_core_file_changes(project):
    core = project.root / "src" / "demo"
    (core / "baseline.py").write_text("VALUE = 1\n")
    proposal_id, candidate = prepare(project, "Add a helper")
    (candidate / "src" / "demo" / "helper.py").write_text("VALUE = 2\n")
    digest = seal(project, proposal_id, (python("print('ok')"),))
    write_json(
        project.state_dir / "proposals" / proposal_id / "approval.json",
        {"digest": digest, "reviewer": "test human"},
    )
    (core / "baseline.py").write_text("VALUE = 7\n")
    with pytest.raises(Exception, match="changed since review"):
        apply(project, proposal_id)


def test_interrupted_approved_application_is_resumable(project, monkeypatch):
    proposal_id, candidate = prepare(project, "Add two helpers")
    for name in ("first", "second"):
        (candidate / "src" / "demo" / f"{name}.py").write_text("VALUE = 1\n")
    digest = seal(project, proposal_id, (python("print('ok')"),))
    proposal = project.state_dir / "proposals" / proposal_id
    write_json(proposal / "approval.json", {"digest": digest, "reviewer": "test human"})
    original_copy = shutil.copy2
    calls = 0

    def interrupted(source, destination, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated interruption")
        return original_copy(source, destination, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(shutil, "copy2", interrupted)
        with pytest.raises(OSError, match="simulated"):
            apply(project, proposal_id)
    assert read_json(proposal / "manifest.json")["status"] == "applying"
    apply(project, proposal_id)
    assert read_json(proposal / "manifest.json")["status"] == "applied"


def test_cli_json_has_named_identifiers_and_agent_session_cannot_approve(project):
    env = os.environ.copy()
    env["SIFT_ACTOR"] = "agent"
    result = subprocess.run(
        [sys.executable, "-m", "sift", "--json", "explore", "cli"],
        cwd=project.root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["result"]["path"]
    denied = subprocess.run(
        [sys.executable, "-m", "sift", "--json", "promote", "approve", "not-a-proposal"],
        cwd=project.root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert denied.returncode == 2
    assert "human" in json.loads(denied.stdout)["error"].lower()


@pytest.mark.parametrize("value", ["../outside", "/tmp/record", ".", "..", "a/b", "a\\b"])
def test_identifiers_cannot_escape_the_store(value):
    with pytest.raises(SiftError):
        safe_id(value)


def test_optional_notebook_template_is_valid_python(project):
    scratch = create_exploration(project, "notebook", notebook=True)
    content = (scratch / "notebook.py").read_text()
    compile(content, "notebook.py", "exec")
    assert "marimo>=" in content


def test_example_core_imports_and_runs_without_scratch_or_experiments(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/minimal/src"
    library = tmp_path / "core-only"
    shutil.copytree(source, library)
    program = (
        f"import sys; sys.path.insert(0, {str(library)!r}); "
        "from toy_research import evaluate; "
        "assert evaluate([1,2],[2,4],lambda x:x)['score']==1.5"
    )
    subprocess.run([sys.executable, "-I", "-c", program], cwd=tmp_path, check=True)


def test_example_iterations_run_against_two_datasets_and_models(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/minimal"
    root = tmp_path / "study"
    shutil.copytree(
        source, root, ignore=shutil.ignore_patterns(".research", "results", "__pycache__")
    )
    config = ProjectConfig.load(root)
    assert not check_boundaries(config)
    original, status = create_run(
        config,
        "python scratch/baseline/experiment.py",
        ["results/metrics.json"],
        inputs=["dataset=data/original.json"],
    )
    assert status == 0
    expanded, status = create_run(
        config,
        "python scratch/expanded/experiment.py",
        ["results/metrics.json"],
        inputs=["dataset=data/shifted.json"],
    )
    assert status == 0
    first = read_json(config.state_dir / "runs" / original / "artifacts/results/metrics.json")
    second = read_json(config.state_dir / "runs" / expanded / "artifacts/results/metrics.json")
    assert first["score"] == 1.5
    assert second["score"] == 0.0
    assert replay_run(config, original)[2]
