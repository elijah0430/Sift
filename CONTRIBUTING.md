# Contributing to Sift

Sift supports Python 3.11+ on Windows and Linux. The core runtime has no mandatory third-party
dependencies; optional integrations are activated only when used.

## Development setup

Install [uv](https://docs.astral.sh/uv/), clone the repository, and create the development
environment:

```bash
uv sync --extra dev
```

Run the checks used by continuous integration:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Build the source distribution and wheel with:

```bash
uv build
```

Changes to the review and application path should retain the central safety property: the version
applied to core must be the exact version the researcher reviewed and approved. Changes to experiment
runs should keep source, inputs, outputs, and later reproduction attempts auditable without rewriting
the original record.

Please include focused tests for behavior changes and update the relevant user documentation when a
command or guarantee changes.
