from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
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
from .promotion import approve, prepare, proposal_summary, seal
from .snapshots import create_run, load_run, replay_run
from .util import find_project, read_json, safe_id


def _config() -> ProjectConfig:
    return ProjectConfig.load(find_project())


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def _result(args, value: dict, message: str) -> None:
    _json(value) if args.json_output else print(message)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sift",
        description="Explore freely. Keep what matters.",
    )
    parser.add_argument("--version", action="version", version="sift 0.1.0")
    parser.add_argument("--json", dest="json_output", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize Sift in an existing project")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--package")

    explore = sub.add_parser("explore", help="Create an isolated scratch exploration")
    explore.add_argument("name")
    explore.add_argument("--question", default="")
    explore.add_argument("--from-run")
    explore.add_argument(
        "--notebook", action="store_true", help="Include a marimo scratch notebook"
    )

    run = sub.add_parser("run", help="Run from a frozen source snapshot")
    run.add_argument("command_text")
    run.add_argument("--artifact", action="append", default=[])
    run.add_argument("--parent")
    run.add_argument("--change")
    run.add_argument("--input", action="append", default=[], help="Record NAME=PATH_OR_ID")
    run.add_argument("--seed", action="append", type=int, default=[])
    run.add_argument("--meta", action="append", default=[], help="Record NAME=VALUE")
    run.add_argument("--verify", help="Command whose zero exit code accepts this run and replay")
    run.add_argument("--environment", choices=["current", "uv"], default="current")
    run.add_argument("--cache-ref", action="append", default=[])
    run.add_argument(
        "--launcher", help="Shared-filesystem scheduler prefix, e.g. srun --partition=gpu"
    )

    inspect = sub.add_parser("inspect", help="Inspect runs or promotion proposals")
    inspect.add_argument("kind", choices=["runs", "proposals", "archive", "dependencies"])
    inspect.add_argument("identifier", nargs="?")

    check = sub.add_parser("check", help="Check architectural boundaries")
    check.add_argument("--json", action="store_true")
    check.add_argument("--engine", choices=["builtin", "import-linter", "tach"])

    preserve_parser = sub.add_parser("preserve", help="Preserve scratch as an experiment recipe")
    preserve_parser.add_argument("scratch_name")
    preserve_parser.add_argument("--name")
    preserve_parser.add_argument("--run", dest="run_id")

    replay = sub.add_parser("replay", help="Replay a recorded run")
    replay.add_argument("run_id")

    cache = sub.add_parser("cache", help="Manage explicit content-addressed computation outputs")
    cache_sub = cache.add_subparsers(dest="cache_command", required=True)
    cache_key_parser = cache_sub.add_parser("key", help="Derive a reusable or fresh-trial key")
    cache_key_parser.add_argument("--code", action="append", default=[])
    cache_key_parser.add_argument("--input", action="append", default=[])
    cache_key_parser.add_argument("--config", action="append", default=[])
    cache_key_parser.add_argument("--seed", action="append", type=int, default=[])
    cache_key_parser.add_argument("--fresh", action="store_true")
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

    pin = sub.add_parser("pin", help="Protect or unprotect a record from garbage collection")
    pin.add_argument("identifier")
    pin.add_argument("--remove", action="store_true")

    gc_parser = sub.add_parser("gc", help="Plan and apply retention-based cleanup")
    gc_sub = gc_parser.add_subparsers(dest="gc_command", required=True)
    gc_sub.add_parser("plan", help="Create a reviewable cleanup plan")
    gc_apply = gc_sub.add_parser("apply", help="Interactively apply an unchanged cleanup plan")
    gc_apply.add_argument("plan_id")

    promote = sub.add_parser("promote", help="Prepare and review exact core promotion patches")
    promote_sub = promote.add_subparsers(dest="promote_command", required=True)
    promote_prepare = promote_sub.add_parser(
        "prepare", help="Create an isolated candidate workspace"
    )
    promote_prepare.add_argument("--title", required=True)
    promote_prepare.add_argument("--rationale", default="")
    promote_prepare.add_argument("--baseline-run")
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
    writer = harness_sub.add_parser("check-write", help="Validate a host write-tool path")
    writer.add_argument("path")
    writer.add_argument("--proposal")
    launch_parser = harness_sub.add_parser(
        "launch", help="Launch an agent in an isolated candidate"
    )
    launch_parser.add_argument(
        "--sandbox", choices=["candidate", "bubblewrap"], default="candidate"
    )
    launch_parser.add_argument("agent_command", nargs=argparse.REMAINDER)

    doctor_parser = sub.add_parser("doctor", help="Inspect live processes and interrupted records")
    doctor_parser.add_argument("--recover", action="store_true")
    doctor_parser.add_argument("--reindex", action="store_true")
    export_parser = sub.add_parser("export", help="Export a portable run and its captured inputs")
    export_parser.add_argument("run_id")
    export_parser.add_argument("destination")
    artifact = sub.add_parser("artifact", help="Store files in local or mounted artifact storage")
    artifact_sub = artifact.add_subparsers(dest="artifact_command", required=True)
    artifact_put = artifact_sub.add_parser("put")
    artifact_put.add_argument("file")
    artifact_put.add_argument("--store", required=True)
    artifact_get = artifact_sub.add_parser("get")
    artifact_get.add_argument("sha256")
    artifact_get.add_argument("destination")
    artifact_get.add_argument("--store", required=True)

    skill = sub.add_parser("skill", help="Locate or install the bundled agent skill")
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
    if os.environ.get("SIFT_ACTOR") == "agent" and (
        (args.command == "promote" and args.promote_command in {"approve", "apply"})
        or (args.command == "gc" and args.gc_command == "apply")
    ):
        raise SiftError("Approval and application belong to the human-controlled host.")
    if args.command == "explore":
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
    elif args.command == "retire":
        if args.retire_command == "path":
            retirement_id = retire(config, args.relative_path)
            _result(args, {"id": retirement_id, "recoverable": True}, retirement_id)
        else:
            print(restore_retirement(config, args.retirement_id))
    elif args.command == "doctor":
        result = doctor(config, args.recover)
        if args.reindex:
            result["indexed"] = rebuild_index(config)
        _json(result)
        return 1 if result["issues"] else 0
    elif args.command == "export":
        print(export_run(config, args.run_id, Path(args.destination).resolve()))
    elif args.command == "artifact":
        store = LocalArtifactStore(Path(args.store))
        if args.artifact_command == "put":
            _json(asdict(store.put(Path(args.file))))
        else:
            print(store.get(ArtifactRef(args.sha256, "", args.store), Path(args.destination)))
    return 0


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    try:
        if args.json_output:
            if (args.command == "promote" and args.promote_command == "approve") or (
                args.command == "gc" and args.gc_command == "apply"
            ):
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
