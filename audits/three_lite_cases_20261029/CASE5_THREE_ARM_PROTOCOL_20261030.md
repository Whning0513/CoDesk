# Case 5 Lite v1: three-arm evaluation protocol

Status: candidate, **not frozen**. Freeze only after a clean Isolated Guest scripted positive, a real GUI wrong-width negative, request-level tool allowlist verification, and one bounded Isolated model Pilot. Keep every attempted run ID, including infrastructure-invalid starts.

## Fixed gates before model comparison

1. Resource gate: no unrelated active Guest, at least 15 GiB free, unique run ID, and the run-owned QEMU/container cleanup path available. Run `run_case5_isolated_control.sh` only after the shared resource owner releases the window.
2. Isolated scripted positive: both real Guest desktops and Blender/Text Editor render; A's *new* saved revision is at least 1, delivered to B with the same SHA and read-only peer mode before A's handoff message; B's post-Revert screenshot visibly shows the saved 1.46 m width and the pinned dimension-display change is at least 3.0. Host Oracle must report A/B/joint true, both saved outputs reopen byte-identically, two Guest resets succeed, and the bridge reports no unresolved error. A mere artifact PASS with B still viewing 1.20 m is an invalid process control.
3. Isolated model Pilot: one concurrent no-lock run, `gpt-6-astra` medium, 12 desktop calls and 600 active seconds per role, same prompts/fixtures/tools as full runs. Inspect relay request allowlist, model/tool logs, GUI screenshots, A revision and B handoff/reload. A task failure with sound environment remains a valid diagnostic failure; it is not a reason to retune only one topology. An app, bridge, relay, or cleanup fault is infrastructure-invalid and must be repaired symmetrically before the full triad.
4. Full triad: freeze one commit and the listed model/budget/Oracle settings, then execute Isolated → Shared → Shared+Lock once each. Exit 2 is a retained task failure and does not stop the triad; exit 3 or another runner error stops before the next arm. Never select a replacement run because its score was low.

## Task and common settings

`CDD-MAR-LITE-001` uses the existing Blender 5.0 public `Lamp_Review.blend`, role prompts, saved-file bridge, host-only Gold/Oracle, `gpt-6-astra` at medium effort, Codex GUI/collaboration MCP-only request allowlist, B yield/wake lifecycle, 25 desktop calls per role and 1200 seconds per role. A changes only `Lamp_Shade` X/Y dimensions to 1.46 m and publishes a saved `.blend` revision; B independently opens/reverts that revision in Blender, reads the actual width, computes radial clearance, and publishes a text review. The same fixture, prompt, step/time budget, model endpoint and scorer apply to all arms. No Actor sees Gold or Oracle.

Pilot: one Isolated concurrent model run with 12 desktop calls per role and 600 seconds per role. This is diagnostic and is not counted in the full-arm outcome rates. If the Pilot shows an infrastructure failure, fix the infrastructure symmetrically and revalidate controls before freezing. If it shows a model task failure with valid infrastructure, keep the failure and do not revise the task to obtain a desired topology result.

## Three arms

| Arm | Guest topology | GUI input handling |
|---|---|---|
| Isolated | Two independent Ubuntu Guests, one per Actor | Each desktop receives its own input; saved revisions are copied with ownership, SHA verification and read-only peer mode. |
| Shared | One Ubuntu Guest, two independent concurrent Actors | Both Actors send input to the same desktop with no coordination lock. |
| Shared+Lock | Same Shared Guest topology | A run-scoped cross-process `flock` serializes one MCP GUI input call at a time. Screenshot, model reasoning and the interval from observing to the next action remain unlocked. This is a simple input-lock ablation, not an Observe–Act lock. |

One triad uses Isolated → Shared → Shared+Lock. A second triad, if the resource gate remains open, uses Shared+Lock → Shared → Isolated to reduce order bias. No run is repeated or omitted based on its score. If Guest startup or bridge validation fails, label that attempt infrastructure-invalid, retain its trace and start a new run ID only after a concrete repair or environment retry.

## Evidence and interpretation

Each run must retain per-step model screenshot and action logs, actual A/B model usage, messages, artifact revisions and transfer hashes, final files, independent host Blender Oracle, postscore GUI reopen, exact run-owned reset, resource samples and lifecycle events. Report A, B and joint artifact Oracle separately from **behavioral handoff**: B must visibly inspect the delivered Blender revision after A's publish. A correct report typed from A's message alone is not proof of GUI review. If a saved file reached B but Blender displayed its old in-memory scene, that is an adapter or model reload issue, not a bridge loss.

Compute setup time, Actor phase, model HTTP time, token usage, B suspended wait, active Actor overlap excluding suspended wait, model request overlap, GUI input overlap, per-action lock wait/hold and sampled QEMU CPU/RSS. Focus interference requires timestamped window/action/screenshot evidence. Compare Shared+Lock with Shared for both success and extra wait/cost; removing simultaneous input calls alone does not establish that stale observations were resolved. Isolated uses two Guests, so aggregate RSS and setup time differ by topology and cannot be assigned solely to GUI separation.

## Supervision and arm validity gate

The postscore closed-editor path and corrected Guest readiness gate passed the independent real-Guest control `case5-lifecycle-health-20261031T073128Z`; details and limits are in [the recovery report](CASE5_DOCKER_RECOVERY_20261031.md). Inotify watch exhaustion remains observed on the host. It is recorded as an environmental risk without attributing the earlier daemon exit to it.

The triad supervisor records its process identity, start ticks, exit code, unique stamp and frozen source commit. It starts the same `run_case5_model.sh triad1` settings, and never varies Actor prompts, task inputs or scoring by topology. Per-run host samples record CPU, memory, swap, disk, I/O pressure and inotify use; QEMU samples remain run-label scoped. After every arm, a read-only evidence gate checks the exit/status combination, independent Oracle, model and request whitelist, saved-output reopens, reset ownership/cleanliness, bridge health and resource records. An ordinary task FAIL with valid evidence remains a scored sample and does not stop the triad. Missing evidence, a bridge error or a non-200/interrupted relay request stops subsequent arms for review; it is not silently scored as a model collaboration failure. The exact source commit and run IDs are written to the triad config and manifest before execution.
