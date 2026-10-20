from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .boundaries import check_boundaries
from .config import ProjectConfig, initialize_project
from .errors import SiftError
from .lifecycle import create_exploration, preserve, restore_retirement, retire
from .promotion import apply as apply_promotion
from .promotion import approve, prepare, proposal_summary, seal
from .snapshots import create_run, replay_run
from .util import find_project, read_json


def _config() -> ProjectConfig:
    return ProjectConfig.load(find_project())


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sift",
        description="Explore freely. Keep what matters.",
    )
    parser.add_argument("--version", action="version", version="sift 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize Sift in an existing project")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--package")

    explore = sub.add_parser("explore", help="Create an isolated scratch exploration")
    explore.add_argument("name")
    explore.add_argument("--question", default="")

    run = sub.add_parser("run", help="Run from a frozen source snapshot")
    run.add_argument("command_text")
    run.add_argument("--artifact", action="append", default=[])
    run.add_argument("--parent")
    run.add_argument("--change")

    inspect = sub.add_parser("inspect", help="Inspect runs or promotion proposals")
    inspect.add_argument("kind", choices=["runs", "proposals", "archive"])
    inspect.add_argument("identifier", nargs="?")

    check = sub.add_parser("check", help="Check architectural boundaries")
    check.add_argument("--json", action="store_true")

    preserve_parser = sub.add_parser("preserve", help="Preserve scratch as an experiment recipe")
    preserve_parser.add_argument("scratch_name")
    preserve_parser.add_argument("--name")

    replay = sub.add_parser("replay", help="Replay a recorded run")
    replay.add_argument("run_id")

    promote = sub.add_parser("promote", help="Prepare and review exact core promotion patches")
    promote_sub = promote.add_subparsers(dest="promote_command", required=True)
    promote_prepare = promote_sub.add_parser(
        "prepare", help="Create an isolated candidate workspace"
    )
    promote_prepare.add_argument("--title", required=True)
    promote_prepare.add_argument("--rationale", default="")
    promote_seal = promote_sub.add_parser("seal", help="Freeze candidate patch and run checks")
    promote_seal.add_argument("proposal_id")
    promote_seal.add_argument("--check", action="append", default=[])
    promote_show = promote_sub.add_parser("show", help="Show the candidate, checks, and digest")
    promote_show.add_argument("proposal_id")
    promote_approve = promote_sub.add_parser(
        "approve", help="Interactively approve the exact sealed patch"
    )
    promote_approve.add_argument("proposal_id")
    promote_apply = promote_sub.add_parser("apply", help="Apply a human-approved patch")
    promote_apply.add_argument("proposal_id")

    retire_parser = sub.add_parser("retire", help="Archive then remove scratch or an experiment")
    retire_sub = retire_parser.add_subparsers(dest="retire_command", required=True)
    retire_path = retire_sub.add_parser("path", help="Retire a project-relative path")
    retire_path.add_argument("relative_path")
    retire_restore = retire_sub.add_parser("restore", help="Restore a retired path")
    retire_restore.add_argument("retirement_id")

    harness = sub.add_parser("harness", help="Expose and enforce host integration policy")
    harness_sub = harness.add_subparsers(dest="harness_command", required=True)
    harness_sub.add_parser("policy", help="Print the machine-readable agent policy")
    guard = harness_sub.add_parser("guard", help="Reject commands reserved for a human")
    guard.add_argument("guarded_command", nargs=argparse.REMAINDER)

    skill = sub.add_parser("skill", help="Locate or install the bundled agent skill")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)
    skill_sub.add_parser("path", help="Print the bundled skill path")
    skill_install = skill_sub.add_parser(
        "install", help="Install the skill into an agent skill root"
    )
    skill_install.add_argument("--target", help="Skill root; defaults to $CODEX_HOME/skills")
    return parser


def _inspect(config: ProjectConfig, kind: str, identifier: str | None) -> None:
    directory = config.state_dir / kind
    if identifier:
        if kind == "proposals":
            _json(proposal_summary(config, identifier))
        else:
            _json(read_json(directory / identifier / "manifest.json"))
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
    return {
        "schema": 1,
        "actor": "agent",
        "allowed": [
            "sift explore",
            "sift run",
            "sift check",
            "sift inspect",
            "sift preserve",
            "sift replay",
            "sift promote prepare",
            "sift promote seal",
            "sift promote show",
        ],
        "human_only": ["sift promote approve", "sift promote apply"],
        "core_write_mode": "candidate-only until exact patch approval",
    }


def _guard(command: list[str]) -> None:
    if command and command[0] == "--":
        command = command[1:]
    normalized = " ".join(command).lower().strip()
    denied = ("sift promote approve", "sift promote apply")
    if any(item in normalized for item in denied):
        raise SiftError("This command is reserved for a human reviewer.")
    _json({"allowed": True, "command": command})


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


def execute(args: argparse.Namespace) -> int:
    if args.command == "init":
        config = initialize_project(Path(args.path).resolve(), args.package)
        print(f"Initialized Sift at {config.root}")
        return 0

    if args.command == "harness":
        if args.harness_command == "policy":
            _json(_policy())
        else:
            _guard(args.guarded_command)
        return 0

    if args.command == "skill":
        if args.skill_command == "path":
            print(_skill_source())
        else:
            print(_install_skill(args.target))
        return 0

    config = _config()
    if args.command == "explore":
        print(create_exploration(config, args.name, args.question))
    elif args.command == "run":
        run_id, exit_code = create_run(
            config, args.command_text, args.artifact, args.parent, args.change
        )
        print(f"{run_id} (exit {exit_code})")
        return exit_code
    elif args.command == "inspect":
        _inspect(config, args.kind, args.identifier)
    elif args.command == "check":
        violations = check_boundaries(config)
        if args.json:
            _json([vars(item) | {"file": str(item.file)} for item in violations])
        elif violations:
            for item in violations:
                print(f"{item.file}:{item.line}: {item.rule}: {item.imported}")
        else:
            print("Sift boundaries passed.")
        return 1 if violations else 0
    elif args.command == "preserve":
        print(preserve(config, args.scratch_name, args.name))
    elif args.command == "replay":
        replay_id, exit_code, matches = replay_run(config, args.run_id)
        print(f"{replay_id} (exit {exit_code}, exact_match={str(matches).lower()})")
        return 0 if matches else 1
    elif args.command == "promote":
        if args.promote_command == "prepare":
            proposal_id, candidate = prepare(config, args.title, args.rationale)
            print(f"{proposal_id}\nEdit candidate: {candidate}")
        elif args.promote_command == "seal":
            digest = seal(config, args.proposal_id, tuple(args.check))
            summary = proposal_summary(config, args.proposal_id)
            print(f"{summary['status']}: {digest}\nDiff: {summary['diff_path']}")
            return 0 if summary["status"] == "ready" else 1
        elif args.promote_command == "show":
            _json(proposal_summary(config, args.proposal_id))
        elif args.promote_command == "approve":
            print(f"Approved by {approve(config, args.proposal_id)}")
        elif args.promote_command == "apply":
            apply_promotion(config, args.proposal_id)
            print(f"Applied {args.proposal_id}")
    elif args.command == "retire":
        if args.retire_command == "path":
            print(retire(config, args.relative_path))
        else:
            print(restore_retirement(config, args.retirement_id))
    return 0


def main(argv: list[str] | None = None) -> None:
    try:
        raise SystemExit(execute(_parser().parse_args(argv)))
    except SiftError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
