import pytest

from sift.errors import SiftError
from sift.lifecycle import create_exploration, preserve, restore_retirement, retire


def test_explore_preserve_retire_restore(project):
    scratch = create_exploration(project, "Odd Scoring", "Does it help?")
    (scratch / "result.txt").write_text("useful", encoding="utf-8")

    experiment = preserve(project, "odd-scoring", "scoring-ablation")
    assert (experiment / "result.txt").read_text(encoding="utf-8") == "useful"
    assert (experiment / "sift-record.json").exists()

    retirement_id = retire(project, "scratch/odd-scoring")
    assert not scratch.exists()
    restored = restore_retirement(project, retirement_id)
    assert (restored / "result.txt").read_text(encoding="utf-8") == "useful"


def test_retire_rejects_core(project):
    with pytest.raises(SiftError, match="limited"):
        retire(project, "src/demo")
