# Agent host integration

Sift separates preparing a change from authorizing it. Use the bundled skill and connect this contract
to the host's tool and filesystem permissions.

## Launch an agent

~~~bash
sift harness launch -- your-agent
~~~

The agent starts in an isolated promotion candidate. `SIFT_ACTOR=agent` prevents Sift's human-only
commands in that session. The original core is compared before/after the session; the candidate is
left available for review. No candidate is applied automatically.

This backend detects original-core changes; it cannot prevent arbitrary writes by an unrestricted
same-user process. It never attempts to roll back unrelated user edits.

On Linux hosts where bubblewrap is installed and permitted:

~~~bash
sift harness launch --sandbox bubblewrap -- your-agent
~~~

The filesystem is mounted read-only except for the candidate and temporary runtime files. The
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

Only a human-controlled terminal or trusted host review UI may approve and apply a promotion.
The skill never runs `promote approve`, `promote apply`, or `gc apply`. A terminal flag is not proof
of human identity against an unrestricted process; actual authority is supplied by the host.

Seals bind candidate content, diffs, checks, and the reference project state. Editing any reviewed
content requires resealing and fresh review. Application validates the seal again before writing.

