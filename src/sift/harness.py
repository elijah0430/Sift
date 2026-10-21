from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

from .config import ProjectConfig
from .errors import SiftError
from .promotion import _protected_hash, prepare
from .util import safe_id, utc_now, write_json

HUMAN_ONLY = {"core review", "review", "promote approve", "promote apply", "gc apply"}


def policy(config: ProjectConfig | None = None) -> dict:
    scratch = config.scratch.as_posix() if config else "scratch"
    state = config.state.as_posix() if config else ".research"
    return {
        "schema": 1,
        "actor": "agent",
        "write_scopes": [f"{scratch}/**", f"{state}/proposals/*/candidate/**"],
        "human_only": [f"sift {command}" for command in sorted(HUMAN_ONLY)],
        "approval_authentication": "host-controlled; interactive input alone is not identity",
        "sandbox_backends": ["candidate", "bubblewrap"],
        "candidate_backend": "isolated working copy plus original-core change detection",
        "bubblewrap_backend": (
            "Linux read-only filesystem with writable candidate and temporary files"
        ),
    }


def guard(command: list[str]) -> dict:
    if command and command[0] == "--":
        command = command[1:]
    if len(command) == 1:
        command = shlex.split(command[0])
    if not command:
        raise SiftError("Expected a Sift command.")
    first = Path(command[0]).stem.lower()
    if first.startswith("python") and command[1:3] == ["-m", "sift"]:
        arguments = command[3:]
    elif first == "sift":
        arguments = command[1:]
    else:
        raise SiftError(
            "This gate accepts Sift argv only; arbitrary shells require a host sandbox."
        )
    operation = " ".join(arguments[:2])
    if (
        not arguments
        or operation in HUMAN_ONLY
        or arguments[0] in HUMAN_ONLY
        or arguments[0].startswith("-")
    ):
        raise SiftError("This command is reserved for a human reviewer or is not an agent action.")
    allowed = {
        "archive",
        "core",
        "explore",
        "experiment",
        "run",
        "check",
        "inspect",
        "preserve",
        "propose",
        "reproduce",
        "replay",
        "status",
        "cache",
        "pin",
        "retire",
        "doctor",
        "export",
        "artifact",
    }
    if arguments[0] not in allowed and operation not in {
        "promote prepare",
        "promote seal",
        "promote show",
        "gc plan",
    }:
        raise SiftError("This operation is not enabled for agents.")
    return {"allowed": True, "command": command, "enforcement": "argv gate, not a shell sandbox"}


def check_write(config: ProjectConfig, path: str, proposal_id: str | None = None) -> dict:
    target = Path(path)
    if not target.is_absolute():
        target = config.root / target
    target = target.resolve()
    permitted = target.is_relative_to(config.root / config.scratch)
    if proposal_id:
        candidate = config.state_dir / "proposals" / safe_id(proposal_id) / "candidate"
        permitted = permitted or target.is_relative_to(candidate)
    if not permitted:
        raise SiftError(
            "Agent writes are restricted to scratch or the selected candidate workspace."
        )
    return {"allowed": True, "path": str(target)}


def launch(config: ProjectConfig, command: list[str], sandbox: str = "candidate") -> dict:
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SiftError("Provide the coding-agent command after --.")
    if sandbox == "bubblewrap" and not shutil.which("bwrap"):
        raise SiftError(
            "bubblewrap is unavailable; select a host sandbox or the detection-only backend."
        )
    proposal_id, candidate = prepare(
        config, "Agent session", "Prepared in an isolated agent workspace."
    )
    before = _protected_hash(config)
    env = os.environ.copy()
    env.update(SIFT_ACTOR="agent", SIFT_PROPOSAL=proposal_id, SIFT_PROJECT=str(config.root))
    argv = command
    if sandbox == "bubblewrap":
        argv = [
            "bwrap",
            "--die-with-parent",
            "--ro-bind",
            "/",
            "/",
            "--bind",
            str(candidate),
            str(candidate),
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
            "--chdir",
            str(candidate),
            "--",
            *command,
        ]
    result = subprocess.run(argv, cwd=candidate, env=env, check=False)
    unchanged = _protected_hash(config) == before
    report = {
        "proposal_id": proposal_id,
        "candidate": str(candidate),
        "sandbox": sandbox,
        "exit_code": result.returncode,
        "original_core_unchanged": unchanged,
        "finished_at": utc_now(),
    }
    write_json(config.state_dir / "proposals" / proposal_id / "session.json", report)
    if not unchanged:
        raise SiftError(
            "The original core changed outside the candidate; inspect before continuing."
        )
    return report
