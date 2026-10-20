<p align="center">
  <img src="assets/logo.svg" alt="Sift — explore freely, keep what matters" width="760">
</p>

<p align="center">
  <strong>Research moves fast. Your core should stay understandable.</strong><br>
  A Python toolkit, CLI, and agent workflow for the full life of research code.
</p>

<p align="center">
  <a href="https://github.com/elijah0430/Sift/actions/workflows/ci.yml"><img src="https://github.com/elijah0430/Sift/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-7c3aed" alt="Python 3.11+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-06b6d4" alt="MIT"></a>
</p>

A motivation becomes a preliminary analysis, then a method, another dataset, another model, and an
ablation. Agents can write each iteration well while the accumulated code becomes difficult to
understand, reproduce, and change.

Sift gives those iterations a lifecycle. Explore in scratch. Preserve a specific procedure when it
matters. Extract a maintained capability when its interface is justified. Review the exact change
before it reaches core. Retire obsolete working files without losing their research record.

![The Sift lifecycle: explore, record, preserve, review, promote, and retire.](assets/workflow.svg)

### Three places for code. A separate record for evidence.

| Place | What belongs there | What it can depend on |
|---|---|---|
| **Core** | Supported, tested capabilities with explicit interfaces | Other permitted core capabilities |
| **Experiments** | Maintained recipes for particular scientific procedures | Core and their own local modules |
| **Scratch** | New methods, small analyses, debugging, uncertain implementations | Core and their own local modules |

A useful one-off analysis can remain an experiment. A reusable component can implement a scientific
hypothesis that still needs evaluation. Sift keeps maintenance status separate from scientific validity.

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

Map existing directories in `research.toml`. There is no required training framework or pipeline DAG.

### Try a complete, runnable example

The [example research project](examples/minimal) uses only the Python standard library.

~~~bash
git clone https://github.com/elijah0430/Sift.git
cd Sift/examples/minimal

sift check
sift run "python scratch/baseline/experiment.py" --artifact results/metrics.json --input dataset=data/original.json
sift run "python scratch/expanded/experiment.py" --artifact results/metrics.json --input dataset=data/shifted.json --seed 7
~~~

The second recipe adds a dataset, model, and metric while core stays unchanged. Attach the baseline
run's printed ID to its maintained recipe, then retire its scratch files:

~~~bash
sift preserve baseline --name baseline-study --run RUN_ID
sift retire path scratch/baseline
sift replay RUN_ID
~~~

Replay uses the original source and captured inputs, even after the current core changes.
The finalized run record stays unchanged; replay produces a separate evidence record.

### Promotion is a reviewed patch

~~~bash
sift promote prepare --title "Share the calibrated scorer" --rationale "Two studies need this capability"
~~~

Edit the returned **candidate workspace**. Extract the smallest useful interface, update callers, and
add independent correctness checks plus a bounded comparison with the reference behavior.

~~~bash
sift promote seal PROPOSAL_ID
sift promote show PROPOSAL_ID
~~~

Sealing runs mandatory boundary checks and the configured checks. Extra `--check` commands supplement
them. The proposal includes a readable diff, a review report, file hashes, check results, and a digest.

A human reviews that candidate and runs these commands in a human-controlled terminal:

~~~bash
sift promote approve PROPOSAL_ID
sift promote apply PROPOSAL_ID
~~~

**Passing tests does not grant approval.** Editing the candidate, diff, or check report invalidates
the seal. Resealing revokes earlier approval. Changes to core, tests, configuration, or affected
callers require a new review. Interrupted application is journaled and can resume without silently
overwriting conflicting edits.

### Record executions, not just metrics

Each run captures a pristine source tree and executes in a separate working copy. It records the
command, parent run, declared change, captured inputs and hashes, seeds, runtime information,
environment files, logs, and registered outputs. Missing outputs cannot be replaced by stale files.

~~~bash
sift run "python scratch/my-method/train.py" --artifact results/metrics.json --input dataset=data/train.json --seed 7 --meta model=small
~~~

Seeds are recorded and exposed as `SIFT_SEEDS`; your experiment remains responsible for setting its
random generators. Captured inputs are available through `SIFT_INPUT_NAME`. An unresolved identifier
is recorded explicitly and cannot produce a replay-verified claim.

For stochastic outputs, supply `--verify "python verify.py"`. That program encodes your numerical
tolerances or statistical criteria and can read original outputs from `SIFT_REFERENCE` on replay.
Without a verifier, replay requires matching registered artifact hashes.

Use `--environment uv` to reconstruct a project from its frozen `uv.lock`. The default preserves the
selected project environment. Sift does not promise bitwise reproducibility across different GPU stacks.

### Reuse deliberate computations. Execute fresh trials.

~~~bash
sift cache key --code encoder-v3 --input dataset-sha256 --config batch=32 --seed 7 --environment torch-v2
sift cache key --code encoder-v3 --input dataset-sha256 --seed 7 --fresh
~~~

Stable keys support reuse; `--fresh` adds a trial nonce. Cache objects are content-addressed.
Reusing one key for different content fails. Code, input, parameter, seed, and environment identities
are explicit: Sift does not infer every dependency of arbitrary Python code.

Drop an obsolete cache reference with `sift cache drop KEY`. Its object remains until a reviewed
cleanup plan establishes that nothing retains it.

### Cleanup with a way back

~~~bash
sift retire path scratch/old-idea
sift retire restore RETIREMENT_ID
sift pin RUN_ID
sift gc plan
~~~

Retirement checks maintained dependencies and active run records, verifies an archive, then removes
the active directory. Restore verifies archive integrity. GC considers retention age and references
from preserved recipes, run ancestry, replays, pending proposals, cache entries, and pins.

A human applies the exact cleanup plan with `sift gc apply PLAN_ID`. Newly added pins or references
invalidate a plan. **Permanent GC deletion cannot be undone by Sift.**

### Agent skill and harness

The skill is bundled in the installed package:

~~~bash
sift skill install
# Another agent's skill root:
sift skill install --target /path/to/agent/skills
~~~

The [skill](skills/sift/SKILL.md) teaches exploration, preservation, interface design, evidence
reporting, and retirement. It reserves promotion approval/application and permanent GC for a human.

The [harness](harness/README.md) provides command gates, write-path checks, and an agent launcher:

~~~bash
sift harness policy
sift harness guard -- sift promote prepare --title "New capability"
sift harness launch -- your-coding-agent
~~~

The default launcher gives the agent an isolated candidate and detects changes to the original core.
It is **not an OS sandbox**. On Linux, `--sandbox bubblewrap` supplies a read-only filesystem with a
writable candidate. Otherwise, connect the supplied policy to your host's filesystem/tool permissions.
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
| **Python** | [`sift.api`](src/sift/api.py) exposes the lifecycle operations and artifact adapter contracts |

The scheduler launcher is synchronous and expects the source path and environment to be accessible
on the execution node. It does not upload a project or provision a cluster. Plain Python callables
provide replaceable experimental components; adopting Hamilton or another graph framework is optional.

### Commands and documentation

| Lifecycle | Commands |
|---|---|
| Start and run | `init` · `explore` · `run` |
| Understand and validate | `inspect` · `check` · `doctor` |
| Preserve and reproduce | `preserve` · `replay` · `export` |
| Maintain core | `promote prepare` · `seal` · `show` · `approve` · `apply` |
| Store and retire | `artifact` · `cache` · `pin` · `retire` · `gc` |
| Connect an agent | `skill` · `harness` |

Use `sift --json COMMAND` for structured output. Human approval keeps its review visible in the terminal.
[Design and configuration](docs/design.md) · [Acceptance coverage](docs/acceptance.md) ·
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

