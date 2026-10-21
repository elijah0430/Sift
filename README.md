<p align="center">
  <img src="assets/logo.svg" alt="Sift — explore freely, keep what matters" width="760">
</p>

<p align="center">
  <strong>Explore in scratch. Keep reusable code in core.</strong><br>
  A Python toolkit for organizing research code and reproducing experiments with coding agents.
</p>

<p align="center">
  <a href="https://github.com/elijah0430/Sift/actions/workflows/ci.yml"><img src="https://github.com/elijah0430/Sift/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-7c3aed" alt="Python 3.11+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-06b6d4" alt="MIT"></a>
</p>

Research code grows through preliminary analyses, new methods, additional datasets and models, and
ablations. As agents add each iteration, shared code and experiment-specific code become entangled,
making the project harder to understand, reproduce, and extend.

Sift separates reusable code from exploratory work. Try ideas in scratch, keep experiment scripts
that you need to rerun, and move reusable functions into core after testing and code review. Save
the code, inputs, environment information, and outputs for each experiment run so earlier results
can be checked after the project changes. Archive unused code when you no longer need it.

![Sift workflow: exploratory code, experiment runs, code review, reusable modules, and archived code.](assets/workflow.svg)

### Organize research code

| Place | What belongs there | What it can depend on |
|---|---|---|
| **Core** | Tested, reusable modules: data loading, model components, training, evaluation | Other core modules, subject to the project's import rules |
| **Experiments** | Experiment scripts and configurations you want to keep and rerun | Core and the experiment's own modules |
| **Scratch** | Exploratory scripts, notebooks, debugging, and one-off analyses | Core and the exploration's own modules |

A script can be worth keeping because it reproduces a reported result, even if no other experiment
will reuse it. Core is for code shared across experiments. Moving code into core means committing to
maintaining it; it does not establish that the underlying method works.

### Install

~~~bash
uv tool install git+https://github.com/elijah0430/Sift.git
# Or: pip install git+https://github.com/elijah0430/Sift.git
~~~

Initialize an existing project without moving its source:

~~~bash
cd my-research-project
sift init
sift explore calibrated-scoring --question "Does calibration improve retrieval?"
~~~

Map existing directories in `research.toml`. You can keep your existing training framework and scripts.

### Try a complete, runnable example

The [example research project](examples/minimal) uses only the Python standard library.

~~~bash
git clone https://github.com/elijah0430/Sift.git
cd Sift/examples/minimal

sift check
sift run "python scratch/baseline/experiment.py" --artifact results/metrics.json --input dataset=data/original.json
sift run "python scratch/expanded/experiment.py" --artifact results/metrics.json --input dataset=data/shifted.json --seed 7
~~~

The second experiment adds a dataset, model, and metric while core stays unchanged. Use the baseline
run's printed ID to keep the version of the script that produced its results, then archive its scratch
directory:

~~~bash
sift preserve baseline --name baseline-study --run RUN_ID
sift retire path scratch/baseline
sift replay RUN_ID
~~~

`sift replay` reruns the experiment using its saved code and inputs, even after core changes.
It compares the new outputs with the original results and saves the comparison separately.

### Move reusable code into core through code review

~~~bash
sift promote prepare --title "Share the calibrated scorer" --rationale "Two experiments use this scoring function"
~~~

Edit the separate working copy created by this command. Extract the reusable function or module,
update the experiment scripts that call it, and test its expected behavior. Where relevant, compare
its outputs with the original implementation to check that refactoring preserves the results.

~~~bash
sift promote seal PROPOSAL_ID
sift promote show PROPOSAL_ID
~~~

`sift promote seal` runs the import dependency checks and your configured tests, then saves a fixed
version of the proposed changes for review. Additional `--check` commands supplement those checks.
The review includes the code diff, test results, and a checksum identifying that version.

A researcher reviews the changes in one terminal flow:

~~~bash
sift review
~~~

If several changes are waiting, Sift asks which one to review. It shows the explanation, changed
files, test results, and diff, then offers familiar actions:

~~~text
[d] diff  [t] test output  [e] editor  [a] approve and apply  [l] later
~~~

The approval uses your OS username, shown before the diff; use `sift review --reviewer NAME` to
change it. Choosing `a` approves and applies without another prompt. Press Enter to leave it pending.

The editor comes from `VISUAL` or `EDITOR`, or from `sift review --editor COMMAND`. Use a command that
waits until editing finishes, such as `sift review --editor "code --wait"`. If an edit changes the
proposed code, Sift requires checks and a fresh review before approval. The lower-level
`sift promote approve` and `sift promote apply` commands remain available for explicit workflows.

**Passing tests does not grant approval.** Approval applies only to the reviewed version. Changes to
the proposed code, diff, or test report require running `seal` again and obtaining new approval.
Changes to the original project's core, tests, configuration, or affected scripts also require a new
review. If applying an approved change is interrupted, Sift can resume after checking for conflicting edits.
If another session updates and approves the proposal, an open review still cannot apply that newer
version: reopen `sift review` to inspect it first.

### Track experiment runs and reproduce results

An **experiment run** is one execution of a script or command. Sift saves a snapshot of the source
code and runs a separate copy. It logs the command, related previous run, description of the change,
inputs and their hashes, random seeds, runtime information, dependency files, logs, and specified
output files (**artifacts**). It removes previous copies of those outputs before execution so stale
results cannot be mistaken for new ones.

~~~bash
sift run "python scratch/my-method/train.py" --artifact results/metrics.json --input dataset=data/train.json --seed 7 --meta model=small
~~~

Seeds are recorded and exposed as `SIFT_SEEDS`; your experiment remains responsible for setting its
random generators. Captured inputs are available through `SIFT_INPUT_NAME`. An unresolved identifier
is logged, but is not sufficient to verify that the results can be reproduced.

For stochastic outputs, supply `--verify "python verify.py"`. That program encodes your numerical
tolerances or statistical criteria and can read original outputs from `SIFT_REFERENCE` when rerunning
the experiment. Without this comparison program, Sift checks whether the specified output files have
identical hashes.

Use `--environment uv` to reconstruct a project from its frozen `uv.lock`. The default preserves the
selected project environment. Sift does not promise bitwise reproducibility across different GPU stacks.

### Cache intermediate results

~~~bash
sift cache key --code encoder-v3 --input dataset-sha256 --config batch=32 --seed 7 --environment torch-v2
sift cache key --code encoder-v3 --input dataset-sha256 --seed 7 --fresh
~~~

Use a cache key to reuse an expensive computation, such as preprocessing or feature extraction.
Include the code version, input data, configuration, random seed, and environment that affect its
output. `--fresh` adds a unique identifier for a new run; it does not change the random seed or
guarantee statistical independence. Sift stores files by content hash and rejects different outputs
under the same key. It cannot automatically identify every dependency of arbitrary Python code.

Remove an unused key with `sift cache drop KEY`. The cached file remains until cleanup confirms that
no runs, cache entries, or pins still reference it.

### Archive unused code and clean up old files

~~~bash
sift retire path scratch/old-idea
sift retire restore RETIREMENT_ID
sift pin RUN_ID
sift gc plan
~~~

`sift retire` checks whether maintained code or active runs depend on the directory, verifies an
archive copy, then removes the directory from the working project. `restore` checks the archive
before copying it back. Cleanup considers file age and references from saved experiments, related
runs, rerun comparisons, pending code changes, cache entries, and pinned items.

A researcher reviews the files listed by `sift gc plan`, then applies that plan with
`sift gc apply PLAN_ID`. New pins or references invalidate the plan. **Files permanently deleted by
`sift gc apply` cannot be restored by Sift.**

### Agent skill and harness

The skill is bundled in the installed package:

~~~bash
sift skill install
# Another agent's skill root:
sift skill install --target /path/to/agent/skills
~~~

The [skill](skills/sift/SKILL.md) guides the agent through exploratory coding, saving experiment
scripts, refactoring shared code, reporting tests and results, and archiving unused code. The agent
prepares core changes and hands them to the researcher through `sift review`. A human must approve
core changes and permanent cleanup.

The [harness](harness/README.md) checks which commands an agent may run and which files it may edit,
and can launch an agent in a separate working copy:

~~~bash
sift harness policy
sift harness guard -- sift promote prepare --title "Shared evaluation function"
sift harness launch -- your-coding-agent
~~~

The default launcher gives the agent a separate working copy and detects changes to the original core.
It is **not an OS sandbox**. On Linux, `--sandbox bubblewrap` supplies a read-only filesystem with a
writable working copy. Otherwise, connect the supplied policy to your host's filesystem/tool permissions.
Interactive input alone cannot authenticate a human against an unrestricted same-user agent.

### Integrations without a new research framework

| Integration | How it fits |
|---|---|
| **uv** | Frozen project environments and per-script dependency metadata |
| **Import Linter / Tach** | `sift check --engine import-linter` or `--engine tach` runs native contracts alongside Sift's rules |
| **marimo** | `sift explore NAME --notebook` creates an optional reactive scratch notebook |
| **Artifact storage** | `sift artifact put/get --store PATH` works with local or mounted storage |
| **Existing remote stores** | `CommandArtifactStore` adapts explicit upload/download argv and verifies downloaded content |
| **Schedulers** | `sift run ... --launcher "srun --partition=gpu"` delegates execution on a shared filesystem |
| **Python** | [`sift.api`](src/sift/api.py) provides the same operations and storage adapters for Python code |

The scheduler launcher is synchronous and expects the source path and environment to be accessible
on the execution node. It does not upload a project or provision a cluster. Plain Python callables
provide replaceable experimental components; adopting Hamilton or another graph framework is optional.

### Commands and documentation

| Task | Commands |
|---|---|
| Start and run | `init` · `explore` · `run` |
| Understand and validate | `inspect` · `check` · `doctor` |
| Preserve and reproduce | `preserve` · `replay` · `export` |
| Maintain core | `promote prepare` · `seal` · `show` · `review` |
| Store and retire | `artifact` · `cache` · `pin` · `retire` · `gc` |
| Connect an agent | `skill` · `harness` |

Use `sift --json COMMAND` for structured output. `sift review` is interactive and keeps the code
review visible in the terminal.
[Design and configuration](docs/design.md) · [Test coverage](docs/acceptance.md) ·
[Runnable example](examples/minimal/README.md) · [Agent workflow](skills/sift/references/workflows.md)

### Develop

~~~bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv build
~~~

Sift targets Python 3.11+ on Windows and Linux. Core runtime has no mandatory third-party dependencies.
Optional integrations are activated when used. [MIT licensed](LICENSE).

