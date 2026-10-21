# Artifacts, caching, archiving, and cleanup

## Store run artifacts

Pass `--artifact PATH` to `sift experiment run NAME` for each output needed to inspect or reproduce
the result, such as metrics, figures, or model checkpoints. Sift stores artifact content by hash.

Use `sift artifact put/get --store PATH` with a local or mounted store. Python integrations can use
`LocalArtifactStore` or adapt an existing upload and download command with `CommandArtifactStore`.
Downloaded content is checked against its expected hash.

## Cache intermediate results

Use a cache key for an expensive reusable computation such as preprocessing or feature extraction:

```bash
sift cache key \
  --code encoder-v3 \
  --input dataset-sha256 \
  --config batch=32 \
  --seed 7 \
  --environment torch-v2
```

Include every code version, input, configuration value, random seed, and environment property that
can affect the output. `--fresh` adds a unique identifier for a new execution; it does not change the
random seed or guarantee independent trials.

Store and restore cached files with `sift cache put` and `sift cache get`. Sift rejects a key reused
for different content. Remove an unused key with `sift cache drop KEY`; the content remains until no
run, cache entry, or pin references it and cleanup removes it.

Sift cannot infer every dependency of arbitrary Python code. Cache correctness depends on the inputs
included in the key.

## Archive unused code

```bash
sift archive scratch/old-idea
sift archive --restore ARCHIVE_ID
```

Before removing the original directory, Sift checks references from maintained code and active runs,
copies the directory, and verifies the archive. Restore verifies the archived content and refuses to
overwrite an occupied destination. Undeclared dynamic file dependencies remain the experiment's
responsibility.

Archiving scratch work does not mean that the experiment failed. Save any code and results
needed for later analysis before archiving the scratch directory.

## Clean up retained files

```bash
sift pin RUN_ID
sift gc plan
sift gc apply PLAN_ID
```

Pins retain important records. A cleanup plan lists exact targets and their hashes. Applying the plan
rechecks the digest, current references, pins, and target contents. New references invalidate the
plan. Only a human should apply permanent cleanup because files deleted by `sift gc apply` cannot be
restored by Sift.

Runs remain referenced by saved experiments, related runs, reproduction comparisons, active
work, and pins. Cache objects remain while an entry or content pin retains them. Cleanup does not
scan arbitrary external artifact stores for deletion.

Use `sift doctor` to inspect interrupted work. `sift doctor --recover` reconciles interrupted runs and
stale transaction locks without killing live jobs. `sift doctor --reindex` rebuilds the local SQLite
index from the canonical portable records.
