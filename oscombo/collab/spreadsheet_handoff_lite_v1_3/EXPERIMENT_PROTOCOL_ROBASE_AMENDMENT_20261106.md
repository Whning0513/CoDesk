# Spreadsheet Handoff Lite v1.3 resource-policy amendment (draft)

Status: offline-only amendment candidate. It does not replace the original v1.3
protocol or change the Task Card, A/B prompts, Fixture, Gold, Oracle, tool
allowlist, model budget, or three-arm comparison.

## Scope and precedence

The original `EXPERIMENT_PROTOCOL.md` remains authoritative for the original
`run_model_triad.sh` entry point and all existing evidence. This amendment
applies only to the separate `run_model_triad_robase.sh` candidate and only to
a newly frozen cohort; it does not retroactively waive the old image-filesystem
gate. A Guest/model run remains unauthorized under the current offline-only
instruction.

## Entry point and freeze

Use `run_model_triad_robase.sh` from the independent Case 6 clone. The source
checkout must be clean and frozen at the commit reviewed for this amendment;
the original `run_model_triad.sh` remains available for the original policy.
The run base must be fresh and on `/data2`. This amendment does not authorize
starting a Guest or contacting a model endpoint.

The RO-base runner requires `CODESK_CASE6_V13_OSWORLD_COMMIT` and
`CODESK_CASE6_V13_OSWORLD_DIFF_SHA256`. Before contacting Docker or starting a
Guest, it compares `git -C "$OSWORLD_DIR" rev-parse HEAD` with the commit pin,
hashes `git diff --binary HEAD`, and rejects non-ignored untracked files.
Tracked staged or unstaged changes are allowed only when their combined diff
hash is explicitly pinned. The exact commit and diff hash are recorded in the
resource preflight and each arm's run metadata; both are rechecked before arms
and after the triad. This OSWorld source pin applies only to new RO-base cohorts.
The original runner and historical evidence are unchanged.

The frozen manifest must record the exact Guest image SHA-256. A candidate
baseline is recorded in
`GUEST_IMAGE_BASELINE_CANDIDATE_20261106.json`: it comes from the existing
Case 7 image freeze, and the current file size and nanosecond mtime match that
freeze. This is not yet a Case 6 freeze. Supply the Case 6 frozen digest in
`CODESK_CASE6_V13_GUEST_IMAGE_SHA256`; the runner hashes the selected file and
fails closed unless it matches. The digest is public provenance, not a
credential.

## Resource policy

Retain the 15 GiB free-space and 1024-inode reserve for each writable path:
the run base, the selected Docker data-root, and Git common storage. They must
resolve under `/data2`. The Guest image remains at its pinned path and must be
readable; its filesystem is exempt from the writable-capacity threshold only.

The common Guest boot path must verify that Docker mounted that exact image at
`/System.qcow2` with `RW=false`; the QEMU overlay must be run-owned. DesktopEnv
cache, screenshots, collaboration/relay logs, and final artifacts stay under
the run root. The shell runner records the image device/inode/size/mtime/ctime
before the triad and checks the same metadata on every exit. The SHA helper
compares metadata before and after hashing, rejects a symlink/noncanonical
image path, and the canonical image path is the one passed to every Guest.
The Case 6 model adapter also verifies the runtime image ID, actual mount,
overlay, and DesktopEnv/SetupController cache root at boot and after postscore
reset only when the new entrypoint passes `--robase-validation`. Boot validation
allows `DesktopEnv.cache_dir` to be absent before OSWorld `_set_task_info()`;
postscore-reset validation requires the task-specific path to be nonempty and
inside this Guest's cache root. The original v1.3 model runner does not enable
that policy and retains its previous result contract.
After validating the selected Docker socket, the runner exports that same
`DOCKER_HOST` so the Python Docker SDK and Guest provider cannot silently fall
back to a different daemon; it rejects a set `DOCKER_CONTEXT` to avoid CLI
context precedence ambiguity. The runner rechecks writable filesystem reserve
before each arm. Python bytecode writing remains disabled for external OSWorld
imports. These checks are startup guards, not a peak-disk quota, so resource
samples still need review during any future authorized episode.

## Comparison conditions and validity

The arms remain Isolated, Shared, and Shared+PerActionLock in the same order
and use the same model, role prompts, public Fixture, task budget, allowlisted
tools, workspace bridge, and Oracle. Only the Guest topology and existing
per-action lock differ. All forwarded model requests must retain the
request-level `actor_mcp_only=True` filter.

An actual cohort still requires shared/isolated scripted GUI positive and
negative controls, review of save/reopen/reset and mount/overlay evidence, and
a small model pilot before the complete triad. Preserve every failed or
invalid attempt; do not select a favorable arm or retry only a failed
condition. Old v1.3 runs and the old capacity-gate protocol remain unchanged.

## Current verification

The shell syntax and offline unit tests validate the gate and evidence checks.
There is no Guest positive/negative control, model Pilot, or formal arm under
this amendment yet. A clean freeze and live controls must be produced after an
authorized Guest window and the dedicated `/data2` Docker data-root are
available.
