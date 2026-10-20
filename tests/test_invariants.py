import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sift.adapters import LocalArtifactStore
from sift.boundaries import check_boundaries
from sift.cache import cache_key
from sift.diagnostics import doctor, process_alive, rebuild_index
from sift.errors import SiftError
from sift.gc import apply as gc_apply
from sift.gc import plan, set_pin
from sift.harness import check_write, guard, launch
from sift.lifecycle import create_exploration, preserve, restore_retirement, retire
from sift.promotion import apply, prepare, seal
from sift.snapshots import create_run, load_run, replay_run
from sift.util import read_json, sha256_file, write_json


def command(script):
    return f'"{sys.executable}" -c "{script}"'


def sealed_proposal(project):
    proposal_id, candidate = prepare(project, "A maintained capability", "Used by two studies.")
    target = candidate / "src" / "demo" / "method.py"
    target.write_text("def score(value):\n    return value * 2\n", encoding="utf-8")
    digest = seal(
        project, proposal_id, (command("from demo.method import score; assert score(3)==6"),)
    )
    proposal = project.state_dir / "proposals" / proposal_id
    assert read_json(proposal / "manifest.json")["status"] == "ready"
    write_json(proposal / "approval.json", {"digest": digest, "reviewer": "test human"})
    return proposal_id, candidate


def test_post_review_candidate_edit_cannot_be_applied(project):
    proposal_id, candidate = sealed_proposal(project)
    (candidate / "src" / "demo" / "method.py").write_text("raise RuntimeError('changed')\n")
    with pytest.raises(SiftError, match="changed"):
        apply(project, proposal_id)
    assert not (project.root / "src" / "demo" / "method.py").exists()


def test_review_diff_and_test_results_are_bound_to_digest(project):
    proposal_id, _ = sealed_proposal(project)
    proposal = project.state_dir / "proposals" / proposal_id
    record = read_json(proposal / "manifest.json")
    record["checks"][0]["exit_code"] = 17
    write_json(proposal / "manifest.json", record)
    with pytest.raises(SiftError, match="changed"):
        apply(project, proposal_id)


def test_additional_checks_cannot_replace_configured_checks(project):
    config_path = project.root / "research.toml"
    config_path.write_text(
        config_path.read_text().replace(
            "commands = []",
            'commands = ["python -c \\"raise SystemExit(9)\\""]',
        )
    )
    from sift.config import ProjectConfig

    config = ProjectConfig.load(project.root)
    proposal_id, candidate = prepare(config, "Fails baseline check")
    (candidate / "src" / "demo" / "new.py").write_text("VALUE = 1\n")
    seal(config, proposal_id, (command("print('extra passed')"),))
    record = read_json(config.state_dir / "proposals" / proposal_id / "manifest.json")
    assert record["status"] == "checks_failed"


def test_failed_reseal_revokes_prior_approval(project):
    proposal_id, candidate = sealed_proposal(project)
    (candidate / "src" / "demo" / "method.py").unlink()
    with pytest.raises(SiftError):
        seal(project, proposal_id)
    assert not (project.state_dir / "proposals" / proposal_id / "approval.json").exists()


def test_missing_output_cannot_reuse_an_old_output(project):
    output = project.root / "result.txt"
    output.write_text("old result")
    run_id, exit_code = create_run(project, command("pass"), ["result.txt"])
    assert exit_code != 0
    assert load_run(project, run_id)["status"] == "failed"
    assert output.read_text() == "old result"


def test_execution_cannot_modify_its_saved_source(project):
    script = project.root / "experiment.py"
    script.write_text(
        "from pathlib import Path\n"
        "Path('result.txt').write_text('new')\n"
        "Path('experiment.py').write_text('raise RuntimeError()')\n"
    )
    run_id, status = create_run(project, f'"{sys.executable}" experiment.py', ["result.txt"])
    assert status == 0
    snapshot = project.state_dir / "runs" / run_id / "source" / "experiment.py"
    assert snapshot.read_text() == script.read_text()
    original_manifest = sha256_file(snapshot.parent.parent / "manifest.json")
    assert replay_run(project, run_id)[2]
    assert sha256_file(snapshot.parent.parent / "manifest.json") == original_manifest


def test_replaying_a_failed_run_does_not_verify_failure(project):
    run_id, status = create_run(project, command("raise SystemExit(4)"))
    assert status == 4
    with pytest.raises(SiftError, match="successful"):
        replay_run(project, run_id)


def test_unresolved_input_identity_is_not_replay_verified(project):
    run_id, status = create_run(
        project,
        command("from pathlib import Path; Path('result.txt').write_text('ok')"),
        ["result.txt"],
        inputs=["checkpoint=model:mutable-tag"],
    )
    assert status == 0
    assert load_run(project, run_id)["evidence_state"] == "recorded"
    assert not replay_run(project, run_id)[2]


def test_cache_keys_change_with_scientific_inputs_and_environment():
    base = dict(code=["a"], inputs=["data-v1"], config=["batch=1"], seeds=[1])
    baseline = cache_key(**base)
    for field, new_value in [
        ("code", ["b"]),
        ("inputs", ["data-v2"]),
        ("config", ["batch=2"]),
        ("seeds", [2]),
    ]:
        assert cache_key(**{**base, field: new_value}) != baseline
    assert cache_key(**base, environment=["torch-v2"]) != baseline


def test_archive_corruption_is_detected_before_restore(project):
    source = create_exploration(project, "idea")
    retirement = retire(project, source.relative_to(project.root).as_posix())
    payload = project.state_dir / "archive" / retirement / "payload" / "experiment.py"
    payload.write_text("corrupted")
    with pytest.raises(SiftError, match="corrupted"):
        restore_retirement(project, retirement)


def test_new_pin_invalidates_cleanup_plan(project):
    create_exploration(project, "idea")
    retired = retire(project, "scratch/idea")
    plan_id, digest, _ = plan(project, datetime.now(UTC) + timedelta(days=91))
    set_pin(project, retired, True)
    with pytest.raises(SiftError, match="pin or reference"):
        gc_apply(project, plan_id, digest[:12])


def test_retirement_rejects_dependencies_from_maintained_code(project):
    create_exploration(project, "idea")
    (project.root / "src" / "demo" / "bad.py").write_text("import scratch.idea.experiment\n")
    with pytest.raises(SiftError, match="still depends"):
        retire(project, "scratch/idea")


def test_indirect_and_literal_dynamic_imports_are_checked(project):
    (project.root / "src" / "demo" / "method.py").write_text("import helper\n")
    (project.root / "helper.py").write_text(
        "import importlib\nimportlib.import_module('scratch.idea')\n"
    )
    assert any("indirectly" in item.rule for item in check_boundaries(project))


def test_invalid_python_does_not_silently_pass_checks(project):
    (project.root / "src" / "demo" / "method.py").write_text("def broken(:\n")
    assert any("cannot analyze" in item.rule for item in check_boundaries(project))


def test_harness_rejects_module_invocation_of_human_command():
    with pytest.raises(SiftError, match="human"):
        guard([sys.executable, "-m", "sift", "promote", "approve", "x"])


def test_harness_checks_paths_and_launches_in_a_candidate(project):
    with pytest.raises(SiftError, match="restricted"):
        check_write(project, "src/demo/method.py")
    report = launch(
        project,
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('src/demo/local.py').write_text('VALUE=3')",
        ],
    )
    assert report["original_core_unchanged"]
    assert not (project.root / "src" / "demo" / "local.py").exists()
    assert (Path(report["candidate"]) / "src" / "demo" / "local.py").exists()


def test_doctor_uses_process_evidence_and_rebuildable_index(project):
    assert process_alive(os.getpid())
    directory = project.state_dir / "runs" / "run-interrupted"
    write_json(
        directory / "manifest.json",
        {
            "id": "run-interrupted",
            "status": "running",
            "owner_pid": 2147483647,
            "host": __import__("platform").node(),
        },
    )
    assert doctor(project)["issues"][0]["type"] == "interrupted-run"
    assert doctor(project, recover=True)["recovered"]
    assert read_json(directory / "manifest.json")["status"] == "interrupted"
    assert rebuild_index(project) == 1


def test_content_addressed_artifact_adapter_roundtrip(tmp_path):
    original = tmp_path / "input.txt"
    original.write_text("immutable")
    store = LocalArtifactStore(tmp_path / "store")
    reference = store.put(original)
    restored = store.get(reference, tmp_path / "restored.txt")
    assert restored.read_text() == "immutable"


def test_new_state_directory_is_excluded_from_snapshots(project):
    path = project.root / "research.toml"
    path.write_text(path.read_text().replace('state = ".research"', 'state = ".labstate"'))
    from sift.config import ProjectConfig

    config = ProjectConfig.load(project.root)
    run_id, status = create_run(config, command("print('ok')"))
    assert status == 0
    assert not (config.state_dir / "runs" / run_id / "source" / ".labstate").exists()


def test_baseline_survives_extensions_promotion_and_retirement(project):
    core = project.root / "src" / "demo" / "method.py"
    core.write_text("def score(value):\n    return value\n")
    scratch = create_exploration(project, "baseline")
    script = scratch / "experiment.py"
    script.write_text(
        "from pathlib import Path\nfrom demo.method import score\n"
        "Path('metric.txt').write_text(str(score(3)))\n"
    )
    run_id, status = create_run(
        project,
        f'"{sys.executable}" scratch/baseline/experiment.py',
        ["metric.txt"],
    )
    assert status == 0
    preserve(project, "baseline", run_id=run_id)
    proposal_id, _ = sealed_proposal(project)
    apply(project, proposal_id)
    retire(project, "scratch/baseline")
    assert replay_run(project, run_id)[2]
    assert (project.state_dir / "runs" / run_id / "artifacts" / "metric.txt").read_text() == "3"
