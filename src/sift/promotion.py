from __future__ import annotations

import difflib
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import ProjectConfig
from .errors import SiftError
from .util import (
    copy_tree,
    read_json,
    relative_files,
    sha256_file,
    short_id,
    tree_hash,
    utc_now,
    write_json,
)


def _proposal_dir(config: ProjectConfig, proposal_id: str) -> Path:
    path = config.state_dir / "proposals" / proposal_id
    if not path.exists():
        raise SiftError(f"Unknown proposal: {proposal_id}")
    return path


def prepare(config: ProjectConfig, title: str, rationale: str = "") -> tuple[str, Path]:
    proposal_id = short_id("promotion")
    proposal = config.state_dir / "proposals" / proposal_id
    proposal.mkdir(parents=True)
    copy_tree(config.root, proposal / "base")
    copy_tree(config.root, proposal / "candidate")
    manifest = {
        "schema": 1,
        "id": proposal_id,
        "title": title,
        "rationale": rationale,
        "status": "draft",
        "created_at": utc_now(),
        "base_tree_hash": tree_hash(proposal / "base"),
    }
    write_json(proposal / "manifest.json", manifest)
    return proposal_id, proposal / "candidate"


def _file_state(root: Path) -> dict[str, str]:
    return {path.as_posix(): sha256_file(root / path) for path in relative_files(root)}


def _make_diff(base: Path, candidate: Path, changed: list[str]) -> str:
    output: list[str] = []
    for name in changed:
        before_path = base / name
        after_path = candidate / name
        try:
            before = (
                before_path.read_text(encoding="utf-8").splitlines(keepends=True)
                if before_path.exists()
                else []
            )
            after = (
                after_path.read_text(encoding="utf-8").splitlines(keepends=True)
                if after_path.exists()
                else []
            )
        except UnicodeDecodeError as exc:
            raise SiftError(f"Promotion contains an unsupported binary file: {name}") from exc
        output.extend(difflib.unified_diff(before, after, fromfile=f"a/{name}", tofile=f"b/{name}"))
    return "".join(output)


def _run_checks(candidate: Path, commands: tuple[str, ...]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    env = os.environ.copy()
    source = candidate / "src"
    env["PYTHONPATH"] = str(source) + os.pathsep + env.get("PYTHONPATH", "")
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=candidate,
            shell=True,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        results.append(
            {
                "command": command,
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-8000:],
                "stderr": completed.stderr[-8000:],
            }
        )
    return results


def seal(config: ProjectConfig, proposal_id: str, commands: tuple[str, ...] = ()) -> str:
    proposal = _proposal_dir(config, proposal_id)
    manifest = read_json(proposal / "manifest.json")
    if manifest["status"] == "applied":
        raise SiftError("An applied proposal cannot be resealed.")
    base = proposal / "base"
    candidate = proposal / "candidate"
    before = _file_state(base)
    after = _file_state(candidate)
    changed = sorted(
        name for name in set(before) | set(after) if before.get(name) != after.get(name)
    )
    if not changed:
        raise SiftError("The candidate has no changes.")
    diff = _make_diff(base, candidate, changed)
    diff_path = proposal / "proposal.diff"
    diff_path.write_text(diff, encoding="utf-8", newline="\n")
    checks = _run_checks(candidate, commands or config.checks)
    digest_payload = diff.encode() + b"\0" + "\n".join(changed).encode()
    digest = hashlib.sha256(digest_payload).hexdigest()
    manifest.update(
        {
            "status": "ready"
            if all(item["exit_code"] == 0 for item in checks)
            else "checks_failed",
            "sealed_at": utc_now(),
            "digest": digest,
            "changes": [
                {
                    "path": name,
                    "before": before.get(name),
                    "after": after.get(name),
                    "action": "add"
                    if name not in before
                    else "delete"
                    if name not in after
                    else "modify",
                }
                for name in changed
            ],
            "checks": checks,
        }
    )
    approval = proposal / "approval.json"
    if approval.exists():
        approval.unlink()
    write_json(proposal / "manifest.json", manifest)
    return digest


def approve(config: ProjectConfig, proposal_id: str) -> str:
    proposal = _proposal_dir(config, proposal_id)
    manifest = read_json(proposal / "manifest.json")
    if manifest["status"] != "ready":
        raise SiftError("Only a sealed proposal with passing checks can be approved.")
    if not sys.stdin.isatty():
        raise SiftError("Approval requires an interactive human terminal.")
    digest = manifest["digest"]
    print((proposal / "proposal.diff").read_text(encoding="utf-8"))
    print(f"Proposal digest: {digest}")
    try:
        confirmation = input(
            "Type the first 12 digest characters to approve this exact patch: "
        ).strip()
    except EOFError as exc:
        raise SiftError("Approval requires input from a human reviewer.") from exc
    if confirmation != digest[:12]:
        raise SiftError("Approval cancelled: digest did not match.")
    try:
        reviewer = input("Reviewer name: ").strip()
    except EOFError as exc:
        raise SiftError("Approval requires input from a human reviewer.") from exc
    if not reviewer:
        raise SiftError("Approval cancelled: reviewer name is required.")
    write_json(
        proposal / "approval.json",
        {"digest": digest, "reviewer": reviewer, "approved_at": utc_now()},
    )
    return reviewer


def apply(config: ProjectConfig, proposal_id: str) -> None:
    proposal = _proposal_dir(config, proposal_id)
    manifest = read_json(proposal / "manifest.json")
    approval = read_json(proposal / "approval.json")
    if manifest["status"] != "ready" or approval.get("digest") != manifest.get("digest"):
        raise SiftError("This exact sealed proposal has not been approved.")
    candidate = proposal / "candidate"
    for change in manifest["changes"]:
        relative = Path(change["path"])
        current = config.root / relative
        expected = change["before"]
        actual = sha256_file(current) if current.is_file() else None
        if actual != expected:
            raise SiftError(f"Project changed since review: {relative}")
    for change in manifest["changes"]:
        relative = Path(change["path"])
        current = config.root / relative
        proposed = candidate / relative
        if change["action"] == "delete":
            current.unlink()
        else:
            current.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(proposed, current)
    manifest["status"] = "applied"
    manifest["applied_at"] = utc_now()
    write_json(proposal / "manifest.json", manifest)


def proposal_summary(config: ProjectConfig, proposal_id: str) -> dict[str, object]:
    proposal = _proposal_dir(config, proposal_id)
    manifest = read_json(proposal / "manifest.json")
    manifest["diff_path"] = str(proposal / "proposal.diff")
    manifest["candidate_path"] = str(proposal / "candidate")
    manifest["approved"] = (proposal / "approval.json").exists()
    return manifest
