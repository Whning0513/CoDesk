# Calc Locale Handoff — candidate 0.1

**Status: provisional design and offline artifact scorer; not registered or runnable as a formal Case.**

The candidate uses a LibreOffice Calc application-profile locale change to alter how numeric text is parsed in another open workbook. The real-Guest gate is recorded in `docs/handoff/13-case-handoff/next-five/design/HANDOFF_AUDIT_AND_CALC_LOCALE_GATE_20261107.md`.

The public fixture has separate Northstar USD and Elbe EUR quote workbooks plus a purchase decision workbook. A owns the US quote and final comparison. B owns the EU quote. A's final decision depends on B's correctly saved numeric total. The files are separate to avoid same-file ownership collisions; the Isolated arm will need to deliver B's completed ODS through the existing workspace bridge.

`fixtures/public/` contains the only files intended for Actor workspaces. `fixtures/private/` contains evaluator controls and must never be mounted or exposed to Actors. `fixtures.py` can regenerate both into a new empty directory. `oracle.py` checks typed numeric values, calculations, source preservation, A/B agreement, and the final cap-based recommendation.

Before promotion, still required:

1. Real GUI target-negative and recovery controls under a clean/reset locale.
2. Two-Guest MA-ID profile separation and actual saved-file handoff through the existing bridge.
3. Shared and Shared+PerActionLock scripted controls with event/screenshot causal evidence.
4. Verified model endpoint/tool compatibility, a short equal-budget Pilot, then a frozen three-arm model run.

Do not add this candidate to `CASE_REGISTRY.md`, combine it with an existing Case, or claim MA-ID/MA-SD results before those gates pass.
