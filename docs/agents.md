# Using Sift with coding agents

Sift divides responsibility between an agent that conducts research work and a researcher who
controls changes to maintained code.

## Agent workflow

The agent normally works through two command groups:

| Research task | Command |
|---|---|
| Start uncertain work | `sift experiment new NAME` |
| Execute a saved source snapshot | `sift experiment run NAME` |
| Compare selected runs | `sift experiment compare RUN_A RUN_B` |
| Keep experiment code | `sift experiment save RUN_ID` |
| Prepare reusable code | `sift core propose --from-run RUN_ID` |

The agent may inspect status, experiments, runs, proposals, and reviewer feedback. It does not run
`sift core review`,
approve or apply core changes, or apply permanent cleanup.

## Install the agent skill

The Python package includes a skill that explains this workflow to a coding agent:

```bash
sift skill install
# Or install into another agent's skill directory:
sift skill install --target /path/to/agent/skills
```

The source is available in [`skills/sift`](../skills/sift/SKILL.md). Its detailed lifecycle guidance
is in the [workflow reference](../skills/sift/references/workflows.md).

## Connect host permissions

Inspect Sift's machine-readable agent policy with:

```bash
sift harness policy
sift harness guard -- sift core propose --title "Shared evaluation function"
```

`guard` validates Sift command arguments and rejects human-only commands. A host can also call
`sift harness check-write PATH --proposal ID` before file writes so ordinary agent edits remain in
scratch or in the selected proposal directory.

The guard does not parse arbitrary shell programs. Protect core, tests, project configuration,
proposal approvals, and the host policy through the agent host's filesystem and tool permissions.

## Launch an agent in a separate working copy

```bash
sift harness launch -- your-coding-agent
```

The launcher sets `SIFT_ACTOR=agent`, creates a separate working copy, and checks that the original
core did not change during the session. It leaves the working copy available for review. This detects
original-core changes but cannot prevent arbitrary writes from an unrestricted process running as the
same operating-system user.

The working copy receives validated copies of existing finalized runs, so the agent can compare and
extend previous experiments by their usual names and IDs. These copies do not expose writable links
to the original history; modified inherited records are rejected during publication.
Current declared project inputs are also copied when source snapshot exclusions would omit them.

When the agent exits, Sift validates and imports finalized runs, saved experiment scripts, and new
unapproved core proposals into the original project. Ready proposals are checked and sealed again in
the receiving project, then appear in `sift core list`, `sift status`, and the researcher's review queue.
Their IDs remain the same. Source, input, and artifact hashes are checked before publication;
maintained core is not changed and approval files are never imported. Runs still preparing or running remain in the candidate,
with their IDs listed under `research.pending_runs` in the launch report. This is not a live shared
history while the isolated agent is still running.

On Linux with bubblewrap installed:

```bash
sift harness launch --sandbox bubblewrap -- your-coding-agent
```

This makes the filesystem read-only except for the working copy and temporary runtime files. The
command fails if bubblewrap cannot start instead of silently using weaker isolation.

Only a human-controlled terminal or trusted host review interface should run `sift core review` or
`sift gc apply`. Interactive input alone does not authenticate a human against an unrestricted
same-user agent.
