<p align="center">
  <img src="assets/logo.svg" alt="Sift — explore freely, keep what matters" width="760">
</p>

<p align="center">
  <strong>Explore freely. Preserve experiments. Review shared code.</strong><br>
  A Python toolkit for organizing research code written with coding agents.
</p>

<p align="center">
  <a href="https://github.com/elijah0430/Sift/actions/workflows/ci.yml"><img src="https://github.com/elijah0430/Sift/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-7c3aed" alt="Python 3.11+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-06b6d4" alt="MIT"></a>
</p>

<p align="center">
  <a href="examples/minimal/README.md">Runnable example</a> ·
  <a href="docs/review.md">Review workflow</a> ·
  <a href="docs/agents.md">Agent setup</a> ·
  <a href="docs/related-tools.md">Related tools</a>
</p>

Coding agents make rapid research iteration easier, but repeated edits can mix preliminary analyses,
experiment-specific scripts, and reusable code into one difficult codebase. Sift gives each kind of
code a separate path:

- **Explore** uncertain ideas in scratch without modifying maintained code.
- **Run** experiments from saved source and input snapshots and keep their outputs and logs.
- **Preserve** the exact experiment code needed to reproduce an important result.
- **Review** reusable code before it enters the maintained project.

Sift works inside an existing Python repository. It does not replace the project's training
framework, configuration system, scheduler, or experiment tracker.

![Sift workflow: exploratory code, experiment runs, code review, reusable modules, and archived code.](assets/workflow.svg)

## Quick start

```bash
uv tool install git+https://github.com/elijah0430/Sift.git
# Or: pip install git+https://github.com/elijah0430/Sift.git

cd my-research-project
sift init
```

A typical iteration looks like this:

```bash
# The agent explores and runs an experiment.
sift explore sampler-study
sift run "python scratch/sampler-study/experiment.py" \
  --artifact results/metrics.json \
  --input dataset=data/train.json \
  --seed 7

# Keep the experiment code that produced an important run.
sift preserve sampler-study --name sampler-ablation --run RUN_ID

# Prepare a reusable function for review.
sift propose --title "Share the calibrated sampler" \
  --rationale "Two experiments now use the same implementation"
# Edit the proposal directory printed by Sift, then:
sift propose PROPOSAL_ID --ready

# The researcher reviews the core change and can reproduce the experiment.
sift review
sift reproduce sampler-ablation
```

Sift prints `RUN_ID` and `PROPOSAL_ID` when they are created. Run `sift status` at any time to see
active explorations, experiment runs, and proposals awaiting review.

## How Sift organizes code

| Area | Purpose |
|---|---|
| **Scratch** | Preliminary analyses, debugging, notebooks, and uncertain ideas |
| **Experiments** | Scripts and configurations kept to reproduce particular results |
| **Core** | Tested modules maintained and reused across experiments |

These directories are configured in `research.toml`, so an existing repository does not need to be
reorganized. Experiment code can remain experiment-specific indefinitely; preserving a result does
not require turning its script into a shared module.

## Human review for core changes

An agent prepares a core change in a separate review workspace and runs the configured checks. The
researcher opens it with `sift review`, using normal editor diffs or a terminal diff. The researcher
can request changes, rerun checks after editing, approve the displayed version, or leave it for later.

The agent workflow cannot approve or apply a proposal. Approval is tied to the exact code, diff,
check results, and project state displayed during review. Experiment runs retain their source,
declared inputs, environment information, logs, and declared outputs.

These guarantees concern code history and execution. Passing software tests or reproducing an output
does not establish that a scientific conclusion is valid.

## Documentation

- [Experiment runs and reproducibility](docs/reproducibility.md)
- [Reviewing core changes](docs/review.md)
- [Using Sift with coding agents](docs/agents.md)
- [Configuration and integrations](docs/configuration.md)
- [Artifacts, caching, archiving, and cleanup](docs/storage.md)
- [Related research tools](docs/related-tools.md)
- [Technical design](docs/design.md) and [test coverage](docs/acceptance.md)
- [Contributing](CONTRIBUTING.md)

Sift supports Python 3.11+ on Windows and Linux and is [MIT licensed](LICENSE).
