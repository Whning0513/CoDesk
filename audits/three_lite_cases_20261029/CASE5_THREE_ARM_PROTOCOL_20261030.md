# Case 5 Lite v1: three-arm evaluation protocol

Status: candidate, **not frozen**. Freeze only after a clean Isolated Guest scripted positive, a real GUI wrong-width negative, request-level tool allowlist verification, and one bounded Isolated model Pilot. Keep every attempted run ID, including infrastructure-invalid starts.

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
