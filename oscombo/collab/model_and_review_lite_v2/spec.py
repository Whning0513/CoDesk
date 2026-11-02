"""Actor-visible Model-and-Review Lite v2 contract."""
CASE_ID = "CDD-MAR-LITE-002"
CASE_VERSION = "2.0.0"
CONDITIONS = ("collaborative_shared", "collaborative_isolated")
FIXTURE_NAMES = {"scene": "Lamp_Review.blend", "report": "shade_review.txt", "brief": "case_brief.md"}
OUTPUTS = {"A": "outputs/agent_A/Lamp_Review.blend", "B": "outputs/agent_B/shade_review.txt"}
ROLE_BUDGET = {"A": {"steps": 25, "model_tokens": None}, "B": {"steps": 25, "model_tokens": None}}
TOTAL_MODEL_TOKEN_BUDGET = None
HANDOFF_DEPENDENCIES = {"B": "A"}

AGENT_A_INSTRUCTION = """You are A, the Blender geometry owner. Your project is open with Lamp_Shade selected. Enlarge its width and depth together by a factor of 1.25 while preserving its height and the other objects. In the 3D viewport, with the selected shade, use Blender's S, Shift+Z, type 1.25, Enter sequence. Save the project, publish the saved revision, and tell B it is ready without reporting the resulting width. You and B may work concurrently. Do not use Terminal, scripts, Python Console, evaluator files or Gold data. Edit through the Blender GUI only."""

AGENT_B_INSTRUCTION = """You are B, the geometry reviewer. Your review text file is open and you may inspect the initial scene while A works. The final shade width is not in your brief. After A publishes a saved Blender revision, inspect that revision in Blender through the GUI. If the project was open before the revision, use File > Revert. Read Lamp_Shade's actual X dimension. The bulb is 0.50 m wide; radial clearance is (shade width - 0.50) / 2 and the minimum is 0.40 m. In shade_review.txt record shade width, radial clearance and PASS or FAIL; save and publish it. If A's revision is not available after initial inspection, ask A and end this turn saying you are waiting; the coordinator wakes this conversation after the public handoff. Do not poll using desktop wait calls. Do not edit A's Blender project. Do not use Terminal, scripts, Python Console, evaluator files or Gold data."""

PUBLIC_BRIEF = """# Lamp shade geometry review

A enlarges the supplied shade in Blender, saves and publishes the scene. B reviews the saved scene in Blender and records the measured shade width, the bulb's radial clearance and a pass/fail judgement in the text report. The bulb is 0.50 m wide; radial clearance is half the difference between shade and bulb widths, and at least 0.40 m is required. B should report what is actually saved. Preserve the other objects. Both roles can start work and use collaboration messages and saved-file tools.
"""
