from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from .adapters import runner_for
from .config import ProjectConfig
from .errors import SiftError
from .util import (
    contained_path,
    copy_tree,
    python_runtime,
    read_json,
    safe_id,
    sha256_file,
    short_id,
    slugify,
    tree_hash,
    utc_now,
    write_json,
)


def _git_metadata(root: Path) -> dict:
    if not shutil.which("git"):
        return {"commit": None, "dirty": None}

    def output(*args):
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    return {
        "commit": output("rev-parse", "HEAD"),
        "branch": output("branch", "--show-current"),
        "dirty": bool(output("status", "--porcelain")),
    }


def _named_values(values: Iterable[str]) -> dict[str, str]:
    result = {}
    for value in values:
        if "=" not in value:
            raise SiftError(f"Expected NAME=VALUE: {value}")
        name, content = value.split("=", 1)
        if not name or not content or name in result:
            raise SiftError(f"Expected a unique NAME=VALUE: {value}")
        safe_id(name)
        result[name] = content
    return result


def execution_environment(config: ProjectConfig, work: Path) -> dict[str, str]:
    env = os.environ.copy()
    managed = work / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    virtual = (
        work / ".venv"
        if managed.is_file()
        else Path(env.get("VIRTUAL_ENV", str(config.root / ".venv")))
    )
    scripts = virtual / ("Scripts" if os.name == "nt" else "bin")
    interpreter = scripts / ("python.exe" if os.name == "nt" else "python")
    discovered = shutil.which("python", path=env.get("PATH", ""))
    if interpreter.is_file():
        env["PATH"] = str(scripts) + os.pathsep + env.get("PATH", "")
    elif not discovered or "WindowsApps" in discovered:
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = os.pathsep.join([*(str(work / path) for path in config.core), str(work)])
    return env


def _environment(root: Path, config: ProjectConfig | None = None) -> dict:
    lockfiles = {
        name: sha256_file(root / name)
        for name in (
            "pyproject.toml",
            "uv.lock",
            "requirements.txt",
            "environment.yml",
            "poetry.lock",
            "Dockerfile",
        )
        if (root / name).is_file()
    }
    packages = sorted(
        {
            f"{distribution.metadata['Name']}=={distribution.version}"
            for distribution in importlib.metadata.distributions()
            if distribution.metadata.get("Name")
        }
    )
    observation = {
        "sift_runtime": python_runtime(),
        "sift_environment_packages": packages,
        "lockfiles": lockfiles,
        "hardware": {
            "machine": platform.machine(),
            "system": platform.system(),
            "release": platform.release(),
        },
    }
    if config:
        env = execution_environment(config, root)
        target = shutil.which("python", path=env["PATH"])
        if target and Path(target).resolve() != Path(sys.executable).resolve():
            query = subprocess.run(
                [
                    target,
                    "-I",
                    "-c",
                    "import importlib.metadata as m,json,sys; "
                    "print(json.dumps({'runtime':sys.version,'packages':sorted("
                    "d.metadata['Name']+'=='+d.version for d in m.distributions() "
                    "if d.metadata.get('Name'))}))",
                ],
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            if query.returncode == 0:
                observation["target_python"] = json.loads(query.stdout)
    return observation


def _input_records(config: ProjectConfig, run_dir: Path, values: Iterable[str]) -> list[dict]:
    records = []
    source = run_dir / "source"
    for name, value in _named_values(values).items():
        original = Path(value).expanduser()
        if not original.is_absolute():
            original = config.root / original
        try:
            relative = original.resolve().relative_to(config.root.resolve())
            captured = source / relative
        except ValueError:
            relative, captured = None, None
        if original.exists():
            if captured is None or not captured.exists():
                captured = run_dir / "inputs" / name
                if original.is_dir():
                    copy_tree(original, captured, ignores=())
                else:
                    captured.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, captured)
            kind = "directory" if captured.is_dir() else "file"
            digest = tree_hash(captured, ignores=()) if captured.is_dir() else sha256_file(captured)
            records.append(
                {
                    "name": name,
                    "value": value,
                    "kind": kind,
                    "sha256": digest,
                    "captured": str(captured.relative_to(run_dir)).replace("\\", "/"),
                    "source_relative": relative.as_posix() if relative is not None else None,
                }
            )
        else:
            records.append({"name": name, "value": value, "kind": "identifier", "captured": None})
    return records


def _execute(
    config: ProjectConfig,
    run_dir: Path,
    work: Path,
    command: str,
    *,
    environment: str = "current",
    env_extra: dict[str, str] | None = None,
    launcher: str | None = None,
) -> int:
    env = execution_environment(config, work)
    env.update(env_extra or {})
    if environment == "uv":
        if not (work / "uv.lock").is_file():
            raise SiftError("The uv environment requires a frozen project uv.lock.")
        selector = env.get("UV_PYTHON") or (
            (work / ".python-version").read_text().strip()
            if (work / ".python-version").is_file()
            else shutil.which("python", path=env["PATH"])
        )
        with (run_dir / "environment.log").open("w", encoding="utf-8") as setup_log:
            prepared = subprocess.run(
                ["uv", "sync", "--frozen", "--no-dev", "--python", selector or sys.executable],
                cwd=work,
                env=env,
                check=False,
                stdout=setup_log,
                stderr=subprocess.STDOUT,
            )
        if prepared.returncode:
            raise SiftError("Could not reconstruct the locked uv environment; see environment.log.")
        scripts = work / ".venv" / ("Scripts" if os.name == "nt" else "bin")
        env["PATH"] = str(scripts) + os.pathsep + env["PATH"]
        write_json(run_dir / "managed-environment.json", _environment(work, config))
    with (
        (run_dir / "stdout.log").open("w", encoding="utf-8") as stdout,
        (run_dir / "stderr.log").open("w", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(
            runner_for(launcher).argv(command),
            cwd=work,
            env=env,
            stdout=stdout,
            stderr=stderr,
        )
        write_json(
            run_dir / "process.json",
            {"pid": process.pid, "host": platform.node(), "started_at": utc_now()},
        )
        try:
            return process.wait()
        except KeyboardInterrupt:
            process.terminate()
            process.wait()
            raise


def _run_verification(
    run_dir: Path, work: Path, command: str, config: ProjectConfig, reference: Path
) -> dict:
    env = execution_environment(config, work)
    env["SIFT_REFERENCE"] = str(reference)
    with (
        (run_dir / "verify.stdout.log").open("w", encoding="utf-8") as stdout,
        (run_dir / "verify.stderr.log").open("w", encoding="utf-8") as stderr,
    ):
        result = subprocess.run(
            command,
            cwd=work,
            env=env,
            shell=True,
            check=False,
            stdout=stdout,
            stderr=stderr,
        )
    return {"command": command, "exit_code": result.returncode}


def create_run(
    config: ProjectConfig,
    command: str,
    artifacts: Iterable[str] = (),
    parent: str | None = None,
    change: str | None = None,
    inputs: Iterable[str] = (),
    seeds: Iterable[int] = (),
    metadata: Iterable[str] = (),
    verify_command: str | None = None,
    environment: str = "current",
    cache_refs: Iterable[str] = (),
    launcher: str | None = None,
    exploration: str | None = None,
) -> tuple[str, int]:
    metadata_values = _named_values(metadata)
    input_values, seed_values, output_paths = list(inputs), list(seeds), list(artifacts)
    _named_values(input_values)
    for value in output_paths:
        contained_path(config.root, value)
    if parent:
        read_json(config.state_dir / "runs" / safe_id(parent) / "manifest.json")
    exploration_name = slugify(exploration) if exploration else None
    if (
        exploration_name
        and not contained_path(config.root / config.scratch, exploration_name).is_dir()
    ):
        raise SiftError(f"Exploration does not exist: {exploration}")
    refs = [safe_id(value) for value in cache_refs]
    for value in refs:
        read_json(config.state_dir / "cache" / "entries" / f"{value}.json")
    run_id = short_id("run")
    run_dir = config.state_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    manifest = {
        "schema": 2,
        "id": run_id,
        "status": "preparing",
        "started_at": utc_now(),
        "command": command,
        "exploration": exploration_name,
        "parent": parent,
        "change": change,
        "seeds": seed_values,
        "metadata": metadata_values,
        "environment": environment,
        "cache_refs": refs,
        "artifacts": [],
        "replay_verified": False,
        "owner_pid": os.getpid(),
        "host": platform.node(),
        "launcher": launcher,
    }
    write_json(run_dir / "manifest.json", manifest)
    exit_code = 2
    try:
        copy_tree(config.root, run_dir / "source", config.snapshot_ignores)
        manifest["source_hash"] = tree_hash(run_dir / "source", ignores=())
        manifest["inputs"] = _input_records(config, run_dir, input_values)
        manifest["environment_record"] = _environment(run_dir / "source", config)
        manifest["git"] = _git_metadata(config.root)
        manifest["evidence_state"] = (
            "restorable" if all(item["captured"] for item in manifest["inputs"]) else "recorded"
        )
        work = run_dir / "work"
        copy_tree(run_dir / "source", work, ignores=())
        for value in output_paths:
            output = contained_path(work, value)
            if output.is_dir():
                shutil.rmtree(output)
            else:
                output.unlink(missing_ok=True)
        manifest["status"] = "running"
        write_json(run_dir / "manifest.json", manifest)
        env_extra = {"SIFT_RUN_ID": run_id, "SIFT_SEEDS": ",".join(map(str, seed_values))}
        for item in manifest["inputs"]:
            env_extra["SIFT_INPUT_" + item["name"].upper().replace("-", "_")] = (
                str(run_dir / item["captured"]) if item["captured"] else item["value"]
            )
        exit_code = _execute(
            config,
            run_dir,
            work,
            command,
            environment=environment,
            env_extra=env_extra,
            launcher=launcher,
        )
        manifest["exit_code"] = exit_code
        if tree_hash(run_dir / "source", ignores=()) != manifest["source_hash"]:
            raise SiftError("The saved source was modified during execution.")
        for value in output_paths:
            produced = contained_path(work, value)
            if not produced.is_file():
                if exit_code == 0:
                    raise SiftError(f"Artifact was not produced: {value}")
                continue
            destination = contained_path(run_dir / "artifacts", value)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(produced, destination)
            manifest["artifacts"].append({"path": value, "sha256": sha256_file(destination)})
        if exit_code == 0 and verify_command:
            verification = _run_verification(
                run_dir,
                work,
                verify_command,
                config,
                run_dir / "artifacts",
            )
            manifest["verification"] = verification
            exit_code = verification["exit_code"]
        manifest["status"] = "completed" if exit_code == 0 else "failed"
    except (OSError, SiftError, KeyboardInterrupt) as exc:
        exit_code = 130 if isinstance(exc, KeyboardInterrupt) else 2
        manifest.update(status="interrupted" if exit_code == 130 else "failed", error=str(exc))
    manifest.update(finished_at=utc_now(), effective_exit=exit_code)
    write_json(run_dir / "manifest.json", manifest)
    return run_id, exit_code


def load_run(config: ProjectConfig, run_id: str) -> dict:
    manifest = read_json(config.state_dir / "runs" / safe_id(run_id) / "manifest.json")
    for path in (config.state_dir / "replays").glob("*/manifest.json"):
        replay = read_json(path)
        if replay.get("original_run") == run_id and replay.get("accepted"):
            manifest = {**manifest, "replay_verified": True, "evidence_state": "replay-verified"}
    return manifest


def replay_run(config: ProjectConfig, run_id: str) -> tuple[str, int, bool]:
    original = config.state_dir / "runs" / safe_id(run_id)
    manifest = read_json(original / "manifest.json")
    if manifest.get("schema") != 2:
        raise SiftError(
            "Results from this older run format cannot be verified; the saved code is retained."
        )
    if manifest.get("status") != "completed":
        raise SiftError("Only a completed successful run can be rerun to verify its results.")
    if tree_hash(original / "source", ignores=()) != manifest["source_hash"]:
        raise SiftError("The recorded source snapshot is corrupted.")
    replay_id = short_id("replay")
    replay_dir = config.state_dir / "replays" / replay_id
    replay_dir.mkdir(parents=True)
    work = replay_dir / "work"
    copy_tree(original / "source", work, ignores=())
    record = {
        "schema": 2,
        "id": replay_id,
        "original_run": run_id,
        "created_at": utc_now(),
        "status": "running",
        "accepted": False,
    }
    write_json(replay_dir / "manifest.json", record)
    exit_code, accepted = 2, False
    try:
        for artifact in manifest["artifacts"]:
            output = contained_path(work, artifact["path"])
            if output.is_dir():
                shutil.rmtree(output)
            else:
                output.unlink(missing_ok=True)
        env_extra = {"SIFT_RUN_ID": replay_id, "SIFT_SEEDS": ",".join(map(str, manifest["seeds"]))}
        for item in manifest["inputs"]:
            captured = item["captured"]
            if captured:
                path = contained_path(original, captured)
                digest = tree_hash(path, ignores=()) if path.is_dir() else sha256_file(path)
                if digest != item["sha256"]:
                    raise SiftError(f"Captured input changed: {item['name']}")
                value = str(path)
            else:
                raise SiftError(f"Input identity has no captured data: {item['name']}")
            env_extra["SIFT_INPUT_" + item["name"].upper().replace("-", "_")] = value
        exit_code = _execute(
            config,
            replay_dir,
            work,
            manifest["command"],
            environment=manifest["environment"],
            env_extra=env_extra,
            launcher=manifest.get("launcher"),
        )
        exact = exit_code == 0
        artifact_results = []
        for artifact in manifest["artifacts"]:
            path = contained_path(work, artifact["path"])
            matches = path.is_file() and sha256_file(path) == artifact["sha256"]
            exact = exact and matches
            artifact_results.append({"path": artifact["path"], "matches": matches})
        accepted = exact and bool(manifest["artifacts"])
        if exit_code == 0 and manifest.get("verification"):
            verification = _run_verification(
                replay_dir,
                work,
                manifest["verification"]["command"],
                config,
                original / "artifacts",
            )
            record["verification"] = verification
            accepted = verification["exit_code"] == 0
        record.update(
            exact_artifacts=exact,
            artifacts=artifact_results,
            environment_record=_environment(work, config),
        )
    except (OSError, SiftError, KeyboardInterrupt) as exc:
        record["error"] = str(exc)
        exit_code = 130 if isinstance(exc, KeyboardInterrupt) else 2
    record.update(
        accepted=accepted,
        exit_code=exit_code,
        finished_at=utc_now(),
        status="completed" if accepted else "failed",
    )
    write_json(replay_dir / "manifest.json", record)
    return replay_id, exit_code, accepted
