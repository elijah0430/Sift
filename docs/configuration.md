# Configuration and integrations

`sift init` creates `research.toml`. Map Sift's three code areas to the directories already used by
the project:

```toml
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
```

Configured directories must be distinct, non-overlapping, project-relative paths. A core entry may
also name an individual Python module in a flat repository. Snapshot ignores accept basename globs
and root-relative patterns. Capture important excluded data explicitly with `--input NAME=PATH`.

Sift rejects symlinks and junctions in snapshotted source rather than silently including an external
tree.

## Import boundaries

The built-in checker resolves local modules, relative imports, and literal dynamic imports. It checks
for core-to-scratch dependencies, circular dependencies in core, imports between modules marked as
independent, and optional restrictions to named public APIs.

Computed dynamic imports, native extensions, side effects, and references inside arbitrary strings
cannot be inferred exhaustively. Add project-specific installation, import, and behavior checks under
`[checks]`.

Sift can also run an existing Import Linter or Tach configuration:

```bash
sift check --engine import-linter
sift check --engine tach
```

The selected tool must be installed in the project environment. The built-in rules still run.

## Existing tools

| Tool | Sift integration |
|---|---|
| **uv** | Reconstruct an experiment environment from `uv.lock` with `--environment uv` |
| **VS Code or another editor** | Set `[review].command`, `VISUAL`, or `EDITOR` |
| **marimo** | `sift experiment new NAME --notebook` creates a reactive scratch notebook |
| **Local or mounted storage** | `sift artifact put/get --store PATH` |
| **Existing remote storage** | Adapt explicit upload and download commands with `CommandArtifactStore` |
| **Slurm or another scheduler** | `sift experiment run NAME --launcher "srun --partition=gpu"` |
| **Hydra, Snakemake, or Metaflow** | Run the existing command with `--command`; save resolved configuration, backend run IDs, and outputs as metadata or declared artifacts |
| **Python applications** | Use the operations and storage adapters in [`sift.api`](../src/sift/api.py) |

The scheduler launcher is synchronous and assumes that the source path and environment are visible
on the execution node. It does not upload a project or provision a cluster.

Use `sift --json COMMAND` when a program needs structured output. `sift core review` remains interactive
so that the code and approval decision stay visible to the researcher.
