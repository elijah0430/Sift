# Agent host integration

Sift separates preparing code changes from approving them. Use the bundled skill and connect these rules
to the host's tool and filesystem permissions.

## Launch an agent

~~~bash
sift harness launch -- your-agent
~~~

The agent starts in a separate working copy for proposed core changes. `SIFT_ACTOR=agent` prevents Sift's human-only
commands in that session. The original core is compared before and after the session; the working
copy is left available for review. Changes are not applied automatically.

At session exit, completed/failed/interrupted runs and saved experiment scripts are validated and
published to the original project. The launch report lists imported IDs and paths under `research`.
Source, input, and artifact hash mismatches abort publication. Running jobs remain in the candidate
and are reported under `research.pending_runs`; publication is not continuous. Core and approval
state remain part of the separate human review workflow.

This backend detects original-core changes; it cannot prevent arbitrary writes by an unrestricted
same-user process. It never attempts to roll back unrelated user edits.

On Linux hosts where bubblewrap is installed and permitted:

~~~bash
sift harness launch --sandbox bubblewrap -- your-agent
~~~

The filesystem is mounted read-only except for the working copy and temporary runtime files. The
backend fails if bubblewrap cannot start; it does not silently fall back to weaker enforcement.
Configure writable agent credential/session state through your trusted host if the agent needs it.

## Route tools

- `sift harness policy` returns a machine-readable contract.
- `sift harness guard -- sift ...` validates Sift argv. It rejects human-only commands, including
  Python module invocation forms; it does not claim to parse arbitrary shell programs.
- `sift harness check-write PATH --proposal ID` validates a file-tool write destination. Ordinary
  writes belong in scratch or the selected candidate.

Protect core, tests, configuration, proposal manifests/seals/approvals, and the host policy itself.
Allow toolkit-managed state changes through the permitted CLI actions, not arbitrary file writes.

## Human actions

Only a human-controlled terminal or trusted host review UI may approve and apply core changes.
The skill never runs `core review`, `promote approve`, `promote apply`, or `gc apply`. A terminal flag is
not proof of human identity against an unrestricted process; actual authority is supplied by the host.

`sift core review` lists pending core changes, opens the candidate in the configured editor, and returns
to a human-controlled approval menu. The candidate is a local Git repository when Git is available,
so normal editor Source Control views show the proposal. If the reviewer edits it, Sift reruns the
configured checks and displays the refreshed diff before approval.

Requesting changes removes the proposal from the human review queue. The agent reads the feedback
with `sift core propose PROPOSAL_ID --feedback`, revises the candidate, and runs
`sift core propose PROPOSAL_ID --ready`.

`sift core propose PROPOSAL_ID --ready` saves an exact version of the proposed code, diff, check results,
and original project state. Editing reviewed content requires running the checks again and obtaining
new approval. Sift validates that version again before applying the changes.

