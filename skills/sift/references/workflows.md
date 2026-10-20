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

Use `sift preserve SCRATCH_NAME --name EXPERIMENT_NAME` when an exact analysis or training recipe
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

Run `sift replay RUN_ID`. An exact artifact hash match is meaningful only for deterministic outputs.
For stochastic experiments, preserve a comparison program or metrics with scientifically justified
tolerances and record that command as part of validation.

## Retire and restore

Run `sift retire path scratch/NAME` only after preserving the research record or deciding that it does
not need preservation. Sift archives the target before removing it. Restore it with
`sift retire restore RETIREMENT_ID`.

Retirement is not evidence that an experiment failed, and preservation is not evidence that its code
belongs in core.

