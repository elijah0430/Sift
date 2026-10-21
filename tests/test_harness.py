import json
import subprocess
import sys
from pathlib import Path

import pytest

from sift.cli import _guard, _policy, _skill_source
from sift.errors import SiftError
from sift.harness import guard


def test_agent_policy_reserves_approval_and_apply():
    policy = _policy()
    assert "sift review" in policy["human_only"]
    assert "sift promote approve" in policy["human_only"]
    assert "sift promote apply" in policy["human_only"]


def test_guard_rejects_human_only_command():
    with pytest.raises(SiftError, match="human"):
        _guard(["sift", "promote", "approve", "proposal-1"])
    with pytest.raises(SiftError, match="human"):
        _guard(["sift", "review", "proposal-1"])
    with pytest.raises(SiftError, match="human"):
        _guard(["sift", "core", "review", "proposal-1"])


def test_guard_allows_research_lifecycle_commands():
    for command in (
        ["sift", "status"],
        ["sift", "experiment", "new", "baseline"],
        ["sift", "core", "propose", "--title", "Shared loader"],
        ["sift", "propose", "--title", "Shared loader"],
        ["sift", "reproduce", "baseline-study"],
        ["sift", "archive", "scratch/old-idea"],
    ):
        assert guard(command)["allowed"] is True


def test_skill_is_packaged_or_available_from_checkout():
    assert (_skill_source() / "SKILL.md").is_file()


def test_bundled_policy_matches_the_runtime_host_contract():
    root = Path(__file__).resolve().parents[1]
    assert json.loads((root / "harness/policy.json").read_text()) == _policy()


def test_launcher_failure_is_not_reported_as_cli_success(project):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sift",
            "--json",
            "harness",
            "launch",
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(7)",
        ],
        cwd=project.root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 7
    assert json.loads(result.stdout)["result"]["exit_code"] == 7
