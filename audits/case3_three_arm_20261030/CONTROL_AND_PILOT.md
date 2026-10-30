# Case 3 v1.0.6 controls and bounded Pilot

All run IDs below are immutable directories under `runs/` in the Case 3 worktree. Scripted controls use real Ubuntu OSWorld Guests, screenshots, GUI input and independent scoring. They are not model success samples.

| Run ID | Purpose | Outcome | Lifecycle evidence |
| --- | --- | --- | --- |
| `bv-lite-v1p6-scripted-positive-shared-20261030T170338Z` | Shared positive | A/B/joint Oracle PASS | Both saved artifacts reopened with identical SHA-256; one Guest reset clean; no bridge errors. |
| `bv-lite-v1p6-scripted-positive-isolated-20261030T172023Z` | Isolated positive | A/B/joint Oracle PASS | A→B saved-file copy read back with identical SHA-256 in about 1.83 s, peer file mode 444; both artifacts reopened; two Guests reset clean. |
| `bv-lite-v1p6-scripted-negative-shared-20261030T174521Z` | First wrong-value negative | Oracle A/B/joint FAIL as expected; **invalid full control** | Both files reopened; postscore replacement QEMU stalled at about 575 MiB RSS and 384 KiB overlay for over 10 min. Only this run's container was terminated. `abort.json` records `INVALID_INFRA_OR_RUNNER_ERROR`. |
| `bv-lite-v1p6-scripted-negative-shared-retry-20261030T181145Z` | Wrong-value negative retry | Oracle A/B/joint FAIL as expected; valid negative | A/B saved bytes reopened identically; replacement Guest reset `workspace_clean=true`; `postscore_lifecycle_ok=true`. |
| `bv-lite-v1p6-shared-lock-mcp-smoke-20261030T183057Z` | First lock smoke | **Invalid test script** | Two MCP processes shared a desktop call counter directory, so input was rejected at the synthetic budget. Real screenshots obtained; run-owned Guest cleaned. |
| `bv-lite-v1p6-shared-lock-mcp-smoke-retry-20261030T183700Z` | Real Shared action-lock smoke | PASS | Two independent MCP stdio processes each captured a PNG and executed `move` against one Guest. Both logs show `input_lock.enabled=true`, same run-owned lock path, input overlap 0 s; A waited 8.4938 s for B. Guest reset clean. |

## Small concurrent model Pilot

`bv-lite-v1p6-pilot-isolated-20261030T184542Z` used `gpt-6-astra` medium, v1.0.6 prompts and fixture, 8 desktop calls per role, 360 seconds active model time, `--yield-wait-lifecycle` and request-level `--actor-mcp-only`. Both Actors began about 0.002 s apart. A used 8 calls and stopped in a GUI replace dialog before saving. B sent A a handoff request after its first screenshot, suspended without further model/GUI calls, and became `blocked_on_peer` five seconds after A ended without a revision or message. The Pilot diagnoses a bounded execution chain; it is not a full-budget solvability sample.

The Pilot's Oracle A/B/joint FAIL follows from the 8-call diagnostic limit. Its result is a valid scored task failure: `postscore_lifecycle_ok=true`, both GUI reopen checks `same_bytes=true`, two run-owned resets `workspace_clean=true`, no workspace sync errors. All 14 provider requests returned HTTP 200 and logged `actor_mcp_only=true`; the relay removed extra built-in tools including `apply_patch`, `get_goal` and `view_image`. A scan of run files found no provider key bytes.

Usage was 93,815 input and 1,388 output tokens. Total wall time was 1,344.8 s, including 636.3 s before Actor start and later GUI reopen/reset. Sampled peak two-Guest QEMU RSS was 9.243 GiB and sampled QEMU CPU delta 5,677 s. Model HTTP intervals overlapped for 16.486 s. `model_metrics.json` reports 40.017 s of effective Actor overlap after excluding B's voluntary suspension. The generic `actor_execution_overlap_s=344.027` is wall-clock overlap containing B's wait and must not be interpreted as active overlap. GUI input actions did not overlap in this Isolated Pilot.

## Full-budget Isolated feasibility (diagnostic, outside formal triads)

`bv-lite-v1p6-feasibility-isolated-20261030T190848Z` used the same model, role prompts, fixture and Oracle with 25 desktop calls per role and 1,200 active seconds. It is a complete, valid task FAIL: Oracle A/B/joint false, GUI reopen complete with unchanged saved bytes, `postscore_lifecycle_ok=true`, both run-owned Guests reset clean, no workspace sync error, all 16 provider requests HTTP 200 with the request-level Actor allowlist, and no provider key bytes in run files.

A voluntarily ended after 11 desktop calls. Its Gedit trajectory searched for correctly spelled `delivered`, pressed Escape, then Ctrl+S, but did not replace the option value typo `delievered`; the saved file stayed at bridge revision 0. A sent B a message claiming “published revision 0.” B had requested the handoff and suspended after 2 calls. The public message arrived but the required saved revision did not, so the common lifecycle correctly kept B suspended and then marked `blocked_on_peer` five seconds after A ended. This is A's mistaken claim of completion and missing artifact change, not an early coordinator termination of B or a workspace bridge transfer fault.

Actor active overlap excluding B's suspension was 62.012 s; their wall-clock phase overlap including that wait was 292.024 s. Model HTTP intervals overlapped for 7.901 s. A used 109,794 total tokens and B 23,274. Total wall time was 1,269.1 s, including 636.3 s of setup before Actor start and later GUI reopen/reset. The diagnostic outcome does not change the frozen v1.0.6 task or select formal samples by score.

The first formal triad follows the preregistered Isolated → Shared → Shared+Lock order. All attempts remain in the audit, regardless of score.
