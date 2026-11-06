# Case 6 v1.3.2 diagnostic Pilot entry

This runner-only addition provides the small Isolated model Pilot required by
the RO-base experiment protocol. It does not change the case version, role
prompts, public Fixture, Gold, Oracle, or formal three-arm budget.

## Budget and execution

- The Pilot is Isolated-only and defaults to 8 GUI tool steps per role.
- Its allowed diagnostic cap is 4–12 steps per role.
- It uses the same model, endpoint, medium effort, 1,200-second per-request
  timeout, retry policy, collaboration tools, GUI tools, workspace bridge,
  Fixture, and Oracle as the formal runner.
- Formal runs omit the Pilot option and retain the pinned 18 steps per role.
- The selected execution mode and effective role budget are included in the
  per-run model contract and provenance.
- A Pilot result is diagnostic; it does not count as a formal arm or justify
  changing only one formal condition.

The wrapper accepts a separate, empty run base for the Pilot:

```bash
CODESK_CASE6_V13_PILOT_RUN_BASE=/data2/whn/codesk-runs/case6-v13p1-pilot-UNIQUE \
  bash oscombo/collab/spreadsheet_handoff_lite_v1_3/run_model_triad_robase.sh pilot 8
```

Run the wrapper from the independent, clean `/data2` checkout with the normal
RO-base variables and owner-only credential configuration. It runs only the
Isolated arm, writes `pilot_manifest.tsv`, and exits without starting a formal
arm. Review tool-boundary, model transport, lifecycle, saved artifacts, and
Oracle evidence before creating a new empty formal run base and starting the
full `isolated → shared → sharedlock` triad.

## Offline validation

The Pilot's code path can be tested without a Guest or API request:

```bash
PYTHONPATH=. pytest -q tests/test_spreadsheet_handoff_lite_v1_3_model.py
bash -n oscombo/collab/spreadsheet_handoff_lite_v1_3/run_model_triad_robase.sh
```
