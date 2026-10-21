---
name: sift
description: Organize Python research code with Sift when an agent should explore in scratch, save experiment scripts, prepare reusable code for human review, rerun experiments, or archive unused code.
---

# Sift research workflow

Use Sift to keep exploratory work fast while protecting maintained code.

## Choose the operation

- For uncertain implementations or analyses, use `sift experiment new NAME` and work in its scratch
  directory.
- Extend a saved experiment with `sift experiment new NAME --from-run REFERENCE`. Its code, run
  options, and parent link carry forward; the new run uses current core and input files.
- Run work that may support a research decision with `sift experiment run NAME`, declaring relevant
  inputs, outputs, seeds, and configuration metadata.
- Use `sift experiment compare RUN_A RUN_B` before deciding that a result or implementation matters.
- Keep the exact experiment code with `sift experiment save RUN_ID` when it should remain reproducible.
- When a function or module should be maintained and reused, prepare a core change with
  `sift core propose --from-run RUN_ID` and submit it for human review.

Read [references/workflows.md](references/workflows.md) before preparing core changes, rerunning an
experiment, or archiving code.

Prefer `sift --json COMMAND` for machine-readable results. Use `sift doctor` to inspect interrupted
work and actual process liveness; do not infer that a job stopped from a timeout or an old manifest.
Use the bundled harness with host permissions. The default candidate launcher detects changes to
the original core; only a configured OS/host sandbox prevents arbitrary writes.

At setup, confirm `sift check` names the intended core files. Inspect large snapshot paths and exclude
unused data/checkpoints in `research.toml`; `.gitignore` does not control snapshots. Use the short IDs
printed by Sift. Inspect results with `experiment show` and failures with `experiment logs`.

## Protect core

During ordinary exploration, write only inside the relevant scratch directory. Core may be read and imported.

To move reusable code into core, run
`sift core propose --title TITLE --rationale RATIONALE --from-run RUN_ID`, edit only the separate
review workspace it creates, then run `sift core propose PROPOSAL_ID --ready`. This checks and saves
an exact version for review. Cite the motivating run when the change follows from an experiment.
Present the reason for the change, public API, test results, behavior changes, and remaining
uncertainty to the user.

Before revising a proposal returned by the reviewer, run
`sift core propose PROPOSAL_ID --feedback`. Address the concrete requests in the candidate, rerun the
relevant software and experiment checks, and mark the proposal ready again.

Never run `sift core review`, `sift promote approve`, or `sift promote apply`. Tell the user that the core
change is ready and ask them to run `sift core review` in their terminal. That flow opens the proposal in
their configured editor, shows the checks, and can approve and apply the exact reviewed version. If
the proposed code changes, run `sift core propose PROPOSAL_ID --ready` again and request a new review.

You may prepare a cleanup plan with `sift gc plan`. Never run `sift gc apply`; show its targets and
digest to the user for human review. Pin any run or archive that must survive retention cleanup.

Prefer the smallest interface justified by concrete uses. Keep experiment-specific orchestration in
the experiment. Do not add core flags for scratch experiment names; pass experimental functions or
objects through an explicit interface.

## Report tests and results precisely

Distinguish:

- passing software tests from supporting a research claim;
- matching the original implementation from checking expected behavior;
- saving code and logs from capturing all declared input data;
- having code and inputs available from rerunning the experiment and comparing its outputs.

Use familiar terms in reports: scratch code, reusable modules, experiment scripts, experiment runs,
and results. Describe what was saved, run, and checked rather than using internal status labels
such as `restorable` or `replay-verified` as conclusions.

Preserve shapes, axes, normalization, operation order, randomness, datasets, checkpoints, and model
conditions when they affect the result.

