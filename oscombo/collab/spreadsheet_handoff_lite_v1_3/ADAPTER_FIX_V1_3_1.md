# Case 6 v1.3.1 adapter correction

## Why this version exists

Two v1.3.0 scripted positive controls completed their Oracle and saved-file
lifecycle checks, but their B peer-view screenshots showed the GTK Open dialog
over the order workbook. The runner's window-title metadata named the peer
revision, so the old evidence gate accepted contradictory visual evidence.
Those runs are retained as Oracle/lifecycle checks only; they are not valid
handoff controls.

| Topology | Run ID | Oracle | Reopen/reset | Handoff classification | Runtime |
|---|---|---|---|---|---:|
| Shared | `case6-v13-shared-positive-20261106T174511Z-71885-28900` | A/B/joint PASS | PASS | Invalid: screenshot still showed Open dialog | 865.8 s |
| Isolated | `case6-v13-isolated-positive-20261106T180745Z-131305-26679` | A/B/joint PASS | PASS | Invalid: screenshot still showed Open dialog | 1334.6 s |

The isolated Oracle measured forecast need 73, 8 cartons, 80 units, and $2240.
The bridge delivered revision 1 and both saved files reopened byte-identically.
Those facts do not establish that B read A's forecast in the GUI.

## v1.3.1 changes

- B explicitly focuses GTK's location field with Ctrl+L before entering the
  immutable peer-view path.
- After the GUI action, the control waits for two consecutive active-window
  samples naming the exact read-only peer revision before capturing evidence.
- It retains three timestamped screenshot candidates. `B-peer-revision-open.png`
  points to the last candidate; a human must review its visible workbook
  contents before treating the control as handoff evidence.
- The handoff gate rejects a non-read-only title and screenshots without the
  expected 1920x1080 Guest geometry.

The task goal, role prompts, public Fixture, Gold, Oracle, model runner, and
budgets are unchanged from v1.3.0. The version bump isolates this scripted
adapter and evidence correction.

## Offline verification

Run from the checkout root:

```bash
PYTHONPATH=. pytest -q \
  tests/test_spreadsheet_handoff_lite_v1_3_adapter.py \
  tests/test_spreadsheet_handoff_lite_v1_3.py
```

Result on 2026-11-06: **26 passed**. This does not validate Guest startup,
Calc's GTK dialog behavior, visual handoff, reset, or any model execution.
The v1.3.1 positive/negative Shared and Isolated Guest controls remain
mandatory before a model Pilot.
