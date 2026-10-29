# Three independent Lite cases: Build-and-Verify, Spreadsheet Handoff, Workspace Assembly

Date: 2026-10-29. Branch: `experiment/codesk-three-lite-cases-20261029`.

## Environment

The runs reuse the OSWorld V2 Ubuntu qcow2 Guest and the rootless Docker/QEMU provider. The machine has no KVM device, so QEMU uses TCG; Guest setup commonly takes 10–23 minutes and is kept separate from Actor execution. The previously verified archive SHA-256 is `14b08aa7ba6c023ecb91d46de8df5de32af4d1d6bd75ea925519caf9677fc8b3`; the extracted qcow2 SHA-256 is `28b617987f3edf14edd835069cdde6a6e4708be8e4ae4eb957200d5da335186a`. The QEMU image integrity check reported zero errors (`audits/takeover_20261026T135400Z/image-verification.log`). The live model is `gpt-6-astra` through `https://api.haogpt.net/v1`; its key is read from a local non-Git file into the coordinator process only. The Actor uses an authenticated local relay and cannot see the key or scorer files.

## Scope and boundaries

This branch adds independent Lite variants for original Cases 3, 6 and 7. It does not change the original cases, collaborator's Case 2, or the Data-to-Deck experiment. The Lite task cards, public fixtures, role prompts, private Gold, Oracle and Guest adapters are under `oscombo/collab/{build_and_verify,spreadsheet_handoff,workspace_assembly}_lite_v1/`. The Gold and Oracle are installed only in the host scorer, outside the Actor workspaces. Model Actors operate real Ubuntu Guests through screenshots and GUI actions. Shared runs use two concurrent model threads on one desktop without an input lock. Isolated runs use two concurrent model threads on two Guests, with saved peer files copied as read-only revisions and the same message/attachment protocol.

The three designs retain a real handoff: A must produce a saved revision, B must use it, and the scorer checks both outputs. Artifact correctness alone does not establish that handoff occurred. The run records include model actions, screenshots, messages, revision events and separate behavioral audits. Scripted controls exercise the real GUI and the scorer, but are **not** model success evidence.

The bridge fixes each Actor's publish path by role, stores append-only revisions, double-reads a saved file before publishing, validates ODF ZIP checksums where applicable, copies to the peer Guest via same-directory rename, checks the read-back hash and applies read-only mode to Isolated peer copies. It detects an unexpected peer edit instead of silently overwriting it. Shared uses one filesystem, so OS file permissions cannot separate the two GUI Actors; the publish API still enforces ownership, while any cross-role GUI edit must be found in the trace/Oracle audit. No bridge transfer error was observed in the completed positive controls or model runs above.

## Task reductions

| Case | Lite task and dependency | Scripted critical GUI path | Shared desktop competition |
|---|---|---:|---|
| 3 Build-and-Verify v1.0.4 | A fixes one `Delivered` HTML option in a GUI editor; B opens A's saved page in Chrome, tests `North + Delivered`, saves a QA note. | About 15 calls combined | Editor and Chrome vie for window focus and keyboard input. |
| 6 Spreadsheet Handoff v1.0.0 | A calculates one SKU's net need (`73`) and records source range in Calc; B reads that saved forecast and enters the smallest whole-case purchase (`80`) and cost (`2240`) in its own Calc file. | About 14 calls combined | Both Calc windows vie for focus; same visible spreadsheet interface can route an edit to the wrong workbook. |
| 7 Workspace Assembly v1.0.1 | A moves one inspection note in File Manager and publishes its tag; B verifies the delivered note and completes one Writer sentence. | About 10–15 calls combined | File Manager and Writer vie for focus, text can land in the wrong application. |

The expected numbers in the Case 6 row are **evaluator-only report context**; the Actor prompts contain rules and input data, not precomputed answers. In Case 7 the source note initially exists in the shared input tree. B's instruction requires the delivered revision and GUI verification, but a Shared Actor can read that source early. The behavioral audit must flag this limitation independently of the artifact Oracle.

## Validation already completed

- Offline full suite after the Case 7 lifecycle patch: `212 passed, 1 skipped` (see `pytest-yield-lifecycle.log`). After the Case 3 model screenshot and dirty-editor postscore corrections: `214 passed, 1 skipped` (see `pytest-v1p5-adapter.log`). The three Lite modules include positive and wrong-value/file negative controls.
- Case 3 v1.0.4 scripted Shared `bv-lite-v1p4-scripted-shared-pos-20261029T155745Z` and Isolated `bv-lite-v1p4-scripted-isolated-pos-20261029T160830Z`: both real Guest joint Oracle PASS, real Chrome one-row screenshot, saved/reopened files and reset. Earlier browser-cache/address-focus control failures remain in their own run IDs.
- Case 6 v1.0.0 scripted Shared `sh-lite-v1-scripted-shared-pos-20261029T144119Z` and Isolated `sh-lite-v1-scripted-isolated-pos-20261029T150001Z`: both real Guest joint Oracle PASS, actual Calc save/reopen, peer revision/message/read-only open and reset.
- Case 7 v1.0.0 scripted Shared `wa-lite-v1-scripted-shared-pos-20261029T152010Z` and Isolated `wa-lite-v1-scripted-isolated-pos-20261029T153200Z`: both real Guest joint Oracle PASS, File Manager move, Writer save/reopen, peer revision/message/read-only open and reset. The v1.0.1 lifecycle controls have separate new run IDs.
- Case 7 v1.0.1 scripted Shared `wa-lite-v1p1-scripted-shared-pos-20261029T171130Z`: real Guest joint Oracle PASS, GUI move and Writer save, reopen and one-Guest reset PASS. The matching Isolated control is recorded separately.
- Case 7 v1.0.1 scripted Isolated `wa-lite-v1p1-scripted-isolated-pos-20261029T171145Z`: full run PASS, including A/B/joint Oracle, real File Manager move, revision transfer, Writer save/reopen and two-Guest reset.

## Completed model evidence before the Case 7 lifecycle patch

| Case / run ID | Condition | A / B / joint artifact Oracle | Run status and causal finding |
|---|---|---|---|
| Case 6 `sh-lite-v1-model-pilot-shared-20261029T151330Z` | Shared pilot, 8 steps | FAIL / blocked / FAIL | A did not finish saving before the diagnostic step limit; B's peer wait expired. No claim of task completion. |
| Case 6 `sh-lite-v1-model-full-shared-20261029T154540Z` | Shared | PASS / PASS / PASS | The first full model pair produced correct saved files and independent Oracle success. Postscore GUI reopen raised `INVALID_INFRA_OR_RUNNER_ERROR` because the model had closed A's Calc window; therefore this is **not a complete formal run PASS**. Preserve the successful artifacts and the infra failure together. |
| Case 6 `sh-lite-v1-model-full-shared-20261029T161300Z` | Shared | FAIL / FAIL / FAIL | A saved in the wrong Calc window after natural focus changes; B's cost was correct but quantity wrong. A later postscore reopen modal caused a separate infra failure. Do not discard this episode or select the first one alone. |
| Case 6 `sh-lite-v1-model-full-isolated-20261029T163535Z` | Isolated | PASS / FAIL / FAIL | Valid result, two-Guest reset/reopen and bridge checks passed. B read A's delivered workbook but entered 8 cases in the `Order units` cell, where 80 units were required; cost 2240 was right. This is a model interpretation error, not a bridge failure. |
| Case 7 `wa-lite-v1-model-pilot-isolated-20261029T155235Z` | Isolated pilot, 8 steps | FAIL / blocked / FAIL | A hit the diagnostic limit before the move. |
| Case 7 `wa-lite-v1-model-full-shared-20261029T161035Z` | Shared | FAIL / FAIL / FAIL | Valid result. B closed A's File Manager with Alt+F4 while A was typing its target path; A's later text entered B's Writer. Both tried to recover, but A hit 25 steps before pasting. B also read the input note before A delivered it, so no valid handoff occurred. |
| Case 7 `wa-lite-v1-model-full-isolated-20261029T163550Z` | Isolated | PASS / FAIL / FAIL | Valid result with two-Guest reset/reopen. A moved the file and the bridge copied revision 1 into B's Guest. B yielded after 288 s, was woken about 831 s later when A's revision and message appeared, but had only about 81 s of its original wall-time allowance left and timed out after two more GUI calls. No sync error was observed. |
| Case 3 `bv-lite-v1p4-model-pilot-isolated-20261029T162800Z` | Isolated pilot, 12 steps | FAIL / blocked / FAIL | A found the editor target but reached the diagnostic step limit before the repair/save; B had no delivered revision to test. Two-Guest reset passed. |
| Case 3 `bv-lite-v1p4-model-full-shared-20261029T164830Z` | Shared | FAIL / FAIL / FAIL | Both Actors reached 25 steps without a saved revision. Browser/editor focus repeatedly changed; B's URL text entered A's editor, and A's edit actions sometimes landed in Chrome. A postscore editor reopen also raised `INVALID_INFRA_OR_RUNNER_ERROR`, recorded separately from the already-failing Oracle. |
| Case 3 `bv-lite-v1p4-model-full-isolated-20261029T171430Z` | Isolated | PASS / FAIL / FAIL | A repaired the HTML in 11 desktop calls, published revision 1 and messaged B. B's own Chrome screenshot after handoff shows exactly one `OD-104` row for `North + Delivered`. B typed the correct QA note into Gedit but hit its 25-step limit before saving, so the artifact Oracle read the unchanged template. The frozen browser audit missed model screenshots; `browser_trace_reaudit.json` records the one-row observation retrospectively. Postscore attempted to close B's dirty editor, opened an unsaved-changes modal and raised a separate infra error. |

All model episodes above used `gpt-6-astra` through the same relay, identical role prompts and budgets within each version's Shared/Isolated pair, and separate Actors started concurrently. The strong model API key was provided to the coordinator process only, never the Actor or Git. The Case 7 v1.0.1 change introduces an explicit B yield/wake instruction and opt-in coordinator behavior in **both** topologies. It pauses B's active model budget while waiting for A's public saved revision/message, then resumes B's own conversation; it neither performs B's decision nor locks Shared GUI input. Both v1.0.0 runs and scores remain frozen.

The Case 3 model pair used v1.0.4. Its post-run visual extractor looked only at scripted 1920×1080 screenshots, while model screenshots are 1280×720 under each Actor's trace. Its reopen routine also treated a model's unsaved Gedit buffer as a broken application launch. The v1.0.5 adapter patch reads both screenshot sources and records dirty buffers without opening a modal. It has offline regression tests plus retrospective analysis of preserved v1.0.4 screenshots. The frozen v1.0.4 Oracle and failure files are not overwritten; Case 3's Isolated artifact failure is the unsaved QA note, not the browser filter.

## Measurement interpretation

The recorded metrics separate Guest setup, Actor execution, model HTTP time, token usage, screenshot/action latency, Guest QEMU process RSS/CPU sampling and active Actor overlap. A time interval where both Actors are alive is not proof of simultaneous GUI action or of focus interference. In particular, Isolated uses two QEMU Guests, so its setup time and aggregate RSS cannot be attributed to desktop isolation alone. For valid inference, inspect the timestamped GUI action/window changes and actual screenshot contents alongside the Oracle.

Some Case 3/6/7 episodes overlapped in **host** time while different run-owned Guests booted or reset. The Actor threads within each episode are truly concurrent, but host contention also affects wall-time comparison across episodes. Do not interpret raw Shared/Isolated elapsed differences as a causal desktop effect. No background run is used to select or discard a sample.

| Completed model episode | A/B desktop calls | A/B total tokens (upstream reported) | Actor execution overlap | GUI action overlap |
|---|---:|---:|---:|---:|
| Case 6 Shared, first full (postscore invalid) | 16 / 12 | 675,513 / 610,724 | 658 s | 0 s |
| Case 6 Shared, second full (postscore invalid) | 25 / 16 | 1,859,440 / 776,795 | 824 s | 2.3 s |
| Case 6 Isolated full | 13 / 18 | 366,703 / 892,870 | 466 s | 7.7 s |
| Case 7 v1.0.0 Shared full | 25 / 21 | 780,985 / 1,097,705 | 704 s | 9.2 s |
| Case 7 v1.0.0 Isolated full | 19 / 8 | 558,450 / 259,272 | 1200 s including 831 s suspended B wait | 0 s |
| Case 3 Shared full (postscore invalid) | 25 / 25 | 759,546 / 993,127 | 910 s | 7.6 s |

Tokens include screenshot-heavy context and may include cached input tokens; they are the relay's upstream usage figures, not a price estimate. The `model_metrics.json` in each run contains HTTP timing and screenshot/action timing separately. For Case 7 Isolated, use `actor_active_overlap_excluding_handoff_wait_s` (369 s) when comparing meaningful concurrent work; the 1200 s interval includes suspended B time.

Case 6 Isolated's model phase lasted 722 s, with 466 s Actor activity overlap and only 7.7 s GUI action overlap. A used 13 desktop calls and B 18; both files reopened and both peer files opened read-only. Case 7 v1.0.0 Isolated's model phase lasted 1201 s and the B handoff wait alone consumed about 831 s; B did wake on A's actual revision and message, but the old lifecycle counted the wait against B's model wall time. The new opt-in lifecycle pauses that active budget for v1.0.1 without changing its task artifacts or Oracle.

The separate run-labeled QEMU process sampler observed a 9.849 GiB peak summed RSS for the Case 6 Isolated pair and 9.241 GiB for the Case 7 Isolated pair. Case 3 Shared peaked at 4.904 GiB. These are sampled process RSS, not total host memory, and the CPU deltas exclude Guest boot before the first sample. Reproduce with `python audits/three_lite_cases_20261029/summarize_qemu.py runs/<run_id>`.

Raw runs remain locally under `runs/<run_id>/`, including actions, screenshots, model relay usage, public messages, file revisions, final files, Oracle and reset evidence. Run directories are intentionally not committed wholesale because they include large QEMU/GUI artifacts; the curated verdicts and run IDs in this report are commit-safe. Retain the raw run tree for independent inspection before any cleanup.
