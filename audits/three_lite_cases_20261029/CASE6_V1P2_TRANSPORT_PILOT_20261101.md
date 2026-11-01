# Case 6 v1.2 transport-gated controls and Isolated Pilot (2026-11-01)

Source commit for **all five runs**: `84a26e266638b5d30fb576db62f1813c986cd355`. This is the independent Case 6 integration branch described in `CASE6_TRANSPORT_INTEGRATION_20261101.md`; that earlier report recorded the preregistration before these runs. The public task, Fixture, prompts, Gold and Oracle were unchanged. This report preserves one Pilot outcome and does not freeze or start formal arms.

## Real Guest scripted controls

The four controls ran in their fixed order, with separate run IDs in the [controls manifest](case6-v1p2-controls-20261101T190311Z-3412583.tsv). Each control used a real Ubuntu Guest desktop, Calc save and reopen, immutable revision-zero and revision-one views, SHA-checked workspace delivery and independent scoring. Two real screenshots per control were visually reviewed and bound to their exact image SHA in run-local `stale_view_visual_review.json` and `peer_view_visual_review.json`. The old read-only revision displayed a blank H3; the delivered read-only revision displayed H3 = 73. `verify_controls` returned `valid: true` for the complete manifest with the pinned source and Fixture fingerprints.

| Control | Topology | Run ID | Oracle A/B/joint | Expected result |
| --- | --- | --- | --- | --- |
| Positive | Shared | `sh-lite-v1p2-positive-shared-20261101T190311Z-3412583` | PASS/PASS/PASS | Met |
| Positive | Isolated | `sh-lite-v1p2-positive-isolated-20261101T190311Z-3412583` | PASS/PASS/PASS | Met |
| Wrong units | Shared | `sh-lite-v1p2-wrong-units-shared-20261101T190311Z-3412583` | PASS/FAIL/FAIL | Met |
| Wrong units | Isolated | `sh-lite-v1p2-wrong-units-isolated-20261101T190311Z-3412583` | PASS/FAIL/FAIL | Met |

Every control completed artifact collection, GUI reopen, run-owned Guest reset and resource observation. Negative controls exited 2 by design; this is the expected Oracle failure, not an infrastructure failure. No control was omitted or rerun for outcome selection.

## One concurrent model Pilot

The [Pilot manifest](case6-v1p2-pilot-20261101T203723Z-3554501175962.tsv) records the only model Pilot on this source commit: `sh-lite-v1p2-pilot-isolated-20261101T203723Z-3554501175962`. It used two independent Ubuntu Guests, `gpt-6-astra` at medium effort, 18 GUI calls and 900 active seconds per role. A and B began concurrently; there was no GUI input lock. The source/model/budget were the registered Pilot configuration. The supervisor exited 0.

The independent artifact Oracle returned A PASS, B PASS and joint PASS. A saved `forecast.ods` with H3 = 73, published immutable revision 1 with SHA-256 `803bdc417592a2415a2def3457cc98ba076ed249e3bc1da8d04e1f3b36e04d96`, then sent a nonnumeric ready message. B's own GUI screenshot `actor_runs/B/B/shots/010.png` visibly shows Calc displaying `forecast-r000001.ods (read-only)` with H3 = 73 and the source row. B later saved `order_plan.ods`, SHA-256 `59d075f4c911836bbcc6cd83dca1ed271fb91f587b27dcb50cffcdd9adadb620`, with E3 = 80 and F3 = 2240; the Oracle verified the E3 × C3 formula in the saved file. B's final screenshot shows those values in Calc. The message, metadata, immutable file delivery, GUI view and final artifact together support an actual handoff; the message alone does not.

| Metric | A | B |
| --- | ---: | ---: |
| Actor outcome | `done` | `max_steps` |
| Desktop tool calls | 4 | 18 |
| GUI actions | 3 | 13 |
| Actor elapsed | 106.01 s | 448.21 s |
| Input tokens | 48,336 | 330,634 |
| Output tokens | 239 | 1,194 |
| Total tokens | 48,575 | 331,828 |
| Model requests | 8 | 25 |

Setup until Actor start was 819.126 s, Actor phase 448.208 s, and total run 1691.7 s including postscore reopen/reset. Actual Actor execution overlap was 106.011 s, active overlap excluding handoff wait 79.863 s, GUI action overlap 7.903 s and model request overlap 30.386 s. B suspended for 26.148 s after A's revision existed but before the ready message was available, then woke on the message; the lifecycle recorded zero model requests and zero desktop calls during that wait. This demonstrates the wait/resume mechanism in this Pilot only, not stability across repetitions.

The 33 recorded model requests all had a valid terminal response; the strict transport audit found zero errors or malformed events. The GUI/collaboration allowlist audit found no outside-contract calls. Workspace bridge verification and persistent history checks passed, postscore reopen completed, both reset Guests had clean workspaces, and the resource profile check observed two initial 8-CPU/8-GiB QEMU Guests. No run-owned `oscombo` Guest remained after cleanup. `model_metrics.json` reports zero for aggregate sampled QEMU CPU/RSS despite the separate profile check confirming Guest settings, so these aggregate CPU/RSS fields are not usable cost measurements for this run.

## Visual evidence gate: unresolved

The Pilot's `handoff_audit.json` correctly identifies B action 2 as formula prework before A's delivery. Its sole prework screenshot candidate is `actor_runs/B/B/shots/002.png`, captured immediately after `type_text('=E3*C3')`. In that image F3 is selected but appears blank, and the formula bar does not show the expression. After the next `Return`, screenshot `003.png` visibly shows F3 = 0; the action log and saved ODS independently establish the formula. A Calc screenshot of the expression itself was not captured. The scoring-side visual review therefore records `visible_F3_cost_formula: false`, while recording the delivered-revision screenshot and nonnumeric message as verified.

On the unchanged gate, `verify_pilot` reports `infrastructure_and_resource_valid`, `request_tool_boundary_valid`, `model_transport_valid`, `source_and_model_config_valid` and `fixture_matches_controls` all true, but `handoff_behavior_visually_reviewed: false` and `gate_passed: false`. This is an **evidence/visual-candidate gap**, not an Oracle failure or a reason to discard the Pilot. The run-local honest review and original screenshots remain unchanged. A scoring-side-only review could consider the immediately following Return screenshot, action chronology and saved formula as separate evidence, with an explicit statement that pixels alone do not reveal the formula expression. Any gate change needs independent review before formal freeze; the Task Card, Actor behavior, Oracle and budget should remain fixed.

Full raw evidence, including screenshots, actions, messages, immutable revision events, artifacts, Oracle, relay events and reset records, is retained locally under `runs/sh-lite-v1p2-pilot-isolated-20261101T203723Z-3554501175962/` (Git-ignored, about 255 MiB). The four controls remain in their separate run directories. No formal Shared, Isolated or Shared+Lock arm was started on this cohort.
