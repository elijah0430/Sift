# A complete research iteration

This example uses only Python's standard library. Start from this directory with Sift installed.

~~~bash
sift check
sift experiment run baseline --artifact results/metrics.json --input dataset=data/original.json --meta method=baseline
sift experiment run expanded --artifact results/metrics.json --input dataset=data/shifted.json --seed 7 --meta method=scaled
sift experiment compare RUN_A RUN_B
~~~

The baseline mean absolute error is 1.5. The expanded experiment introduces another dataset, a scaled
model, and a clipped metric. Its score is 0.0. These are illustrative arithmetic results, not evidence
about a real ML method. Core does not branch on either experiment's name.

Use the first printed run ID to keep the baseline script and link it to that run's results:

~~~bash
sift experiment save RUN_A --name baseline-study
sift experiment archive scratch/baseline
sift experiment reproduce baseline-study
~~~

You can rerun the baseline and check its results after archiving its scratch directory.

To move a shared metric into core, prepare a separate working copy:

~~~bash
sift core propose --title "Share clipped mean absolute error" \
  --rationale "Two studies need the metric" \
  --from-run RUN_B
~~~

Inside the printed candidate directory, extract the metric into core, add known-value and edge-case
tests, update callers, and run the core tests without scratch on the import path. From the original
project, run the checks and save the proposed changes for review:

~~~bash
sift core propose PROPOSAL_ID --ready
~~~

Review the code diff, API, assumptions, and test results. A human then runs:

~~~bash
sift core review PROPOSAL_ID
~~~

Review the change in the configured editor or terminal diff. Choose `a` to approve and apply it, or
`f` to send concrete requested changes back to the agent. Passing tests do not grant approval. Reproducing
the original run still uses its saved original core.
