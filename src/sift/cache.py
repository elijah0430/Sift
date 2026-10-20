from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .config import ProjectConfig
from .errors import SiftError
from .util import read_json, safe_id, sha256_bytes, sha256_file, state_locked, utc_now, write_json


def cache_key(
    *,
    code: list[str],
    inputs: list[str],
    config: list[str],
    seeds: list[int],
    fresh: bool = False,
    environment: list[str] | None = None,
) -> str:
    if not code or not inputs:
        raise SiftError("A computation cache key requires code and input identities.")
    payload: dict[str, object] = {
        "code": sorted(code),
        "inputs": sorted(inputs),
        "config": sorted(config),
        "seeds": seeds,
        "environment": sorted(environment or []),
    }
    if fresh:
        payload["trial_nonce"] = os.urandom(16).hex()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(canonical)


@state_locked
def put(config: ProjectConfig, key: str, source: Path) -> dict[str, str]:
    safe_id(key)
    if not source.is_file():
        raise SiftError(f"Cache source is not a file: {source}")
    content_hash = sha256_file(source)
    cache = config.state_dir / "cache"
    object_path = cache / "objects" / content_hash
    entry_path = cache / "entries" / f"{key}.json"
    if entry_path.exists():
        existing = read_json(entry_path)
        if existing["sha256"] != content_hash:
            raise SiftError("Cache key already refers to different content.")
        if not object_path.is_file() or sha256_file(object_path) != content_hash:
            raise SiftError("Existing cache content is corrupted.")
        return existing
    object_path.parent.mkdir(parents=True, exist_ok=True)
    if not object_path.exists():
        shutil.copy2(source, object_path)
    entry = {
        "key": key,
        "sha256": content_hash,
        "created_at": utc_now(),
        "source_name": source.name,
    }
    write_json(entry_path, entry)
    return entry


@state_locked
def get(config: ProjectConfig, key: str, destination: Path) -> dict[str, str]:
    safe_id(key)
    entry = read_json(config.state_dir / "cache" / "entries" / f"{key}.json")
    object_path = config.state_dir / "cache" / "objects" / safe_id(entry["sha256"])
    if not object_path.is_file() or sha256_file(object_path) != entry["sha256"]:
        raise SiftError(f"Cached object is unavailable or corrupted: {key}")
    if destination.exists():
        raise SiftError(f"Cache destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(object_path, destination)
    return entry


@state_locked
def drop(config: ProjectConfig, key: str) -> dict[str, str]:
    safe_id(key)
    for category in ("runs", "proposals"):
        for manifest_path in (config.state_dir / category).glob("*/manifest.json"):
            if key in read_json(manifest_path).get("cache_refs", []):
                raise SiftError(f"A recorded {category[:-1]} still references cache key {key}.")
    entry_path = config.state_dir / "cache" / "entries" / f"{key}.json"
    entry = read_json(entry_path)
    entry_path.unlink()
    return entry
