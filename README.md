<p align="center">
  <img src="assets/logo.svg" alt="Sift" width="720">
</p>

<p align="center">
  <strong>Explore freely. Keep what matters.</strong><br>
  A lifecycle toolkit for research code written by humans and agents.
</p>

<p align="center">
  <a href="https://github.com/elijah0430/Sift/actions/workflows/ci.yml"><img src="https://github.com/elijah0430/Sift/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-06b6d4" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-7c3aed" alt="Python 3.11+">
</p>

Research code changes differently from product code. A promising result becomes a new method, then a
new dataset, another model, an ablation, and three analysis scripts. The iterations are useful; the
resulting codebase often is not.

Sift gives those iterations a lifecycle:

```text
scratch  ── preserve ──▶  reproducible experiment
   │
   └──── prepare ─────▶  sealed proposal ── human review ──▶ core
```

Agents can explore, run, preserve, and prepare changes. A core promotion is applied only after a human
reviews the exact sealed patch.

## Why Sift

- **Scratch stays cheap.** Try uncertain ideas without forcing an early abstraction.
- **Results outlive working files.** Runs capture source, command, runtime, logs, and registered outputs.
- **Experiments and libraries stay distinct.** A valuable paper result can remain a specific recipe.
- **Promotion is reviewable.** The candidate patch, checks, and digest are frozen together.
- **Cleanup is recoverable.** Retirement archives before it removes active files.
- **The workflow is agent-independent.** The CLI is the shared protocol; skills are thin adapters.

## Install

```bash
uv tool install git+https://github.com/elijah0430/Sift.git
# or
pip install git+https://github.com/elijah0430/Sift.git
```

Initialize Sift inside an existing Python research repository:

```bash
cd my-research-project
sift init
```

This creates `research.toml`, `scratch/`, `experiments/`, and local `.research/` state. Existing source
layout remains intact and can be mapped in `research.toml`.

## A complete research iteration

```bash
# 1. Create a place for an uncertain idea
sift explore calibrated-scoring \
  --question "Does calibrated token scoring improve retrieval?"

# 2. Run it from a frozen source snapshot
sift run "python scratch/calibrated-scoring/experiment.py" \
  --artifact outputs/metrics.json \
  --change "Introduce calibrated token scoring"

# 3a. Preserve a result-specific recipe
sift preserve calibrated-scoring --name retrieval-calibration-ablation

# 3b. Or prepare a maintained capability
sift promote prepare \
  --title "Add calibrated token scorer" \
  --rationale "Used by two retrieval experiments"
```

`promote prepare` prints an isolated candidate directory. An agent edits that directory, adds tests,
then seals the proposal:

```bash
sift promote seal promotion-... \
  --check "python -m pytest" \
  --check "python -m sift check"
sift promote show promotion-...
```

A human reviews the diff and digest in an interactive terminal:

```bash
sift promote approve promotion-...
sift promote apply promotion-...
```

Approval is invalidated by resealing. Application stops if an affected project file changed after the
candidate was prepared.

## Repository model

```text
src/project/        maintained, supported capabilities
experiments/        preserved procedures for particular results
scratch/            active exploration
tests/              core checks and compatibility evidence
research.toml       paths, checks, and retention policy
.research/          local run records, proposals, and archives
```

Core never imports scratch or experiments. Scratch and experiments may call core through explicit
interfaces. `sift check` enforces the first rule without requiring the project to adopt a pipeline
framework.

## Commands

| Command | Purpose |
|---|---|
| `sift explore` | Start an isolated exploration |
| `sift run` | Execute from a frozen source snapshot and record evidence |
| `sift inspect` | Inspect runs, proposals, and archives |
| `sift preserve` | Keep a scratch procedure as an experiment |
| `sift promote prepare` | Create an isolated candidate workspace |
| `sift promote seal` | Freeze its patch, checks, and digest |
| `sift promote approve` | Record interactive human approval |
| `sift promote apply` | Apply only that approved patch |
| `sift replay` | Re-execute a recorded run and compare artifacts |
| `sift retire` | Archive and remove obsolete active code |
| `sift check` | Enforce core dependency boundaries |
| `sift harness policy` | Emit the host integration contract |

## Agent skill and harness

The installable skill lives in [`skills/sift`](skills/sift). Copy or link it into the skill directory of
your coding agent. It teaches the agent when to explore, preserve, promote, replay, and retire, while
reserving approval and application for a human.

For Codex, the packaged installer places it in `$CODEX_HOME/skills/sift` (or `~/.codex/skills/sift`):

```bash
sift skill install
```

[`harness/policy.json`](harness/policy.json) declares write scopes and human-only commands for agent
hosts. Sift checks patch integrity itself; the host enforces filesystem permissions. See
[`docs/design.md`](docs/design.md) for the complete trust boundary.

## Status

Sift is an early working release. It is designed for Python-first research repositories and uses
portable JSON records and source snapshots. Remote artifact stores, scheduler adapters, and
tolerance-based replay checks are natural extensions of the same lifecycle model.

## License

[MIT](LICENSE)

