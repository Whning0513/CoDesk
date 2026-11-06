# Case 6 v1.3 read-only base capacity amendment (draft)

Status: offline draft only. The original `run_model_triad.sh` and v1.3
protocol remain unchanged. A separate `run_model_triad_robase.sh` candidate
implements this resource policy; it has not started a Guest or model run.

## Rationale

The current triad script applies the same free-space threshold to the run base,
Docker data-root, Git common directory, and the Guest image's filesystem. The
first three are writable during the experiment and must keep the existing
15 GiB / 1024 inode reserve. The qcow2 base is intended to be mounted at
`/System.qcow2` as read-only; QEMU writes through a per-run overlay. Requiring
15 GiB free on the base-image filesystem is therefore not a write-capacity
check for the experiment's outputs.

## Proposed amended gate

1. Preserve the existing capacity and `/data2` placement gates for run output,
   Docker data-root, and Git common storage.
2. For the Guest base, require an absolute, regular, readable file and an
   expected SHA-256 recorded in the frozen run manifest. Do not apply the
   writable-filesystem free-space check to that file's device.
3. After each Guest starts, require Docker mount evidence with source equal to
   the resolved frozen image path, destination `/System.qcow2`, and `RW=false`.
4. Require that the QEMU overlay and DesktopEnv cache resolve under this run's
   `overlay/` and `cache/` directories. Keep all screenshots, relay logs,
   fixtures, actor traces, and results under the run root.
5. Record image metadata at the digest check and confirm the same device,
   inode, size, and mtime after the triad. The read-only mount is the primary
   protection against Guest writes; the metadata check detects ordinary host
   replacement/modification without rescanning a multi-gigabyte image.
6. Continue to set `PYTHONDONTWRITEBYTECODE=1` for the external OSWorld Python
   environment, and do not run provider patching during a trial.

## Offline implementation and controls

`run_model_triad_robase.sh` keeps the existing 15 GiB / 1024 inode checks on
the writable run, Docker, and Git paths. It requires a frozen image digest,
skips only the base image's free-space check, and checks that image metadata
did not change at process exit. The shared `model_pilot.py` still checks the
actual Docker base mount is read-only and the overlay is run-owned. The
cache_dir is already passed under the run root. `resource_gate_amendment.py`
contains equivalent pure helpers; `tests/test_case6_v13_resource_gate_amendment.py`
tests writable-space thresholds, missing paths, digest mismatch, wrong mount,
escaped overlay/cache, post-run image changes, and the new runner's gate.
Together with the existing v1.3 and relay tests, 69 offline tests pass. These
tests use tiny temporary files, not the OSWorld image. They do not prove that
every provider path is write-free in a live run; Guest mount evidence and
scripted GUI controls remain mandatory.

Do not apply this draft to Case 7's frozen v2.2 cohort or Case 5's separate
40 GiB safety policy. A future live cohort requires a new protocol amendment,
clean source freeze, pinned Guest image SHA, disk reserve recheck, assigned
Guest slot, scripted GUI positive/negative controls, then a small model pilot
before the full triad. Set `CODESK_CASE6_V13_GUEST_IMAGE_SHA256` to the frozen
digest; it is not a secret and must never be learned from an Actor.
