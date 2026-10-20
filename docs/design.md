# Design and configuration

Sift maintains code and evidence separately. A preserved recipe is not a core abstraction, and passing
software tests does not establish a scientific claim.

## Configuration

~~~toml
[paths]
core = ["src"]
experiments = "experiments"
scratch = "scratch"
tests = "tests"
state = ".research"

[checks]
commands = ["python -m pytest"]

[boundaries]
engine = "builtin"
public_api = ["myproject.evaluate", "myproject.data.load"]
independent = ["myproject.data", "myproject.scoring"]
acyclic = true

[snapshot]
ignore = ["datasets", "outputs"]

[retention]
archive_days = 90
~~~

Configured lifecycle directories must be distinct, non-overlapping project-relative paths.
Core entries may also name individual Python modules in a flat existing repository.
Snapshot ignores accept basename globs and root-relative patterns. Large data can be excluded from
source and captured explicitly with `--input NAME=PATH`. Sift rejects symlinks and junctions in
snapshotted source rather than silently capturing an uncontrolled external tree.

## Boundary checks

The standard-library AST checker resolves local modules, relative imports, and literal dynamic
imports. It follows local imports to detect indirect core-to-scratch dependencies, checks independent
capabilities and core cycles, and optionally restricts consumers to named public interfaces.

Computed dynamic imports, native extensions, side effects, and references embedded in arbitrary
strings cannot be inferred exhaustively. Use installation/import checks and research-specific tests
as additional configured commands. Consumers declared in unregistered external repositories are outside
this check's scope.

Install Import Linter or Tach in the selected project environment and set `engine = "import-linter"`
or `engine = "tach"` to run its native project configuration as well. Both are optional; the builtin
rules always run. The example includes working native configurations for both tools.

## Promotion protocol

1. Prepare baseline and candidate source copies, including relevant uncommitted source.
2. Edit only the candidate.
3. Revoke prior approval before checking. Run mandatory boundaries, configured checks, and extra checks.
4. Reject source changes made by the checks. Freeze candidate bytes separately and record hashes.
5. Bind the diff, changed-file list, reference snapshot, protected project state, candidate, rationale,
   and check report to one digest.
6. A human reviews and approves that exact digest through a human-controlled terminal.
7. Revalidate the seal and original project before application. Journal application and write files
   through atomic replacements. Resume interrupted application only if affected files still match
   their recorded before/after content.

Tests can simulate human input to exercise this protocol. Real agent skill/harness operations cannot
approve themselves. Same-user unrestricted shell access defeats an advisory approval file, so host
permissions remain part of the trust boundary.

## Run records

A run has an immutable source snapshot and a separate execution directory. Metadata starts in
preparing/running state before execution. Completed or failed records include effective status,
outputs, errors, and runtime information. A missing artifact causes failure even if the command exits
successfully. Failed runs cannot become replay-verified by reproducing their failure.

Declared file/directory inputs are copied and hashed before execution. Identifiers without captured
data remain unresolved. Experiments should use `SIFT_INPUT_NAME` for captured external inputs;
literal absolute paths inside application code are not rewritten automatically.

The default environment retains an activated or project-local environment. `--environment uv`
reconstructs a project lock; commands should select Python through that managed environment's PATH.
Containers and GPU drivers remain execution prerequisites. `--launcher` supplies an existing scheduler
prefix for a shared filesystem, not a scheduler or transfer service.

Replay validates source/input integrity, starts from pristine source without registered old outputs,
and records its own environment and evidence. The original finalized manifest is never rewritten.
`sift inspect runs ID` derives the evidence state from the original run and its replay records.

A verifier is an acceptance program, not a guarantee supplied by Sift. It should encode scientifically
justified tolerances, conditions, and reference comparisons. Original artifacts are exposed through
`SIFT_REFERENCE`. A successful command without artifacts or a verifier is insufficient for a verified
replay.

## Preservation and portability

`preserve --run ID` copies the recipe from that run's snapshot, rather than a potentially edited live
scratch directory. Its record links the exact source hash and reproduction command. The linked run is
protected from retention GC.

`export ID DESTINATION` copies a portable run bundle containing source, inputs, records, and outputs.
The bundle does not include a newly installed uv virtual environment; reconstruct it from the lock.
Keep bundles or storage backups when moving projects between machines. Git alone does not contain
the ignored local state.

## Cleanup and recovery

Retirement checks static maintained dependencies and unresolved active runs, verifies copied bytes,
then removes the original directory. Restore rejects corrupted archives or occupied destinations.
Undeclared dynamic file dependencies remain the experiment's responsibility.

GC plans list exact targets, hashes, and a digest. Application recomputes the digest, rechecks current
references and pins, verifies targets, and journals progress. Run records are retained by preserved
recipes, parent/child links, replay records, active work, and explicit pins. Cache objects remain while
an entry or content pin retains them. GC never scans arbitrary external artifact stores for deletion.

`doctor` uses actual process liveness on the recorded host. `doctor --recover` reconciles interrupted
runs and stale transaction locks; it does not kill live jobs. Interrupted approved applications are
reported for human resumption. `doctor --reindex` rebuilds the SQLite listing from canonical portable
records. The database is an index, not the source of truth.

## Adapter contracts

`sift.api` exports lifecycle operations, `ArtifactRef`, `ArtifactStore`, `LocalArtifactStore`, and
`CommandArtifactStore`. The command adapter takes argv templates with `{source}`, `{destination}`,
and `{sha256}`; it invokes no shell and validates downloaded content.

`LocalRunner` and `CommandRunner` delegate execution without inventing cluster state. Notebook
integration creates a marimo Python file with inline dependency metadata; the core project remains an
ordinary Python package.

