import sys

from sift.snapshots import create_run, load_run, replay_run


def test_run_records_and_replays_exact_artifact(project):
    script = project.root / "make_result.py"
    script.write_text(
        "from pathlib import Path\nPath('outputs').mkdir(exist_ok=True)\n"
        "Path('outputs/result.txt').write_text('42')\n",
        encoding="utf-8",
    )
    command = f'"{sys.executable}" make_result.py'

    run_id, exit_code = create_run(project, command, ["outputs/result.txt"])
    replay_id, replay_exit, matches = replay_run(project, run_id)

    assert exit_code == 0
    assert replay_exit == 0
    assert matches is True
    manifest = load_run(project, run_id)
    assert manifest["replay_verified"] is True
    assert manifest["evidence_state"] == "replay-verified"
    assert (project.state_dir / "replays" / replay_id / "manifest.json").exists()


def test_run_records_inputs_seeds_metadata_and_verification(project):
    data = project.root / "data.txt"
    data.write_text("dataset", encoding="utf-8")
    script = project.root / "stochastic.py"
    script.write_text(
        "from pathlib import Path\nPath('result.txt').write_text('accepted')\n",
        encoding="utf-8",
    )
    command = f'"{sys.executable}" stochastic.py'
    verify = (
        f'"{sys.executable}" -c "from pathlib import Path; assert Path(\'result.txt\').exists()"'
    )

    run_id, exit_code = create_run(
        project,
        command,
        ["result.txt"],
        inputs=["dataset=data.txt"],
        seeds=[7, 9],
        metadata=["model=tiny"],
        verify_command=verify,
    )
    _, _, accepted = replay_run(project, run_id)
    manifest = load_run(project, run_id)

    assert exit_code == 0
    assert accepted is True
    assert manifest["seeds"] == [7, 9]
    assert manifest["metadata"]["model"] == "tiny"
    assert manifest["inputs"][0]["sha256"]
    assert manifest["evidence_state"] == "replay-verified"
