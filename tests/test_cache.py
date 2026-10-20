from pathlib import Path

import pytest

from sift.cache import cache_key, get, put
from sift.errors import SiftError


def test_reuse_key_is_stable_and_fresh_trial_is_unique():
    arguments = {
        "code": ["encoder-v3"],
        "inputs": ["dataset:abc"],
        "config": ["batch=32"],
        "seeds": [7],
    }
    assert cache_key(**arguments) == cache_key(**arguments)
    assert cache_key(**arguments, fresh=True) != cache_key(**arguments, fresh=True)


def test_cache_refuses_key_collision(project, tmp_path: Path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    put(project, "stable-key", first)

    with pytest.raises(SiftError, match="different content"):
        put(project, "stable-key", second)

    destination = tmp_path / "restored.txt"
    get(project, "stable-key", destination)
    assert destination.read_text(encoding="utf-8") == "one"
