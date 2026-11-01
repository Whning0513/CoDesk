# Case 6 v1.2 transport-gated candidate (2026-11-01)

This is a **new candidate source cohort**, not a continuation of the
`00ef3ddfe836c856d831e98914451e14aa7e85ab` model cohort. The original
four controls, Pilot and first triplet remain unchanged in their own run
directories. In that triplet, Isolated reached joint Oracle PASS; Shared and
Shared+Lock had provider stream exceptions, so their scores cannot be used as
unqualified topology outcomes.

The independent worktree is `/data2/whn/CoDesk-case6-transport-integration`,
branch `experiment/case6-v1p2-transport-gate-20261101`. It starts from the
tested layout commit `00ef3dd`, then cherry-picks response terminal evidence
`76ef6a0` as `d8629e9` and the Case 6 fail-closed transport gate `7318a05`
as `11f8bfe`. The only cherry-pick conflict was in a test file; both the
painted Calc grid test and the relay event helper were retained. `e8f9344`
adds preflight checks for at least 15 GiB on both `/data2` and `/data3`, an
unambiguous Docker Guest query, exact run-owned container collision check,
and atomic driver log creation. An existing run directory or log causes a
new arm to stop before launch. The runner itself also creates its run root
with `exist_ok=False`.

No Task Card, role instruction, public Fixture, Gold or Oracle was changed by
this integration. The model adapter still uses `gpt-6-astra` medium, the
same GUI/collaboration tool boundary and wait lifecycle, 18 GUI calls and
900 active seconds per role for Pilot, and 25 calls and 1200 active seconds
for formal arms. The transport gate checks every recorded relay request for
HTTP 200, delivered bytes and `response.completed`; any partial SSE or
ambiguous terminal marks the new run infrastructure-invalid while preserving
its Oracle and original evidence.

## Offline and resource check

- `bash -n` passed for the common, scripted-control and model shell runners.
- Relevant offline tests: 77 passed, including malformed/partial relay,
  no-overwrite, private-key inheritance, and simulated low space on each disk.
- The source was clean when the real read-only `case6_preflight` returned 0.
  `/data2` had about 286 GiB free and `/data3` about 137 GiB; dedicated Docker
  was reachable and no `oscombo` Guest was active. No Guest was launched.
- The existing local provider credential file is current-user-owned, mode
  `0600`, and nonempty. The path/key is not copied into this report or an Actor.

## Next fixed validation sequence

1. Pin the final integration commit and allocate a Case 6 Guest window.
   Start a new, unique supervised controls cohort in the fixed order positive
   Shared, positive Isolated, wrong-units Shared, wrong-units Isolated. Stop on
   the first unexpected result; retain every run ID and manifest row.
2. Inspect both stale and delivered revision screenshots for each arm. Record
   exact screenshot hashes and real visible Calc values in the run-local
   review JSON, then run `verify_controls` with the **full new commit SHA**.
   The old `00ef3dd` controls do not satisfy a new-source gate.
3. Run one new Isolated concurrent Pilot with the fixed diagnostic budget.
   Review B's formula prework, revision opening, A's nonnumeric message,
   bridge revisions, saved artifacts, relay terminal audit, postscore reopen,
   reset and resources. A task FAIL is retained; transport invalidity is
   investigated before any replacement.
4. Freeze only after the new controls and Pilot are valid. Formal order stays
   Isolated → Shared → Shared+Lock, then the two preregistered reverse orders.
   Preserve all scores and invalid attempts; never select a run by outcome.

The four controls and model Pilot have **not** run on this new commit yet.
