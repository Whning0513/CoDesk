# Case 7 Lite v1.0.2: proposed three-arm protocol

Status: **not yet frozen**. Real Guest v1.0.2 scripted controls and a bounded Isolated model Pilot are required first. This protocol does not change or rescore the v1.0.1 cohort.

## Task and fair comparison

The public attachment, Writer draft, Gold and Oracle retain v1.0.1 semantics. v1.0.2 changes A's workflow to move the note before reading the delivered file and maximizes the initial Files window in both topologies. B keeps the same wait/yield/wake instruction and is now explicitly told to open the delivered file through GUI before editing Writer; a message alone is not verification. The intended scripted critical path remains about 10–15 GUI actions across A and B; no hard model step cap follows from that design target.

All formal arms use `gpt-6-astra`, identical v1.0.2 role prompts, public fixture, 25 desktop calls per role, 1200 seconds of active model budget, request-level desktop/collaboration tool allowlist, the same file bridge and independent Oracle. Each run starts two independent model Actors concurrently. Shared uses one Guest with no lock. Isolated uses two Guests. Shared+Lock uses one Guest with the same prompts and a cross-process `flock` around each actual mouse/keyboard input call. Screenshots and model reasoning remain outside that simple lock, so it does not guarantee an atomic observe–act transaction. No arm may get a condition-specific instruction or evaluator data.

The lock arm uses `--condition collaborative_shared --gui-input-lock`; its arm identity is also recorded in run metadata and each desktop tool action's `input_lock` timing. No input lock is enabled in the other two arms.

## Validation sequence

1. Real Guest scripted positive in Shared and Isolated, then a wrong-value/file negative. Check GUI screenshots, A's post-move opening of the delivered note, B's GUI read, saved revisions, peer read-back SHA and read-only mode, Oracle, file reopen and exact run-owned reset. An infrastructure error is recorded separately and does not count as a task failure.
2. One bounded Isolated model Pilot (`12` desktop calls, `600` seconds) to check A/B basic solvability, real handoff and tool/recording stability. Retain the Pilot whatever its outcome.
3. Freeze the above configuration before full runs. Propose two complete triplets in balanced order: triplet 1 Isolated, Shared, Shared+Lock; triplet 2 Shared+Lock, Shared, Isolated. The parent Agent may reduce concurrency for disk/Guest responsiveness, but not change a single arm's task or budget. Keep all launched episodes; replace only independently documented infrastructure-invalid attempts with a new run_id.

## Analysis contract

Report A, B and joint artifact Oracle separately from behavioral handoff validity. Verify that A moved and published the actual note, B viewed the delivered revision after publication and used its tag, and the bridge transferred the right bytes. For Shared focus interference, pair timestamped input actions with foreground-window changes and screenshots; a failed Oracle alone is insufficient. For the lock arm, count acquisition waits, total wait time, held time, input overlap, model-request overlap, Actor active overlap excluding B's suspended wait, tokens, setup/execution/reopen/reset time and QEMU resources. Compare success and cost descriptively; two triplets cannot establish a stable causal effect.
