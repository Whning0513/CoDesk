# Case 6 v1.3 offline audit and run recipe

Audit date: 2026-11-05. This is a source/trajectory audit only; no Guest or
model request was started.

## Version/worktree identity

The only v1.3 package found in registered Case 6 worktrees is
`/data3/whn/Project2/CoDesk-case6/oscombo/collab/spreadsheet_handoff_lite_v1_3/`
with `tests/test_spreadsheet_handoff_lite_v1_3*.py`. The checkout is currently
on `experiment/case6-lite-v1p2-20261031`, HEAD
`7318a051f6d4db6d2781b73879e167f057c08210`; the entire v1.3 package and tests
are untracked. The base worktree `/data3/whn/Project2/CoDesk` and the other
registered Case 6 worktrees checked do not contain v1.3. There is no dedicated
v1.3 branch/worktree or committed version checkpoint yet. Preserve the
existing v1.1/v1.2 worktrees and runs. Do not launch an experiment from this
v1.2-named checkout as if it were a frozen v1.3 branch.

## Unit-interpretation audit

The earlier model failure was real: in the v1.0 whitelist pair, Shared B
entered `8` in a unit field and computed `$224`, treating the eight cases as
eight items. See
`audits/three_lite_cases_20261029/CASE6_WHITELIST_PAIR_RESULTS_20261030.md`
and the saved B artifact/trace in
`runs/sh-lite-v1-whitelist-shared-20261030T130038Z/`.

The v1.2 positive Shared scripted control is a different failure. Its A
artifact passes with H3=73. B's order file was saved and recovered, but E3 and
F3 are blank, the cost formula returns `#VALUE!`, and the Oracle records
`order_units=null` and `order_cost_usd=null`. B's trace shows navigation with
Up/Left before typing `80`; the active window remained `order_plan.ods`.
`reopen_evidence.json` shows both scored files reopened byte-identically and
`result.json` records `reopen_complete=true`, a clean reset, and intact source
files. This is consistent with cell-selection/navigation failure; it does not
show an eight-cases-versus-eight-items calculation in this run and provides no
evidence of a shared focus race. Evidence:

- `runs/sh-lite-v1p2-positive-shared-20261031T101949Z-694693519912/oracle.json`
- `runs/sh-lite-v1p2-positive-shared-20261031T101949Z-694693519912/result.json`
- `runs/sh-lite-v1p2-positive-shared-20261031T101949Z-694693519912/actor_runs/B/stage-04/trace.json`
- `runs/sh-lite-v1p2-positive-shared-20261031T101949Z-694693519912/actor_runs/B/stage-04/B-step04.png`
- `runs/sh-lite-v1p2-positive-shared-20261031T101949Z-694693519912/reopen_evidence.json`

v1.3 addresses the ambiguity in the public workbook and scoring contract:
E3 is `Need (individual units)`, F3 is `WHOLE CARTONS TO ORDER`, G3 is
`TOTAL INDIVIDUAL UNITS`, and H3 is total USD cost. B's prompt names both units
explicitly. The Oracle checks E3 against A's saved need, F3 against the minimum
whole-carton count, G3/H3 against the formulas and values, and the budget.
`tests/test_spreadsheet_handoff_lite_v1_3.py::test_cases_units_confusion_is_rejected`
verifies that entering 80 in the carton field is rejected. These checks are
offline; they have not been exercised in a v1.3 Guest.

## Save and postscore audit

v1.2's scripted Shared control did persist a B ODS artifact, bridge-publish
both revisions, reopen both saved files with matching bytes, and reset the
run-owned Guest cleanly. B's saved content was wrong/blank, but this was scored
as a task failure rather than a postscore infrastructure failure. The v1.3
scripted adapter has explicit Ctrl+S actions, bridge publication, Oracle
collection, GUI close/reopen and byte comparison, and a postscore lifecycle
gate. It is not Guest-tested.

The common postscore-recovery code has a separate real Guest positive control,
including an injected stale `Open` dialog that was cancelled before reopening
the saved file. See
`audits/three_lite_cases_20261029/CASE6_POSTSCORE_REPORT_20261030.md` and its
referenced run `sh-lite-v1-postscore-open-control-20261030T091200Z`. This
validates the shared recovery helper, but does not validate the new v1.3
adapter's setup or reopen path.

## Codex tool allowlist audit

The v1.1 triad's actual model requests were routed through the loopback
Responses relay. `provenance.json` has `actor_mcp_only=true`; each relay event
records the flag, the removed built-in tool names, and upstream HTTP 200. The
relay's `restrict_actor_tools()` filters the request body before forwarding
and retains only pinned `mcp__desktop` and `mcp__collaboration` functions in
`oscombo/responses_tool_image_relay.py`. The per-run Codex rollout audit found
zero calls outside the desktop/collaboration allowlist for each arm:

| Run | Relay requests with allowlist flag | Upstream non-200 | Actor calls outside contract |
| --- | ---: | ---: | ---: |
| `sh-lite-v1p1-triad1-isolated-20261030T225247Z` | 30/30 | 0 | A=0, B=0 |
| `sh-lite-v1p1-triad1-shared-20261030T225247Z` | 32/32 | 0 | A=0, B=0 |
| `sh-lite-v1p1-triad1-sharedlock-20261030T225247Z` | 40/40 | 0 | A=0, B=0 |

Evidence for each arm: its `provenance.json`, `codex_relay_events.jsonl`, and
`actor_tool_boundary_audit.json` under `runs/`; source enforcement is in
`oscombo/responses_tool_image_relay.py::restrict_actor_tools` and
`oscombo/collab/data_to_deck/live_pilot.py::_start_codex_compat_relay`.
This establishes that the option was active and the action logs show no
out-of-contract Actor tool calls. It does not preserve a copy of the outgoing
filtered request body (intentionally omitted from logs). Also, the later v1.2
fail-closed `relay_transport.audit()` cannot validate these older relay events
as complete Responses streams because they lack its newer terminal/forwarded
byte evidence fields. Do not conflate that transport-evidence limitation with
the request allowlist flag.

## Current adapter coverage and gap

`live_pilot.py` offers version-pinned scripted positive/negative controls for
`collaborative_shared` and `collaborative_isolated`. It has no model option and
does not expose `Shared+PerActionLock`. It is therefore suitable only as a
future scripted GUI/setup/save/sync/reopen smoke, not as the requested model
triad. The 24 offline tests do not invoke its Guest path. A model adapter for
v1.3 still needs to launch the two model actors concurrently, use the same
allowlisted relay in all arms, and pass the shared lock path to
`_run_model_actor(..., gui_input_lock_path=...)` only in the lock arm.

## Run recipe after an explicit resource release

1. Review this untracked v1.3 diff and make a dedicated v1.3 branch/worktree
   from the exact v1.2 base plus the v1.3 files. Keep the current historical
   run roots untouched. Do not call it frozen until fixture, scripted
   positives/negatives, and both topology smoke controls have real Guest
   evidence.
2. Store the new worktree, run roots, caches and QEMU overlays on a filesystem
   with sufficient verified free space. At audit time `/data3` had 4.9 GiB
   available and `/data2` had 37 GiB. The current account could not read/write
   `/dev/kvm` or `/var/run/docker.sock`; use an authorized rootless Docker
   runtime or fix the intended runtime access before starting. Check image and
   runtime paths are readable, and keep model credentials outside run logs.
3. Run scripted positive and negative for Shared and Isolated with unique run
   IDs, one run at a time. Expected mapping: positive Oracle joint PASS;
   negative Oracle joint FAIL; bridge/handoff/reopen/reset failures are
   `INVALID_INFRA_OR_RUNNER_ERROR`. Inspect the A/B saved files, B's exact
   peer-view GUI screenshot, collaboration event log, `workspace_sync_result`,
   `oracle`, `reopen_evidence`, `reset_evidence`, and `result` for every run.
4. Only after both scripted conditions pass their positive and negative
   controls, implement/review the v1.3 concurrent model adapter. Preregister
   the three-arm order and budget. Use identical model, prompt, fixture, relay,
   tools and Oracle in Isolated, Shared, and Shared+PerActionLock; the lock arm
   alone passes the existing per-action lock path. Preserve all runs and do
   not repeat based on score.
5. Capture per-arm setup, model and screenshot time, token usage, active
   overlap, GUI action overlap, focus/window changes, revision/message/sync
   evidence, Oracle, reopen/reset, and Guest CPU/RSS. Keep setup and total
   Guest cost separate from model time.

Resource reference, not a v1.3 prediction: the prior v1.1 triad run roots use
about 238–257 MiB each and sampled peak QEMU RSS was about 9.75 GiB summed for
the two-Guest Isolated arm, versus about 4.93–4.99 GiB for one-Guest Shared
arms. Three full run roots therefore need roughly 0.75 GiB for evidence at
that historical rate, plus image/cache/overlay headroom. The OSWorld notes
warn per-Guest overlays can consume GBs. Current RAM availability was ample
(about 959 GiB), but disk/runtime permissions are the immediate blockers.
No Guest or API was started during this audit.

## 2026-11-06 isolated v1.3 model-entry preparation

An isolated copy of the uncommitted v1.3 package was made at
`/data2/whn/CoDesk-case6-v1p3-20261106` on branch
`experiment/case6-v1p3-model-threearm-20261106`, based on commit
`7318a051f6d4db6d2781b73879e167f057c08210`. The source worktree on `/data3`
was not changed. `LINEAGE_MANIFEST_20261106.json` records the inherited source
hashes; `MODEL_ADAPTER_CHANGE_MANIFEST_20261106.json` records this isolated
model-entry addition and the unchanged inherited v1.3 hashes.

The active working copy is now an independent local clone at
`/data2/whn/CoDesk-case6-v1p3-independent-20261106`, branch
`experiment/case6-v1p3-model-threearm-independent-20261106`, at the same base
commit. It was cloned with `--no-local --no-hardlinks`; Git common storage is
the clone's local `.git`, and no alternates file exists. The v1.3 package and
three test files were copied into it with matching SHA-256 values; `__pycache__`
was excluded. The original staging copy and the `/data3` source remain intact.

The new `model_pilot.py` and `run_model_triad.sh` provide a three-arm concurrent
model entry, require request-level `actor_mcp_only=True`, audit fail-closed
relay and Codex tool-boundary evidence, preserve saved-file Oracle/reopen/reset
checks, and report wall interval overlap separately from observable active
request/GUI overlap. The readiness-only message audit permits explicit revision
IDs, version strings and dates, while detecting remaining numeric or spelled-out
unit/currency quantities. An exact peer path, message and metadata read, GUI open
action, subsequent screenshot call, and B publication are required for automated
handoff validity; a human must still visually review the saved screenshot trail.

This preparation is offline only. The new model runner and triad script have not
started a Guest, queried Docker/QEMU, or called a model API. The future triad
driver resolves `DOCKER_HOST`, checks the selected Unix socket, then uses
read-only `docker info --format '{{.DockerRootDir}}'` and `docker image inspect`
queries to verify the dedicated `/data2` Docker root and pinned runtime image ID.
It does not start containers or copy images. A real run remains blocked on
coordinator assignment of the Guest slot and an authorized dedicated rootless
Docker daemon/data-root on `/data2`; the current CoDesk socket/data-root on
`/data3` is not to be reused. The driver requires at least 15 GiB and 1024 free
inodes separately on the run base, Docker data-root, Git common directory, and
Guest image filesystems. At the last read-only check, `/data2` had about 35 GiB
free, the standard Docker socket was not accessible, and `/dev/kvm` was
unreadable/unwritable.
