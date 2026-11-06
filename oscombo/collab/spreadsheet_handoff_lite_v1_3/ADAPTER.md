# Lite v1.3 scripted Guest adapter

`live_pilot.py` provides an explicit positive/negative scripted-control entry
for this version only. It reuses `lite_file_guest_pilot` Guest helpers,
`SavedArtifactBridge`, the run provenance utilities, Calc launch, and the v1.3
Fixture and Oracle. It remains scripted-only.

The adapter verifies the delivered A revision bytes, B's received ready
message, the exact immutable peer-view path in B's GUI action trace, the active
Calc window and screenshot, and the publish/message/read/edit/save ordering.
The revision number or SHA by itself cannot pass the handoff gate. The
positive control follows a correct forecast. The negative control saves a
wrong forecast formula and makes a coherent order from that delivered value;
the Oracle should reject the joint result.

Example invocation (starts real Guest(s); not run as part of the offline
implementation review):

```bash
PYTHONPATH=. python -m oscombo.collab.spreadsheet_handoff_lite_v1_3.live_pilot \
  --case-version 1.3.0 \
  --condition collaborative_isolated \
  --control positive \
  --run-root runs/sh13-unique-run-id \
  --provider /path/to/OSWorld \
  --image /path/to/pinned-guest-image.qcow2 \
  --runtime oscombo-runtime:tag
```

Use a fresh, unique, non-existing `--run-root` for every invocation. This
entry point performs a scripted sequence, not a concurrent-model episode; its
`Shared` and `Isolated` runs are setup/synchronization/reopen smoke controls.
Do not report a PASS as Guest-validated until the command actually completes
with real screenshots, saved artifacts, Oracle evidence, and reset evidence.

Offline coverage:

```bash
PYTHONPATH=. pytest -q \
  tests/test_spreadsheet_handoff_lite_v1_3_adapter.py \
  tests/test_spreadsheet_handoff_lite_v1_3.py
```

These tests inspect version routing, the scripted action plan, result mapping,
and handoff evidence requirements only. They do not start a Guest or call an
API, and they do not validate this adapter's real-Guest execution path.

## Concurrent model triad entry

`model_pilot.py` adds a separate v1.3 model episode entry. It reuses the existing
Codex model actor, loopback Responses relay, collaboration service, SavedArtifactBridge,
and run-owned Guest lifecycle. `--arm` accepts `isolated`, `shared`, or
`sharedlock`; only `sharedlock` passes a per-action lock path to the existing
model actor. The actor request relay is hard-coded to `actor_mcp_only=True` and
the runner audits every recorded response stream and Actor tool call before
classifying a scored result. Task, prompts, fixture, Gold, Oracle and old run
records are unchanged.

The experiment protocol and three-arm shell driver are in
`EXPERIMENT_PROTOCOL.md` and `run_model_triad.sh`. This adapter has offline
contract and lifecycle coverage only; it is **not** Guest- or model-validated.
Do not invoke it until a frozen commit, a coordinator-assigned Guest slot, an
authorized `/data2` Docker runtime, enough free disk, and a configured model
credential environment variable are available.
