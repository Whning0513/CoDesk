"""Actor-visible Model-and-Review Lite v1 task contract."""

CASE_ID = "CDD-MAR-LITE-001"
CASE_VERSION = "1.0.0"
CONDITIONS = ("collaborative_shared", "collaborative_isolated")
FIXTURE_NAMES = {"scene": "Lamp_Review.blend", "report": "shade_review.txt", "brief": "case_brief.md"}
OUTPUTS = {"A": "outputs/agent_A/Lamp_Review.blend",
           "B": "outputs/agent_B/shade_review.txt"}
ROLE_BUDGET = {"A": {"steps": 25, "model_tokens": None},
               "B": {"steps": 25, "model_tokens": None}}
TOTAL_MODEL_TOKEN_BUDGET = None
HANDOFF_DEPENDENCIES = {"B": "A"}

AGENT_A_INSTRUCTION = """You are A, the Blender geometry owner. Your Blender project is open. Change only Lamp_Shade so its outside X and Y dimensions are each 1.46 m; preserve its 0.60 m height, position, mesh shape and material. Do not change Lamp_Bulb, Lamp_Base or Camera_Main. Save the Blender project, publish your saved revision, and tell B the measured final shade width. You and B may work at the same time. Do not use Terminal, scripts, Python Console, evaluator files or Gold data. Edit through the Blender GUI only."""

AGENT_B_INSTRUCTION = """You are B, the geometry reviewer. Your short review text file is open, and you can inspect the Blender scene while A works. Your own brief does not give A's target width. When A publishes a saved Blender revision, inspect the current saved Lamp_Review.blend in Blender through the GUI; use File > Revert if the project was already open before A's revision. Read the actual Lamp_Shade X dimension. Lamp_Bulb is 0.50 m wide, so radial clearance is (shade width - 0.50) / 2. In shade_review.txt, write the measured shade width, computed radial clearance and whether it meets the 0.40 m minimum. Save and publish the review. If A's revision is not available after initial inspection, ask A and end this turn stating that you are waiting; the coordinator will wake this same conversation after the public handoff. Do not spend desktop wait calls polling A. Do not edit A's Blender project. Do not use Terminal, scripts, Python Console, evaluator files or Gold data."""

PUBLIC_BRIEF = """# Lamp shade geometry review

A adjusts the supplied Blender scene's Lamp_Shade, saves the project and publishes it. B reviews the saved scene in Blender and records its measured width, the bulb's radial clearance and a pass/fail judgement in the supplied text report. The bulb is 0.50 m wide; radial clearance is half the difference between shade and bulb widths, and at least 0.40 m is required. B should report what is actually saved, even if it disagrees with A's message. Preserve the other scene objects. Both roles can start work immediately and use the same collaboration message and saved-file tools. Deliver the revised Blender project and review text file.
"""
