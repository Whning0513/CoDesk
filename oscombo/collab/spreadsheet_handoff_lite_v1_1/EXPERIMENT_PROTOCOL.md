# Case 6 Lite v1.1 three-arm protocol

Freeze this protocol before the first full model triad. Earlier v1.0.0 episodes remain a separate cohort. Do not choose repeats by whether a previous arm passed.

## Validation gate

1. Run offline Gold/Oracle positive and wrong-value controls, including the exact `8` units / `$224` case-count mistake.
2. Run real Guest scripted positive Shared and Isolated with GUI save, version transfer, message, file collection, GUI reopen and reset. Run the v1.1 scripted negative Shared: A correct, B writes a case count into E3, independent Oracle A true/B false/joint false, reopen and reset complete. Any Guest startup/reopen error is infrastructure-invalid and must keep its run ID.
3. Run a bounded Isolated strong-model Pilot at 12 desktop calls per Actor and 600 seconds of active role time to check GUI, tool allowlist, public handoff and B's basic solvability. Do not score this diagnostic as a full sample. If the task design changes, make a new version and repeat both topology controls.

## Frozen full runs

Use `gpt-6-astra`, medium effort, 25 GUI calls per role, 1200 seconds active role time, request-level `--actor-mcp-only`, public `--handoff-lifecycle`, the same v1.1 Fixture, role prompts, workspace bridge, independent Oracle and postscore recovery. The Actor API key stays in the coordinator process only. Each run has a unique run ID. Actor threads start concurrently.

- **Isolated:** two Guests, no cross-Guest GUI input lock, A's full saved revisions/messages delivered to B.
- **Shared:** one Guest, two Actors, no GUI input lock.
- **Shared+Lock:** same one-Guest Shared setup, only `--gui-input-lock` added. The simple mutex serializes one GUI input tool call at a time; screenshots and reasoning remain outside the mutex. It does not perform collaboration decisions or hide focus changes.

Collect two complete triads if resources allow. Order triad 1 as Isolated → Shared → Shared+Lock; order triad 2 as Shared+Lock → Shared → Isolated, preserving all valid outcomes and invalid infrastructure attempts. If a triad cannot be completed, report the available episodes without a causal superiority claim. Do not change model/Prompt/Fixture/Oracle/budget between arms or run more on the apparently weaker arm to chase success.

## Report evidence

For every episode report A/B/joint Oracle, saved-file hashes and revisions, actual A-message/B-read order, GUI edit/save chronology, request-level tool filtering, screenshots and actions, focus or input misrouting, lock wait/acquire/hold time, Actor active overlap, GUI action overlap, model tokens/HTTP time, setup/Actor/full wall time, sampled QEMU CPU/RSS and complete reopen/reset. A correct artifact alone does not prove B used A's handoff; a model task failure is separate from bridge, startup and postscore errors. Shared+Lock may improve correctness while reducing parallel action time; quantify both. No input-lock benefit or harm is inferred from a single anecdote.
