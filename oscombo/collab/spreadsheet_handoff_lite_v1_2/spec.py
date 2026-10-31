"""Actor-visible contract for the independent Case 6 GUI-read candidate."""

CASE_ID = "CDD-SH-LITE-002"
CASE_VERSION = "1.2.0"
TASK_ROOT = "/tmp/sh12"
CONDITIONS = ("collaborative_shared", "collaborative_isolated")
FIXTURE_NAMES = {"forecast": "forecast_input.ods", "order": "order_template.ods",
                 "brief": "case_brief.md"}
OUTPUTS = {"A": "outputs/agent_A/forecast.ods", "B": "outputs/agent_B/order_plan.ods"}
ROLE_BUDGET = {"A": {"steps": 25, "model_tokens": None},
               "B": {"steps": 25, "model_tokens": None}}
TOTAL_MODEL_TOKEN_BUDGET = None
HANDOFF_DEPENDENCIES = {"B": "A"}

AGENT_A_INSTRUCTION = """You are A, the Forecast Verifier. Your editable forecast.ods is open in Calc with H3 initially selected; verify the selected cell before typing because the desktop can change. Calculate the two-month non-negative net need in units for SKU-LAMP: average the three visible monthly sales, multiply by two, add safety stock, and subtract on-hand and inbound stock. Enter your result in Forecast!H3 and commit the cell with Enter. The source labels beside it are provided for reference; leave the source data and labels unchanged. Save with Ctrl+S and publish your saved artifact. Send B only the message 'Saved forecast is ready for review.' Do not include the computed number or a calculation in messages. You may work while B prepares the purchase plan. Edit only your own workbook through Calc; do not use terminal commands, scripts, macros, evaluator files or Gold data."""

AGENT_B_INSTRUCTION = """You are B, the Procurement Planner. Your editable order_plan.ods is open in Calc with F3 initially selected; verify the selected cell before typing because the desktop can change. While A works, inspect the units per case, price per unit and budget, and enter the general cost formula =E3*C3 in Order!F3; commit it with Enter. This formula uses your eventual order units, not a supplied answer. Ask A for the saved forecast if needed; if it is not ready, end this turn stating that you are waiting. After A's saved revision and ready message arrive, call list_saved_artifacts and obtain A's peer_view_path. It is relative to /tmp/sh12; prepend /tmp/sh12/ and open that exact revision file in Calc through the GUI (Ctrl+O, then Ctrl+L for the full path). Visually read the saved Forecast!H3 value, and return to your order_plan.ods. Enter in Order!E3 the smallest whole-case multiple covering that saved need, commit with Enter, and check that F3 shows the cost and it does not exceed the budget. Save your workbook with Ctrl+S and publish it. Do not use a number from a message as the forecast; the saved revision is the evidence. Do not edit the peer revision. Your waiting conversation resumes without polling desktop tools. Edit only your own workbook through Calc; do not use terminal commands, scripts, macros, evaluator files or Gold data."""
