# Handoff audit and Calc locale gate (2026-11-07)

Status: read-only audit of the supplied `codex/13-case-handoff-20261104` branch plus two preliminary real-Guest mechanism gates. This is not a promoted benchmark Case and contains no model run.

## Handoff branch audit

- Audited branch: `codex/13-case-handoff-20261104`, HEAD `c175333ee66984c7b41bad815eb160102c5bbac7`; checkout was detached and clean during the read-only audit. The roster is under `docs/handoff/13-case-handoff/HANDOFF.md`, not at repository root.
- The roster contains 16 Cases. The handoff audit found 11 with one same-version MA-ID PASS / MA-SD FAIL / MA-SD+Lock FAIL triplet. This is one qualifying triplet per Case, not evidence of repeatability. Five do not satisfy that exact rule.
- The short mechanism Cases generally use about 12–20 GUI actions per actor and take about 18–28 minutes for a three-arm set. The audited macro-workflows use about 18 actions per actor and take about 22–49 minutes. This is a practical scale reference for a new candidate; it does not imply all actions are equally difficult or all failures are mechanism-attributable.
- Existing qualified mechanisms already include focus/input routing, clipboard, browser tab/context, active object/undo, shell CWD, viewport drift, reviewer identity, and stale business artifacts. PRINT-ROUTE1 was a Guest-level NO-GO because the pinned Guest had no print queues. ATTACH-EVIDENCE1 remains close to existing selection/context mechanisms unless a native chooser-specific state is demonstrated.
- Recommendation: preserve the existing 16-case roster and historical artifacts. Continue a new candidate on this isolated experiment branch. Prefer a 12–20 GUI-action/actor workflow with a consequential saved artifact and exact semantic scoring. Do not combine results across Case versions or label a one-triplet result as stable.

## Candidate gate: Calc global locale / number parsing

Candidate label: `CALC-LOCALE1`, provisional `candidate-0.1`.

This candidate tests a Calc application-profile setting that changes how typed numeric strings are interpreted. It is distinct from a selected cell, active window, or Find/Replace scope. It is adjacent to the broader family of application preferences, including FIND-1, so any future report should describe the specific decimal-parsing mechanism rather than claim a wholly unrelated state category.

### Real Guest setup

- Run ID: `calc-locale-gate-20261107T083100Z`.
- One real OSWorld Ubuntu Guest from `/data3/whn/Project2/images/osworld-v2-ubuntu-x86.qcow2`, mounted read-only; runtime `sha256:4696860fc79a4a6815f61f2a063f473eb8df33534aef3107d126199cb3f2a116`.
- QEMU used TCG because `/dev/kvm` was not accessible. Guest requested 4 vCPU / 4 GiB. LibreOffice Calc 7.3.7.2 opened a real ODS file. No model or API was used.
- Guest desktop and Calc cold start took about 3–6 minutes each on TCG across these two runs. GUI calls and screenshot polling were also slow on TCG. All subsequent interaction was through the OSWorld Guest's real PyAutoGUI interface. Both exact owned containers were closed and verified absent; the base image was not modified.
- Evidence root: `/data2/whn/codesk-runs/case-probes/calc-locale-gate-20261107T083100Z/`. It retains 14 GUI action records, input/screenshot event records, real 1920x1080 screenshots, the ODS fixture, and saved ODS artifacts. Selected screenshots: `manual-001.png` (Calc fixture), `manual-002.png` (English-locale baseline entry), `manual-004.png` (Options dialog), `manual-007.png` (locale settings), `manual-010.png` (German locale selected), `manual-011.png` (settings warning), `manual-012.png` (same dot input after change), and `manual-013.png` (locale-correct recovery input).

### Scripted causal controls and result

In the visible Calc GUI:

1. Before changing locale, typing `1.25` into the Amount cell produced a numeric value.
2. In LibreOffice Options → Language Settings → Languages, the locale was changed from English (Hong Kong) to German (Germany); “Same as locale setting” showed the decimal separator changing from `.` to `,`.
3. The same visible Calc document remained active after dismissing the normal settings notice. Typing `1.25` into the next cell produced a text cell, not a numeric value.
4. Typing `1,25` into another cell under German locale produced a numeric value equal to 1.25.

The saved ODS was scored independently of the Guest UI by parsing `content.xml`:

| Cell | GUI input and setting | Saved type | Saved numeric value | Display text |
|---|---|---|---:|---|
| B2 | `1.25`, before locale change | float | 1.25 | `1,25` after the setting changed |
| B3 | `1.25`, after German locale change | string | — | `1.25` |
| B4 | `1,25`, after German locale change | float | 1.25 | `1,25` |

Saved artifact: `artifacts/german_locale_after.ods`, SHA-256 `2b01a0a6e186d3d867a23ac18f5b4f4161e3a0e320818d4c5a2e2904255f2116`.

Preliminary interpretation: the GUI setting changed numeric parsing semantics, and locale-appropriate input restored the intended value. This is a real Guest mechanism exposure with a visible recovery path. It is not yet evidence that a second open workbook inherits the setting, that isolated Guest profiles stay independent, or that a model Agent will make the same choice. No formal Case result is claimed.

### Cross-workbook verification

- Run ID: `calc-locale-crossdoc-gate-20261107T091300Z`; same pinned Guest/runtime and TCG resources; no model/API.
- Two separate ODS workbooks were open in Calc at the same time. In workbook A, the real GUI first entered `1.25` under the original setting and saved it as float 1.25 (`A_before_locale.ods`, SHA-256 `d25b705c492ff500d6f3b43f372334efa57c7be26ad588acc48d566349b0fe5f`).
- In workbook B, the real GUI changed the application locale to German (Germany). The selection was verified on screen with decimal separator `,` before applying. The first recorded dropdown choice was not applied; the subsequent screenshot confirms German (Germany) before pressing OK. All intermediate actions and screenshots remain in the run log.
- The GUI then switched back to the still-open workbook A. Without using a shell or changing focus after selecting the target cell, the same `1.25` text was typed in A's next row and saved. The separate A workbook shows B2 as `1,25` and B3 as `1.25`; independent ODS parsing confirms B2 is float 1.25 while B3 is a string (`A_after_locale.ods`, SHA-256 `16fd28be3a23200ae89a027a8ca5853f62baa0fa3e18bcbf7744f63590532b06`).
- Evidence root: `/data2/whn/codesk-runs/case-probes/calc-locale-crossdoc-gate-20261107T091300Z/`; selected frames `manual-001.png` (A baseline), `manual-004.png`/`manual-006.png` (B's final locale choice), `manual-008.png` (A reactivated), `manual-009.png` (A result). It retains 10 logged GUI actions, screenshots, both workbooks, before/after files, Oracle JSON, ownership and teardown records.

This closes the cross-workbook part of the mechanism gate: the preference changed the interpretation of input in a different, already-open workbook. It still does not test two Guest profiles. The per-Guest separation expected under MA-ID remains an unverified topology hypothesis, not a measured PASS.

## Candidate artifact prototype

The evidence supports a small independent candidate package at `oscombo/collab/calc_locale_handoff/`; it is deliberately not in `CASE_REGISTRY.md` and is not yet a runnable Case.

- `TASK_CARD_ZH.md` defines a two-vendor purchase comparison: A enters the USD quote and makes the final budget decision; B uses the EU quote's decimal-comma convention, saves its numeric result, and hands the saved workbook to A. A's final result depends on B's actual file.
- `fixtures/public/` contains three separate real ODS inputs. Public manifest SHA-256 values are recorded there. The public manifest contains no path to private Gold. `fixtures/private/gold/` and the two negative control workspaces are evaluator-only and must not be copied to Actors.
- `oracle.py` reads the saved ODS cell types and values, checks calculation formulas reference the required input cells, preserves source fields, checks A's decision against B's saved output, and computes whether the recommendation fits the budget. It does not score collaboration from an Evidence string or asserted revision ID.
- Offline controls run from the package: Gold joint PASS; wrong EU total negative FAIL; text-parsed EU price negative FAIL. `controls_pass=True`. This is an offline scorer/fixture result, not GUI, Guest topology, or model evidence.
- Estimated task size is A 12–18 and B 12–18 consequential GUI actions. This matches the supplied handoff's short Case scale. The locale-setting operation is part of the causal mechanism and remains visible; normal recovery counts as task success.

The new task fixture has not yet been opened and completed end-to-end in a Guest. There is no workspace bridge Adapter or role message/revision protocol in this candidate directory yet. The actual Guest gate used a smaller probe ODS, so it establishes the Calc behavior, not full Case executability.

## Draft workflow at the audited Case scale

Possible user need: compare two vendor quotes with different decimal conventions and issue one purchase recommendation.

- **Agent A:** enter a short US-format quote in Calc, calculate its landed unit cost, then use Agent B's saved EU quote to complete a two-vendor comparison and recommendation.
- **Agent B:** enter and verify a short decimal-comma quote as numeric values in Calc, save the normalized quote, and send A the exact saved artifact/value.
- **Information dependency:** A's final choice and threshold check require B's normalized, saved price. Distinct per-role source fields and outputs prevent same-file edit collisions; A still must read and use B's result.
- **Candidate shared state:** B changes Calc's locale to handle the EU source; A's already-open Calc work then inherits that application-profile decimal parsing setting on a shared Guest. MA-ID should keep the setting in B's Guest profile. This must be explicitly verified with two open workbooks before the task is promoted.
- **Fairness:** same prompt, fixture, model, workspace files, message tools, budgets and Oracle in all arms. Do not tell an Actor that a shared desktop exists. Keep locale and number-format cues visible; a correct adaptation or recovery scores as success. Shared+Lock uses the existing per-action lock only.
- **Target artifact/oracle:** check typed cell values and types, formulas/calculated totals, source traceability, final supplier recommendation, and that A used B's saved revision. A nonempty evidence cell or a copied revision string is insufficient. Message plus saved revision and final use must agree.
- **Action budget target:** approximately 12–20 consequential GUI actions per actor, matching the short Case scale in the handoff. Do not hard-cap a model run at this design estimate.

### Next gates before promoting a Case

1. Open the packaged public quote files through the real Guest and run the target-negative control (locale unchanged, dot input remains numeric) plus recovery control (locale changed, locale-correct comma input remains numeric). Current evidence uses a smaller probe workbook; it is not yet a full-fixture Guest control.
2. Verify isolated profile separation on two Guests and saved-file delivery/ownership through the existing workspace bridge before introducing any model actor.
3. Implement a thin Shared/Isolated adapter and trace integration only after the two topology gates pass; do not change the already auditable source data or semantic Oracle to favor either arm.
4. Freeze a new versioned task card, fixture, gold, oracle, and adapter only after those gates pass. Keep all current Case cards and artifacts untouched.
5. The current environment has no verified working model endpoint configuration in these runs. Do not report model-agent feasibility or any Shared/Isolated model result until a small endpoint/tool compatibility pilot succeeds.
