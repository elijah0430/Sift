<p align="center">
  <img src="assets/logo.svg" alt="Sift — explore freely, keep what matters" width="760">
</p>

<p align="center">
  <strong>Explore freely. Preserve experiments. Review shared code.</strong><br>
  A Python toolkit for organizing research code and reproducing experiments with coding agents.
</p>

<p align="center">
  <a href="https://github.com/elijah0430/Sift/actions/workflows/ci.yml"><img src="https://github.com/elijah0430/Sift/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-7c3aed" alt="Python 3.11+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-06b6d4" alt="MIT"></a>
</p>

Research code grows through preliminary analyses, new methods, additional datasets and models, and
ablations. When every iteration modifies the same code, the project becomes difficult to understand,
reproduce, and extend.

Sift gives exploratory and maintained code different workflows. An agent can try ideas freely, save
the exact code and inputs used for an experiment, and prepare reusable code as a proposal. The
project's maintained code changes only after human review.

![Sift workflow: exploratory code, experiment runs, code review, reusable modules, and archived code.](assets/workflow.svg)

## Three places for research code

| Place | What belongs there |
|---|---|
| **Scratch** | Preliminary analyses, debugging, notebooks, and uncertain ideas |
| **Experiments** | Scripts and configurations needed to reproduce a result |
| **Core** | Tested modules maintained and reused across experiments |

Experiment code does not need to become core. A script can be worth preserving because it produced
a reported result even when no other experiment will reuse it.

## Install

```bash
uv tool install git+https://github.com/elijah0430/Sift.git
# Or: pip install git+https://github.com/elijah0430/Sift.git
```

Initialize Sift inside an existing research project:

```bash
cd my-research-project
sift init
sift status
```

Sift creates `research.toml` and its local state directory. It does not move existing source files or
replace your training framework. Map the project's current directories in `research.toml`.

## One research iteration

The agent starts an exploration and runs it from a saved source snapshot:

```bash
sift explore sampler-study
# Edit scratch/sampler-study/experiment.py
sift run "python scratch/sampler-study/experiment.py" \
  --artifact results/metrics.json \
  --input dataset=data/train.json \
  --seed 7
```

If the experiment matters, the agent preserves the code that produced the run:

```bash
sift preserve sampler-study --name sampler-ablation --run RUN_ID
```

The experiment can now be reproduced by name, even after scratch or core changes:

```bash
sift reproduce sampler-ablation
```

If a function should be shared across experiments, the agent prepares a core change:

```bash
sift propose --title "Share the calibrated sampler" \
  --rationale "The same implementation is now used by two experiments"
# Edit only the proposal directory printed by Sift.
sift propose PROPOSAL_ID --ready
```

The researcher reviews the proposal and decides whether it enters core:

```bash
sift review
```

Sift can open the proposal in the researcher's editor with normal file navigation and side-by-side
diffs. The same review also works entirely in the terminal. The reviewer can request changes, rerun
checks after editing, approve the displayed version, or leave it for later.

## Researcher and agent interfaces

The researcher normally needs three commands:

```bash
sift status                       # Show current work and proposals needing attention
sift review                       # Review a proposed core change
sift reproduce EXPERIMENT_OR_RUN  # Rerun saved code and compare its outputs
```

The agent uses `explore`, `run`, `preserve`, `propose`, and `archive` while conducting the research.
It prepares proposals but never approves or applies them.

## What Sift guarantees

- A core change cannot be applied through the agent workflow without human review.
- Approval is tied to the exact code, diff, checks, and project state shown to the reviewer.
- Experiment runs retain source, declared inputs, environment information, logs, and declared outputs.
- Preserved experiments remain separate from reusable core modules.

These guarantees concern code history and execution. Passing tests or reproducing an output does not
establish that a scientific conclusion is valid.

## Documentation

- [Experiment runs and reproducibility](docs/reproducibility.md)
- [Reviewing core changes](docs/review.md)
- [Artifacts, caching, archiving, and cleanup](docs/storage.md)
- [Using Sift with coding agents](docs/agents.md)
- [Configuration and integrations](docs/configuration.md)
- [Related research tools](docs/related-tools.md)
- [Technical design](docs/design.md)
- [Runnable example](examples/minimal/README.md)
- [Contributing](CONTRIBUTING.md)

Sift supports Python 3.11+ on Windows and Linux. Its core runtime has no mandatory third-party
dependencies. Sift is [MIT licensed](LICENSE).
