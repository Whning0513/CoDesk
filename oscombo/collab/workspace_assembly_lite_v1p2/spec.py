"""Actor-visible task contract."""

CASE_ID = "CDD-WA-LITE-001"
CASE_VERSION = "1.0.2"
CONDITIONS = ("collaborative_shared", "collaborative_isolated")
FIXTURE_NAMES = {"asset": "inspection_note.txt", "report": "handoff_report.odt", "brief": "case_brief.md"}
OUTPUTS = {"A": "outputs/agent_A/inspection_note.txt",
           "B": "outputs/agent_B/handoff_report.odt"}
ROLE_BUDGET = {"A": {"steps": 25, "model_tokens": None},
               "B": {"steps": 25, "model_tokens": None}}
TOTAL_MODEL_TOKEN_BUDGET = None
HANDOFF_DEPENDENCIES = {"B": "A"}

AGENT_A_INSTRUCTION = """You are A, the asset organizer. The File Manager is open at this task's incoming folder. First move inspection_note.txt into your delivery folder outputs/agent_A through the GUI File Manager, preserving its bytes. Then open the delivered note in a GUI application and read its inspection tag. Publish the saved delivered file and tell B its filename and that tag. Before cutting or moving, check that the file is selected in File Manager. Do not use Terminal, scripts, evaluator files or Gold data. B may inspect the draft report while you work."""

AGENT_B_INSTRUCTION = """You are B, the report editor. Your editable one-page Writer document handoff_report.odt is open. You may inspect its draft while A moves the attachment. Wait for A's delivered file revision and message. After the handoff, open the delivered inspection_note.txt in a GUI application and read its tag yourself before editing Writer; A's message alone is not a file check. If the handoff is not yet available after your initial inspection, ask A for it and end your current turn stating that you are waiting; the coordinator will wake this same conversation after the public handoff. Do not spend desktop wait calls polling A. Replace the report's unfinished attachment sentence with one concise sentence naming inspection_note.txt and the inspection tag from A's delivered note. Preserve the report title and other text. Save and publish your Writer document. Do not use Terminal, scripts, evaluator files or Gold data; do not edit A's attachment."""
