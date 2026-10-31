# Case 6 v1.2 runner and supervised control protocol

This is a candidate; no Guest or model result is implied by the existence of these scripts. The coordinator must first validate the dedicated Docker service and assign the resource window. The runner requires `CODESK_GUEST_WINDOW_ASSIGNED=case6-v1p2`, at least 15 GiB free, no active QEMU/OSWorld Guest, and a healthy Docker endpoint. It explicitly sets 8 vCPU and 8 GiB per Guest. A run-owned sampler records the requested profile, actual QEMU command lines, process CPU/RSS and host memory, swap, disk/I/O and pressure; incomplete samples or a mismatched profile make the wrapper return infrastructure-review status 3. The original runner result, sampler evidence and manifest remain separate and are not overwritten.

Run long jobs through the detached supervisor, using the OSWorld virtualenv Python and the case worktree as the current directory:

```bash
python -m oscombo.collab.spreadsheet_handoff_lite_v1_2.supervisor start controls
python -m oscombo.collab.spreadsheet_handoff_lite_v1_2.supervisor status <cohort-id>
python -m oscombo.collab.spreadsheet_handoff_lite_v1_2.supervisor stop <cohort-id>
```

`start` creates a unique cohort directory under `audits/three_lite_cases_20261029/case6-v1p2-supervisors/`, a detached session, supervisor log and identity (PID, process start ticks, boot ID, source commit and cohort). The worker records its runner identity, current run-owned driver identity and eventual exit code. `status` validates the boot ID and start ticks before calling a PID live; a missing/timeout response is not proof that it stopped.

`stop` only creates the cohort's cooperative stop request. If an arm is active, it runs to completion and normal finally/reset cleanup; no later arm starts. A SIGTERM sent **only to the supervisor PID** has the same drain behavior. Do not signal the supervisor's process group: the currently active model or Guest must not be interrupted while writing. If the worker or driver has crashed, inspect its recorded PID/start ticks/boot ID, run manifest, `ownership.json` and exact `oscombo.run` labels, then use the existing exact-ID cleanup path; do not globally kill QEMU or delete other work. The stop request is a request, not evidence that the active arm has finished.

The controls manifest has one positive and one wrong-units control in each topology. Each control records two real Calc screenshots: the old immutable revision and the newly delivered revision. Review them on the scoring side, then create `stale_view_visual_review.json` and `peer_view_visual_review.json` in each run root. Both records require the exact screenshot SHA-256, path, revision, reviewer and review time. The stale review sets `visible_H3_blank: true`; the latest review records numeric `visible_H3_value` and `visible_H3_matches_scored_A: true`. A manual visual check must actually verify those statements. Run:

```bash
python -m oscombo.collab.spreadsheet_handoff_lite_v1_2.verify_controls <controls-manifest.tsv>
```

The Pilot requires the verified controls manifest in `CODESK_CASE6_V12_CONTROLS_MANIFEST` and a private, current-user-owned credential file in `CODESK_CASE6_KEY_FILE`. The provider key is read by shell builtin into the coordinator/relay environment; the Actor and Guest do not inherit it. Start it through `supervisor start pilot`. Once the Pilot ends, review both the B prework formula screenshot and delivered-revision screenshot, plus all A messages; write `pilot_visual_review.json` with the filenames, SHA-256 values, revision/view path, observed H3, `visible_F3_cost_formula`, `visible_H3_matches_saved_revision`, `A_messages_disclose_no_result`, reviewer and time. Run `python -m oscombo.collab.spreadsheet_handoff_lite_v1_2.verify_pilot <pilot-run-root>`.

Only after both gates and review, freeze the exact commit in `CODESK_CASE6_V12_FROZEN_COMMIT`, supply the Pilot root in `CODESK_CASE6_V12_PILOT_RUN`, and start the preregistered `triad1`, `triad2`, `triad3` through the same supervisor. Preserve each manifest and each invalid attempt. No score-selected reruns are permitted.

The wrapper checks the prior manifest and refuses to restart a whole Pilot or round for the same source commit once any valid sample exists; a later round additionally requires complete prior rounds. For a partially completed round, there is no automatic resume: inspect the preserved manifest and coordinate a controlled run of only the unfinished or infrastructure-invalid arm after the external fault has recovered. If task, bridge or runner code changes, repeat the affected controls and Pilot and start a separately identified frozen cohort; do not label old and new commits as one complete paired round. A coordinator-only admission lock prevents two Case 6 v1.2 wrappers from launching concurrently; it does not lock GUI inputs.
