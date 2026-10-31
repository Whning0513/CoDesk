# Case 5 dual Guest system screenshot control

Run `case5-dual-system-health-20261031T085432Z`, source `3ffe6aa`, supervisor exit 0, elapsed 1305.547 s. No model called.

- The same-number system GUI screenshots used distinct paths and guest identities. B SHA256 before and after A's screenshot: `6a9d9c3a1a2a04bd5cf7690c8949267891405b74a2a0f73629f60064b007d88e`. A SHA256: `1f5c23a3ccee0e640892268d4557bf7c35dd6c9d3505d9a9c5c31852349e437f`.
- Both Guests were reset into new run-labeled containers, their marker workspaces were clean, and reset screenshots were manually inspected as real Ubuntu desktops. All run-owned containers were removed; no QEMU processes remained.
- Peak observed combined QEMU RSS: 8.557 GiB. Before and after the control the inotify probe allocated only 2 of 64 watches before ENOSPC (limit 65536); this remains a risk, not an established cause of any daemon failure.
- Raw evidence and resource sampling are in `evidence/case5_dual_system_085432/`; full local run data is retained under `runs/case5-dual-system-health-20261031T085432Z`.
