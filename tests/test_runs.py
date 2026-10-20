import json
import sys

from sift.snapshots import create_run, replay_run


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
    manifest = json.loads(
        (project.state_dir / "runs" / run_id / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["replay_verified"] is True
    assert (project.state_dir / "replays" / replay_id / "manifest.json").exists()
