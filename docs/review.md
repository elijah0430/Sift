# Reviewing core changes

Core contains modules that the project will maintain and reuse. An agent prepares a proposed change
in a separate directory; the researcher's working core remains unchanged until approval.

## Prepare a proposal

The agent starts a proposal and edits the returned directory:

```bash
sift propose --title "Share the calibrated scorer" \
  --rationale "Two experiments use the same scoring function"
```

When Git is available, the proposal directory is a local repository whose first commit contains the
baseline. Editor Source Control views therefore show proposed files as ordinary uncommitted changes.

After adding appropriate tests and updating callers, the agent marks the proposal ready:

```bash
sift propose PROPOSAL_ID --ready
```

This runs import-boundary checks and the checks configured in `research.toml`, then saves the exact
code, diff, results, and original project state presented for review. Extra checks can be supplied
with `--check COMMAND`.

## Review a proposal

The researcher runs:

```bash
sift review
```

Sift shows the purpose, changed files, and check results. It can open the proposal in the configured
editor, and always retains a terminal diff. The review menu provides these actions:

```text
[o] open code review  [d] terminal diff  [c] checks
[f] request changes   [a] approve and apply  [l] later
```

Configure an editor in `research.toml`:

```toml
[review]
command = "code --wait"
```

Sift also honors `VISUAL`, `EDITOR`, and `sift review --editor`. Use `sift review --terminal` to stay
in the terminal.

If the reviewer edits the proposal, Sift can rerun the same checks and show the refreshed diff before
approval. Requesting changes stores feedback with the reviewed version and removes the proposal from
the review queue. The agent reads it with:

```bash
sift propose PROPOSAL_ID --feedback
```

The agent then revises the proposal and runs `sift propose PROPOSAL_ID --ready` again.

## What approval covers

Passing checks does not grant approval. Approval applies only to the code, diff, check report, and
project state displayed in that review session. Changing the proposal or affected project files
requires new checks and a new review.

Before applying an approved proposal, Sift revalidates the saved version and current project state.
Application uses a journal and atomic file replacement. An interrupted application can resume only
when affected files still match their recorded before or after contents. A concurrently approved
revision cannot be substituted into an already open review session.

The lower-level `promote` commands expose the underlying prepare, seal, approve, and apply operations.
They are intended for integration and recovery; the normal researcher interface is `sift review`.

Software checks establish properties of the implementation. They do not establish the scientific
validity of the proposed method or its empirical claims.
