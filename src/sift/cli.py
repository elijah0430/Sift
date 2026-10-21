from __future__ import annotations

import argparse
import contextlib
import getpass
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from .adapters import ArtifactRef, LocalArtifactStore
from .boundaries import check_boundaries, run_boundary_engine
from .cache import cache_key
from .cache import drop as cache_drop
from .cache import get as cache_get
from .cache import put as cache_put
from .config import ProjectConfig, initialize_project
from .diagnostics import doctor, export_run, rebuild_index
from .errors import SiftError
from .gc import apply as apply_gc
from .gc import plan as plan_gc
from .gc import set_pin
from .harness import check_write, guard, launch, policy
from .lifecycle import create_exploration, preserve, restore_retirement, retire
from .promotion import apply as apply_promotion
from .promotion import (
    approve,
    approve_reviewed,
    feedback_draft,
    pending_proposals,
    prepare,
    proposal_feedback,
    proposal_summary,
    request_changes,
    review_material,
    seal,
)
from .snapshots import create_run, load_run, replay_run
from .util import find_project, read_json, safe_id, slugify
from .workspace import compare_experiments, experiment_runs, resolve_run, workspace_status


def _config() -> ProjectConfig:
    return ProjectConfig.load(find_project())


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def _result(args, value: dict, message: str) -> None:
    _json(value) if args.json_output else print(message)


def _page(text: str) -> None:
    content = text.rstrip() + "\n"
    command = os.environ.get("PAGER")
    if command:
        argv = shlex.split(command, posix=os.name != "nt")
        if os.name == "nt":
            argv = [part.strip("\"'") for part in argv]
    else:
        executable = "more.com" if os.name == "nt" else "less"
        argv = [executable]
    if sys.stdout.isatty() and argv and shutil.which(argv[0]):
        completed = subprocess.run(argv, input=content, text=True, check=False)
        if completed.returncode == 0:
            return
    print(content, end="")


def _open_editor(path: Path, editor: str | None = None) -> None:
    command = editor or os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not command:
        raise SiftError("Set VISUAL or EDITOR, or pass sift core review --editor COMMAND.")
    argv = shlex.split(command, posix=os.name != "nt")
    if os.name == "nt":
        argv = [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in {'"', "'"} else part
            for part in argv
        ]
    if not argv:
        raise SiftError("The editor command is empty.")
    completed = subprocess.run([*argv, str(path)], check=False)
    if completed.returncode:
        raise SiftError(f"Editor exited with status {completed.returncode}.")


def _choose_proposal(config: ProjectConfig, proposal_id: str | None) -> str | None:
    if proposal_id:
        return proposal_id
    proposals = pending_proposals(config)
    if not proposals:
        print("No core changes are waiting for review.")
        return None
    if len(proposals) == 1:
        return proposals[0]["id"]
    print("Core changes waiting for review:\n")
    for index, item in enumerate(proposals, start=1):
        state = "approved" if item["approved"] else "ready"
        print(f"  {index}. {item['title']} ({item['changes']} files, {state})")
        print(f"     {item['id']}")
    try:
        selection = input("\nSelect a number, or [l] leave for later: ").strip().lower()
    except EOFError as exc:
        raise SiftError("Review requires input from a human reviewer.") from exc
    if selection in {"l", "q", ""}:
        return None
    if not selection.isdigit() or not 1 <= int(selection) <= len(proposals):
        raise SiftError("Select one of the listed proposal numbers.")
    return proposals[int(selection) - 1]["id"]


def _format_checks(material: dict) -> str:
    sections = []
    for item in material["checks"]:
        section = [f"$ {item['command']}", f"exit {item['exit_code']}"]
        if item.get("stdout"):
            section.extend(("", item["stdout"].rstrip()))
        if item.get("stderr"):
            section.extend(("", "stderr:", item["stderr"].rstrip()))
        sections.append("\n".join(section))
    return "\n\n".join(sections) or "No checks were recorded."


def _print_workspace_status(status: dict) -> None:
    runs = status["runs"]
    print("Research workspace")
    print(f"  {status['root']}\n")
    print("Needs your attention")
    print(f"  Core changes needing review    {status['needs_review']}")
    print(f"  Changes requested              {status['changes_requested']}\n")
    print("Current work")
    print(f"  Scratch workspaces             {len(status['explorations'])}")
    print(f"  Draft core changes             {status['draft_proposals']}")
    print(f"  Running experiments            {runs['active']}\n")
    print("Saved research")
    print(f"  Experiments                    {len(status['experiments'])}")
    print(f"  Experiment runs                {runs['total']}")
    if runs["failed"] or runs["interrupted"]:
        print(f"  Failed or interrupted          {runs['failed'] + runs['interrupted']}")


def _display_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _print_experiment_runs(table: dict) -> None:
    columns, rows = table["columns"], table["rows"]
    if not rows:
        print("No experiment runs.")
        return
    leaves = [column.rsplit(".", 1)[-1] for column in columns]
    counts = {leaf: leaves.count(leaf) for leaf in set(leaves)}
    labels = [
        (leaf if counts[leaf] == 1 else column).replace("metadata.", "meta.").upper()
        for column, leaf in zip(columns, leaves, strict=True)
    ]
    widths = []
    for column, label in zip(columns, labels, strict=True):
        width = max(len(label), *(len(_display_value(row.get(column, ""))) for row in rows))
        widths.append(min(width, 24))

    def render(value: object, width: int) -> str:
        content = _display_value(value)
        if len(content) > width:
            content = content[: max(width - 3, 1)] + ("..." if width >= 4 else "")
        return content.ljust(width)

    print("  ".join(render(label, width) for label, width in zip(labels, widths, strict=True)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print(
            "  ".join(
                render(row.get(column, ""), width)
                for column, width in zip(columns, widths, strict=True)
            )
        )


def _editor_command(config: ProjectConfig, editor: str | None) -> str | None:
    return editor or config.review_command or os.environ.get("VISUAL") or os.environ.get("EDITOR")


def _review_header(config: ProjectConfig, material: dict, selected: str, reviewer: str) -> None:
    passed = sum(item["exit_code"] == 0 for item in material["checks"])
    print(f"\n{material['title']}")
    if material.get("rationale"):
        print(f"\nPurpose\n  {material['rationale']}")
    if material.get("baseline_run"):
        print("\nMotivating experiment")
        _print_experiment_runs(experiment_runs(config, (material["baseline_run"],)))
    print("\nChanged files")
    action_labels = {"add": "added", "modify": "modified", "delete": "deleted"}
    for change in material["changes"]:
        print(f"  {action_labels.get(change['action'], change['action'])}: {change['path']}")
    print(f"\nValidation\n  {passed}/{len(material['checks'])} checks passed")
    print(f"\nReview workspace\n  {material['candidate_path']}")
    print(f"\nReview ID: {selected}")
    if not material["approved"]:
        print(f"Reviewer: {reviewer}")


def _reseal_after_edit(config: ProjectConfig, selected: str, material: dict) -> dict | None:
    while True:
        try:
            action = (
                input(
                    "\nThe review workspace changed.\n"
                    "[r] rerun checks and refresh review  [l] leave for the agent\n> "
                )
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            action = "l"
        if action in {"l", "q", ""}:
            print(f"Left {selected} pending. The candidate must be checked again before approval.")
            return None
        if action != "r":
            print("Choose r or l.")
            continue
        seal(config, selected, tuple(material.get("check_commands", ())))
        summary = proposal_summary(config, selected)
        if summary["status"] != "ready":
            _page(_format_checks(summary))
            print("Checks failed. The proposal remains with the agent for revision.")
            return None
        refreshed = review_material(config, selected)
        print("Checks passed. Review the updated change before approval.")
        _page(f"{refreshed['report']}\n\n{refreshed['diff']}")
        return refreshed


def _open_review_workspace(
    config: ProjectConfig,
    selected: str,
    material: dict,
    command: str | None,
) -> dict | None:
    try:
        _open_editor(Path(material["candidate_path"]), command)
    except (SiftError, OSError, ValueError) as exc:
        print(f"Could not open review workspace: {exc}")
        return material
    try:
        refreshed = review_material(config, selected)
    except SiftError:
        return _reseal_after_edit(config, selected, material)
    if refreshed["digest"] != material["digest"]:
        print(f"The proposal changed during review. Run sift core review {selected} again.")
        return None
    return refreshed


def _collect_feedback(
    config: ProjectConfig,
    selected: str,
    material: dict,
    reviewer: str,
    command: str | None,
) -> bool:
    draft = feedback_draft(config, selected)
    if command:
        try:
            _open_editor(draft, command)
        except (SiftError, OSError, ValueError) as exc:
            print(f"Could not open feedback note: {exc}")
            return False
        feedback = draft.read_text(encoding="utf-8")
    else:
        try:
            feedback = input("Requested changes: ").strip()
        except (EOFError, KeyboardInterrupt):
            return False
    try:
        request_changes(config, selected, material["digest"], reviewer, feedback)
    except SiftError as exc:
        print(f"Feedback was not saved: {exc}")
        return False
    print(f"Requested changes saved for {selected}.")
    return True


def _review(
    config: ProjectConfig,
    proposal_id: str | None,
    editor: str | None,
    reviewer: str | None = None,
    terminal: bool = False,
) -> int:
    if not sys.stdin.isatty():
        raise SiftError("Review requires an interactive human terminal.")
    selected = _choose_proposal(config, proposal_id)
    if selected is None:
        return 0
    material = review_material(config, selected)
    reviewer = (reviewer if reviewer is not None else getpass.getuser()).strip()
    if not reviewer:
        raise SiftError("Reviewer name is required; use sift core review --reviewer NAME.")
    command = _editor_command(config, editor)
    _review_header(config, material, selected, reviewer)
    if command and not terminal:
        print("\nOpening the code review in your editor...")
        material = _open_review_workspace(config, selected, material, command)
        if material is None:
            return 0
    else:
        _page(f"{material['report']}\n\n{material['diff']}")

    while True:
        action_label = "apply" if material["approved"] else "approve and apply"
        try:
            action = (
                input(
                    f"\n[o] open code review  [d] terminal diff  [c] checks\n"
                    f"[f] request changes   [a] {action_label}  [l] later\n> "
                )
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            print(f"\nLeft {selected} pending.")
            return 0
        if action == "d":
            _page(material["diff"])
        elif action in {"c", "t"}:
            _page(_format_checks(material))
        elif action in {"o", "e"}:
            material = _open_review_workspace(config, selected, material, command)
            if material is None:
                return 0
        elif action == "f":
            if _collect_feedback(config, selected, material, reviewer, command):
                return 0
        elif action == "a":
            if not material["approved"]:
                approve_reviewed(config, selected, material["digest"], reviewer)
            apply_promotion(config, selected, reviewed_digest=material["digest"])
            print(f"Applied {selected}")
            return 0
        elif action in {"l", "q", ""}:
            print(f"Left {selected} pending.")
            return 0
        else:
            print("Choose o, d, c, f, a, or l.")


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--artifact", action="append", default=[], help="Output file or directory to save"
    )
    parser.add_argument("--parent")
    parser.add_argument("--change")
    parser.add_argument("--input", action="append", default=[], help="Capture NAME=PATH_OR_ID")
    parser.add_argument(
        "--seed",
        action="append",
        type=int,
        default=[],
        help="Record a seed; your code must set its random generators",
    )
    parser.add_argument("--meta", action="append", default=[], help="Record NAME=VALUE")
    parser.add_argument(
        "--verify", help="Command to compare outputs; exit 0 means the comparison passed"
    )
    parser.add_argument("--environment", choices=["current", "uv"], default="current")
    parser.add_argument("--cache-ref", action="append", default=[])
    parser.add_argument(
        "--launcher", help="Shared-filesystem scheduler prefix, e.g. srun --partition=gpu"
    )


def _add_proposal_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("proposal_id", nargs="?")
    parser.add_argument("--title", help="Short description for a new core change")
    parser.add_argument("--rationale", default="", help="Why the code should be maintained")
    parser.add_argument(
        "--from-run",
        "--baseline-run",
        dest="baseline_run",
        help="Run ID or saved experiment that motivated this reusable change",
    )
    parser.add_argument("--ready", action="store_true", help="Run checks and mark it ready")
    parser.add_argument("--check", action="append", default=[])
    parser.add_argument("--feedback", action="store_true", help="Show requested changes")


def _add_review_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("proposal_id", nargs="?")
    parser.add_argument("--editor", help="Editor command; defaults to VISUAL or EDITOR")
    parser.add_argument(
        "--reviewer", help="Name stored with approval; defaults to your OS username"
    )
    parser.add_argument(
        "--terminal", action="store_true", help="Use the terminal diff instead of opening an editor"
    )


def _is_human_action(args: argparse.Namespace) -> bool:
    return (
        args.command == "review"
        or (args.command == "core" and args.core_command == "review")
        or (args.command == "promote" and args.promote_command in {"approve", "apply"})
        or (args.command == "gc" and args.gc_command == "apply")
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sift",
        description=(
            "Move research code from scratch to comparable experiments and reviewed core."
        ),
    )
    parser.add_argument("--version", action="version", version="sift 0.4.0")
    parser.add_argument("--json", dest="json_output", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    init = sub.add_parser("init", help="Initialize Sift in an existing project")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--package")

    sub.add_parser("status", help="Show scratch work, experiment runs, and changes needing review")

    experiment = sub.add_parser(
        "experiment", help="Create, run, save, compare, and reproduce experiments"
    )
    experiment_sub = experiment.add_subparsers(
        dest="experiment_command", required=True, metavar="ACTION"
    )
    experiment_new = experiment_sub.add_parser(
        "new", help="Create a scratch workspace for a new experiment"
    )
    experiment_new.add_argument("name")
    experiment_new.add_argument("--question", default="")
    experiment_new.add_argument("--from-run")
    experiment_new.add_argument(
        "--notebook", action="store_true", help="Include a marimo scratch notebook"
    )
    experiment_run = experiment_sub.add_parser(
        "run", help="Run a scratch experiment from a saved source snapshot"
    )
    experiment_run.add_argument("name", help="Scratch experiment name")
    experiment_run.add_argument(
        "--command", dest="command_text", help="Override the default experiment.py command"
    )
    _add_run_options(experiment_run)
    experiment_save = experiment_sub.add_parser(
        "save", help="Keep the scratch code used by an experiment run"
    )
    experiment_save.add_argument("run_id")
    experiment_save.add_argument("--name", help="Name for the saved experiment")
    experiment_save.add_argument(
        "--from", dest="scratch_name", help="Scratch name for a legacy or direct run"
    )
    experiment_list = experiment_sub.add_parser(
        "list", help="List recent runs with their configuration and results"
    )
    experiment_list.add_argument("--limit", type=int, default=20)
    experiment_compare = experiment_sub.add_parser(
        "compare", help="Compare configurations and JSON results across runs"
    )
    experiment_compare.add_argument("references", nargs="+")
    experiment_reproduce = experiment_sub.add_parser(
        "reproduce", help="Rerun saved code and compare its outputs"
    )
    experiment_reproduce.add_argument("reference")

    core = sub.add_parser("core", help="Propose and review changes to maintained code")
    core_sub = core.add_subparsers(dest="core_command", required=True, metavar="ACTION")
    core_propose = core_sub.add_parser(
        "propose", help="Prepare reusable code without changing maintained code"
    )
    _add_proposal_options(core_propose)
    core_review = core_sub.add_parser(
        "review",
        help="Review, request changes, or approve an exact core proposal",
        description="Inspect the diff and checks, then approve and apply or leave for later.",
    )
    _add_review_options(core_review)

    explore = sub.add_parser("explore")
    explore.add_argument("name")
    explore.add_argument("--question", default="")
    explore.add_argument("--from-run")
    explore.add_argument(
        "--notebook", action="store_true", help="Include a marimo scratch notebook"
    )

    run = sub.add_parser("run")
    run.add_argument("command_text")
    _add_run_options(run)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("kind", choices=["runs", "proposals", "archive", "dependencies"])
    inspect.add_argument("identifier", nargs="?")

    check = sub.add_parser("check")
    check.add_argument("--json", action="store_true")
    check.add_argument("--engine", choices=["builtin", "import-linter", "tach"])

    preserve_parser = sub.add_parser("preserve")
    preserve_parser.add_argument("scratch_name")
    preserve_parser.add_argument("--name")
    preserve_parser.add_argument("--run", dest="run_id")

    replay = sub.add_parser("replay")
    replay.add_argument("run_id")

    reproduce = sub.add_parser(
        "reproduce", help="Rerun a saved experiment or run and compare its outputs"
    )
    reproduce.add_argument("experiment_or_run")

    cache = sub.add_parser("cache")
    cache_sub = cache.add_subparsers(dest="cache_command", required=True)
    cache_key_parser = cache_sub.add_parser(
        "key", help="Create a cache key from computation inputs"
    )
    cache_key_parser.add_argument("--code", action="append", default=[])
    cache_key_parser.add_argument("--input", action="append", default=[])
    cache_key_parser.add_argument("--config", action="append", default=[])
    cache_key_parser.add_argument("--seed", action="append", type=int, default=[])
    cache_key_parser.add_argument(
        "--fresh", action="store_true", help="Create a unique key; does not change random seeds"
    )
    cache_key_parser.add_argument("--environment", action="append", default=[])
    cache_put_parser = cache_sub.add_parser("put", help="Store a file under an explicit key")
    cache_put_parser.add_argument("key")
    cache_put_parser.add_argument("file")
    cache_get_parser = cache_sub.add_parser("get", help="Restore a file stored under a key")
    cache_get_parser.add_argument("key")
    cache_get_parser.add_argument("destination")
    cache_drop_parser = cache_sub.add_parser(
        "drop", help="Remove a cache reference; GC removes unreferenced content"
    )
    cache_drop_parser.add_argument("key")

    pin = sub.add_parser("pin")
    pin.add_argument("identifier")
    pin.add_argument("--remove", action="store_true")

    gc_parser = sub.add_parser("gc")
    gc_sub = gc_parser.add_subparsers(dest="gc_command", required=True)
    gc_sub.add_parser("plan", help="Create a reviewable cleanup plan")
    gc_apply = gc_sub.add_parser("apply", help="Interactively apply an unchanged cleanup plan")
    gc_apply.add_argument("plan_id")

    promote = sub.add_parser("promote")
    promote_sub = promote.add_subparsers(dest="promote_command", required=True)
    promote_prepare = promote_sub.add_parser(
        "prepare", help="Create a separate working copy for proposed core changes"
    )
    promote_prepare.add_argument("--title", required=True)
    promote_prepare.add_argument("--rationale", default="")
    promote_prepare.add_argument("--baseline-run")
    promote_seal = promote_sub.add_parser(
        "seal", help="Run checks and save a fixed version for review"
    )
    promote_seal.add_argument("proposal_id")
    promote_seal.add_argument("--check", action="append", default=[])
    promote_show = promote_sub.add_parser(
        "show", help="Show the proposed changes, check results, and checksum"
    )
    promote_show.add_argument("proposal_id")
    promote_approve = promote_sub.add_parser(
        "approve", help="Approve the reviewed version of the proposed core changes"
    )
    promote_approve.add_argument("proposal_id")
    promote_apply = promote_sub.add_parser("apply", help="Apply a human-approved patch")
    promote_apply.add_argument("proposal_id")

    propose = sub.add_parser("propose")
    _add_proposal_options(propose)

    review = sub.add_parser(
        "review",
        description="Inspect the diff and checks, then approve and apply or leave for later.",
    )
    _add_review_options(review)

    retire_parser = sub.add_parser("retire")
    retire_sub = retire_parser.add_subparsers(dest="retire_command", required=True)
    retire_path = retire_sub.add_parser("path", help="Archive and remove a project directory")
    retire_path.add_argument("relative_path")
    retire_restore = retire_sub.add_parser("restore", help="Restore an archived directory")
    retire_restore.add_argument("retirement_id")

    archive = sub.add_parser("archive")
    archive.add_argument("path", nargs="?")
    archive.add_argument("--restore", metavar="ARCHIVE_ID")

    harness = sub.add_parser("harness")
    harness_sub = harness.add_subparsers(dest="harness_command", required=True)
    harness_sub.add_parser("policy", help="Print the machine-readable agent policy")
    guard = harness_sub.add_parser("guard", help="Reject commands reserved for a human")
    guard.add_argument("guarded_command", nargs=argparse.REMAINDER)
    writer = harness_sub.add_parser("check-write", help="Validate a host write-tool path")
    writer.add_argument("path")
    writer.add_argument("--proposal")
    launch_parser = harness_sub.add_parser(
        "launch", help="Launch an agent in a separate working copy"
    )
    launch_parser.add_argument(
        "--sandbox", choices=["candidate", "bubblewrap"], default="candidate"
    )
    launch_parser.add_argument("agent_command", nargs=argparse.REMAINDER)

    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--recover", action="store_true")
    doctor_parser.add_argument("--reindex", action="store_true")
    export_parser = sub.add_parser("export")
    export_parser.add_argument("run_id")
    export_parser.add_argument("destination")
    artifact = sub.add_parser("artifact")
    artifact_sub = artifact.add_subparsers(dest="artifact_command", required=True)
    artifact_put = artifact_sub.add_parser("put")
    artifact_put.add_argument("file")
    artifact_put.add_argument("--store", required=True)
    artifact_get = artifact_sub.add_parser("get")
    artifact_get.add_argument("sha256")
    artifact_get.add_argument("destination")
    artifact_get.add_argument("--store", required=True)

    skill = sub.add_parser("skill")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)
    skill_sub.add_parser("path", help="Print the bundled skill path")
    skill_install = skill_sub.add_parser(
        "install", help="Install the skill into an agent skill root"
    )
    skill_install.add_argument("--target", help="Skill root; defaults to $CODEX_HOME/skills")
    return parser


def _inspect(config: ProjectConfig, kind: str, identifier: str | None) -> None:
    if kind == "dependencies":
        from .boundaries import dependency_graph

        graph, violations = dependency_graph(config)
        _json(
            {
                "modules": {
                    module: {"path": str(node["path"]), "imports": node["imports"]}
                    for module, node in graph.items()
                    if not identifier or identifier in module
                },
                "errors": [str(item) for item in violations],
                "scope": "registered local source; computed dynamic imports are not inferred",
            }
        )
        return
    directory = config.state_dir / kind
    if identifier:
        if kind == "proposals":
            _json(proposal_summary(config, identifier))
        else:
            _json(
                load_run(config, identifier)
                if kind == "runs"
                else read_json(directory / safe_id(identifier) / "manifest.json")
            )
        return
    if not directory.exists():
        _json([])
        return
    records = []
    for path in sorted(directory.iterdir(), reverse=True):
        manifest = path / "manifest.json"
        if manifest.exists():
            records.append(read_json(manifest))
    _json(records)


def _policy() -> dict[str, object]:
    return policy()


def _guard(command: list[str]) -> None:
    _json(guard(command))


def _skill_source() -> Path:
    bundled = Path(__file__).parent / "bundled_skill"
    if bundled.exists():
        return bundled
    development = Path(__file__).parents[2] / "skills" / "sift"
    if development.exists():
        return development
    raise SiftError("The Sift agent skill was not included in this installation.")


def _install_skill(target: str | None) -> Path:
    if target:
        skill_root = Path(target).expanduser().resolve()
    else:
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        skill_root = codex_home / "skills"
    destination = skill_root / "sift"
    if destination.exists():
        raise SiftError(f"Skill already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_skill_source(), destination)
    return destination


def _execute_reproduction(config: ProjectConfig, args, reference: str) -> int:
    run_id = resolve_run(config, reference)
    replay_id, exit_code, matches = replay_run(config, run_id)
    _result(
        args,
        {
            "id": replay_id,
            "run_id": run_id,
            "exit_code": exit_code,
            "accepted": matches,
        },
        f"{replay_id} reproduced {run_id} (accepted={str(matches).lower()})",
    )
    return 0 if matches else 1


def _execute_proposal(config: ProjectConfig, args) -> int:
    review_command = "sift core review" if args.command == "core" else "sift review"
    if args.title and not args.proposal_id and not args.ready and not args.feedback:
        motivating_run = resolve_run(config, args.baseline_run) if args.baseline_run else None
        proposal_id, candidate = prepare(config, args.title, args.rationale, motivating_run)
        _result(
            args,
            {
                "id": proposal_id,
                "candidate": str(candidate),
                "status": "draft",
                "from_run": motivating_run,
            },
            f"{proposal_id}\nEdit candidate: {candidate}",
        )
        return 0
    if args.proposal_id and args.ready and not args.title and not args.feedback:
        digest = seal(config, args.proposal_id, tuple(args.check))
        summary = proposal_summary(config, args.proposal_id)
        ready = summary["status"] == "ready"
        _result(
            args,
            {
                "id": args.proposal_id,
                "status": summary["status"],
                "digest": digest,
                "next": (
                    f"Ask the researcher to run {review_command}"
                    if ready
                    else "Fix the failing checks and mark the proposal ready again"
                ),
            },
            (
                f"{summary['status']}: {args.proposal_id}\n"
                + (
                    f"The researcher can now run: {review_command}"
                    if ready
                    else "Fix the failing checks before requesting review."
                )
            ),
        )
        return 0 if ready else 1
    if args.proposal_id and args.feedback and not args.title and not args.ready:
        feedback = proposal_feedback(config, args.proposal_id)
        if args.json_output:
            _json(feedback)
        else:
            print(feedback["feedback"].rstrip())
            print(f"\nEdit candidate: {feedback['candidate_path']}")
        return 0
    if args.proposal_id and not args.title and not args.ready and not args.feedback:
        _json(proposal_summary(config, args.proposal_id))
        return 0
    raise SiftError("Start with --title, or provide a proposal ID with --ready or --feedback.")


def execute(args: argparse.Namespace) -> int:
    if args.command == "init":
        config = initialize_project(Path(args.path).resolve(), args.package)
        print(f"Initialized Sift at {config.root}")
        return 0

    if args.command == "harness":
        if args.harness_command == "policy":
            try:
                root = find_project()
            except SiftError:
                root = None
            _json(policy(ProjectConfig.load(root) if root else None))
        elif args.harness_command == "guard":
            _guard(args.guarded_command)
        elif args.harness_command == "check-write":
            _json(check_write(_config(), args.path, args.proposal))
        else:
            report = launch(_config(), args.agent_command, args.sandbox)
            _json(report)
            return report["exit_code"]
        return 0

    if args.command == "skill":
        if args.skill_command == "path":
            print(_skill_source())
        else:
            print(_install_skill(args.target))
        return 0

    config = _config()
    if os.environ.get("SIFT_ACTOR") == "agent" and _is_human_action(args):
        raise SiftError("Approval and application belong to the human-controlled host.")
    if args.command == "review" or (args.command == "core" and args.core_command == "review"):
        return _review(config, args.proposal_id, args.editor, args.reviewer, args.terminal)
    if args.command == "core":
        return _execute_proposal(config, args)
    if args.command == "experiment":
        if args.experiment_command == "new":
            path = create_exploration(
                config, args.name, args.question, args.from_run, args.notebook
            )
            _result(args, {"path": str(path)}, str(path))
            return 0
        if args.experiment_command == "run":
            exploration = slugify(args.name)
            script = config.root / config.scratch / exploration / "experiment.py"
            if not script.is_file():
                raise SiftError(f"Experiment script does not exist: {script}")
            command = args.command_text or (
                f'python "{script.relative_to(config.root).as_posix()}"'
            )
            run_id, exit_code = create_run(
                config,
                command,
                args.artifact,
                args.parent,
                args.change,
                args.input,
                args.seed,
                args.meta,
                args.verify,
                args.environment,
                args.cache_ref,
                args.launcher,
                exploration=exploration,
            )
            _result(
                args,
                {"id": run_id, "experiment": exploration, "exit_code": exit_code},
                f"{run_id} (exit {exit_code})",
            )
            return exit_code
        if args.experiment_command == "save":
            run_id = resolve_run(config, args.run_id)
            manifest = load_run(config, run_id)
            scratch_name = args.scratch_name or manifest.get("exploration")
            if not scratch_name:
                raise SiftError("This run predates experiment names; provide --from SCRATCH_NAME.")
            path = preserve(config, scratch_name, args.name, run_id)
            _result(
                args,
                {"path": str(path), "run_id": run_id, "scratch": scratch_name},
                str(path),
            )
            return 0
        if args.experiment_command == "list":
            table = experiment_runs(config, limit=args.limit)
        elif args.experiment_command == "compare":
            table = compare_experiments(config, tuple(args.references))
        else:
            return _execute_reproduction(config, args, args.reference)
        _json(table) if args.json_output else _print_experiment_runs(table)
        return 0
    if args.command == "status":
        status = workspace_status(config)
        if args.json_output:
            _json(status)
        else:
            _print_workspace_status(status)
    elif args.command == "explore":
        path = create_exploration(config, args.name, args.question, args.from_run, args.notebook)
        _result(args, {"path": str(path)}, str(path))
    elif args.command == "run":
        run_id, exit_code = create_run(
            config,
            args.command_text,
            args.artifact,
            args.parent,
            args.change,
            args.input,
            args.seed,
            args.meta,
            args.verify,
            args.environment,
            args.cache_ref,
            args.launcher,
        )
        _result(args, {"id": run_id, "exit_code": exit_code}, f"{run_id} (exit {exit_code})")
        return exit_code
    elif args.command == "inspect":
        _inspect(config, args.kind, args.identifier)
    elif args.command == "check":
        violations = check_boundaries(config)
        native = run_boundary_engine(config, args.engine)
        if args.json or args.json_output:
            _json(
                {
                    "violations": [vars(item) | {"file": str(item.file)} for item in violations],
                    "native": native,
                }
            )
        else:
            if violations:
                for item in violations:
                    print(f"{item.file}:{item.line}: {item.rule}: {item.imported}")
            else:
                print("Sift boundaries passed.")
            if native:
                print(native["stdout"])
                if native["stderr"]:
                    print(native["stderr"], file=sys.stderr)
        return 1 if violations or (native and native["exit_code"]) else 0
    elif args.command == "preserve":
        path = preserve(config, args.scratch_name, args.name, args.run_id)
        _result(args, {"path": str(path), "run_id": args.run_id}, str(path))
    elif args.command == "replay":
        replay_id, exit_code, matches = replay_run(config, args.run_id)
        _result(
            args,
            {"id": replay_id, "exit_code": exit_code, "accepted": matches},
            f"{replay_id} (exit {exit_code}, accepted={str(matches).lower()})",
        )
        return 0 if matches else 1
    elif args.command == "reproduce":
        return _execute_reproduction(config, args, args.experiment_or_run)
    elif args.command == "cache":
        if args.cache_command == "key":
            print(
                cache_key(
                    code=args.code,
                    inputs=args.input,
                    config=args.config,
                    seeds=args.seed,
                    fresh=args.fresh,
                    environment=args.environment,
                )
            )
        elif args.cache_command == "put":
            _json(cache_put(config, args.key, Path(args.file).resolve()))
        elif args.cache_command == "get":
            _json(cache_get(config, args.key, Path(args.destination).resolve()))
        else:
            _json(cache_drop(config, args.key))
    elif args.command == "pin":
        set_pin(config, args.identifier, not args.remove)
        print(f"{'Unpinned' if args.remove else 'Pinned'} {args.identifier}")
    elif args.command == "gc":
        if args.gc_command == "plan":
            plan_id, digest, candidates = plan_gc(config)
            _json(
                {
                    "id": plan_id,
                    "digest": digest,
                    "candidates": candidates,
                    "next": f"Human review, then: sift gc apply {plan_id}",
                }
            )
        else:
            if not sys.stdin.isatty():
                raise SiftError("GC application requires an interactive human terminal.")
            record = read_json(config.state_dir / "gc" / safe_id(args.plan_id) / "plan.json")
            _json(record)
            try:
                confirmation = input(
                    "Type the first 12 digest characters to apply this exact cleanup plan: "
                ).strip()
            except EOFError as exc:
                raise SiftError("GC application requires input from a human reviewer.") from exc
            print(f"Removed {apply_gc(config, args.plan_id, confirmation)} archived records")
    elif args.command == "promote":
        if args.promote_command == "prepare":
            proposal_id, candidate = prepare(config, args.title, args.rationale, args.baseline_run)
            _result(
                args,
                {"id": proposal_id, "candidate": str(candidate)},
                f"{proposal_id}\nEdit candidate: {candidate}",
            )
        elif args.promote_command == "seal":
            digest = seal(config, args.proposal_id, tuple(args.check))
            summary = proposal_summary(config, args.proposal_id)
            _result(
                args,
                {
                    "id": args.proposal_id,
                    "digest": digest,
                    "status": summary["status"],
                    "diff": summary["diff_path"],
                },
                f"{summary['status']}: {digest}\nDiff: {summary['diff_path']}",
            )
            return 0 if summary["status"] == "ready" else 1
        elif args.promote_command == "show":
            _json(proposal_summary(config, args.proposal_id))
        elif args.promote_command == "approve":
            print(f"Approved by {approve(config, args.proposal_id)}")
        elif args.promote_command == "apply":
            apply_promotion(config, args.proposal_id)
            print(f"Applied {args.proposal_id}")
    elif args.command == "propose":
        return _execute_proposal(config, args)
    elif args.command == "retire":
        if args.retire_command == "path":
            retirement_id = retire(config, args.relative_path)
            _result(args, {"id": retirement_id, "recoverable": True}, retirement_id)
        else:
            print(restore_retirement(config, args.retirement_id))
    elif args.command == "archive":
        if args.restore and not args.path:
            print(restore_retirement(config, args.restore))
        elif args.path and not args.restore:
            retirement_id = retire(config, args.path)
            _result(args, {"id": retirement_id, "recoverable": True}, retirement_id)
        else:
            raise SiftError("Provide a path to archive or use --restore ARCHIVE_ID.")
    elif args.command == "doctor":
        result = doctor(config, args.recover)
        if args.reindex:
            result["indexed"] = rebuild_index(config)
        _json(result)
        return 1 if result["issues"] else 0
    elif args.command == "export":
        print(export_run(config, args.run_id, Path(args.destination).resolve()))
    elif args.command == "artifact":
        config.check_output_destination(Path(args.store))
        store = LocalArtifactStore(Path(args.store))
        if args.artifact_command == "put":
            _json(asdict(store.put(Path(args.file))))
        else:
            config.check_output_destination(Path(args.destination))
            print(store.get(ArtifactRef(args.sha256, "", args.store), Path(args.destination)))
    return 0


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    try:
        if args.json_output:
            if _is_human_action(args):
                raise SiftError("Human review requires visible terminal output; omit --json.")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = execute(args)
            value = output.getvalue().strip()
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
            _json({"exit_code": exit_code, "result": value})
        else:
            exit_code = execute(args)
        raise SystemExit(exit_code)
    except (SiftError, OSError) as exc:
        if args.json_output:
            _json({"error": str(exc), "exit_code": 2})
            raise SystemExit(2) from exc
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
