# Sift harness contract

Sift separates agent preparation from human authorization. Hosts should load
[`policy.json`](policy.json), restrict ordinary agent writes to the declared scopes, and reserve
`sift promote approve` and `sift promote apply` for a human-controlled terminal.

`sift harness policy` exposes the same policy through the CLI. `sift harness guard -- <command>`
provides a lightweight command gate for hosts that can route Sift commands through a wrapper.
Filesystem enforcement remains the host's responsibility because an unrestricted shell can bypass
an advisory command wrapper.

The promotion protocol remains safe under concurrent edits: sealing removes prior approval, approval
records the exact digest, and applying verifies every affected base file before writing.

