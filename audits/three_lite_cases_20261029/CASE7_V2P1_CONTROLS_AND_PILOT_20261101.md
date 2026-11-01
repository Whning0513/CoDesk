# Case 7 v2.1 controls and first model Pilot, 2026-11-01

## Frozen control cohort

All six GUI controls ran sequentially from `5b4e37630503805ad84ff564456396188b537efe`, with the same deterministic control Fixture and the registered 8 vCPU / 8 GiB per Guest TCG profile. Each run passed the `/data2` and `/data3` 15 GiB gate and the no-active-Guest gate before launch. Every run retained its own screenshots, GUI actions, collaboration messages, revision events, final artifacts, independent Oracle, reopen evidence, reset evidence, and QEMU resource audit. A separate earlier Shared positive from `b8fc08a` remains preserved and is not part of this cohort.

| Slot | Run ID | Artifact Oracle A / B / joint | Reopen / reset / resources |
| --- | --- | --- | --- |
| Shared positive | `wa-lite-v2p1-control-positive-shared-20261101T095206Z-2534288` | PASS / PASS / PASS | PASS / PASS / PASS |
| Isolated positive | `wa-lite-v2p1-control-positive-isolated-20261101T100835Z-2565201` | PASS / PASS / PASS | PASS / PASS / PASS |
| Shared wrong-tag negative | `wa-lite-v2p1-control-negative-shared-20261101T103343Z-2610604` | PASS / FAIL / FAIL | PASS / PASS / PASS |
| Isolated wrong-tag negative | `wa-lite-v2p1-control-negative-isolated-20261101T104936Z-2632510` | PASS / FAIL / FAIL | PASS / PASS / PASS |
| Shared immutable-revision probe | `wa-lite-v2p1-control-probe-shared-20261101T111311Z-2670318` | PASS / PASS / PASS | PASS / PASS / PASS |
| Isolated immutable-revision probe | `wa-lite-v2p1-control-probe-isolated-20261101T113101Z-2689401` | PASS / PASS / PASS | PASS / PASS / PASS |

The original `freeze._control` validation passed separately for every slot. It verified source commit, deterministic Fixture hashes, independently rescored Oracle, A's message chronology, peer-view mode and SHA, bridge state, QEMU resources, reopen, and reset. I manually inspected each control's B prework Writer screenshot and read-only peer-view screenshot. The screenshot paths, SHA values, and review are saved in `runs/case7-v2p1-six-control-visual-review-20261101.json`. Both revision probes retained three distinct, read-only revision paths: rev1 SHA prefix `d0d32f0c`, rev2 `986f3e1e`, rev3 `d0d32f0c` (restored original bytes). The wrong-tag controls failed only the intended tag checks.

## Original model Pilot

The preregistered Isolated Pilot `wa-lite-v2p1-pilot-20261101T120007Z-2729992` used `gpt-6-astra`, 12 diagnostic desktop calls per role, 600 seconds of **active** Actor time, request-level desktop/collaboration tool allowlist, and the normal wait/wake lifecycle. It started both Actors at the same time. A delivered revision 1 and messaged B after the saved peer view was verified. B saved an audience draft before A's publication, asked for the delivery, suspended for 172.874 s, and woke upon A's message. B then opened Writer's file picker and typed the correct read-only peer-view path, but timed out before submitting the picker. The saved B action sequence and `reopen-B-failed.png` show the still-open dialog. The behavioral audit records no B read-only document window.

The independent artifact Oracle found A success, B failure, and joint failure. The bridge final sync and both Guest resets passed; the resource audit was valid. B used 8 of the 12 diagnostic GUI calls and reached approximately 600.066 active seconds; its 772.940 s Actor wall time included the suspended wait. A ended `done` after 7 GUI calls. The run was **infrastructure-invalid overall**, rather than a clean scored model episode, for two additional reasons: B's postscore GUI reopen failed because the remaining Open modal blocked Writer activation, and the last B relay request started just before Actor timeout then ended 127.826 s later as `ProxyError/upstream_connect` without HTTP status or response terminal. The earlier 23 relay requests were HTTP 200 with `response.completed`; the request-level tool audit found only desktop and collaboration calls. These raw facts remain in the original run; no result was replaced.

| Metric | Value |
| --- | ---: |
| Environment setup | 845.712 s |
| Actor phase | 772.940 s |
| Post-Actor processing | 289.073 s |
| Total | 1907.725 s |
| A input / output / total tokens | 75,779 / 394 / 76,173 |
| B input / output / total tokens from completed responses | 93,718 / 484 / 94,202 |
| A/B active overlap | 239.153 s |
| A/B GUI input overlap | 1.489 s |
| A/B model request overlap | 158.964 s |
| Peak sampled QEMU RSS sum | 10,045,816,832 bytes |

## Postscore repair and validation boundary

The accompanying code change cancels an Actor-left Writer `Open` picker **only after both Actors have stopped and the saved artifacts have already been scored**. It retains a before frame, sends at most three Escape presses, requires the picker to disappear, and retains an after frame. It does not submit the entered path, edit a task file, change the Oracle, or alter an Actor's budget. The existing saved-byte comparison remains mandatory after GUI reopen. The same postscore path is used in Shared and Isolated conditions. Offline tests cover a two-Escape picker, no picker, a picker that refuses to close, and an unverifiable screenshot.

This new source commit has **not** been exercised in a Guest. Under the v2.1 protocol, both topology controls and a new Pilot must be verified from the revised commit before a formal freeze. The old six controls and original Pilot remain attributed to `5b4e376`; no full freeze manifest can be created from that Pilot because the required transport and postscore checks failed. No model run is started by this repair.
