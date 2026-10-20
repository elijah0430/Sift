import pytest

from sift.cli import _guard, _policy, _skill_source
from sift.errors import SiftError


def test_agent_policy_reserves_approval_and_apply():
    policy = _policy()
    assert "sift promote approve" in policy["human_only"]
    assert "sift promote apply" in policy["human_only"]


def test_guard_rejects_human_only_command():
    with pytest.raises(SiftError, match="human"):
        _guard(["sift", "promote", "approve", "proposal-1"])


def test_skill_is_packaged_or_available_from_checkout():
    assert (_skill_source() / "SKILL.md").is_file()
