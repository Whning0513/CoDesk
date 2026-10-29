"""Actor-visible task contract; no evaluator answers are stored here."""

CASE_ID = "CDD-SH-LITE-001"
CASE_VERSION = "1.0.0"
CONDITIONS = ("collaborative_shared", "collaborative_isolated")
FIXTURE_NAMES = {"forecast": "forecast_input.ods", "order": "order_template.ods",
                 "brief": "case_brief.md"}
OUTPUTS = {"A": "outputs/agent_A/forecast.ods",
           "B": "outputs/agent_B/order_plan.ods"}
ROLE_BUDGET = {"A": {"steps": 25, "model_tokens": None},
               "B": {"steps": 25, "model_tokens": None}}
TOTAL_MODEL_TOKEN_BUDGET = None
HANDOFF_DEPENDENCIES = {"B": "A"}

AGENT_A_INSTRUCTION = """You are A, the Forecast Verifier. Your editable forecast.ods workbook is already open. On its single Forecast sheet, use the visible sales and inventory inputs to calculate the two-month non-negative net need for SKU-LAMP in H3: average monthly sales times two, plus safety stock, minus on-hand and inbound stock. Put the input-cell range in I3 as evidence. Save the workbook, publish the saved artifact, and send B the verified net need and source range. Preserve all source cells. You may work while B prepares the order plan. Edit only your forecast output through the Calc GUI; do not use Terminal, scripts, macros, evaluator files or Gold data."""

AGENT_B_INSTRUCTION = """You are B, the Procurement Planner. Your editable order_plan.ods workbook is already open. You may inspect its case-pack size, unit price and budget cap while A works. Wait for A's saved forecast revision and message. Use A's verified net need to enter the smallest whole-case order quantity that covers it in E3, and enter the purchase cost in F3. Ensure the cost fits the visible budget cap. Save and publish your workbook, and tell A if the forecast or budget cannot be reconciled. Preserve the provided SKU, pack, price, cap and source label. Edit only your order output through the Calc GUI; do not use Terminal, scripts, macros, evaluator files or Gold data."""
