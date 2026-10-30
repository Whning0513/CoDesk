# Four-case three-arm study: live status

Date: 2026-10-30 UTC. Coordinator branch: `experiment/codesk-whitelist-case7-case5-20261030`. This document tracks the new cohort only; prior episodes remain frozen under their original run IDs. Case priority is 3 > 6 > 7 > 5. The platform permits three active child agents alongside the coordinator, so the four case owners rotate slots while keeping independent worktrees and branches.

## Common protocol

Each case must first pass real Guest scripted positive and wrong-value negative controls, then a bounded model feasibility Pilot, before a frozen `Isolated / Shared / Shared+simple input lock` comparison. All arms use the same model, prompts, fixtures, Oracle, call and time budgets and request-level tool whitelist. Shared and Shared+Lock use one Guest; Isolated uses two. The lock arm changes only GUI input scheduling: host-side `fcntl.flock` serializes each click/drag/move/type/key/scroll action across the two Shared Actor MCP processes. Screenshots and model reasoning are outside the lock, so the arm does not guarantee an atomic observation-to-action sequence. Every action records lock wait and hold time. No lock is enabled in the Shared baseline.

The relay filters built-in Codex tools at the request boundary. Earlier clean whitelist model runs have zero out-of-contract Actor tool calls. Each new model run must still audit its own forwarded requests and rollout. Oracle artifact success, behavioral handoff evidence, GUI lifecycle and bridge health are separate fields; invalid infrastructure episodes remain in the record and are not scored as model failures.

## Case status

| Case | Version and worktree | Real Guest controls | New model three-arm cohort |
|---|---|---|---|
| 3 Build-and-Verify | v1.0.6; `CoDesk-case3` | Shared positive `bv-lite-v1p6-scripted-positive-shared-20261030T170338Z` and Isolated positive `bv-lite-v1p6-scripted-positive-isolated-20261030T172023Z` both fully PASS: A/B/joint Oracle, browser one-row check, exact-byte GUI reopen and clean resets. Isolated A→B transfer matched SHA in 1.83 s. Wrong-value negative pending. | Not started. |
| 6 Spreadsheet Handoff | v1.1; `CoDesk-case6` | Shared positive `sh-lite-v1p1-scripted-positive-shared-20261030T172722Z` fully PASS: A/B/joint/protection Oracle true, A/B GUI reopen exact bytes, one-Guest reset clean. Shared wrong-units negative `sh-lite-v1p1-scripted-wrong-units-shared-20261030T174114Z` in progress. Public unit labels and B prompt revised symmetrically; old v1 model episodes are not reclassified. | Not started. |
| 7 Workspace Assembly | v1.0.2; `CoDesk-case7` | New version has offline controls only. Old Pair 1 Isolated artifact PASS did not include B opening the delivered note in GUI, per separate re-audit. | Not started. |
| 5 Model-and-Review | Lite v1; `CoDesk-case5` | Clean Shared positive PASS; Shared wrong-width negative correctly rejected. One Isolated startup timeout was infrastructure invalid. A second Isolated attempt had artifact Oracle PASS and verified transfer but B's GUI showed stale initial width; the scripted reload is under repair and needs a new Guest control. | Not started. |

The current host has no KVM, so TCG Guest boot is expensive. At the latest sample, the experiment filesystem has about 29 GB free; 152 logical CPUs and ~1 TiB RAM are available, and I/O pressure is low. Guest starts are scheduled by priority and monitored against a 15 GB free-space stop threshold. One Case 5 dual-Guest run timed out on its second VM and was preserved as infrastructure invalid, then its retry booted both Guests. The timeout does not count as a topology score.

Case 1's previous clean whitelist pair and the Case 6/7 historical cohorts remain in their own reports; this study does not rewrite their verdicts. No controlled Shared input-lock result exists yet.

The common file-case runner now maps PASS to exit 0, task FAIL to exit 2, and infrastructure-invalid or unexpected status to exit 3. The corresponding data-to-deck runner mapping is under review. This distinction prevents a later three-arm script from treating a postscore reset fault as a model task failure.
