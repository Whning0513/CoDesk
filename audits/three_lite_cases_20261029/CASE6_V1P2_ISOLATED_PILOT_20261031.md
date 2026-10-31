# Case 6 v1.2: isolated two-Agent Pilot (2026-10-31)

The preregistered diagnostic Pilot `sh-lite-v1p2-pilot-isolated-20261031T125342Z-950992898955` produced **A PASS, B PASS, joint PASS** in the independent Oracle. It used source commit `00ef3ddfe836c856d831e98914451e14aa7e85ab`, the fixture validated by the four controls, `gpt-6-astra` at medium effort, and a budget of 18 GUI calls and 900 active seconds per role. This is one Pilot, not a success-rate estimate.

A completed the forecast and sent only a readiness notification. B first entered the general cost formula in F3, then received A's message and opened the delivered read-only revision in Calc. B's screenshot 010 visibly shows `forecast-r000001.ods` with H3 = 73; B subsequently saved its order. Oracle checks confirmed 80 units, cost 2240, correct formula and unchanged inputs. The chronology supports a real GUI handoff; it does not reveal the model's internal reasoning.

| Measure | A | B |
| --- | ---: | ---: |
| Active Actor elapsed | 104.010 s | 534.070 s |
| Desktop calls / GUI actions | 4 / 3 | 15 / 12 |
| Model requests (all HTTP 200) | 7 | 22 |
| Model request aggregate | 70.282 s | 377.757 s |
| Screenshot aggregate | 14.667 s | 67.276 s |
| GUI action aggregate | 8.916 s | 49.821 s |
| Provider total tokens | 41,542 | 254,533 |
| Input / output tokens | 41,038 / 504 | 253,228 / 1,305 |
| Cached input tokens | 23,869 | 163,945 |

Actor execution overlap was 104.009 s, model request overlap 56.066 s and GUI action overlap 1.260 s. B suspended and woke almost immediately because A's delivery was already available (rounded wait 0.000 s): this shows the ready/wake path, not reliable prolonged waiting. Setup until Actor start was 707.901 s, Actor phase 534.068 s, and total driver elapsed 1658.610 s including reopen/reset. Per-role time aggregates overlap and are not additive wall time.

The Actor-side tool audit recorded 7 A and 20 B total calls, with zero calls outside the GUI/collaboration contract. The independent pilot gate passed for same fixture/source/budget, both Actors' relay boundary, bridge diagnostics, complete resource sampling, both Guest reopen/reset, and manual screenshot review.

**Resource metric limitation:** `model_metrics.json` incorrectly reports zero QEMU processes, RSS and CPU for this run because it does not consume the versioned sampler format; those zeros are invalid. Direct `resource_samples.jsonl` analysis instead found two concurrent Guests, 9.941 GiB peak sampled summed QEMU RSS and minimum 17.06 GiB of disk free (18.32 decimal GB). The sum of per-process observed CPU counter deltas is 14,166.07 CPU-seconds, including Guest reset processes; sampling makes it a lower bound, not model-only CPU cost. The separate `resource_postprocess.py` reads the versioned samples without modifying the original run; the `model_metrics.json` QEMU fields remain invalid.

Raw evidence is retained locally under `/data3/whn/Project2/CoDesk-case6-ready/runs/sh-lite-v1p2-pilot-isolated-20261031T125342Z-950992898955/`: `oracle.json`, `result.json`, `model_metrics.json`, `actor_tool_boundary_audit.json`, `actor_lifecycle.jsonl`, `handoff_audit.json`, `pilot_visual_review.json`, `collaboration/events.jsonl`, `workspace_versions/events.jsonl`, `resource_samples.jsonl`, `resource_profile_check.json`, GUI logs, screenshots and saved files. Large run artifacts remain local and need a separate archive for independent review. This Pilot supports basic isolated solvability only; formal Shared, Isolated and Shared+Lock samples must be kept regardless of outcome.
