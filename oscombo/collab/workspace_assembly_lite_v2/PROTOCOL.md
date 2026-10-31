# Case 7 Lite v2 candidate preregistration

Status: **candidate; configuration not yet frozen; no v2 Guest/model outcome**.
Case 6 has priority for the shared host. Start no Guest until the coordinator
releases the resource window, the dedicated Docker daemon is healthy, there are
no other run-owned Guests, available disk is at least 15 GiB and the inotify
probe records adequate headroom. Assign a unique run ID for every attempt.

## Common configuration

Use `gpt-6-astra` at medium reasoning, identical v2 public fixtures, role
instructions, GUI and collaboration tools, Actor request-level allowlist,
saved-output bridge, evaluation, 25 desktop calls per role and 1200 active
model seconds per role. B's handoff suspension excludes waiting from active
budget. No Gold or Oracle is exposed to Actors. Shared is one Guest and one
unlocked desktop; Isolated is two Guests; Shared+Lock is one Guest with the
existing run-scoped lock around each individual GUI input, screenshots and model
reasoning outside the lock. All arms use **8 vCPU and 8 GiB RAM per Guest**;
record both the environment request and actual QEMU command line. Do not
change focus, lock or task semantics for a particular condition.

## Gates and fixed sequence

1. Real Shared and Isolated GUI scripted positives, then wrong-tag GUI negatives
   in both topologies. Each verifies B's saved prework before A's first
   delivered revision, A move, revision metadata and notification with no tag,
   B's own GUI open of the revision-specific peer view, 0444 mode, SHA and GUI
   screenshot, saved B report, host Oracle, byte-for-byte reopen and exact
   run-owned reset. Negative controls must reject wrong tag. Preserve every
   invalid startup/adapter attempt and diagnose before resuming.
2. In each topology, run an additional **scripted positive revision probe**:
   A moves the note, edits and saves a different revision through the GUI, then
   restores and saves the original through GUI. Confirm all resulting old/new
   view files persist with their own correct SHA and 0444 mode, A's original is
   writable, the final original bytes and Oracle pass, B GUI reads the final
   view, and reopen/reset complete. These extra diagnostic actions are outside
   the 14-input task critical path and never run for model Actors.
3. One Isolated concurrent model Pilot, 12 desktop calls and 600 active seconds
   per role. Inspect actual tool use, timestamps, GUI and peer view, raw messages,
   sync history, Oracle, reopen and reset. Keep an ordinary task failure; repair
   a proven environment defect symmetrically and rerun the affected control.
4. Freeze one commit and one model/role/Oracle/budget configuration, and three
   deterministic, distinct public fixture seeds before formal execution. I/S/L
   in each round use the same seed and fixture hashes; controls and Pilot use
   separate fixed seeds. The seed and manifest stay on the coordinator side,
   while the Actor-visible note is the only task source for its inspection tag.
   Execute **I→S→L, L→S→I, I→L→S** (L=Shared+Lock), one run per slot.
   Retain all valid PASS and FAIL runs and do not select or rerun by score.
   Stop on infra-invalid, preserve its full evidence, repair symmetrically and
   resume the affected slot only after required controls. Any task/scoring or
   fairness change requires a distinct version and fresh controls. Three samples
   per arm describe these runs only; they do not establish stable success rates.

## Evidence and analysis

Save per-step screenshots, action/window timing, raw messages, immutable revision
views and transfer hashes, independent artifact Oracle, scorer-side behavioral
audit, reopens and resets. Report A/B/joint artifact outcome separately from
whether B's prework occurred before A's first delivered revision, A's message
contained the tag, and B actually opened/read the correct view after delivery.
The automatic audit marks candidates and always requires screenshot review;
neither message, a revision string, nor correct final text proves GUI reading.
Do not filter or rewrite Actor messages; report deviations as observed.

Record setup/Actor/postscore time separately, token/request counts, B suspended
wait and actual active overlap, GUI input overlap, lock wait/hold, QEMU CPU and
RSS, host memory/swap, filesystem free space and I/O pressure. A Shared focus
claim requires time-aligned action/window/screenshot evidence. Isolated uses
more Guests and potentially more CPU/RSS; do not attribute all cost differences
to desktop isolation. If any persisted bridge transfer/view/ownership fault or
unresolved validation retry occurred, mark the episode infrastructure review
required even if a later final sync succeeds. A same-user 0444 view is an
accidental-write guard, not role-level isolation; Shared's writable A source
remains visible under the common Ubuntu user.
