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

Pair 2 is still running and will be appended without selecting by outcome. Full raw screenshots, actions, model requests, messages, revisions, artifacts, Oracle and reset are in the exact local `runs/<run_id>/` directories. Resource figures are run-labeled QEMU process samples, not total host use; Isolated's two Guest boots contribute to its longer wall time.
