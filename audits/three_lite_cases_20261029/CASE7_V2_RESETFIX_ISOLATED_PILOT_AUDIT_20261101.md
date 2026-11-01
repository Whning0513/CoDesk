# Case 7 v2: isolated Pilot failure audit (2026-11-01)

This report audits the preserved real-GUI run `wa-lite-v2-resetfix-pilot-isolated-20261101a`, source commit `a51270b6593903ab09a98a23186817069837c61f`. The original Oracle result remains **A PASS, B FAIL, joint FAIL**. This was a diagnostic Pilot with two Ubuntu Guests, `gpt-6-astra` medium, a 12-GUI-call diagnostic limit per role and 600-second model timeout; it is not a Shared/Isolated comparison or an estimate of success frequency.

## Timeline and coordinator defect

All times below are UTC on 2026-11-01. Raw events retain subsecond timestamps.

| Time | Evidence |
| --- | --- |
| 01:20:10.775 | A and B Actor sessions started concurrently. |
| 01:21:36.197 | B's saved report was recorded as its revision 1. |
| 01:22:03.911 | B told A it had saved the draft and requested the delivered revision. |
| 01:22:14.812 | B ended after four desktop calls, saying it was waiting for A. |
| 01:22:31.606 | A's revision 1 was saved, after B had ended. |
| 01:22:35.148 | A revision 1's B-side read-only view was verified and committed. |
| 01:23:09.678 | A sent B a readiness notification identifying revision 1, without the record's tag. |
| 01:23:20.796 | A ended after seven desktop calls. |

B's response was consistent with the public instruction to end its current turn while waiting. The lifecycle gate in `oscombo/collab/data_to_deck/live_pilot.py` enters suspension only when `state["own_revision"] == 0` and the handoff condition warrants waiting. B had already published its required pre-handoff report revision 1, and A's delivery and message arrived later. There is no `actor_lifecycle.jsonl` suspension/wake event, and no later B session or B GUI calls appear in the run. The gate and chronology support the inference that B's legitimate prework revision prevented suspension; the actual ephemeral gate-state object was not independently persisted. The coordinator therefore did not give B a chance to resume after A's delivery. This is a lifecycle defect, not evidence that B refused to collaborate. It is also distinct from the ordinary missing final attachment in the saved artifact.

## Raw report and two misleading Oracle subchecks

The collected `artifacts/B/handoff_report.odt` is a real, readable ODT, SHA-256 `37eb8ce36299ca152debf88f1e79fb97283bdc96b3830f7620e090215787f584`. Parsing its actual `content.xml` shows exactly three non-empty paragraphs:

1. `Aurora Supply Handoff`
2. `Prepared for operations review.`
3. `Audience: operations reviewers`

The public draft contains the first two lines. The saved ODT preserves them exactly, and B's screenshots `actor_runs/B/B/shots/003.png` and `004.png` show the same original text and audience entry. The artifact manifest and `reopen_evidence.json` show the B file was collected and reopened byte-identically. There is no evidence that the two draft lines were deleted or that the final ODT was missing during collection.

The existing Oracle sets `draft_text_preserved` false whenever the document does not have exactly four non-empty lines, even if the first two are actually preserved. That subcheck is therefore a definite false diagnostic for this file. It also sets `audience_matches_draft` false at the same global length gate. Independently, its audience regex accepts `Audience: operations` and `Audience: operations team` but rejects `Audience: operations reviewers`; a reviewer audience is a reasonable semantic interpretation of the public `Prepared for operations review.` sentence, although semantic equivalence is a human judgment.

A minimal **in-memory-only diagnostic**, without changing files or the old result, ran the original full Oracle on the actual first three lines with a simulated correct fourth line containing the delivered filename and tag. With `Audience: operations reviewers`, draft preservation and every attachment/tag check became true but audience remained false and joint success false. Changing only that simulated audience to `Audience: operations` made all checks and joint success true. This demonstrates a separate over-narrow audience rule even when the four-line gate is satisfied. It is not a rescoring of the actual run: B's actual ODT contains no fourth attachment line, so attachment filename/tag checks and the original joint FAIL remain justified.

A future, separately versioned Oracle should evaluate preservation, audience, attachment and any strict structure requirement separately, with positive/negative controls for equivalent and incorrect audiences, missing/wrong attachments, and altered/deleted draft lines. Do not overwrite v2's Oracle or historical result; new scoring semantics require a new version and both-topology validation.

## Validity and limits

`contract_audit.json` is valid with A/B desktop calls 7/4 and collaboration calls 3/3; no recorded tool calls violate the GUI/collaboration boundary. All 19 relay events have HTTP 200 and no recorded error type. B's inability to continue is explained by the coordination gate above; this is a coordination-invalid Pilot for judging task solvability or topology effects, despite a clean service/Guest transport audit.

`workspace_sync_result.json` reports verified sync and no transient or persistent faults; A's peer view had SHA/mode verification, but B never opened it. `resource_audit.json` is valid: actual 8 vCPU/8 GiB per Guest, two Guests, complete sampling and filesystem capacity checks. Both output files reopened byte-identically and both reset workspaces were reported clean. Peak sampled QEMU RSS was 10,162,245,632 bytes; sampled QEMU CPU delta was 6900.92 seconds including setup/reset. Setup, Actor phase and total driver elapsed were approximately 785.96, 190.02 and 1297.86 seconds. Provider-reported token totals were A 87,873 and B 50,603; Actor overlap 124.036 seconds and GUI-input overlap 0.0 seconds. These are diagnostic measurements, not evidence of shared-desktop interference.

Evidence remains under the original local run root `runs/wa-lite-v2-resetfix-pilot-isolated-20261101a/`: `oracle.json`, `result.json`, `artifacts/B/handoff_report.odt`, `artifact_manifest.json`, `reopen_evidence.json`, `actors.jsonl`, `actor_runs/B/B/actions.jsonl` and `shots/`, `collaboration/events.jsonl`, `workspace_versions/events.jsonl`, `workspace_sync_result.json`, `contract_audit.json`, `codex_relay_events.jsonl`, `resource_audit.json` and `model_metrics_v2.json`. These large original artifacts remain local and need separate archiving for independent review. Neither a full resumed B attempt nor any formal topology experiment was completed by this Pilot.
