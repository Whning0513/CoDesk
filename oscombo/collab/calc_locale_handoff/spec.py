"""Public task contract for CALC-LOCALE1 candidate-0.1.

Gold numbers live only under fixtures/private and must never be copied into an
Actor workspace or prompt. The same public files are supplied in every arm.
"""
from __future__ import annotations

from . import CASE_ID, CASE_VERSION, CONDITIONS

PUBLIC_FILES = ("vendor_us.ods", "vendor_eu.ods", "purchase_decision.ods")
ACTOR_OUTPUTS = {"A": ("vendor_us.ods", "purchase_decision.ods"),
                 "B": ("vendor_eu.ods",)}
ROLE_BUDGET = {"steps": 80, "model_tokens": 6000, "calibrated": False}

ACTOR_A_INSTRUCTION = """You are Agent A on the purchasing desk. In vendor_us.ods, enter the USD unit price and shipping amount from the visible Northstar quote as numeric values, preserve the source quote, and calculate the landed cost for the stated quantity. Save the workbook. The final purchase_decision.ods must compare your saved Northstar total with Agent B's saved EU total, apply the visible USD cap, and state the recommended supplier with a brief source note. B's completed vendor_eu.ods will arrive through the shared workspace or attachment. Open and verify the saved workbook and use its numeric result; do not rely only on a message or revision string. You may begin your Northstar work before B is finished. If a value is not numeric or the totals do not reconcile, correct it and verify the saved result. All source quotes and task rules are available to both agents."""

ACTOR_B_INSTRUCTION = """You are Agent B on the purchasing desk. The Elbe Office Supplies quote uses decimal commas. In LibreOffice Calc, set the locale to the source convention before entering the quote values, then enter the unit price and freight as numeric values in vendor_eu.ods, calculate the USD landed cost using the stated quantity and exchange rate, preserve the source quote, and save the workbook. Tell A when the completed saved workbook is ready and identify the actual saved result. You may begin before A finishes. Check that your saved values are numeric and that the total uses the visible quote, quantity, and rate. All source quotes and task rules are available to both agents."""

TASK_REQUIREMENTS = (
    "Enter the Northstar USD quote as numeric values and calculate its landed total.",
    "Enter the Elbe decimal-comma quote as numeric values and calculate its USD landed total.",
    "Save both source workbooks without changing the quoted source strings.",
    "A must open and use B's saved EU workbook in the final comparison.",
    "Apply the visible budget cap and recommend the eligible lower-cost supplier.",
)
