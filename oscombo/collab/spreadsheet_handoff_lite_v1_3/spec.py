"""Actor-visible contract for the independent Case 6 v1.3 case."""

CASE_ID = "CDD-SH-LITE-003"
CASE_VERSION = "1.3.1"
TASK_ROOT = "/tmp/sh13"
CONDITIONS = ("collaborative_shared", "collaborative_isolated")
FIXTURE_NAMES = {
    "forecast": "forecast_input.ods",
    "order": "order_template.ods",
    "brief": "case_brief.md",
}
OUTPUTS = {
    "A": "outputs/agent_A/forecast.ods",
    "B": "outputs/agent_B/order_plan.ods",
}
ROLE_BUDGET = {
    "A": {"steps": 18, "model_tokens": None},
    "B": {"steps": 18, "model_tokens": None},
}
TOTAL_MODEL_TOKEN_BUDGET = None
HANDOFF_DEPENDENCIES = {"B": "A"}

AGENT_A_INSTRUCTION = """You are A, the demand planner. Your editable forecast.ods workbook is open in Calc with Forecast!H3 selected. Calculate two-month non-negative net need for SKU-LAMP from the visible input cells: average the three monthly sales, multiply by two, add safety stock, then subtract on-hand and inbound units; clamp below zero to zero. Enter a Calc formula in H3 that uses the visible source cells B3:G3, commit with Enter, and save with Ctrl+S. The formula in H3 is the evidence for how you used the source; do not edit the input cells. Publish the saved forecast revision, then tell B only that the saved forecast is ready. Do not send the number or its calculation in a message. You may work while B reviews the order template. Use only Calc GUI and the collaboration tools; do not use Terminal, scripts, macros, evaluator files or Gold data."""

AGENT_B_INSTRUCTION = """You are B, the procurement planner. Your editable order_plan.ods workbook is open in Calc with Order!E3 selected. First inspect the public order inputs: units per carton, USD per individual unit, and budget. While A works, wait using the collaboration handoff tools rather than repeatedly polling the desktop. After A's ready message, call list_saved_artifacts and find A's delivered saved revision. Open that exact peer-view file in Calc using its full path under /tmp/sh13; verify the workbook title and visually read Forecast!H3. This saved Calc revision is your source. Return to the already-open order_template workbook with Alt+Tab. Enter the forecast need in E3 as an individual-unit count. Then enter the smallest sufficient integer carton count in F3; the sheet will calculate total individual units and cost in G3 and H3. Check those results against the budget, save with Ctrl+S, and publish your saved order. The F3 field is CARTONS, while G3 is individual UNITS. Do not edit A's read-only peer view. Use only Calc GUI and the collaboration tools; do not use Terminal, scripts, macros, evaluator files or Gold data."""
