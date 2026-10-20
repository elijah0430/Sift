---
name: sift
description: Manage exploratory Python research code with Sift when an agent should work in scratch, preserve a reproducible experiment, prepare a reviewed core promotion, replay a run, or retire obsolete research code.
---

# Sift research workflow

Use Sift to keep exploratory work fast while protecting maintained code.

## Choose the lifecycle operation

- For uncertain implementations or analyses, create or continue a scratch exploration with `sift explore`.
- For an execution whose evidence may matter, use `sift run` so source and outputs are recorded.
- When a one-off procedure matters, use `sift preserve --run RUN_ID` to attach its recorded execution.
  Preservation without a run keeps a recipe; it does not establish reproducibility.
- When a capability deserves ongoing maintenance, prepare a promotion proposal.
- When scratch or experiment code is no longer active, use recoverable retirement.
- Use cache reuse only when code, inputs, configuration, and randomness belong to the cache key. Use
  a fresh-trial key when the scientific procedure calls for a new stochastic execution.

Read [references/workflows.md](references/workflows.md) before performing a promotion, replay, or retirement.

Prefer `sift --json COMMAND` for machine-readable results. Use `sift doctor` to inspect interrupted
work and actual process liveness; do not infer that a job stopped from a timeout or an old manifest.
Use the bundled harness with host permissions. The default candidate launcher detects changes to
the original core; only a configured OS/host sandbox prevents arbitrary writes.

## Protect core

During ordinary exploration, write only inside the relevant scratch directory. Core may be read and imported.

For promotion, run `sift promote prepare`, edit only the returned candidate workspace, then run
`sift promote seal`. Present the proposal rationale, public interface, validation results, behavior
changes, remaining uncertainty, diff path, and digest to the user.

Never run `sift promote approve` or `sift promote apply`. Those commands are reserved for a human
reviewer and apply only to the exact sealed digest. If the candidate changes, reseal it and request a
new review.

You may prepare a cleanup plan with `sift gc plan`. Never run `sift gc apply`; show its targets and
digest to the user for human review. Pin any run or archive that must survive retention cleanup.

Prefer the smallest interface justified by concrete uses. Keep experiment-specific orchestration in
the experiment. Do not add core flags for scratch experiment names; pass experimental functions or
objects through an explicit interface.

## Report evidence precisely

Distinguish:

- core checks from scientific correctness;
- behavior preservation from independent correctness;
- a recorded run from a restorable run;
- a restorable run from a replay-verified run.

Preserve shapes, axes, normalization, operation order, randomness, datasets, checkpoints, and model
conditions when they affect the result.

