# Related research tools

Sift combines ideas that established research tools usually address separately: project structure,
experiment history, reproducible execution, and movement from exploratory code into maintained code.
The tools below are useful references and potential integrations.

| Tool | Main idea relevant to Sift | Relationship to Sift |
|---|---|---|
| [Cookiecutter Data Science](https://github.com/drivendataorg/cookiecutter-data-science) | A familiar directory structure separates notebooks, reports, data, models, and importable source code. | Sift keeps the separation but maps it onto an existing repository and manages how code moves between roles. |
| [DVC](https://github.com/treeverse/dvc) | Experiments can be run, compared, queued, removed, or made persistent. Data and model outputs are versioned with the code that produced them. | DVC is the closest reference for experiment lifecycle and comparison. Sift adds saved experiment code and human-reviewed changes to core. |
| [MLflow](https://github.com/mlflow/mlflow) | A run records parameters, metrics, code versions, and artifacts and can be queried through an API or UI. | Sift uses the established terms *run* and *artifact* and focuses on local source and input snapshots. MLflow remains a natural external tracking backend. |
| [Sacred](https://github.com/IDSIA/sacred) | Experiments expose configuration, record run context through observers, and support controlled random seeds. | Sacred is a useful model for low-overhead configuration and metadata capture. Sift records seeds but leaves framework-specific random-number setup to the experiment. |
| [Kedro](https://github.com/kedro-org/kedro) | Reusable functions become nodes in modular pipelines with pipeline-specific configuration and tests. | Kedro shows how reusable research code can gain clear interfaces and tests. Sift does not require experiments to adopt a pipeline abstraction. |
| [Metaflow](https://github.com/Netflix/metaflow) | Researchers can move from notebook exploration to durable flows, inspect persisted artifacts, and resume failed work. | Metaflow is a strong reference for long-running work and recovery. Sift currently records whole commands rather than defining step-level workflows. |
| [Hydra](https://github.com/hydra-ecosystem/hydra) | Hierarchical configuration, command-line overrides, and multirun make experiment variants explicit. | Sift should preserve Hydra configurations and overrides rather than introduce a second configuration language. |
| [Snakemake](https://github.com/snakemake/snakemake) | Explicit dependency graphs support reproducible execution across local, cluster, and cloud environments and can produce portable reports. | Snakemake is a natural execution backend for multi-stage analyses. Sift can record its invocation and outputs without replacing its scheduler. |

The corresponding official documentation describes the specific ideas referenced here:
[Cookiecutter Data Science project structure](https://cookiecutter-data-science.drivendata.org/),
[DVC experiment management](https://dvc.org/doc/user-guide/experiment-management),
[MLflow Tracking](https://mlflow.org/docs/latest/tracking/),
[Sacred experiments](https://sacred.readthedocs.io/en/stable/),
[Kedro modular pipelines](https://github.com/kedro-org/kedro/blob/main/docs/build/modular_pipelines.md),
[Metaflow development workflow](https://docs.metaflow.org/metaflow/introduction),
[Hydra configuration and multirun](https://hydra.cc/docs/intro/), and
[Snakemake workflows](https://snakemake.readthedocs.io/en/stable/).

## Ideas worth carrying into Sift

1. **A compact experiment comparison view.** Following DVC's `exp show` and MLflow's run search,
   `sift experiment list` and `sift experiment compare` show configurations, inputs, parent runs,
   status, and scalar values from declared JSON results in one researcher-facing table.
2. **Explicit run relationships.** MLflow's grouped runs and Metaflow's run hierarchy make search and
   debugging easier. Sift already records parent runs; named tags and a clearer iteration history
   would make that information more useful.
3. **Configuration adapters.** Hydra, Sacred, and DVC already express parameter changes well. Sift
   should capture their resolved configurations and overrides through adapters instead of inventing
   another parameter system.
4. **Recovery at the appropriate unit.** Metaflow resumes workflow steps, while Sift currently reruns
   a complete command. Step-level recovery belongs in an execution backend; Sift should preserve the
   backend's run identifier and recovery command.
5. **Portable research reports.** Snakemake can package results with parameters, code, and software
   information. Sift's exported run bundle could gain a small human-readable report over the same
   saved evidence.
6. **Optional structure.** Cookiecutter Data Science and Kedro provide useful templates. Sift should
   offer experiment and core-module templates without requiring an existing project to be reorganized.

## Sift's distinct role

These tools provide strong solutions for their respective parts of the research workflow. Sift's
specific role is to connect four decisions that otherwise remain informal:

1. Explore uncertain ideas in scratch.
2. Compare runs and save the exact experiment code and evidence that matter.
3. Cite the motivating experiment when proposing code that should be maintained and reused.
4. Require a researcher to review that exact change before it enters core.

Sift should remain a small lifecycle layer around existing research tools. Reimplementing a tracking
server, configuration framework, workflow scheduler, or data-versioning system would make it harder
to adopt and would duplicate mature projects.
