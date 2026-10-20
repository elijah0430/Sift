# Acceptance coverage

This maps the full design to implementation and executable evidence. Test results must come from
the current commit; this document is not itself a test result or a claim of scientific validity.

| Requirement | Implementation | Evidence |
|---|---|---|
| Existing repository, mapped directories | config.py | configuration and custom-state snapshot tests |
| Core never depends on scratch, including local indirect imports | boundaries.py | test_boundaries.py; indirect/dynamic-import and invalid-source tests |
| Optional Import Linter and Tach native contracts | boundaries.py, examples/minimal | real native CLI checks of both example configurations |
| Freedom to leave scratch incomplete | boundaries.py, lifecycle.py | incomplete-scratch acceptance test |
| Public core interfaces, independent capabilities, cycles | boundaries.py | public-interface/independence and core-cycle acceptance tests |
| Replace methods, models, and datasets outside core | examples/minimal | executable example iteration test |
| Pristine source separate from runtime outputs | snapshots.py | source-mutation and stale-output invariant tests |
| Inputs, seeds, environments, lineage, outputs | snapshots.py | run recording tests; unresolved-input invariant |
| Exact and declared tolerance replay | snapshots.py | exact replay, verifier, failed-run rejection tests |
| Finalized original record stays unchanged | snapshots.py | source-mutation invariant checks original manifest hash |
| Preserve one-off recipes without promoting them | lifecycle.py | lifecycle tests; preserved-recorded-source acceptance test |
| Keep original results after later core changes and retirement | snapshots.py, lifecycle.py, promotion.py | baseline/promotion/retirement integration invariant |
| Core operates without scratch or experiments | examples/minimal/src | isolated core-only import acceptance test |
| Isolated promotion and readable report | promotion.py | promotion tests; wheel CLI checks |
| Configured checks cannot be bypassed by extra checks | promotion.py | configured-check invariant |
| Exact human-reviewed candidate only | promotion.py | missing approval, reseal, post-review edit, report mutation tests |
| Cache/export/artifact CLI cannot bypass maintained-code or approval-state protection | config.py | test_write_boundary.py |
| Conflict detection and interrupted application | promotion.py | base-conflict and resumable-application acceptance tests |
| Recovery from stopped jobs, real process evidence | diagnostics.py | process-liveness and interrupted-run invariant |
| Portable canonical records, rebuildable index | diagnostics.py | exported bundle replay and index-rebuild tests |
| Cache reuse differs from fresh execution | cache.py | stable/fresh keys and scientific-input/environment invalidation tests |
| Content-addressed cache integrity and references | cache.py, gc.py | collision, round-trip, referenced-object retention tests |
| Recoverable retirement and archive verification | lifecycle.py | retire/restore, core rejection, corruption, dependency tests |
| Reviewed GC with pins and current reachability | gc.py | pin, newly-added-pin, changed-target, exact-digest tests |
| CLI JSON and stable error status | cli.py | JSON and agent-denial acceptance test |
| Agent skill included and installable | skills/sift | official skill validator; clean wheel skill installation |
| Agent-independent host contract and launcher | harness.py | argv gate, write path, isolated launcher tests |
| Optional OS sandbox | harness.py | explicit bubblewrap backend; requires a permitted Linux host |
| Local/mounted and command-backed artifact adapters | adapters.py | real local and subprocess transport round-trips |
| Shared-filesystem scheduler adapter | adapters.py | real wrapper-process launch and replay acceptance test |
| Optional notebook frontend | lifecycle.py | valid generated Python; marimo runtime check in integration verification |
| Windows/Linux, Python 3.11–3.13 | CI workflow | six platform/interpreter jobs, tests, lint, format, wheel smoke |
| Installable package, CLI, bundled skill/harness | pyproject.toml | scripts/check_distribution.py installs wheel outside the checkout |

The subprocess transport/scheduler tests validate Sift's adapter contracts. They do not establish
connectivity to a particular organization's cluster, cloud store, GPU fleet, or credentials.
Bubblewrap requires installation and permission to create namespaces; the default launcher explicitly
reports isolation/detection rather than claiming OS enforcement.
