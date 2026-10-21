# Sift workflows

## Explore and run experiments

Start uncertain work with:

```bash
sift explore new-scoring-method --question "Does calibrated token scoring improve retrieval?"
```

Run important computations from a frozen source snapshot:

```bash
sift run "python scratch/new-scoring-method/experiment.py" \
  --artifact outputs/metrics.json \
  --change "Replace mean score with calibrated score"
```

Use `--parent RUN_ID` when the new run directly extends a previous run. Register outputs that support
the research conclusion; do not register caches merely because they exist.

## Keep an experiment's code

Use `sift preserve SCRATCH_NAME --name EXPERIMENT_NAME --run RUN_ID` to keep the version of an
experiment's code used for that run. Experiment scripts may contain one-off code. Move functions
into core when they will be maintained and reused across experiments.

## Prepare reusable code for review

1. Run `sift promote prepare --title TITLE --rationale RATIONALE`.
2. Edit only the returned candidate directory.
3. Add independent correctness tests and a bounded comparison against the reference behavior when
   both are applicable.
4. Update callers to use the proposed public interface.
5. Run `sift promote seal PROPOSAL_ID`. Supply additional `--check COMMAND` arguments when the
   configured checks do not cover the relevant behavior.
6. Inspect with `sift promote show PROPOSAL_ID` and report the exact diff and digest.
7. Stop. Tell the human reviewer to run `sift review`. It lists pending changes when no proposal ID
   is supplied and combines inspection, approval, and application in one terminal flow.

A code review should explain:

- Which function or module will be shared across experiments?
- Which details remain specific to an experiment?
- What API will the experiment scripts use?
- Which tests check expected behavior, and which comparisons check that refactoring preserves results?
- Which assumptions and unresolved risks remain?

## Rerun an experiment and compare results

Run `sift replay RUN_ID`. It uses the saved code and inputs, compares the new outputs with the
original results, and saves that comparison separately. Matching file hashes is meaningful for deterministic outputs.
For stochastic experiments, preserve a comparison program or metrics with scientifically justified
tolerances using `sift run --verify COMMAND`. The verifier receives original outputs through
`SIFT_REFERENCE`. Unresolved input identifiers are not enough to verify reproduction; capture actual
data with `--input NAME=PATH` and use `SIFT_INPUT_NAME` when external input paths must be portable.

Keep the research environment selected. Use `--environment uv` only when the project has an
appropriate frozen lock. Seeds supplied to Sift are metadata, not automatic changes to every random
generator in the experiment.

## Cache intermediate results

Derive a stable cache key from the relevant code, immutable input identities, configuration, and seeds:

```bash
sift cache key --code encoder-v3 --input dataset:sha256:... --config batch=32 --seed 7
```

Use `--fresh` when the procedure requires a new execution; it adds a unique identifier to prevent
accidental reuse. It does not change seeds or guarantee independent trials. Store and restore cached files with `sift cache put` and
`sift cache get`. Sift rejects a key that is reused for different content.

## Archive and restore unused code

Run `sift retire path scratch/NAME` after saving any experiment code and results that matter or
deciding they are not needed. Sift archives the target before removing it. Restore it with
`sift retire restore RETIREMENT_ID`.

Archiving code does not mean that the experiment failed. Keeping an experiment script does not mean
that it belongs in core.

Pin records that must survive retention cleanup with `sift pin ID`. `sift gc plan` creates an immutable
candidate list and digest. Report that plan to the user. Only a human reviewer runs `sift gc apply`.

