"""Actor-visible task contract; no evaluator answers are stored here."""

CASE_ID = "CDD-SH-LITE-001"
CASE_VERSION = "1.1.0"
CONDITIONS = ("collaborative_shared", "collaborative_isolated")
FIXTURE_NAMES = {"forecast": "forecast_input.ods", "order": "order_template.ods",
                 "brief": "case_brief.md"}
OUTPUTS = {"A": "outputs/agent_A/forecast.ods",
           "B": "outputs/agent_B/order_plan.ods"}
ROLE_BUDGET = {"A": {"steps": 25, "model_tokens": None},
               "B": {"steps": 25, "model_tokens": None}}
TOTAL_MODEL_TOKEN_BUDGET = None
HANDOFF_DEPENDENCIES = {"B": "A"}

AGENT_A_INSTRUCTION = """You are A, the Forecast Verifier. Your editable forecast.ods workbook is already open. On its single Forecast sheet, calculate the two-month non-negative net need for SKU-LAMP in H3, measured in UNITS: average monthly sales times two, plus safety stock, minus on-hand and inbound stock. Put the source-cell range in I3 as evidence. Commit each edited Calc cell with Enter, save the workbook with Ctrl+S, then publish the saved artifact and send B the verified net need and source range. A message alone is not a saved handoff. Preserve all source cells. You may work while B prepares the order plan. Edit only your forecast output through the Calc GUI; do not use Terminal, scripts, macros, evaluator files or Gold data."""

AGENT_B_INSTRUCTION = """You are B, the Procurement Planner. Your editable order_plan.ods workbook is already open. While A works, inspect B3 (units per case), C3 (USD per UNIT) and D3 (budget cap). Wait for both A's published saved forecast revision and A's message; use the reported net need only after the saved revision exists. E3 is ORDER UNITS, not the number of cases: enter the smallest multiple of B3 that covers the verified net need. F3 is total USD cost: E3 times C3. Check the cap. Keep your order_plan.ods window in front while editing; you need not open A's workbook unless its revision and message disagree. Commit each edited Calc cell with Enter, save with Ctrl+S, then publish your saved workbook. If A has not delivered, ask and end this turn stating that you are waiting; the coordinator will wake the same conversation after the public handoff, without spending desktop calls polling. Tell A if the forecast or budget cannot be reconciled. Preserve the provided SKU, pack, price, cap and source label. Edit only your order output through the Calc GUI; do not use Terminal, scripts, macros, evaluator files or Gold data."""
