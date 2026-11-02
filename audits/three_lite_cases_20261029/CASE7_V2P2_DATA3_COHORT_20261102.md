# Case 7 v2.2: data3 reset cohort, 2026-11-02

## Scope and frozen configuration

This cohort reused source commit `c8856cb3d56011f5d159503dd335642a9abc52ee` and the original `freeze.json` byte for byte (SHA-256 `b351b85b0345078cdaa940b52ebb64079b7bd97977d20a22e9cd03151a4d4bdc`). Runs and the independent worktree were moved to `/data3`; earlier `/data2` evidence was read only. The frozen model was `gpt-6-astra`, with 25 desktop calls and 1200 active seconds per role. The registered order was Isolated, Shared, Shared+Lock, one attempt per arm, stopping on infrastructure invalidity. No task, Prompt, Fixture, Oracle, model, budget, or action lock behavior changed during these runs.

The preparatory real GUI Isolated scripted reset smoke `wa-lite-v2p2-data3-reset-smoke-isolated-20261102a` passed: A's saved note reached B's read-only peer view, B opened and read it in the Guest GUI, the independent Oracle passed, saved files reopened with matching SHA-256, and both Guests reset cleanly. The smoke did not call a model.

| Slot | Run ID | Campaign status | Artifact Oracle A/B/joint | Interpretation |
| --- | --- | --- | --- | --- |
| 1 Isolated | `wa-lite-v2p2-isolated-round1-20261102T164744Z-1ef6199a` | `VALID_FAIL` | PASS / FAIL / FAIL | B used A's delivered code but entered `operations review` as Audience, where the draft required `operations`. |
| 2 Shared | `wa-lite-v2p2-shared-round1-20261102T171628Z-7592743a` | `INVALID_INFRA` | FAIL / FAIL / FAIL | Real shared-desktop focus errors occurred, but an HTTP 403 response also broke the strict model transport contract. Exclude this arm from valid outcome comparison. |
| 3 Shared+Lock | Not started | `NOT_STARTED` | — | Stopped after slot 2's infrastructure invalidity, as registered. No lock efficacy claim is possible from this cohort. |

All run IDs and original files were retained. The earlier v2.2 run set, including an Isolated valid pass, a Shared valid fail, and a Shared+Lock transport-invalid run, remains separate. No sample was replaced or selected for its score.

## Slot 1: valid Isolated failure

Both independent Ubuntu Guests became ready; the two model Actors started together. A completed after 7 desktop calls and published revision 1. B completed after 15 desktop calls. B saved initial work, suspended without spending model tokens while awaiting A, and woke 69.3 seconds later on A's message and published revision. The read-only revision was verified in B's Guest by bridge SHA/mode evidence and screenshot `actor_runs/B/B/shots/011.png`, which visibly shows the revision title and note body. B then entered the correct inspection code into Writer. Its Audience field read `operations review`, so the separate `audience_matches_draft` Oracle check failed. That is a model interpretation/editing error, not a workspace bridge failure.

The bridge and independent request/tool contract passed; all 34 model relay requests ended `response.completed`. Both saved outputs reopened with matching SHA-256. Both Guest resets produced clean workspaces, and the resource audit passed. Setup was 840.0 s, Actor phase 489.4 s, post-Actor 359.1 s, total 1688.4 s. Effective A/B active overlap was 98.7 s; B's suspended wait was 69.3 s. A used 87,957 tokens (87,488 input, 469 output); B used 276,503 (275,626 input, 877 output). Two Guests peaked at 10.09 GB sampled aggregate QEMU RSS. These timings include slow TCG Guest startup and reset.

## Slot 2: Shared focus evidence and transport invalidity

A and B operated concurrently on one real Ubuntu desktop without a GUI input lock. The screenshots and recorded actions show two distinct input misroutes:

1. A attempted Files navigation, but its `Ctrl+A` selected the full text of B's Writer report (`actor_runs/A/A/shots/007.png`). A later recovered the Files window.
2. B's `operations review` text, intended for the Writer Audience line, appeared in the Files search field A had brought forward (`actor_runs/B/B/shots/012.png`).

A reached its 25-call budget with the original note still in `incoming`; it had not published a delivery revision. B requested the handoff, suspended after 15 calls, and was marked `blocked_on_peer` five seconds after A ended at `max_steps`. The artifact Oracle found no A delivery or B code, and B's saved report did not pass the Audience check. The observed focus errors are real, but the final failure cannot be attributed solely to them: during B's run the upstream returned HTTP 403, the relay forwarded 131 bytes labeled SSE, and the terminal was `malformed`. The independent `contract_audit.json` therefore reports `valid=false`. A also encountered five earlier `SSLError` events during upstream connection; all were before headers, forwarded zero bytes, and were followed by completed responses. Their root cause and the 403's root cause are not established here.

The workspace sync and resource audits passed. B's saved file reopened with matching SHA-256; A's missing task output is recorded as a task failure rather than a falsely reopened file. The single Guest reset was clean. Setup was 471.9 s, Actor phase 797.7 s, post-Actor 197.9 s, total 1467.5 s. Effective A/B active overlap was 484.1 s, with 313.6 s of B suspended wait. Observed HTTP 200 usage sums to A 567,548 and B 209,019 tokens; these are incomplete cost figures because the malformed 403 has no valid usage record. Sampled QEMU peak RSS was 5.20 GB. GUI input interval overlap was 0.0 s; focus competition did not require simultaneous keystrokes because foreground window state persisted between calls.

## Evidence and stop decision

The local, unmodified raw run roots are `runs/<run_id>/` in the independent `/data3/whn/Project2/CoDesk-case7-v2p2-data3-20261102` worktree. Each contains real screenshots, per-Actor actions, message/revision events, saved artifacts, Oracle, reopen/reset evidence, relay events, and resource samples. `runs/wa-lite-v2p2-data3-cohort-20261102/campaign_state.json` records the exact sequence and campaign classifications. Raw model transcript bodies and credentials are not included in this report or pushed with it.

The current cohort cannot provide a valid three-condition comparison: slot 2 failed the frozen transport contract and slot 3 was deliberately not launched. The focus misroutes remain usable qualitative evidence, while the only valid new outcome is the Isolated task failure caused by B's Audience text. Any later continuation must keep these attempts and register a new cohort or an explicit infrastructure repair review before starting another Guest.
