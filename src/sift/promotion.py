from __future__ import annotations

import difflib
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from .boundaries import check_boundaries, run_boundary_engine
from .config import PROTECTED_FILES, ProjectConfig
from .errors import SiftError
from .snapshots import execution_environment
from .util import (
    canonical_hash,
    contained_path,
    copy_tree,
    project_lock,
    read_json,
    relative_files,
    safe_id,
    sha256_file,
    short_id,
    tree_hash,
    utc_now,
    write_json,
)


def _proposal_dir(config: ProjectConfig, proposal_id: str) -> Path:
    path = config.state_dir / "proposals" / safe_id(proposal_id)
    if not path.exists():
        raise SiftError(f"Unknown proposal: {proposal_id}")
    return path


def _file_state(root: Path, ignores=()) -> dict[str, str]:
    return {path.as_posix(): sha256_file(root / path) for path in relative_files(root, ignores)}


def _protected_state(config: ProjectConfig) -> dict:
    state = _file_state(config.root, config.snapshot_ignores)
    prefixes = [path.as_posix() + "/" for path in (*config.core, config.tests)]
    files = set(PROTECTED_FILES)
    files.update(path.as_posix() for path in config.core)
    return {
        name: value
        for name, value in state.items()
        if name in files or any(name.startswith(prefix) for prefix in prefixes)
    }


def _protected_hash(config: ProjectConfig) -> str:
    return canonical_hash(_protected_state(config))


def _initialize_review_repository(candidate: Path) -> bool:
    if not shutil.which("git"):
        return False
    commands = (
        ("init", "--quiet"),
        ("config", "user.name", "Sift"),
        ("config", "user.email", "sift@localhost"),
        ("config", "core.autocrlf", "false"),
        ("config", "core.filemode", "false"),
        ("add", "--all"),
        ("commit", "--quiet", "--message", "Sift review baseline"),
    )
    for arguments in commands:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=candidate,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            shutil.rmtree(candidate / ".git", ignore_errors=True)
            return False
    return True


def prepare(
    config: ProjectConfig,
    title: str,
    rationale: str = "",
    baseline_run: str | None = None,
) -> tuple[str, Path]:
    with project_lock(config.state_dir):
        run_refs = []
        if baseline_run:
            read_json(config.state_dir / "runs" / safe_id(baseline_run) / "manifest.json")
            run_refs.append(baseline_run)
        for path in (config.root / config.experiments).rglob("sift-record.json"):
            record = read_json(path)
            if record.get("run_id"):
                run_refs.append(record["run_id"])
        proposal_id = short_id("promotion")
        proposal = config.state_dir / "proposals" / proposal_id
        proposal.mkdir(parents=True)
        copy_tree(config.root, proposal / "base", config.snapshot_ignores)
        copy_tree(proposal / "base", proposal / "candidate", ignores=())
        review_repository = _initialize_review_repository(proposal / "candidate")
        write_json(
            proposal / "manifest.json",
            {
                "schema": 1,
                "id": proposal_id,
                "title": title,
                "rationale": rationale,
                "baseline_run": baseline_run,
                "run_refs": sorted(set(run_refs)),
                "status": "draft",
                "created_at": utc_now(),
                "base_tree_hash": tree_hash(proposal / "base", ignores=()),
                "protected_hash": _protected_hash(config),
                "review_repository": review_repository,
            },
        )
        return proposal_id, proposal / "candidate"


def _make_diff(base: Path, candidate: Path, changed: list[str]) -> str:
    output = []
    for name in changed:
        before_path, after_path = base / name, candidate / name
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
        except UnicodeDecodeError:
            output.append(f"Binary change: {name}\n")
            continue
        output.extend(difflib.unified_diff(before, after, fromfile=f"a/{name}", tofile=f"b/{name}"))
    return "".join(output)


def _run_checks(candidate: Path, config: ProjectConfig, commands: tuple[str, ...]) -> list[dict]:
    violations = check_boundaries(ProjectConfig.load(candidate))
    results = [
        {
            "command": "sift check (mandatory)",
            "exit_code": 1 if violations else 0,
            "stdout": "\n".join(f"{item.file}:{item.line}: {item.rule}" for item in violations),
            "stderr": "",
        }
    ]
    env = execution_environment(config, candidate)
    native = run_boundary_engine(ProjectConfig.load(candidate))
    if native:
        results.append(native)
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


def _seal_payload(manifest: dict) -> dict:
    payload = {
        key: manifest[key]
        for key in (
            "title",
            "baseline_run",
            "run_refs",
            "rationale",
            "base_tree_hash",
            "protected_hash",
            "candidate_hash",
            "changes",
            "checks",
            "diff_hash",
        )
    }
    if "review_hash" in manifest:
        payload["review_hash"] = manifest["review_hash"]
    if "check_commands" in manifest:
        payload["check_commands"] = manifest["check_commands"]
    return payload


def seal(config: ProjectConfig, proposal_id: str, commands: tuple[str, ...] = ()) -> str:
    with project_lock(config.state_dir):
        proposal = _proposal_dir(config, proposal_id)
        manifest = read_json(proposal / "manifest.json")
        if manifest["status"] in {"applied", "applying"}:
            raise SiftError("An applied or applying proposal cannot be resealed.")
        feedback_path = proposal / "feedback.json"
        feedback = read_json(feedback_path) if feedback_path.is_file() else None
        if (
            manifest["status"] == "changes_requested"
            and feedback
            and tree_hash(proposal / "candidate", config.snapshot_ignores)
            == feedback.get("candidate_hash")
        ):
            raise SiftError("Revise the candidate before marking the proposal ready again.")
        (proposal / "approval.json").unlink(missing_ok=True)
        manifest["status"] = "checking"
        write_json(proposal / "manifest.json", manifest)
        base, candidate = proposal / "base", proposal / "candidate"
        if ProjectConfig.load(candidate).state != config.state:
            raise SiftError("Moving the state store requires an explicit offline migration.")
        if tree_hash(base, ignores=()) != manifest["base_tree_hash"]:
            raise SiftError("The reference snapshot changed; prepare a new proposal.")
        before = _file_state(base)
        after = _file_state(candidate, config.snapshot_ignores)
        changed = sorted(
            name for name in before.keys() | after.keys() if before.get(name) != after.get(name)
        )
        if not changed:
            raise SiftError("The candidate has no changes.")
        checks_to_run = tuple(dict.fromkeys((*config.checks, *commands)))
        if not checks_to_run:
            raise SiftError("Configure at least one correctness check before sealing.")
        checks = _run_checks(candidate, config, checks_to_run)
        if after != _file_state(candidate, config.snapshot_ignores):
            raise SiftError("Checks modified candidate source. Inspect it and reseal.")
        diff = _make_diff(base, candidate, changed)
        (proposal / "proposal.diff").write_text(diff, encoding="utf-8", newline="\n")
        sealed = proposal / "sealed"
        if sealed.exists():
            shutil.rmtree(sealed)
        copy_tree(candidate, sealed, config.snapshot_ignores)
        manifest.update(
            {
                "status": "ready"
                if all(item["exit_code"] == 0 for item in checks)
                else "checks_failed",
                "sealed_at": utc_now(),
                "candidate_hash": tree_hash(sealed, ignores=()),
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
                "check_commands": list(checks_to_run),
                "diff_hash": sha256_file(proposal / "proposal.diff"),
            }
        )
        action_labels = {"add": "added", "modify": "modified", "delete": "deleted"}
        report = (
            f"# {manifest['title']}\n\n{manifest['rationale']}\n\n"
            "Changed files:\n"
            + "\n".join(
                f"- {action_labels[item['action']]}: {item['path']}" for item in manifest["changes"]
            )
            + "\n\nChecks:\n"
            + "\n".join(
                f"- {'passed' if item['exit_code'] == 0 else 'failed'}: {item['command']}"
                for item in checks
            )
            + "\n\nReview proposal.diff, interfaces, assumptions, and scientific evidence. "
            "Passing checks do not establish scientific validity.\n"
        )
        (proposal / "review.md").write_text(report, encoding="utf-8")
        manifest["review_hash"] = sha256_file(proposal / "review.md")
        manifest["digest"] = canonical_hash(_seal_payload(manifest))
        write_json(proposal / "manifest.json", manifest)
        if feedback and feedback.get("status") == "open" and manifest["status"] == "ready":
            feedback.update(
                status="addressed",
                addressed_at=utc_now(),
                addressed_by_digest=manifest["digest"],
            )
            write_json(feedback_path, feedback)
        return manifest["digest"]


def _validate_seal(config: ProjectConfig, proposal: Path, manifest: dict) -> None:
    try:
        valid = (
            canonical_hash(_seal_payload(manifest)) == manifest["digest"]
            and sha256_file(proposal / "proposal.diff") == manifest["diff_hash"]
            and (
                "review_hash" not in manifest
                or sha256_file(proposal / "review.md") == manifest["review_hash"]
            )
            and tree_hash(proposal / "sealed", ignores=()) == manifest["candidate_hash"]
            and tree_hash(proposal / "candidate", config.snapshot_ignores)
            == manifest["candidate_hash"]
            and tree_hash(proposal / "base", ignores=()) == manifest["base_tree_hash"]
        )
    except (KeyError, OSError) as exc:
        raise SiftError("The sealed proposal is incomplete. Reseal before review.") from exc
    if not valid:
        raise SiftError("The sealed candidate or review record changed. Reseal and review again.")


def pending_proposals(config: ProjectConfig) -> list[dict]:
    root = config.state_dir / "proposals"
    pending = []
    if not root.exists():
        return pending
    for path in root.iterdir():
        manifest_path = path / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = read_json(manifest_path)
        if manifest.get("status") not in {"ready", "applying"}:
            continue
        approval_path = path / "approval.json"
        approval = read_json(approval_path) if approval_path.is_file() else {}
        pending.append(
            {
                "id": manifest["id"],
                "title": manifest["title"],
                "rationale": manifest.get("rationale", ""),
                "created_at": manifest.get("created_at", ""),
                "status": manifest["status"],
                "changes": len(manifest.get("changes", [])),
                "checks": len(manifest.get("checks", [])),
                "approved": approval.get("digest") == manifest.get("digest"),
            }
        )
    return sorted(pending, key=lambda item: item["created_at"], reverse=True)


def review_material(config: ProjectConfig, proposal_id: str) -> dict:
    with project_lock(config.state_dir):
        proposal = _proposal_dir(config, proposal_id)
        manifest = read_json(proposal / "manifest.json")
        if manifest.get("status") not in {"ready", "applying"}:
            raise SiftError("Only a sealed proposal with passing checks can be reviewed.")
        _validate_seal(config, proposal, manifest)
        approval_path = proposal / "approval.json"
        approval = read_json(approval_path) if approval_path.is_file() else {}
        return {
            **manifest,
            "approved": approval.get("digest") == manifest.get("digest"),
            "candidate_path": str(proposal / "candidate"),
            "report": (proposal / "review.md").read_text(encoding="utf-8"),
            "diff": (proposal / "proposal.diff").read_text(encoding="utf-8"),
        }


def feedback_draft(config: ProjectConfig, proposal_id: str) -> Path:
    proposal = _proposal_dir(config, proposal_id)
    path = proposal / "feedback.draft.md"
    if not path.exists():
        path.write_text(
            "# Requested changes\n\n"
            "<!-- Describe concrete code, test, or experiment changes for the agent. -->\n",
            encoding="utf-8",
        )
    return path


def request_changes(
    config: ProjectConfig,
    proposal_id: str,
    reviewed_digest: str,
    reviewer: str,
    feedback: str,
) -> None:
    reviewer = reviewer.strip()
    feedback = feedback.strip()
    if not reviewer:
        raise SiftError("Reviewer name is required.")
    meaningful = (
        feedback.replace("# Requested changes", "")
        .replace("<!-- Describe concrete code, test, or experiment changes for the agent. -->", "")
        .strip()
    )
    if not meaningful:
        raise SiftError("Write at least one requested change before sending feedback.")
    with project_lock(config.state_dir):
        proposal = _proposal_dir(config, proposal_id)
        manifest = read_json(proposal / "manifest.json")
        if manifest.get("status") != "ready":
            raise SiftError("Only a ready proposal can receive review feedback.")
        _validate_seal(config, proposal, manifest)
        if manifest.get("digest") != reviewed_digest:
            raise SiftError("The proposal changed during review.")
        (proposal / "feedback.md").write_text(feedback.rstrip() + "\n", encoding="utf-8")
        write_json(
            proposal / "feedback.json",
            {
                "status": "open",
                "reviewed_digest": reviewed_digest,
                "candidate_hash": manifest["candidate_hash"],
                "reviewer": reviewer,
                "requested_at": utc_now(),
            },
        )
        (proposal / "feedback.draft.md").unlink(missing_ok=True)
        manifest["status"] = "changes_requested"
        write_json(proposal / "manifest.json", manifest)


def proposal_feedback(config: ProjectConfig, proposal_id: str) -> dict:
    proposal = _proposal_dir(config, proposal_id)
    record = read_json(proposal / "feedback.json")
    return {
        **record,
        "feedback": (proposal / "feedback.md").read_text(encoding="utf-8"),
        "candidate_path": str(proposal / "candidate"),
    }


def approve_reviewed(
    config: ProjectConfig,
    proposal_id: str,
    reviewed_digest: str,
    reviewer: str,
) -> str:
    if not sys.stdin.isatty():
        raise SiftError("Approval requires an interactive human terminal.")
    reviewer = reviewer.strip()
    if not reviewer:
        raise SiftError("Reviewer name is required.")
    with project_lock(config.state_dir):
        proposal = _proposal_dir(config, proposal_id)
        current = read_json(proposal / "manifest.json")
        if current.get("status") != "ready":
            raise SiftError("Only a sealed proposal with passing checks can be approved.")
        _validate_seal(config, proposal, current)
        if current.get("digest") != reviewed_digest:
            raise SiftError("The proposal changed during review.")
        write_json(
            proposal / "approval.json",
            {
                "digest": reviewed_digest,
                "reviewer": reviewer,
                "approved_at": utc_now(),
            },
        )
    return reviewer


def approve(config: ProjectConfig, proposal_id: str) -> str:
    proposal = _proposal_dir(config, proposal_id)
    manifest = read_json(proposal / "manifest.json")
    if manifest["status"] != "ready":
        raise SiftError("Only a sealed proposal with passing checks can be approved.")
    _validate_seal(config, proposal, manifest)
    if not sys.stdin.isatty():
        raise SiftError("Approval requires an interactive human terminal.")
    print((proposal / "review.md").read_text(encoding="utf-8"))
    print((proposal / "proposal.diff").read_text(encoding="utf-8"))
    digest = manifest["digest"]
    try:
        confirmation = input("Type the first 12 digest characters to approve: ").strip()
        if confirmation != digest[:12]:
            raise SiftError("Approval cancelled: digest did not match.")
        reviewer = input("Reviewer name: ").strip()
    except EOFError as exc:
        raise SiftError("Approval requires input from a human reviewer.") from exc
    return approve_reviewed(config, proposal_id, digest, reviewer)


def apply(config: ProjectConfig, proposal_id: str, *, reviewed_digest: str | None = None) -> None:
    with project_lock(config.state_dir):
        proposal = _proposal_dir(config, proposal_id)
        manifest = read_json(proposal / "manifest.json")
        if reviewed_digest is not None and manifest.get("digest") != reviewed_digest:
            raise SiftError("The proposal changed during review. Run sift core review again.")
        approval = read_json(proposal / "approval.json")
        if manifest["status"] not in {"ready", "applying"} or approval.get(
            "digest"
        ) != manifest.get("digest"):
            raise SiftError("This exact sealed proposal has not been approved.")
        _validate_seal(config, proposal, manifest)
        recovering = manifest["status"] == "applying"
        baseline_config = replace(ProjectConfig.load(proposal / "base"), root=config.root)
        protected = _protected_state(baseline_config)
        protected_core = {
            *PROTECTED_FILES,
            *(path.as_posix() for path in baseline_config.core),
        }
        if recovering:
            for change in manifest["changes"]:
                name = change["path"]
                if (
                    name in protected
                    or name in protected_core
                    or any(
                        name.startswith(path.as_posix() + "/")
                        for path in (*baseline_config.core, baseline_config.tests)
                    )
                ):
                    if change["before"] is None:
                        protected.pop(name, None)
                    else:
                        protected[name] = change["before"]
        if canonical_hash(protected) != manifest["protected_hash"]:
            raise SiftError("Core, tests, or configuration changed since review.")
        for change in manifest["changes"]:
            target = contained_path(config.root, change["path"])
            actual = sha256_file(target) if target.is_file() else None
            allowed = {change["before"], change["after"]} if recovering else {change["before"]}
            if actual not in allowed or (target.exists() and not target.is_file()):
                raise SiftError(f"Project changed since review: {change['path']}")
        manifest["status"] = "applying"
        write_json(proposal / "manifest.json", manifest)
        for change in manifest["changes"]:
            target = contained_path(config.root, change["path"])
            if change["action"] == "delete":
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".sift-pending")
                shutil.copy2(proposal / "sealed" / change["path"], temporary)
                temporary.replace(target)
        manifest.update(status="applied", applied_at=utc_now())
        write_json(proposal / "manifest.json", manifest)


def proposal_summary(config: ProjectConfig, proposal_id: str) -> dict:
    proposal = _proposal_dir(config, proposal_id)
    manifest = read_json(proposal / "manifest.json")
    return {
        **manifest,
        "diff_path": str(proposal / "proposal.diff"),
        "review_path": str(proposal / "review.md"),
        "candidate_path": str(proposal / "candidate"),
        "approved": (proposal / "approval.json").exists(),
    }
