# Case 6 v1.2: first formal Isolated / Shared / Shared+Lock triad

## Scope and evidence rule

This is one consecutive, unselected three-arm cohort. The frozen benchmark/runner source for every arm is `84a26e266638b5d30fb576db62f1813c986cd355`; the Task Card, public Fixture, prompts, model (`gpt-6-astra`, medium effort), 25 desktop calls and 1,200 active seconds per role, workspace bridge, Gold and Oracle are identical. Shared and Shared+Lock use one real Ubuntu GUI Guest; Isolated uses two. The lock serializes individual GUI input calls and does not reserve desktop focus across calls. Arms were launched in the fixed order Isolated, Shared, Shared+Lock, each once, with no score-based replacement.

The earlier [controls and Pilot](CASE6_V1P2_TRANSPORT_PILOT_20261101.md) used this same source. Four real GUI controls matched expected positive and wrong-units negative outcomes, with save/reopen/reset and SHA-checked revision delivery. The Pilot had joint Oracle PASS and complete transport, but the original `verify_pilot` visual gate was **false**: its screenshot does not directly show the typed F3 formula. Before formal arms, a separate, post hoc, scoring-side review admitted corroborating action chronology, subsequent screenshot and saved ODS to establish that B entered and committed the formula in the GUI before handoff. It did **not** claim that the screenshot shows the formula, that the prework formula was saved before handoff, or that the original verifier passed. This adjudication rule was chosen after observing the Pilot's PASS, so selection/interpretation bias cannot be excluded. The original Pilot/review and all frozen benchmark files remain unchanged. The external review and one-arm caller live outside Git at `/data2/whn/case6-multisource-20261101/`; final lock SHA-256 `8596351820c09e81bf230bff4f5cdc9af7ae9690cc6f1b5c64bf888496f1d1a6`, Pilot review SHA-256 `98110304592d6d167b92b399bb9fe7960cc6d2ca7f51523d94abe590d754879e`. Its append-only ledger is `triad1_events.jsonl`; offline checks passed 14/14 before launch. This external gate checks the unchanged source, controls/Pilot evidence, per-arm configuration and strict transport; it does not alter Actor bytes or the Oracle.

Run directories are retained locally under `/data2/whn/CoDesk-case6-frozen-84a26e/runs/` and are Git-ignored. The cohort stamp is `20261101T211356Z-3582273839069`:

| Arm | Exact run ID | Guest count | Independent Oracle A/B/joint | Validity |
| --- | --- | ---: | --- | --- |
| Isolated | `sh-lite-v1p2-triad1-isolated-20261101T211356Z-3582273839069` | 2 | PASS / PASS / PASS | Valid |
| Shared | `sh-lite-v1p2-triad1-shared-20261101T211356Z-3582273839069` | 1 | PASS / PASS / PASS | Valid |
| Shared+Lock | `sh-lite-v1p2-triad1-sharedlock-20261101T211356Z-3582273839069` | 1 | PASS / FAIL / FAIL | Valid task failure |

Shot paths below are relative to the corresponding run directory. Five unmodified key screenshots are also included in this commit for remote review: [Isolated B11 revision 1](evidence/case6_v1p2_triad1_isolated_B11_revision1.png), [Shared B03 Open dialog](evidence/case6_v1p2_triad1_shared_B03_open_dialog.png), [Shared A05 formula corruption](evidence/case6_v1p2_triad1_shared_A05_formula_corruption.png), [Shared+Lock B02 wrong window](evidence/case6_v1p2_triad1_sharedlock_B02_wrong_window.png), and [Shared+Lock B25 revision 1](evidence/case6_v1p2_triad1_sharedlock_B25_revision1.png). Their SHA-256 values, in that order, are `16442f5cacd6a6918be902a16adde2f3203a90d70e1e7e45a7ddd79c6eed7a36`, `3c5cb9672e6d5d8535ec6e375cb215fc70fba1337b4cc32d0279e82515f1059b`, `c6a691510d744ad361f5ca41ffaadbdd8f22c4467d3543501901f2853a5609f7`, `8fd1684f386bba80895007d620308145072504f54ae8db78b5868d86256b627c`, and `5e24cc13d3d4bb5f722ee052f79be0c7a7229650432282966ba25d1d585439f4`.

## Isolated: independent desktops, successful handoff

A and B started concurrently. A saved `forecast.ods` with net need H3 = 73 and published immutable revision 1, SHA-256 `4cce572e8c758ec27818a3b8f639caa635212cbf22e66fdf09a6033aa1fbce0e`. A then sent a nonnumeric ready message. B suspended without model requests or desktop calls for 40.231 seconds, woke on the delivered revision/message, and its own real GUI screenshot `actor_runs/B/B/shots/011.png` shows `forecast-r000001.ods (read-only)` with H3 = 73. B saved `order_plan.ods` SHA-256 `87cf97b95211495ab02b1fbe295c137d1c766355465d7cf6bcb0376e89f8cc2a`, E3 = 80 whole units, F3 = 2240, formula `of:=[.E3]*[.C3]`. The Oracle independently passed A, B and joint, including source integrity and purchase budget. Message, immutable revision, actual GUI view and final file jointly support the information handoff.

B made a routine Calc error: it first typed `80` into the Name Box (`shots/019.png` and `020.png`) instead of E3, then clicked E3 and corrected it in actions 21–24. This is ordinary GUI difficulty, not a workspace bridge failure. Both saved artifacts reopened with matching bytes in their Guests, both run-owned Guests reset to clean workspaces, the bridge history check passed, and 39/39 model responses had `response.completed`. No Guest remained after cleanup.

## Shared: real focus interference, followed by recovery

This single-desktop arm also passed A/B/joint Oracle. A's saved revision 1 SHA-256 is `613d7048a971c463d5d72e035bd8867c622067ded26ecb80e256c084b96840ba`; B's final order SHA-256 is `d68b4ea509ece039ed123a3524ead64f7967aba74da5f169b9fce3d3b774bf45`, with the same correct 73 need, 80 units, 2240 cost and general E3 × C3 formula. B viewed the delivered read-only forecast with H3 = 73 (`actor_runs/B/B/shots/017.png`) after A's revision/message. Both artifacts reopened with matching bytes, the one Guest reset cleanly, the bridge history check passed, and all 54/54 model responses completed.

The action/screenshot chronology gives direct evidence of natural shared-desktop interference:

1. A opened a file dialog with Ctrl+O while B tried to commit its formula with Return; B `shots/003.png` shows the Open dialog instead of the expected Calc cell.
2. A's forecast path was typed into B's F3 edit buffer; A `shots/005.png` shows the corrupted expression `=3*C3/tmp/sh12/outputs/agent_A/forecast.ods`.
3. B later retyped `=E3*C3` into an Open dialog search (`shots/008.png`) and received no matching result. The actors then restored the intended windows/files. B repaired F3 and E3 near its 25-step budget and saved the correct order.

These incidents occurred while model execution overlapped; they are not inferred merely from final success/failure. Shared succeeded despite the interference. B exhausted 25 calls and was labeled `max_steps`, but the final independently scored files passed. This one observation does not estimate a population success rate.

## Shared+Lock: valid task failure despite serialized input

The per-call input lock was active on all 36 actual GUI input calls (A 13, B 23), with no serialization violation and **zero simultaneous input-action overlap**. A waited essentially zero; B waited 2.215 seconds in total, at most 1.641 seconds on one call. A switched windows between calls; B action 2 then typed `=E3*C3` into A's `forecast.ods` H3 (`actor_runs/B/B/shots/002.png`), showing that the lock did not grant multi-action window ownership. This is a visible cross-Agent focus error despite a correctly operating input lock, not evidence that the lock itself malfunctioned.

A subsequently saved forecast revision 1, SHA-256 `3628bbb694771275f869b1857802257c2596434f2647f8b037bf31d49634ec51`, with H3 = 73 and sent a nonnumeric ready message. B suspended without model requests or desktop calls for 57.303 seconds, woke on the revision/message, then used steps to clear misdirected content, restore its order sheet and open the read-only forecast. B's final screenshot `actor_runs/B/B/shots/025.png` visibly shows `forecast-r000001.ods (read-only)` with H3 = 73, proving actual receipt in the shared GUI. The model spent its last action on that view and did not save the order: the collected B `order_plan.ods` was still immutable revision 0, SHA-256 `55675c4d67439f9808f00cdc880d4315dca8dbdc172cb27e5c5c3e12439c5e06`, 2,136 bytes. The Oracle measured no saved E3 units, F3 formula or cost; A PASS, B FAIL and joint FAIL. B was labeled `max_steps` at 25/25 calls. The chronology supports a contribution from misrouted GUI actions and recovery cost, but a single trace cannot establish that focus contention was the only cause; B also spent several calls on ordinary Calc and file-dialog repair.

This is a **valid task failure**, not an environment failure: all 50/50 model requests ended in `response.completed` with no transport errors; the bridge history was clean, A revision 1 was delivered, both collected artifacts reopened from the real GUI with identical SHA values, the one run-owned Guest reset to a clean workspace, and no `oscombo` Guest remained. The external runner returned task exit 2 with `infrastructure_issues=[]`. The lock itself passed its coverage and serialization checks.

## Measured effort and limitations

| Metric | Isolated | Shared | Shared+Lock |
| --- | ---: | ---: | ---: |
| Setup until Actor start | 781.513 s | 367.336 s | 370.916 s |
| Actor phase | 574.289 s | 793.281 s | 617.402 s |
| Total incl. postscore/reset | 1797.830 s | 1396.010 s | 1240.590 s |
| A / B total model tokens | 61,502 / 507,468 | 303,029 / 606,993 | 252,595 / 553,984 |
| A / B desktop calls | 5 / 24 | 18 / 25 | 15 / 25 |
| A / B executed GUI inputs | 3 / 18 | 14 / 21 | 13 / 23 |
| Actor overlap | 120.010 s | 382.030 s | 326.028 s |
| Active overlap excluding B wait | 79.779 s | 174.839 s | 268.725 s |
| B handoff wait | 40.231 s | 207.190 s | 57.303 s |
| GUI input overlap | 7.287 s, separate Guests | 8.140 s, one Guest | 0 s, lock serialized calls |
| Model request overlap | 38.596 s | 52.307 s | 41.732 s |
| Lock wait A / B | 0 / 0 s | 0 / 0 s | 0 / 2.215 s |

The setup difference includes an extra Isolated Guest and cannot be attributed to desktop sharing. The sampled aggregate QEMU CPU/RSS metrics were zero despite separate resource-profile evidence of live 8-vCPU/8-GiB QEMU Guests; these aggregate fields are unusable as physical resource measurements. Guest count and allocation are recorded, but physical host resource cost is not reliably estimated here. GUI action latency is recorded per Actor (`model_metrics.json`: Isolated A/B 12.792/77.839 s; Shared 61.618/88.240 s; Shared+Lock 53.395/97.332 s), with screenshot time separately recorded; these are sums across different action counts, not a per-action speed estimate. All elapsed values are measured for this single cohort; they do not establish a stable efficiency ranking.

The result is descriptive: one Isolated PASS, one Shared PASS despite clear focus collisions, and one Shared+Lock FAIL despite removing simultaneous input. A simple per-call lock did not reliably solve shared-desktop state contention in this cohort. It may change scheduling and the sequence of model decisions; this one triad cannot show that the lock caused the failure or that unlocked Shared is generally better. The correct next step, if stability is needed, is a separately frozen repeated campaign that retains every run and accounts for provider transport, not a favorable-sample rerun. The post hoc Pilot evidence decision and one run per arm limit any comparative claim.
