# A complete research iteration

This example uses only Python's standard library. Start from this directory with Sift installed.

~~~bash
sift check
sift run "python scratch/baseline/experiment.py" --artifact results/metrics.json --input dataset=data/original.json
sift run "python scratch/expanded/experiment.py" --artifact results/metrics.json --input dataset=data/shifted.json --seed 7 --meta model=scaled
~~~

The baseline mean absolute error is 1.5. The expanded recipe introduces another dataset, a scaled
model, and a clipped metric. Its score is 0.0. These are illustrative arithmetic results, not evidence
about a real ML method. Core does not branch on either experiment's name.

Use the first printed run ID to attach the exact baseline execution to a maintained recipe:

~~~bash
sift preserve baseline --name baseline-study --run RUN_ID
sift retire path scratch/baseline
sift replay RUN_ID
~~~

The earlier result remains reproducible after its active scratch code has been retired.

To extract a shared metric, create a candidate:

~~~bash
sift promote prepare --title "Share clipped mean absolute error" --rationale "Two studies need the metric"
~~~

Inside the printed candidate directory, extract the metric into core, add known-value and edge-case
tests, update callers, and run the core tests without scratch on the import path. Seal the candidate
from the original project:

~~~bash
sift promote seal PROPOSAL_ID
sift promote show PROPOSAL_ID
~~~

Review the exact diff, contract, assumptions, and test evidence. A human then runs:

~~~bash
sift promote approve PROPOSAL_ID
sift promote apply PROPOSAL_ID
~~~

Passing tests do not grant approval. Replaying the original run still uses its saved original core.
