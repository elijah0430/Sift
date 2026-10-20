from __future__ import annotations

import os
import platform
import sqlite3
from pathlib import Path

from .config import ProjectConfig
from .errors import SiftError
from .util import copy_tree, read_json, safe_id, tree_hash, utc_now, write_json


def process_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            status = wintypes.DWORD()
            return (
                bool(kernel.GetExitCodeProcess(handle, ctypes.byref(status)))
                and status.value == 259
            )
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def doctor(config: ProjectConfig, recover: bool = False) -> dict:
    issues, active = [], []
    lock = config.state_dir / "transaction.lock"
    if lock.exists():
        try:
            pid = int(lock.read_text().strip())
            alive = process_alive(pid)
        except ValueError:
            alive = True
        if alive:
            active.append({"type": "transaction", "path": str(lock)})
        elif recover:
            lock.unlink()
        else:
            issues.append({"type": "stale-lock", "action": "sift doctor --recover"})
    for path in (config.state_dir / "runs").glob("*/manifest.json"):
        record = read_json(path)
        if record.get("status") not in {"running", "preparing"}:
            continue
        local = record.get("host") == platform.node()
        process_path = path.parent / "process.json"
        process = read_json(process_path) if process_path.exists() else {}
        alive = not local or any(
            process_alive(pid) for pid in [record.get("owner_pid"), process.get("pid")] if pid
        )
        if alive:
            active.append({"type": "run", "id": record["id"], "local": local})
        elif recover:
            record.update(
                status="interrupted",
                finished_at=utc_now(),
                error="Recovered after owner and child processes ended.",
            )
            write_json(path, record)
        else:
            issues.append(
                {"type": "interrupted-run", "id": record["id"], "action": "sift doctor --recover"}
            )
    for path in (config.state_dir / "proposals").glob("*/manifest.json"):
        record = read_json(path)
        if record.get("status") == "applying":
            issues.append(
                {
                    "type": "interrupted-application",
                    "id": record["id"],
                    "action": f"Human: sift promote apply {record['id']}",
                }
            )
    return {"issues": issues, "active": active, "recovered": recover}


def rebuild_index(config: ProjectConfig) -> int:
    config.state_dir.mkdir(exist_ok=True)
    connection = sqlite3.connect(config.state_dir / "index.sqlite3")
    count = 0
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, path TEXT)")
        connection.execute("DELETE FROM records")
        for kind in ("runs", "replays", "proposals", "archive", "gc"):
            name = "plan.json" if kind == "gc" else "manifest.json"
            for path in (config.state_dir / kind).glob(f"*/{name}"):
                read_json(path)
                connection.execute(
                    "INSERT INTO records VALUES (?, ?, ?)", (kind, path.parent.name, str(path))
                )
                count += 1
        connection.commit()
    finally:
        connection.close()
    return count


def export_run(config: ProjectConfig, run_id: str, destination: Path) -> Path:
    source = config.state_dir / "runs" / safe_id(run_id)
    record = read_json(source / "manifest.json")
    if tree_hash(source / "source", ignores=()) != record["source_hash"]:
        raise SiftError("The source snapshot is corrupted.")
    if destination.resolve().is_relative_to(source.resolve()):
        raise SiftError("Export destination must not be inside its source record.")
    copy_tree(source, destination, ignores=(".venv", "__pycache__"))
    return destination
