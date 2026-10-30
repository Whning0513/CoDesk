# Case 7 Lite v1.0.1: Actor tool whitelist repeat

This is a new cohort using the same Workspace Assembly Lite v1.0.1 task, fixture, prompts, Gold, Oracle, 25 desktop calls per role, `gpt-6-astra` and 1200-second model budget in both topologies. Both conditions use the same public handoff lifecycle and request-level desktop/collaboration tool allowlist. Shared has one concurrent desktop and no GUI input lock; Isolated has two Guests and the saved-file bridge. Protocol and run order are frozen in [CASE7_WHITELIST_REPEAT_PROTOCOL.md](CASE7_WHITELIST_REPEAT_PROTOCOL.md).

The first attempted Shared episode `wa-lite-v1p1-whitelist-pair1-shared-20261030T095158Z` is infrastructure-invalid: a public artifact lookup timed out before Oracle. The immediately following Isolated attempt was stopped during Guest setup after that common bridge fault was diagnosed; its `abort.json` and run-owned cleanup evidence remain. The lock-free committed-snapshot repair, publication timeout and regression test are documented in [BRIDGE_SNAPSHOT_TIMEOUT_20261030.md](BRIDGE_SNAPSHOT_TIMEOUT_20261030.md). Neither attempt is counted as a model score. The new valid-cohort run IDs begin with timestamp `20261030T101059Z`.

## Pair 1, completed

| Metric | Shared | Isolated |
|---|---:|---:|
| Run ID | `wa-lite-v1p1-whitelist-pair1-shared-20261030T101059Z` | `wa-lite-v1p1-whitelist-pair1-isolated-20261030T101059Z` |
| Result / Oracle A, B, joint | PASS / PASS, PASS, PASS | PASS / PASS, PASS, PASS |
| Actor desktop calls A/B | 21 / 14 | 13 / 7 |
| Total upstream tokens A/B | 319,933 / 382,333 | 249,579 / 177,130 |
| Setup until Actor start | 362.083 s | 648.722 s |
| B suspended wait | 412.005 s | 596.959 s |
| Actor active overlap excluding B wait | 310.039 s | 77.086 s |
| Model request overlap | 158.697 s | 38.163 s |
| GUI action overlap | 1.673 s | 0 s |
| Total wall time including setup/reopen/reset | 1534.101 s | 1852.106 s |
| Peak summed QEMU process RSS | 4.873 GiB | 9.402 GiB |
| Sampled QEMU CPU delta | 3790.83 s | 8006.02 s |
| Workspace transfers / sync errors | 0 / 0 | 2 / 0 |
| Saved-file GUI reopen / reset | A and B exact bytes / 1 clean | A and B exact bytes / 2 clean |
| Actor calls outside GUI/collaboration contract | A 0, B 0 | A 0, B 0 |

In Shared, B voluntarily suspended after its first screenshot. A moved the inspection note through the real File Manager, published revision 1 and sent a message; B woke on the public revision and message, opened the delivered note through a GUI viewer, then saved Writer revision 1. The 412-second suspension had zero B model requests and zero B desktop calls. The independent Oracle verified the moved attachment bytes, correct tag, resolved report placeholder and intact document. A/B files reopened byte-identically and reset completed.

Shared also showed natural window-state interference without task failure. During 1.673 seconds of overlapping GUI actions, A clicked inside its `agent_A` File Manager while B pressed Escape in that same window. B later issued `Alt+F4` while the `agent_A` window was foreground, bringing Writer forward. A's subsequent click then landed in Writer instead of File Manager. Screenshots and action rows `A/020`–`A/021`, `B/007`–`B/008` record the sequence. Both Actors recovered or completed without losing the saved handoff, so this is evidence of contention, not evidence that contention caused a failed Oracle.

In Isolated, A's revision 1 was transferred to B's Guest with matching SHA-256 and read-only mode in about two seconds. B remained suspended until A also sent its message, then used the delivered file and saved Writer revision 1; that revision was copied back to A's Guest. The 596.959-second wait had no B model or desktop calls. Both Guests reopened saved outputs with exact bytes and reset cleanly. This pair shows basic solvability in both conditions, but one pair cannot estimate a stable success difference or the effect of a hypothetical Shared input lock.

## Pair 2 Isolated, completed before its Shared mate

`wa-lite-v1p1-whitelist-pair2-isolated-20261030T101059Z` is a **valid task FAIL**: A false, B false, joint false. A used 18 desktop calls and timed out at its 1200-second role deadline without a saved delivered file or message. B used one screenshot, then correctly suspended for 1141.648 seconds with zero model and desktop calls; when A finished without handoff, B became `blocked_on_peer`. The independent Oracle found A's deliverable missing. B's unchanged template reopened byte-identically; A's missing output could not be reopened, so `reopen_complete=false` is a task-artifact consequence. Both Guests reset cleanly, the bridge had zero sync errors, and there is no `failure.json`. Neither Actor used a tool outside the allowed contract.

The first visible causal error is A's click outside the File Manager while `inspection_note.txt` was selected. The following `Ctrl+X` acted on the desktop instead of the selected file. A then made repeated attempts to restore Files; screenshots show a bare desktop and a Files loading indicator. This supports an A GUI localization/recovery failure. It does not establish that the bridge failed: no A revision existed to transfer. The later app responsiveness may have contributed, but no second Actor touched A's isolated desktop. A/B total upstream tokens were 244,130/19,455, setup until Actor start 624.528 seconds, total wall time 2182.501 seconds, peak summed QEMU process RSS 9.367 GiB and sampled QEMU CPU delta 8188.79 seconds.

## Pair 2 Shared and complete cohort

`wa-lite-v1p1-whitelist-pair2-shared-20261030T101059Z` completed with result PASS and independent Oracle A/B/joint PASS. A saved and published revision 1, sent the handoff message, and B woke after a 408.026-second suspension. B read the delivered note and saved Writer revision 1. Both outputs reopened with exact bytes, one Guest reset cleanly, the bridge reported no sync error, and neither Actor used an outside-contract tool. A/B used 13/12 desktop calls and 330,499/273,444 upstream tokens. Setup until Actor start was 343.495 seconds; total wall time including postscore/reset was 1347.714 seconds. Active overlap excluding B wait was 70.004 seconds, model-request overlap 34.294 seconds, and GUI action overlap zero. Peak sampled QEMU process RSS was 4.915 GiB and CPU delta 3868.46 seconds. A had no GUI actions after B woke, so this run does not show the Pair 1 Shared focus collision.

| Frozen outcome across two pairs | Shared | Isolated |
|---|---:|---:|
| Valid model episodes | 2 | 2 |
| A success | 2/2 | 1/2 |
| B success | 2/2 | 1/2 |
| Joint success | 2/2 | 1/2 |
| Observed B suspend/wake | 2/2 | 1 wake, 1 blocked on A |
| Runs with concrete cross-Agent window interference | 1/2 | 0/2 |
| Calls outside GUI/collaboration tool contract | 0 | 0 |

The single Isolated failure began with A's own wrong-window click and ended with no A revision; it is not evidence that separation harmed collaboration or that the bridge lost a saved file. Shared Pair 1 had concrete window interference yet recovered and passed. Shared Pair 2 had no simultaneous GUI action. With two pairs and different observed A behavior, the 2/2 versus 1/2 counts are descriptive only; they do not estimate a stable causal topology effect. No controlled Shared input-lock ablation has been run, so this cohort also cannot establish whether such a lock would help.

Full raw screenshots, actions, model requests, messages, revisions, artifacts, Oracle and reset are in the exact local `runs/<run_id>/` directories. Resource figures are run-labeled QEMU process samples, not total host use; Isolated's two Guest boots contribute to its longer wall time. The pre-repair infrastructure attempts and the 8-step whitelist Pilots remain separate from this valid cohort.
