# Case 3 v1.0.6 first triad: interrupted after Shared postscore

The frozen first-triad order is Isolated → Shared → Shared with an input-action lock. Each arm uses the same `gpt-6-astra` medium, roles, fixture, 25 desktop calls per Actor, 1,200 seconds active model budget, and Oracle. `model-triad1-20261030T193043Z.tsv` is the original manifest. All run directories are retained.

| Arm and run ID | Actor/Oracle outcome | Sample status |
| --- | --- | --- |
| Isolated `bv-lite-v1p6-triad1-isolated-20261030T193043Z` | A 25/25 calls, no corrected saved source or A revision 1; B suspended for the required handoff and received none. A/B/joint false. | Valid task FAIL: both saved files GUI-reopened with equal bytes, both run-owned Guests reset clean. |
| Shared `bv-lite-v1p6-triad1-shared-20261030T193043Z` | A corrected and saved the source at revision 1; B woke, inspected Chrome and typed a correct QA note, but stopped at 25 calls with `*qa_note.txt` unsaved. A true, B/joint false. | **Infrastructure invalid as a complete episode**: after Oracle scoring, an unhandled Gedit “Close without Saving” modal prevented GUI reopen; the run-owned Guest still reset clean. The already scored Oracle and model trace are preserved. |
| Shared + input lock | Not started because the runner stopped on Shared exit 3. | No sample. |

The Isolated Actor active overlap excluding B's handoff wait was 44.020 s; its 808.059 s Actor wall overlap contains the wait. The Shared effective overlap was 52.179 s, model HTTP request overlap 28.602 s, and GUI input overlap 0 s. B suspended for 343.849 s with zero model and desktop calls during suspension. A's saved revision and public handoff woke B. These facts verify the wait/wake protocol; the two desktop streams did not concurrently send GUI input in this Shared attempt.

Shared B's Chrome step 15 showed one visible row after A's saved revision. On returning through the editor dock at B16, the active Gedit tab was A's `orderdesk.html`, which persisted at B18–B19. B selected `qa_note.txt` at B20, typed the expected report at B24 and then clicked the text editor body at B25 instead of saving. The direct failure is the missing saved QA artifact. The shared tab residue cost navigation steps and may have contributed, but this single trajectory does not establish that an input-action lock would change the result. The postscore modal is a coordinator lifecycle error, separate from B's model mistake.

The repair in `61464d2` handles this postscore Gedit modal only after scoring and verifies the saved bytes remain unchanged. A real Guest scripted unsaved-buffer control must pass before the interrupted triad resumes. `triad1_resume` in `aae6073` then runs only a new Shared attempt and the previously unstarted Shared+Lock arm, in the original order and under the frozen parameters. This is infrastructure-invalid sample replacement, not score-based selection; the valid Isolated run is not repeated. Its new manifest and run IDs will be linked here after execution.

## Postscore repair control

The first standalone control `bv-lite-v1p6-postscore-unsaved-shared-20261030T203353Z` had a real Guest and Oracle A/B/joint PASS, but its first screenshot after Ctrl+W arrived before the Gedit modal was drawn. It was classified infrastructure-invalid; its run-owned reset and close completed. The correction in `1619929` polls for the rendered modal and locates its red discard button within the active Gedit modal instead of using a position from a maximized window.

The new standalone control `bv-lite-v1p6-postscore-unsaved-shared-retry-20261030T204919Z` fully PASSed. Oracle A/B/joint and the browser trace were true; its screenshot `screenshots/postscore-B-gedit-unsaved-dialog.png` shows the dirty QA buffer in a non-maximized Gedit window. The guarded GUI click was `(329,558)`. Both saved outputs reopened with identical SHA-256, B's uncommitted buffer was discarded after scoring, the replacement Guest reset with `workspace_clean=true`, and the run-owned container closed. No postscore, cleanup or bridge errors were logged. This validates the recovery path without changing Actor prompts, task artifacts or Oracle.
