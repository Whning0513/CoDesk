# Case 5 Model-and-Review Lite v2: evidence handoff

Status: the v2 task and real GUI controls are implemented and validated; a complete valid Isolated / Shared / Shared+Lock model triad has **not** been obtained. The only valid model Pilot is a diagnostic Isolated FAIL. Two later formal Isolated attempts are infrastructure-invalid for distinct reasons. No claim can be made about Shared interference or whether input locking helps Case 5. The user-specified direction is a hypothesis, not a criterion for selecting or modifying outcomes.

## Task and controls

A changes the Blender lamp shade X/Y from 1.2 m to 1.5 m while preserving height 0.6 m, saves and publishes. B must reopen the saved project, inspect the actual dimensions, compute clearance from the 0.5 m bulb and save a review. B is not given A's target dimensions. The fixture and host-only Gold/Oracle live in `oscombo/collab/model_and_review_lite_v2/`; they do not replace v1. Shared and Isolated use the same task and Oracle; a separate input-lock arm is planned.

On source `7438393`, four full scripted Ubuntu Guest / Blender 5.0 controls include actual GUI input, screenshots, file handoff, independent host Blender scoring, byte-verified reopen and owned Guest reset. In both positive arms A/B/joint PASS; in both intentionally wrong-width negative arms A FAIL, B PASS, joint FAIL, with the B report matching the deliberately wrong scene. B's visible Revert screenshots show 1.5 m in the positive and 1.3 m in the negative. GUI frame matching is only a readiness candidate; human inspection and independent Oracle provide numeric evidence.

| Control | Original run ID | Oracle A / B / joint |
|---|---|---|
| Shared positive | `mar-lite-v2-control-positive-shared-20261102T100758Z-605177` | PASS / PASS / PASS |
| Isolated positive | `mar-lite-v2-control-positive-isolated-20261102T102544Z-629167` | PASS / PASS / PASS |
| Shared negative | `mar-lite-v2-control-negative-shared-20261102T105731Z-699078` | FAIL / PASS / FAIL |
| Isolated negative | `mar-lite-v2-control-negative-isolated-20261102T111802Z-734362` | FAIL / PASS / FAIL |

After the bridge audit change, source `7279b5b` passed another real Isolated positive regression `mar-lite-v2-control-positive-isolated-20261102T131553Z-965049`, including B's 1.5 m GUI screenshot, Oracle, bridge, reopen and both resets; its bridge logged no retry. Recovered changing-save behavior was **offline injection only**, not a naturally observed real Guest retry. Compact evidence including Oracle, bridge, resets, reload frames and selected model screenshots is in `evidence/case5_v2_20261102/`; complete original run directories and raw trajectories are preserved locally under `runs/<run_id>/` and are not all included in Git.

## Model attempts

All three below used gpt-6-astra medium, two actual Ubuntu Guests, the same v2 role prompts and Oracle, and the same public fixture within each declared protocol. Token counts are sums across recorded model requests, including repeated context. Wall times include setup, collection and reset, while actor elapsed time includes suspended waiting.

| Run | Classification | A / B / joint Oracle | A / B steps and stopping | Wall / actor elapsed | A / B input, output tokens |
|---|---|---|---|---|---|
| `mar-lite-v2-pilot-isolated-20261102T114924Z` | valid diagnostic Pilot | PASS / FAIL / FAIL | 11 done / 12 max_steps | 2179 s / 326 s, 614 s | 140104 / 469; 189914 / 1610 |
| `mar-lite-v2-triad1-isolated-20261102T122638Z` | invalid: original bridge gate | PASS / FAIL / FAIL, raw only | 19 done / 15 done | 2752 s / 702 s, 1161 s | 330865 / 1339; 278367 / 1430 |
| `mar-lite-v2-triad1-isolated-20261102T134912Z` | invalid: incomplete model streams | PASS / FAIL / FAIL, raw only | 13 done / 22 timeout | 3175 s / 542 s, 1592 s | 182518 / 2037; 412788 / 4451 |

The Pilot had 34/34 HTTP 200 `response.completed` records, clean bridge, exact reopened bytes and clean resets. B suspended without consuming active budget and woke when A's message and revision arrived. Its step-9 screenshot still shows the old 1.2 m scene and the wrong Blender application menu; B did not establish a successful reload or complete the report in 12 calls. Actual delivery cannot be equated with actual information use.

In the first formal attempt a save double-read mismatch was recorded, followed by A revision 1 verified in the peer Guest and then B's wakeup. B subsequently reported the stale 1.20 m value despite A's saved scene measuring 1.5012 m. The original strict gate rejects any bridge error. Crucially, the old error record lacks actor/path/attempt ID, so the later transfer cannot be uniquely linked to that error: it remains infrastructure-review, never a valid model failure.

In the second formal attempt B again woke after A's message and revision, but no qualifying review was saved. Two separate B relay failures prevent evaluation as a model sample: one HTTP 200 stream terminated without recorded `response.completed`, and a later `BrokenPipeError` arose 0.135 s after B timed out. The latter timing supports, but does not prove, timeout-driven client disconnect. Incomplete transport and the missing whitelist record are not to be relabeled as task failure. Details and a no-task alternate-endpoint namespace probe are in `CASE5_V2_TRANSPORT_AUDIT_20261102.md`.

## Infrastructure and next work

An earlier Shared positive `mar-lite-v2-control-positive-shared-20261102T085904Z-478134` has raw Oracle PASS but was interrupted by SIGTERM/exit 143 before reopen/reset. It is INVALID_INFRA; its signal origin is unknown. A run-owned detached supervisor now records process/session IDs, signals and cleanup; subsequent valid controls completed without such a signal. Exact run-label cleanup is used; no other workspaces or processes were intentionally touched.

The revised bridge records a save-validation retry ID, owner and path before accepting or transferring bytes. A separate Case 5 audit only permits bounded, fully evidenced recovery with matching role/path/ID, stable historical SHA and peer transfer proof; all raw errors remain visible. Missing linkage, unrelated errors or failed transfers still invalidate the run. The original 7438393 gate and original results remain unchanged. See `CASE5_V2_RETRY_PROTOCOL_20261102.md`; targeted offline tests passed (47 passed, 1 Blender-path-dependent skip).

The alternate endpoint passed one short desktop namespace/image probe, while a collaboration namespace probe returned HTTP 200 then timed out without a terminal event. Two requests cannot quantify service reliability; neither endpoint is established as reliable enough for a new cohort. Resolve or characterize stream termination and confirm both namespace tools with no-task probes, then predeclare and run a full single-endpoint I/S/L cohort without filtering task outcomes. Pay special attention to B's actual Blender reload and evidence use, because two observed Isolated task trajectories encountered that ordinary GUI difficulty. Resource preflight and per-arm 40 GiB /data2 stopping policy should remain active. At handoff, all run-owned Guests had stopped and `qemu-system` process count was zero.
