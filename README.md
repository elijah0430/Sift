<p align="center">
  <img src="assets/logo.svg" alt="Sift — explore freely, keep what matters" width="760">
</p>

<p align="center">
  <strong>Explore freely. Compare experiments. Review shared code.</strong><br>
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

Coding agents make research iteration faster, but repeated edits can mix preliminary analyses,
experiment scripts, and reusable code. Sift separates three things:

- **Scratch** is where the researcher and agent try uncertain ideas.
- **Experiments** are runs that can be saved, compared, and reproduced.
- **Core changes** are reusable code proposed for human review.

Sift works inside an existing Python repository. It does not replace the project's training
framework, configuration system, scheduler, or experiment tracker.

![Sift workflow: scratch work, experiment comparison, saved experiments, and reviewed core changes.](assets/workflow.svg)

## Quick start

```bash
uv tool install git+https://github.com/elijah0430/Sift.git
# Or: pip install git+https://github.com/elijah0430/Sift.git

cd my-research-project
sift init
```

A typical iteration looks like this:

```bash
# Work freely in scratch, then run a saved snapshot.
sift experiment new sampler-study
sift experiment run sampler-study \
  --artifact results/metrics.json \
  --input dataset=data/train.json \
  --seed 7 \
  --meta method=baseline

# Compare runs and keep the experiment code that matters.
sift experiment compare RUN_A RUN_B
sift experiment save RUN_B --name sampler-ablation

# Propose reusable code, citing the experiment that motivated it.
sift core propose --title "Share the calibrated sampler" \
  --rationale "Two experiments now use the same implementation" \
  --from-run RUN_B
# Edit the proposal directory printed by Sift, then:
sift core propose PROPOSAL_ID --ready

# The researcher reviews the exact change before it enters core.
sift core review
sift experiment reproduce sampler-ablation
```

`sift experiment list` shows recent runs with their configuration, inputs, status, and scalar values
from declared JSON results. `sift experiment compare` shows the same fields for selected runs. Run
`sift status` to see scratch work, saved experiments, and core changes awaiting review.

Use the short run IDs printed by `list` and `compare` in subsequent commands. To extend a saved
experiment, run `sift experiment new next-study --from-run sampler-ablation`; Sift copies its code
and carries forward the command, declared inputs and outputs, seeds, metadata, and parent run.
Running the new experiment uses the current project core and current input files.
Use `reproduce` when you need the original code and inputs.

Successful runs save their command, inputs, outputs, and metadata as defaults for the next run of
that scratch experiment. Sift prints the effective settings before execution. Override an option or
use `--reset-options` to replace them. Select a focused comparison with
`sift experiment compare RUN_A RUN_B --columns method,seed,accuracy`.

Runs show live output and the saved result paths. Use `sift experiment show RUN_ID` for a summary,
`sift experiment logs RUN_ID --follow` to follow another running terminal, and
`sift experiment archive old-study` to set unused work aside. Use `sift core list` and
`sift experiment archive --list` to find pending changes and archived code.

## How Sift organizes code

| Area | Purpose |
|---|---|
| **Scratch** | Preliminary analyses, debugging, notebooks, and uncertain ideas |
| **Experiments** | Saved code and runs used to compare or reproduce particular results |
| **Core** | Tested modules maintained and reused across experiments |

These directories are configured in `research.toml`, so an existing repository does not need to be
reorganized. Experiment code can remain experiment-specific indefinitely. It enters core only when
the researcher decides it should be maintained and reused.

## Human review for core changes

An agent prepares a core change in a separate review workspace and runs the configured checks. The
researcher opens it with `sift core review`, using normal editor diffs or a terminal diff. The researcher
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
