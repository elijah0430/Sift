# Experiment runs and reproducibility

An **experiment run** is one execution of a scratch experiment. Sift saves a source snapshot, executes
a separate copy, and records the command, related previous run, description of the change, declared
inputs, random seeds, runtime information, dependency files, logs, and declared output files.

```bash
sift experiment new my-method
sift experiment run my-method --command "python scratch/my-method/train.py" \
  --artifact results/metrics.json \
  --input dataset=data/train.json \
  --seed 7 \
  --meta model=small
```

Sift removes previous copies of declared outputs before execution, so stale files cannot be mistaken
for new results. A missing declared output causes the run to fail even when the command exits
successfully.

## Inputs and environments

Declared file or directory inputs are copied and hashed before execution. The run accesses a captured
input through `SIFT_INPUT_NAME`. An input identifier without captured data is retained in the record,
but cannot verify that the same data will be available later.

Seeds are recorded and exposed as `SIFT_SEEDS`. The experiment remains responsible for applying them
to its random number generators.

The default environment preserves information about the active or project-local environment. Use
`--environment uv` to reconstruct an environment from a frozen `uv.lock`. Containers, system
libraries, GPU drivers, and accessible hardware remain execution prerequisites. Sift does not promise
bitwise equality across different GPU stacks.

## Compare runs

List recent runs or compare selected runs:

```bash
sift experiment list
sift experiment compare RUN_A RUN_B
```

The table includes run relationships, seeds, metadata supplied with `--meta`, declared input
identities, and scalar or flat-list values from declared JSON artifacts. Result keys retain the
artifact path: `results/train/metrics.json` and `results/test/metrics.json` produce separate columns.
Input fingerprints distinguish different data saved under the same path. It reads the immutable
copies saved with each run. Other file types remain available as artifacts but are not expanded into
comparison columns. Declared artifact directories are saved recursively.

The printed short run IDs work in all commands that accept experiment references. Ambiguous prefixes
are rejected with a list of candidates. Narrow terminals use one summary per run instead of truncating
IDs or wrapping a wide table. JSON rows retain full IDs, artifact paths, and input SHA-256 values.

## Extend an experiment

```bash
sift experiment new next-study --from-run EXPERIMENT_OR_RUN
sift experiment run next-study
```

The new scratch directory contains the previous experiment's code. Sift carries forward the command,
declared inputs and outputs, seeds, metadata, and parent link. Command-line options override those
defaults. A follow-up uses the current core and input files; `reproduce` uses the saved originals.
Runs from older direct commands without a linked scratch directory need an explicitly copied script.

## Inspect results and failures

```bash
sift experiment show RUN_ID
sift experiment logs RUN_ID
sift experiment logs RUN_ID --follow
```

Normal runs print their ID before execution and stream stdout and stderr. Completion shows output
paths; failure shows the exception tail and log commands. JSON mode returns a single structured result
without streaming experiment output. `--json` can appear before or after an action.

## Save experiment code

After a useful run, save the exact experiment code from its source snapshot:

```bash
sift experiment save RUN_ID --name EXPERIMENT_NAME
```

This copies the code used for the run rather than the possibly edited live scratch directory. The
saved experiment records its source hash and reproduction command. Its linked run is protected
from retention cleanup.

Saving the same run again is idempotent. Saving a different run without `--name` appends the run's
suffix when the default name is occupied. An explicit occupied name requires a different `--name`.

Experiment scripts may contain one-off code. Save them when they are needed to reproduce a
result; move a function into core when it will be maintained and reused.

## Reproduce and compare

```bash
sift experiment reproduce EXPERIMENT_OR_RUN
```

Sift validates the saved code and inputs, starts a new execution without previous output files, and
saves the new environment information and output comparison. The original run remains unchanged.

For deterministic outputs, Sift compares declared output hashes. For stochastic outputs, provide a
program that implements justified numerical tolerances or statistical criteria:

```bash
sift experiment run NAME --command "python scratch/NAME/experiment.py" \
  --artifact results/metrics.json \
  --verify "python verify.py"
```

The verifier can read the original outputs through `SIFT_REFERENCE`. A successful command without
declared outputs or a comparison program is not enough to verify reproduction. Likewise, rerunning a
failed command does not reproduce a successful result.

Use `sift --json experiment compare RUN_A RUN_B` for structured comparison output. The lower-level
`sift inspect runs RUN_ID` command shows a full run record together with later reproduction
comparisons.

## Export a run

```bash
sift export RUN_ID DESTINATION
```

The export contains source, captured inputs, records, and outputs. It does not contain a newly
installed virtual environment; reconstruct that environment from the saved dependency files. Keep
exports or state-directory backups when moving projects between machines, because Git alone does not
contain Sift's ignored local state.

Sift's run states describe what was saved and checked. They do not establish whether an experimental
method works or whether a research conclusion is valid.
