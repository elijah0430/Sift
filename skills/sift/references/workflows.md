# Sift workflows

## Explore and record

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

## Preserve an experiment

Use `sift preserve SCRATCH_NAME --name EXPERIMENT_NAME --run RUN_ID` when an exact recorded recipe
should remain in the active repository. Preserved experiments may contain one-off code. Promotion is
reserved for capabilities the project will maintain as shared interfaces.

## Prepare a promotion

1. Run `sift promote prepare --title TITLE --rationale RATIONALE`.
2. Edit only the returned candidate directory.
3. Add independent correctness tests and a bounded comparison against the reference behavior when
   both are applicable.
4. Update callers to use the proposed public interface.
5. Run `sift promote seal PROPOSAL_ID`. Supply additional `--check COMMAND` arguments when the
   configured checks do not cover the relevant behavior.
6. Inspect with `sift promote show PROPOSAL_ID` and report the exact diff and digest.
7. Stop. A human reviewer runs `sift promote approve` and `sift promote apply`.

A promotion report should answer:

- What recurring capability is being maintained?
- Which details remain specific to an experiment?
- What public contract will callers rely on?
- What evidence checks correctness, and what evidence checks preservation?
- Which assumptions and unresolved risks remain?

## Replay

Run `sift replay RUN_ID`. It uses pristine source and captured inputs, records new evidence, and leaves
the original finalized record unchanged. An exact artifact hash match is meaningful for deterministic outputs.
For stochastic experiments, preserve a comparison program or metrics with scientifically justified
tolerances using `sift run --verify COMMAND`. The verifier receives original outputs through
`SIFT_REFERENCE`. Unresolved input identifiers are not enough to verify reproduction; capture actual
data with `--input NAME=PATH` and use `SIFT_INPUT_NAME` when external input paths must be portable.

Keep the research environment selected. Use `--environment uv` only when the project has an
appropriate frozen lock. Seeds supplied to Sift are metadata, not automatic changes to every random
generator in the experiment.

## Cache reuse and fresh trials

Derive a stable cache key from the relevant code, immutable input identities, configuration, and seeds:

```bash
sift cache key --code encoder-v3 --input dataset:sha256:... --config batch=32 --seed 7
```

Use `--fresh` when the procedure requires a new trial; it adds a nonce and therefore cannot reuse an
earlier output accidentally. Store and restore a deliberate cached file with `sift cache put` and
`sift cache get`. Sift rejects a key that is reused for different content.

## Retire and restore

Run `sift retire path scratch/NAME` only after preserving the research record or deciding that it does
not need preservation. Sift archives the target before removing it. Restore it with
`sift retire restore RETIREMENT_ID`.

Retirement is not evidence that an experiment failed, and preservation is not evidence that its code
belongs in core.

Pin records that must survive retention cleanup with `sift pin ID`. `sift gc plan` creates an immutable
candidate list and digest. Report that plan to the user. Only a human reviewer runs `sift gc apply`.

