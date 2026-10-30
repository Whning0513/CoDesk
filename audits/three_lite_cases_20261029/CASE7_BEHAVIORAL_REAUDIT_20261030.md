# Case 7 v1.0.1 behavioral handoff re-audit

This note corrects the interpretation of the frozen `20261030T101059Z` whitelist cohort. It does not edit old run directories, artifacts, Oracle results or the earlier phase report. The independent Oracle scored saved attachment and Writer bytes; it did not verify B opened A's delivered note in a GUI.

| Frozen episode | Artifact Oracle joint | B GUI opened delivered note after A revision? | Interpretation |
|---|---:|---:|---|
| Pair 1 Shared | PASS | Yes | B action 3 opened `outputs/agent_A/inspection_note.txt`; action 5 shows that delivered path in Gedit before the Writer edit. A revision and message preceded B's read. |
| Pair 1 Isolated | PASS | **No evidence; actual B tool sequence never opened it** | B used A's public message containing `RIVER-27`, then edited Writer directly. Its seven desktop calls stayed in Writer. This is artifact success but does not satisfy the role's explicit GUI file-check step. |
| Pair 2 Shared | PASS | Yes | B action 3 opened the delivered file, action 5 shows its path in Gedit, then B edited Writer. |
| Pair 2 Isolated | FAIL | No handoff existed | A never produced a revision or message; B correctly remained blocked on the peer. |

For Pair 1 Isolated, `actor_runs/B/B/actions.jsonl` lists only two screenshots, a Writer click, a Writer selection, text entry, Save and a wait. The Codex rollout has no GUI open action between A's revision/message and the Writer edit. `actor_runs/B/B/shots/002.png` shows the unchanged Writer draft, and `shots/003.png` shows Writer again. `collaboration/events.jsonl` contains A's tag message. The bridge transfer itself was verified with matching SHA; the missing step is B's GUI inspection. The earlier [whitelist repeat report](CASE7_WHITELIST_REPEAT_RESULTS_20261030.md) says B “used the delivered file” in this episode; that should be read as **used the delivered tag from A's message**, not as observed GUI file use.

The read-only [`audit_case7_handoff.py`](audit_case7_handoff.py) checks A's saved/visible revision, the A→B message, B's saved revision and a foreground-window title showing `outputs/agent_A/inspection_note.txt` after that revision. It reports artifact and behavioral endpoints separately. It is conservative: absence of matching window-title evidence means GUI use is unproven and may require manual screenshot review. Running it on the frozen Pair 1 Isolated episode yields `oracle_joint_success=true` and `behavioral_handoff_verified=false`; the two Shared artifact PASS episodes yield `behavioral_handoff_verified=true`.

Case 7 Lite v1.0.2 addresses this without changing the historical score: A moves before reading the delivered note; B's prompt explicitly requires opening that delivered file in a GUI before editing Writer. The v1.0.2 validation protocol retains artifact Oracle and behavioral handoff as separate reported measures. No claim about desktop isolation or a GUI lock follows from the old 2/2 versus 1/2 artifact counts.
