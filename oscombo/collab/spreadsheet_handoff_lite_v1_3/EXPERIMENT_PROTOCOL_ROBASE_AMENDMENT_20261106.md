# Spreadsheet Handoff Lite v1.3 resource-policy amendment (draft)

Status: offline-only amendment candidate. It does not replace the original v1.3
protocol or change the Task Card, A/B prompts, Fixture, Gold, Oracle, tool
allowlist, model budget, or three-arm comparison.

## Entry point and freeze

Use `run_model_triad_robase.sh` from the independent Case 6 clone. The source
checkout must be clean and frozen at the commit reviewed for this amendment;
the original `run_model_triad.sh` remains available for the original policy.
The run base must be fresh and on `/data2`. This amendment does not authorize
starting a Guest or contacting a model endpoint.

The frozen manifest must record the exact Guest image SHA-256. Supply that
digest in `CODESK_CASE6_V13_GUEST_IMAGE_SHA256`; the runner hashes the selected
file and fails closed unless it matches. The digest is public provenance, not
a credential.

## Resource policy

Retain the 15 GiB free-space and 1024-inode reserve for each writable path:
the run base, the selected Docker data-root, and Git common storage. They must
resolve under `/data2`. The Guest image remains at its pinned path and must be
readable; its filesystem is exempt from the writable-capacity threshold only.

The common Guest boot path must verify that Docker mounted that exact image at
`/System.qcow2` with `RW=false`; the QEMU overlay must be run-owned. DesktopEnv
cache, screenshots, collaboration/relay logs, and final artifacts stay under
the run root. The shell runner records the image device/inode/size/mtime/ctime
before the triad and checks the same metadata on every exit. Python bytecode
writing remains disabled for external OSWorld imports.

## Comparison conditions and validity

The arms remain Isolated, Shared, and Shared+PerActionLock in the same order
and use the same model, role prompts, public Fixture, task budget, allowlisted
tools, workspace bridge, and Oracle. Only the Guest topology and existing
per-action lock differ. All forwarded model requests must retain the
request-level `actor_mcp_only=True` filter.

An actual cohort still requires shared/isolated scripted GUI positive and
negative controls, review of save/reopen/reset and mount/overlay evidence, and
a small model pilot before the complete triad. Preserve every failed or
invalid attempt; do not select a favorable arm or retry only a failed
condition. Old v1.3 runs and the old capacity-gate protocol remain unchanged.

## Current verification

The shell syntax and offline unit tests validate the gate and evidence checks.
There is no Guest positive/negative control, model Pilot, or formal arm under
this amendment yet. A clean freeze and live controls must be produced after an
authorized Guest window and the dedicated `/data2` Docker data-root are
available.
