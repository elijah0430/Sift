---
name: sift
description: Organize Python research code with Sift when an agent should explore in scratch, save experiment scripts, prepare reusable code for human review, rerun experiments, or archive unused code.
---

# Sift research workflow

Use Sift to keep exploratory work fast while protecting maintained code.

## Choose the operation

- For uncertain implementations or analyses, create or continue a scratch exploration with `sift explore`.
- For an experiment run whose results may matter, use `sift run` to save its code, inputs, and outputs.
- To keep an experiment's code, use `sift preserve SCRATCH_NAME --run RUN_ID` to copy the version used
  for that run. Without a run ID, this saves the current code without checking reproducibility.
- When functions or modules should be shared across experiments, prepare a core change for review.
- When scratch or experiment code is no longer needed, archive it with `sift retire`.
- Use cache reuse only when code, inputs, configuration, and randomness belong to the cache key. Use
  `--fresh` to create a new key when reuse is inappropriate. This does not change random seeds.

Read [references/workflows.md](references/workflows.md) before preparing core changes, rerunning an
experiment, or archiving code.

Prefer `sift --json COMMAND` for machine-readable results. Use `sift doctor` to inspect interrupted
work and actual process liveness; do not infer that a job stopped from a timeout or an old manifest.
Use the bundled harness with host permissions. The default candidate launcher detects changes to
the original core; only a configured OS/host sandbox prevents arbitrary writes.

## Protect core

During ordinary exploration, write only inside the relevant scratch directory. Core may be read and imported.

To move reusable code into core, run `sift promote prepare`, edit only the separate working copy it
creates, then run `sift promote seal`. This checks and saves a fixed version for review. Present the
reason for the change, public API, test results, behavior changes, remaining uncertainty, diff path,
and version checksum to the user.

Never run `sift review`, `sift promote approve`, or `sift promote apply`. Tell the user that the core
change is ready and ask them to run `sift review` in their terminal. That flow shows the report, diff,
and test output and can approve and apply the exact reviewed version. If the proposed code changes,
run `seal` again and request a new review.

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

Use familiar terms in reports: exploratory code, reusable modules, experiment scripts, experiment
runs, and results. Describe what was saved, run, and checked rather than using internal status labels
such as `restorable` or `replay-verified` as conclusions.

Preserve shapes, axes, normalization, operation order, randomness, datasets, checkpoints, and model
conditions when they affect the result.

