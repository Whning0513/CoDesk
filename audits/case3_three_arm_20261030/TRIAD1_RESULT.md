# Case 3 Build-and-Verify Lite v1.0.6: first three-arm result

The first frozen comparison used `gpt-6-astra` medium, identical A/B prompts, fixtures, Oracle, 25 desktop calls per Actor and 1,200 seconds active model time. The two independent Actors started concurrently in each arm. Isolated used two OSWorld Ubuntu Guests; Shared and Shared+Lock each used one. The lock serialized individual Shared GUI input actions, with screenshots and model calls outside the lock. No task, Prompt, Fixture or Oracle was changed after any score. All model attempts and their original `runs/` directories are retained.

The original Shared attempt `bv-lite-v1p6-triad1-shared-20261030T193043Z` was **infrastructure-invalid as a complete episode**: A true/B false at Oracle, then a Gedit unsaved-buffer modal blocked GUI reopen. It is not a formal Shared task-failure sample. The postscore-only repair was tested on a real Guest, after which the interrupted triad resumed with new run IDs. See [TRIAD1_INTERRUPTION.md](TRIAD1_INTERRUPTION.md) for both controls and the exclusion rationale. The valid Isolated arm was not repeated.

| Condition | Run ID | A / B / joint Oracle | Actor stop | Validity |
| --- | --- | --- | --- | --- |
| Isolated | `bv-lite-v1p6-triad1-isolated-20261030T193043Z` | FAIL / FAIL / FAIL | A max 25 calls; B `blocked_on_peer` after 1 | Valid task FAIL; two file reopens and two run-owned resets passed. |
| Shared | `bv-lite-v1p6-triad1_resume-shared-20261030T210535Z` | FAIL / FAIL / FAIL | A done after 21; B max 25 | Valid task FAIL; both files reopened unchanged and one run-owned reset passed. |
| Shared+Lock | `bv-lite-v1p6-triad1_resume-shared_lock-20261030T210535Z` | FAIL / FAIL / FAIL | A done after 13; B `blocked_on_peer` after 1 | Valid task FAIL; both files reopened unchanged and one run-owned reset passed. |

All three valid runs have `reopen_complete=true`, `postscore_lifecycle_ok=true`, `workspace_clean=true` for every replacement Guest, and the exact run-owned containers closed. The full-budgets and order are recorded in `model-triad1-20261030T193043Z.tsv` and `model-triad1_resume-20261030T210535Z.tsv`. Their `result.json`, `oracle.json`, `artifact_manifest.json`, `reopen_evidence.json`, `reset_evidence.json`, screenshots, action traces, message and workspace revision events remain under each run ID.

## Time, usage and resources

`active overlap` subtracts B's voluntary handoff suspension; `wall overlap` includes it. Setup is from episode start to Actor start; total includes setup, execution, GUI reopen and reset. QEMU RSS and CPU are sampled estimates. The single Isolated run used two Guests, so its higher memory and CPU cannot be assigned to desktop isolation alone.

| Condition | Total / setup / Actor phase (s) | Active / wall / HTTP / GUI input overlap (s) | B wait (s) | A / B total tokens | Peak summed QEMU RSS / sampled CPU |
| --- | --- | --- | --- | --- | --- |
| Isolated | 1727.2 / 596.9 / 813.4 | 44.020 / 808.059 / 17.873 / 0 | 769.379 | 334,536 / 15,620 | 9.437 GiB / 13,301.4 s |
| Shared | 1582.5 / 394.6 / 953.2 | 76.954 / 448.036 / 33.953 / 0 | 371.083 | 260,579 / 402,015 | 5.496 GiB / 4,388.0 s |
| Shared+Lock | 1231.4 / 398.0 / 491.5 | 44.020 / 486.037 / 20.420 / 0 | 447.519 | 149,140 / 20,087 | 4.821 GiB / 3,200.9 s |

The lock arm's 12 A input actions all logged `input_lock.enabled=true`; their total lock wait was **0.000375 s**, maximum **0.000081 s**, and total held time **88.207 s**. B issued no input action. Screenshots were outside the lock. Thus this arm tested correct lock activation and logging, but it had no actual cross-Actor input contention. A separate two-process real Guest MCP smoke did produce lock contention and zero input overlap, as documented in [CONTROL_AND_PILOT.md](CONTROL_AND_PILOT.md).

## What happened

- **Isolated:** A reached 25 calls without saving the corrected option value. Its source remained revision 0. B suspended awaiting A's message and a new saved revision; none arrived, so the coordinator correctly marked B `blocked_on_peer`. There was no evidence of a bridge transfer fault: the required revision was never published.
- **Shared:** B's first screenshot showed Chrome. A then used `Alt+Tab`; B's next `Ctrl+L`, intended for the browser address bar, landed in A's foreground Gedit tab. B's step 2 screenshot shows `<l!doctype html>` and `*orderdesk.html`. The input actions did **not** overlap in time, so this is a persistent shared-focus misroute rather than simultaneous keystrokes. The stray `l` did not enter A's saved revision. A clicked the VS Code dock icon, later returned to Gedit, and saved revision 1; its own later edit inserted `value="delivered"` into a different closing tag while the original `delievered` option remained. B woke after A's message and saved revision, reopened that file in Chrome, recovered from unsuccessful initial Search input, and then visibly got `North` + `Delivered` → **0 orders shown**. B saved a one-line QA report recording zero/none. A's incorrect saved edit is the direct source failure; B's report and its format also failed Oracle. The early focus misroute and detour consumed actions, but this run does not prove they alone caused the final FAIL.
- **Shared+Lock:** B chose to suspend after only its first screenshot, before any GUI input. A worked alone. It searched for `value="deliverd"`, and a real Gedit screenshot showed “not found”; it saved with no changed file, so revision stayed 0. A sent a message, but B correctly remained blocked because no new saved artifact existed. This is A's string/GUI mistake, not a failed bridge or premature coordinator termination. With B inactive, the action lock had no contention to resolve. The shorter duration and token count mainly reflect the earlier Actor stops; they do not establish a speed benefit from locking.

The historical infrastructure-invalid Shared run also showed A could repair and save the source, while B typed the correct QA content but did not save it before its 25-call budget ended. That trace is useful for capability and modal-repair diagnosis but is excluded from the formal comparison.

## Harness checks and interpretation

All 85 successful provider requests across the three valid arms logged `actor_mcp_only=true` with HTTP 200. Isolated also logged one `ChunkedEncodingError` event after 132.794 s; the harness retried and the episode completed with its normal Oracle and reset evidence. A scan of 25,343 text/JSON/log/source files across the three valid run directories found no provider key bytes. Gold and Oracle stayed scoring-side. No bridge sync error or postscore error was logged in the valid arms.

This one triad shows that a simple per-action input lock can be enabled without adding a screenshot lock, and that Shared focus can misroute an action even when action intervals do not overlap. It does **not** show a success improvement from locking: all three valid conditions failed, and the locked B did not compete for input. More paired samples under the same frozen task would be needed for a stability or treatment-effect claim. No additional Guest run was started after this triad.
