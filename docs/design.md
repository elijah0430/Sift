# Design and configuration

Sift separates reusable modules, experiment scripts, and exploratory code. Saving a script for an
experiment does not require turning it into a shared module. Passing software tests does not
establish that a scientific claim is correct.

## Terminology

An **experiment run** is one execution of a script or command. Its **artifacts** are the output files,
such as metrics, model checkpoints, and figures. This follows the terminology used by
[MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking/). **Core** contains tested modules shared
across experiments; **experiments** contains scripts and configurations worth keeping; **scratch**
contains exploratory code. The separation of exploratory notebooks and reusable source code also
appears in [Cookiecutter Data Science](https://cookiecutter-data-science.drivendata.org/).

The commands `preserve`, `propose`, `reproduce`, and `archive` respectively save an experiment's
code, prepare reusable code for review, rerun an experiment, and archive unused code. The older
`promote`, `replay`, and `retire` commands remain as lower-level interfaces.

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

[review]
command = "code --wait"

[retention]
archive_days = 90
~~~

Configured directories must be distinct, non-overlapping project-relative paths.
Core entries may also name individual Python modules in a flat existing repository.
Snapshot ignores accept basename globs and root-relative patterns. Large data can be excluded from
source and captured explicitly with `--input NAME=PATH`. Sift rejects symlinks and junctions in
snapshotted source rather than silently capturing an uncontrolled external tree.

## Boundary checks

The standard-library AST checker resolves local modules, relative imports, and literal dynamic
imports. It follows local imports to detect indirect core-to-scratch dependencies, checks independent
modules and circular dependencies in core, and optionally restricts imports to named public APIs.

Computed dynamic imports, native extensions, side effects, and references embedded in arbitrary
strings cannot be inferred exhaustively. Use installation/import checks and research-specific tests
as additional configured commands. Consumers declared in unregistered external repositories are outside
this check's scope.

Install Import Linter or Tach in the selected project environment and set `engine = "import-linter"`
or `engine = "tach"` to run its native project configuration as well. Both are optional; the builtin
rules always run. The example includes working native configurations for both tools.

## Reviewing and applying core changes

1. Prepare baseline and candidate source copies, including relevant uncommitted source. When Git is
   available, initialize the candidate as a local repository with the baseline as its first commit.
2. Edit only the candidate.
3. Revoke prior approval before checking. Run mandatory import checks, configured checks, and extra checks.
4. Reject source changes made by the checks. Freeze candidate bytes separately and record hashes.
5. Bind the diff, changed-file list, reference snapshot, protected project state, candidate, rationale,
   and check report to one digest.
6. `sift review` shows the purpose, changed files, and validation status in a human-controlled
   terminal. It opens the candidate in the configured editor, where ordinary Source Control tools
   provide file navigation and side-by-side diffs. A terminal diff remains available.
7. Approval records the digest of the version displayed in that review session. Revalidate the saved
   review version and original project before application. Journal application and write files
   through atomic replacements. Resume interrupted application only if affected files still match
   their recorded before/after content.

The reviewer can save requested changes with the reviewed digest. This removes the proposal from the
human review queue until the agent changes the candidate and reruns its checks. The feedback remains
available to the agent through `sift propose PROPOSAL_ID --feedback`.

Editing the working copy invalidates the saved review and requires the checks to run again. The
reviewer does not need to copy a checksum manually; Sift carries the displayed digest into approval
and application, checking it under the project lock even when another session has approved a newer
version. Returning from an editor cannot replace the displayed version; a changed proposal requires
a fresh review. Sift also validates the code, diff, checks, and project state before applying it.
The lower-level `promote approve` command retains checksum confirmation; `promote apply` applies
the approved version separately.

Tests can simulate human input to exercise this protocol. Real agent skill/harness operations cannot
approve themselves. Same-user unrestricted shell access defeats an advisory approval file, so host
permissions remain part of the trust boundary.

## Experiment runs and reproducibility

A run has an immutable source snapshot and a separate execution directory. Metadata starts in
preparing/running state before execution. Completed or failed records include effective status,
outputs, errors, and runtime information. A missing artifact causes failure even if the command exits
successfully. Rerunning a failed command does not count as reproducing a successful result.

Declared file/directory inputs are copied and hashed before execution. Identifiers without captured
data remain unresolved. Experiments should use `SIFT_INPUT_NAME` for captured external inputs;
literal absolute paths inside application code are not rewritten automatically.

The default environment retains an activated or project-local environment. `--environment uv`
reconstructs a project lock; commands should select Python through that managed environment's PATH.
Containers and GPU drivers remain execution prerequisites. `--launcher` supplies an existing scheduler
prefix for a shared filesystem, not a scheduler or transfer service.

`sift reproduce` resolves either a preserved experiment name or a run ID, validates the saved code
and inputs, and starts a new execution without previous output
files, and saves the new environment information and output comparison. The original run metadata
stays unchanged. `sift inspect runs ID` combines it with the rerun comparisons.

The JSON field `evidence_state` retains its existing values for compatibility: `recorded` means the
run was logged, `restorable` means all declared input data was captured, and `replay-verified` means
a successful rerun met the configured output comparison. These describe what Sift saved and checked;
they do not establish the validity of a research conclusion.

A comparison program supplied through `--verify` should encode justified numerical tolerances,
conditions, and reference comparisons. It receives the original output files through `SIFT_REFERENCE`.
Without a comparison program, Sift checks output hashes. A successful command without specified
outputs or a comparison program is insufficient to verify reproduction.

## Preservation and portability

`preserve --run ID` copies the experiment's code from that run's snapshot, rather than a potentially edited live
scratch directory. Its record links the exact source hash and reproduction command. The linked run is
protected from retention GC.

`export ID DESTINATION` copies a portable run bundle containing source, inputs, records, and outputs.
The bundle does not include a newly installed uv virtual environment; reconstruct it from the lock.
Keep bundles or storage backups when moving projects between machines. Git alone does not contain
the ignored local state.

## Cleanup and recovery

Archiving checks static dependencies from maintained code and unresolved active runs, verifies copied bytes,
then removes the original directory. Restore rejects corrupted archives or occupied destinations.
Undeclared dynamic file dependencies remain the experiment's responsibility.

Cleanup plans list exact targets, hashes, and a digest. Application recomputes the digest, rechecks current
references and pins, verifies targets, and journals progress. Run records are retained by saved
experiments, parent/child links, rerun comparisons, active work, and explicit pins. Cache objects remain while
an entry or content pin retains them. GC never scans arbitrary external artifact stores for deletion.

`doctor` uses actual process liveness on the recorded host. `doctor --recover` reconciles interrupted
runs and stale transaction locks; it does not kill live jobs. Interrupted approved applications are
reported for human resumption. `doctor --reindex` rebuilds the SQLite listing from canonical portable
records. The database is an index, not the source of truth.

## Adapter contracts

`sift.api` exports the project operations, `ArtifactRef`, `ArtifactStore`, `LocalArtifactStore`, and
`CommandArtifactStore`. The command adapter takes argv templates with `{source}`, `{destination}`,
and `{sha256}`; it invokes no shell and validates downloaded content.

`LocalRunner` and `CommandRunner` delegate execution without inventing cluster state. Notebook
integration creates a marimo Python file with inline dependency metadata; the core project remains an
ordinary Python package.

