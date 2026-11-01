# Case 7 Lite v2.1 round 1: transport integrity and three-arm comparison

This report records the complete round 1 sequence and the later transport-only replacement rule. It does not turn an infrastructure-invalid episode into a task failure. Raw runs remain under `/data2/whn/CoDesk-case7-v2p1-integrity/runs/<run_id>/`; the original campaign state and frozen source were not edited for recovery.

## Frozen task and evaluation

- Source commit: `a175694753f623b4697a6aa36e5d288b9dc95f7f`; freeze SHA-256: `b1ef83a46c8f787e67fc18fe95843411ab864e3f570f3b999364bf4c71c11f8e`.
- Round 1 uses the same fixture seed, `gpt-6-astra` at medium effort, 25 tool steps and 1,200 active seconds per role in all three arms. Shared and Shared+Lock use one real Ubuntu Guest; Isolated uses two. The lock serializes individual GUI inputs, not a sequence of actions or application focus.
- A moves `inspection_note.txt` into the delivery folder and publishes a revision without revealing its tag. B can prepare the Writer report before the handoff, then must open A's read-only published view in the GUI and use its tag. Oracle independently checks A's moved bytes, B's preserved draft, audience, filename, and correct delivered tag. Message/revision and screenshots are separate behavioral evidence.
- The freeze contains positive/negative real-Guest controls and a Pilot review. The present report covers the formal round 1 episodes only; controls and Pilot are not additional formal observations.

## All attempts, in chronological order

| Slot | Run ID | Validity and raw Oracle | Evidence and interpretation |
| --- | --- | --- | --- |
| Isolated original | `wa-lite-v2p1-isolated-round1-20261101T161327Z-3bd0f22a` | `INVALID_INFRA`; raw A PASS, B FAIL, joint FAIL | B relay #26 (one-based) had HTTP 200 with 1,177 forwarded bytes and no complete SSE terminal. Retained, excluded from task outcome. |
| Isolated preflight | `wa-lite-v2p1-isolated-round1-transport-retry-8efe3488b2f9` | `NOT_STARTED` | Credential-file preflight failed before Guest or model launch; retained in external ledger and not counted as a complete episode. |
| Isolated replacement | `wa-lite-v2p1-isolated-round1-transport-retry-56c5aaf72333` | `VALID_FAIL`; A PASS, B FAIL, joint FAIL | 41/41 relay responses completed, bridge and two-Guest reset valid. B opened the real read-only peer view, but the saved Writer line used `L0f090A-29` instead of delivered `LOT090A-29` and concatenated `Audience: operationsInspection note`. This is a model/GUI task error. |
| Shared | `wa-lite-v2p1-shared-round1-20261101T173023Z-4b0b1b40` | `VALID_FAIL`; A FAIL, B FAIL, joint FAIL | 36/36 relay responses completed. A did not publish its source file; B waited after requesting handoff. A's `Ctrl+X` landed in B's Writer and B's `Audience` text landed in Files search, so natural shared-focus interference is directly visible. |
| Shared+Lock original | `wa-lite-v2p1-shared_lock-round1-20261101T174908Z-942a8cdd` | `INVALID_INFRA`; raw A PASS, B FAIL, joint FAIL | Five incomplete relay events (#7, #8, #20, #33, #35, one-based). All 25 executed GUI inputs acquired the action lock and input overlap was zero, yet cross-action focus mistakes remained. Retained, excluded from task outcome. |
| Shared+Lock replacement | `wa-lite-v2p1-shared_lock-round1-transport-retry-6909da5f0e36` | `INVALID_INFRA`; raw A PASS, B FAIL, joint FAIL | Unique full replacement, same frozen runner/configuration. Eight incomplete relay events (#5, #12, #13, #21, #23, #26, #27, #29); A timed out, B suspended and then was marked blocked when A finished without a message. Retained; the one-complete-replacement limit is exhausted. |

## Timing, usage, resource, and causal evidence

The first row and last two rows below are **infrastructure-invalid**. Their metrics are descriptive only; they are not task-success observations. Values come from `model_metrics_v2.json` for valid runs and the same read-only analyzer on retained raw logs for invalid runs. `I0` and `L0` are original invalid episodes; `I1` and `L1` are full replacements; `S` is the original Shared episode.

| Run | Setup / actor / post seconds | Total seconds | A / B tokens | Active / GUI-input / model-request overlap seconds | A / B lock wait seconds | Peak sampled QEMU RSS GiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| I0 invalid | 763.327 / 743.387 / 318.966 | 1,825.681 | 62,648 / 325,653 | 82.688 / 7.560 / 35.659 | 0 / 0 | 9.215 |
| I1 valid | 756.770 / 574.287 / 373.949 | 1,705.006 | 76,213 / 516,199 | 119.797 / 3.798 / 41.234 | 0 / 0 | 9.253 |
| S valid | 438.049 / 395.900 / 219.979 | 1,053.929 | 304,649 / 166,524 | 250.064 / 27.536 / 76.422 | 0 / 0 | 4.894 |
| L0 invalid | 524.893 / 1,200.087 / 219.531 | 1,944.510 | 331,970 / 102,659 | 952.065 / 0 / 684.993 | 4.230 / 12.583 | 4.895 |
| L1 invalid | 523.770 / 1,206.044 / 213.024 | 1,942.837 | 204,155 / 53,493 | 410.049 / 0 / 324.945 | 0.888 / 0.000072 | 4.898 |

Relay responses with `response.completed` / total requests were I0 34/35, I1 41/41, S 36/36, L0 30/35, and L1 21/29. All three invalid runs were rejected by the transport contract gate; the valid runs passed it.

Every full episode passed its bridge and resource audits and reset each run-owned Guest to a clean workspace. GUI reopen matched saved bytes for both roles in I0, I1, L0, and L1. In S, B's file reopened with matching bytes, while A had no deliverable to reopen; this was classified as the task failure shown by the valid Oracle, not a postscore infrastructure fault.

Isolated's larger setup and post-actor time includes two Guests and bridge handling; it is not evidence that desktop isolation slowed the model. The two valid arms both failed jointly, for different reasons. This round cannot estimate a success-rate advantage. Shared has observed focus misrouting, while Isolated's B reached the handoff and produced an incorrect tag in the final file. The shared run's missing A deliverable and B's consequent waiting cannot be attributed solely to focus interference.

The valid Isolated bridge committed A revision 1 with SHA-256 `162300d0c1ca1dec6119c7de74ae328b192b6bfe6c7cb889e7ac383ff79d6635` and `views/B/inspection_note-r000001.txt`; A sent one notification. B had saved prework before publication and opened this read-only view in Writer at actions 12–13. Screenshot `actor_runs/B/B/shots/012.png` visibly shows the source tag. The final ODT's `content.xml` contains the wrong tag and concatenated audience/attachment text, so A's delivered revision was available but B transcribed or edited it incorrectly. In valid Shared, no A revision or reply existed; B sent one request and ended `blocked_on_peer` after A failed.

In the invalid original lock episode, a read-only metrics pass found setup 524.893 s, actor 1,200.087 s, post-actor 219.531 s; 952.065 s A/B active overlap, zero GUI input overlap, 684.993 s model-request overlap, A/B tokens 331,970 / 102,659, and lock waits 4.230 / 12.583 s. B action 2 typed `Audience: operations reviewers` into Files search; A action 6 typed a file path into B's Writer. The action lock prevented simultaneous inputs but did not bind an actor to a window across actions. Because the relay failed, these numbers and screenshots describe a mechanism only, not a valid lock-arm task result.

The invalid replacement lock episode confirms the transport fault was not transiently cleared: 29 relay requests contained eight failures, including two HTTP 200 streams with terminal `error` after 2,611 forwarded bytes, two `response.failed` streams after 1,510 bytes, three zero-byte `ProxyError` requests, and one zero-byte `BrokenPipeError`. The independent contract audit rejected it. A read-only metrics pass found setup 523.770 s, actor 1,206.044 s, post-actor 213.024 s, total 1,942.837 s; 410.049 s active overlap, zero GUI input overlap, 324.945 s model-request overlap, A/B tokens 204,155 / 53,493, and lock waits 0.888 / 0.000072 s. A executed 12 GUI inputs and B two, all with the same action lock. B action 3 attempted `Ctrl+S` to save Writer while Files had focus (`window_before=incoming`), and the resulting screenshot shows Nautilus. B's lifecycle records `suspended_for_peer_handoff` with `pause_active_budget=true`, then `peer_finished_without_handoff`; A committed revision 1 but sent no notification before its 1,200-second timeout. These are descriptive observations from an infrastructure-invalid run. Both files reopened with matching bytes, one Guest reset cleanly, and the run-owned Guest count returned to zero.

## Post hoc transport-only replacement rule

The external rule was adopted at `2026-11-01T16:55:18Z`, **after** observing the original Isolated invalid run and its raw A PASS/B FAIL/joint FAIL Oracle. It was not in the original preregistration. The same rule allows at most one complete replacement per arm for terminal transport corruption, with a new run ID. It records the invalid original, observed Oracle, baseline reference, and any `NOT_STARTED` preflight. A partial response or GUI trajectory is never replayed. A source/freeze hash check, exact-run evidence check, cleaned-process check, disk gate, and no-other-Guest gate precede a new full episode. The transport cause was not resolved, and post-observation adoption remains a selection-bias limitation.

The frozen campaign state SHA-256 is `596089aa0c3f3bf0a1d105beb3f69fbcafa0c3e7d1fff1840e61379b3412af76`; recovery used an append-only external continuation under `/data2/whn/case7-transport-recovery-20261101/`. The final lock continuation state and ledger are in its `round1-sharedlock-continuation/` directory; the final ledger SHA-256 is `ecf98622b29d374e90e5e2667e7919ccb5913f426461b25275d32cb7ad38d4e6`. The external coordinator is `recover.py`, SHA-256 `04898bd9d6152336ed45acd8483a535c4b71abc954e1ef45d3fdf9b90ede26d5`, with 14 passing offline tests. It is not copied into the frozen benchmark source. The credential value is not recorded here. After all episodes, the frozen source commit, freeze hash, original campaign state hash, and zero run-owned Guest count were rechecked.

## Evidence map and limits

For each run, `result.json`, `oracle.json`, `contract_audit.json`, `codex_relay_events.jsonl`, `actor_runs/{A,B}/`, `screenshots/`, `reopen_evidence.json`, `reset_evidence.json`, and `resource_samples_v2.jsonl` are the primary evidence. Valid runs also have `model_metrics_v2.json`. In the Shared run, inspect `actor_runs/A/A/shots/011.png` and `actor_runs/B/B/shots/013.png` for wrong-window actions. In the original Shared+Lock run, inspect `actor_runs/B/B/shots/002.png` and `actor_runs/A/A/shots/006.png`. The replacement lock run has a further B save-to-Files example at `actor_runs/B/B/shots/003.png` but is infrastructure-invalid.

The two valid arms cannot establish a Shared versus Isolated success difference; neither lock episode is valid for task outcome. The evidence does show that a simple per-action lock eliminates simultaneous input overlap while leaving window focus vulnerable between actions. A future lock comparison requires a transport-stable, independently frozen cohort, with all invalid and valid episodes reported. No further round 1 replacement is scheduled under the adopted rule.
