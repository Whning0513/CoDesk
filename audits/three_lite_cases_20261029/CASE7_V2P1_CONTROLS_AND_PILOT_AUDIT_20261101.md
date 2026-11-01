# Case 7 Lite v2.1: six GUI controls and Isolated Pilot audit

Source commit: `b23a6a0b8e30fccf2e3ef9489cfae1f7f4bf6ea1`. Runs below are under `runs/` in `/data2/whn/CoDesk-case7-v2-wait-candidate`. This report does not change any run, scoring result, or original automatic audit. The controls are scripted GUI controls, not model samples.

## Six controls

All six were individually checked with the v2.1 freeze `_control` against the same source; both positive controls and both revision probes returned PASS. Both negative controls returned the expected Oracle FAIL, isolating the incorrect delivered tag. All six had valid resource audits, verified bridges and clean post-score reopen/reset. Manual screenshots show B's read-only file; the two negative reports visibly contain the intentional `WRONG-00`. Each A message simply announced revision 1 or 3 without the inspection tag.

| Control | Run ID | Oracle outcome |
| --- | --- | --- |
| Shared positive | `wa-lite-v2p1-positive-shared-20261101a` | PASS |
| Isolated positive | `wa-lite-v2p1-positive-isolated-20261101a` | PASS |
| Shared negative | `wa-lite-v2p1-negative-shared-20261101a` | expected FAIL |
| Isolated negative | `wa-lite-v2p1-negative-isolated-20261101a` | expected FAIL |
| Shared revision probe | `wa-lite-v2p1-probe-shared-20261101a` | PASS |
| Isolated revision probe | `wa-lite-v2p1-probe-isolated-20261101a` | PASS |

Both probes recovered three immutable 444 views, with rev 1 and rev 3 equal by SHA and rev 2 different; owner file was 644. In the Shared probe, `screenshots/control_B_peer_view.png` was captured while Writer was importing and shows a blank canvas; the subsequent `screenshots/B-016.png` shows the fully rendered revision 3 in read-only mode. This manual limitation is not hidden by the automated gate.

## Isolated Pilot

Run `wa-lite-v2p1-pilot-isolated-20261101a` used gpt-6-astra, 12 GUI calls and 600 active seconds per actor. Real OSWorld GUI and independent scoring were used. The two actor active intervals overlap by 441.128 s according to `model_metrics_v2.json`.

B's real GUI trace has four pre-yield calls: screenshot, type `Audience: operations review`, Ctrl+S, and a 3-second desktop wait. Its screenshot `actor_runs/B/B/shots/002.png` shows the original title and operations sentence and that exact audience text. B then checked collaboration state, requested A's notification and ended the turn explicitly saying it was waiting.

`actor_lifecycle.jsonl` records B suspended at Unix 1793505748.446 with own revision 1, peer revision 1 but no peer message, and 167.944 active model seconds remaining. A sent its notification at 1793505906.605; B was woken at 1793505907.362 after approximately 158.916 seconds without spending the paused active budget. On resumption B called `read_messages` and `list_saved_artifacts`; it did not open the peer view in the GUI or add the attachment. A and B both ended with `timeout` after exhausting their respective 600 active seconds (B wall elapsed 758.99 s including the suspension). B's two observed resumed model responses took approximately 105 and 28 seconds; this slow service and the remaining budget constrain what this Pilot can establish about task solvability. No completion or failure should be inferred from the wake event alone.

The recorded Oracle is A PASS, B FAIL and joint FAIL. B's preserved original draft check passed; its audience check rejected `Audience: operations review`, and attachment/filename/tag were absent. This exact phrase is not the `operations reviewers` equivalence accepted by v2.1. Its semantics should be evaluated separately if considering any future scorer change; this run is not rescored.

## Transport review and limitations

A published its artifact and sent its message just before its 600-second deadline. After A had timed out, an in-flight relay attempt logged `BrokenPipeError` at Unix 1793505998.655, `phase=downstream_write`, `headers_sent=true`, `forwarded_bytes=0`, with HTTP upstream status 200. The chronological evidence is consistent with a downstream closure after budget termination, but the exact causal classification is not proven merely by HTTP 200. Treat this Pilot's transport as **requiring infrastructure review**, not a clean model comparison.

The retained `contract_audit.json` reports valid because the v2.1 contract currently checks the HTTP status and allowlist marker without checking `error_type`; `freeze._pilot` has the same omission, and the campaign consumes the contract. Thus the automatic clean result is insufficient. Do not alter the original automatic record; reject or explicitly classify relay error events in a new source revision before using this gate for formal runs.

The bridge audit was verified with no historical faults or unresolved retries. `resource_audit.json` reports valid capacity and monitoring; both recovered artifacts reopened and both new Guests reset cleanly, then were closed using their full run-owned IDs (see `reset_evidence.json` and `resource_actions.jsonl`). This validates the observed pause and wake path, not sustained model solvability. No Shared model comparison or formal v2.1 experiment has been run after this Pilot.
