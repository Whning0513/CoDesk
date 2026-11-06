# Spreadsheet Handoff Lite v1.3 model protocol

This protocol is a prepared entry point, not evidence of a Guest or model run.
The Task Card, actor prompts, Fixture, Gold, Oracle, and scoring conditions are
the version-pinned v1.3 files. Do not modify them within a triad.

## Conditions

`run_model_triad.sh` runs these arms once, in fixed order:

1. `isolated`: two independent Ubuntu Guests.
2. `shared`: both Agents use one Ubuntu Guest and desktop without an input lock.
3. `sharedlock`: the same shared desktop with the existing per-action input lock.

All arms use model and effort supplied once to the driver, identical role prompts,
public Fixture, role step budgets (18 each), 1200 second model timeout, two request
retries, the same collaboration server, SavedArtifactBridge, request-level
`actor_mcp_only=True` Responses relay, Oracle, reopen procedure, and resource
sampling. Only Guest topology and the lock-arm path vary. Both Actors are submitted
to a two-worker executor behind a start barrier in every arm.

## Readiness gate

The driver refuses to start unless the source commit equals
`CODESK_CASE6_V13_FROZEN_COMMIT`, the checkout is clean, with at least 15 GiB free
and 1024 inodes on each of the run-base, Docker data-root, Git
common-directory, and Guest-image filesystems, the assigned Guest slot is named
`case6-v13`, required OSWorld image/provider/runtime paths are set, and the selected
API credential environment variable is nonempty. The caller supplies an explicit
`CODESK_CASE6_V13_DOCKER_DATA_ROOT` and a fresh, empty run base on `/data2`.

The driver resolves `DOCKER_HOST` (default `unix:///var/run/docker.sock`), checks
the selected Unix socket's type and read/write permissions, then makes a read-only
`docker info --format '{{.DockerRootDir}}'` query and requires the actual root to
match the expected path under `/data2`. It does not start containers or copy an
image. A read-only `docker image inspect` also checks that
`OSCOMBO_RUNTIME_IMAGE` resolves to the explicitly supplied
`CODESK_CASE6_V13_RUNTIME_IMAGE_ID` (`sha256:` content ID). Use an authorized
dedicated rootless Docker daemon with its socket and data-root on `/data2`; do not
reuse the existing CoDesk daemon/data-root on `/data3`. Guest overlays and run
output also remain on `/data2`.

The shell exports `PYTHONDONTWRITEBYTECODE=1`; the model runner also points both
Codex MCP servers at a run-owned Python wrapper with bytecode writing disabled.
This avoids cache writes to the OSWorld venv/source filesystem when it is mounted
read-only or resides outside `/data2`.

Do not invoke until an authorized coordinator assigns the Guest slot and confirms
the OSWorld Guest image/runtime are available. API keys remain in the caller's
environment and are never copied into task files, run metadata, or logs.

## Run evidence and classification

Each arm has a unique run ID and retains screenshots/action/session logs, message
events, bridge revisions and diagnostics, final ODS files, Oracle output, token
usage, postscore reopen/reset evidence, relay transport audit, Actor tool-boundary
audit, and resource samples. Saved files that fail the Oracle are task failures;
bridge, relay allowlist/transport, saved-file reopen, reset, or Actor whitelist
failures invalidate the run. Handoff validity also requires A's committed revision
and readiness-only message, B's metadata/message reads before the exact peer-view
path is entered in Calc, a screenshot action after opening it, and a subsequent B
save. The transcript gate does not establish what a screenshot visually showed;
human visual review remains required before interpreting a PASS as behavioral
handoff evidence.

No retry or arm substitution is authorized by this protocol. Preserve any
infrastructure-invalid attempt and have the coordinator decide whether a
symmetric infrastructure recovery is permitted.
