"""Actor-visible case contract. The inspection tag is only in the public note."""
CASE_ID = "CDD-WA-LITE-002"
CASE_VERSION = "2.0.0"
CONDITIONS = ("collaborative_shared", "collaborative_isolated")
FIXTURE_NAMES = {"asset": "inspection_note.txt", "report": "handoff_report.odt", "brief": "case_brief.md"}
OUTPUTS = {"A": "outputs/agent_A/inspection_note.txt", "B": "outputs/agent_B/handoff_report.odt"}
ROLE_BUDGET = {"A": {"steps": 25, "model_tokens": None}, "B": {"steps": 25, "model_tokens": None}}
HANDOFF_DEPENDENCIES = {"B": "A"}
PEER_VIEW_DIRS = {"A": "views/B"}
TASK_ROOT = "/tmp/wa2"

AGENT_A_INSTRUCTION = """You are A, the asset organizer. In File Manager, move inspection_note.txt from the incoming folder into your output folder outputs/agent_A, preserving the file bytes. The folder contains just this one note, initially selected. Check the selection before moving. Publish your saved output with the collaboration tool, then send B only a notification that the file revision is ready and its revision number. Do not send the note's tag or contents in your message. You may work concurrently with B. Do not use Terminal, scripts, evaluator files or Gold data."""

AGENT_B_INSTRUCTION = """You are B, the report editor. Your editable handoff_report.odt is open in Writer, with the caret at the empty final paragraph. Before A's delivery, inspect the existing draft, identify its intended review audience, and append a short 'Audience: <audience>' line. Save that draft change. You may do this while A moves the note. Then wait for A's delivered revision and notification. If it is not available, ask A for its availability and end your current turn stating you are waiting; the coordinator will wake this conversation. Do not spend desktop wait calls polling A. After handoff, call list_saved_artifacts and use A's peer_view_path joined to the task root to open that revision in a GUI application. It is a read-only view; read the inspection tag yourself. Return to your report and append one concise line naming inspection_note.txt and its inspection tag. Preserve the existing title and operations sentence, then save and publish the report. Do not inspect A's incoming or original output path, edit the peer file, use Terminal, scripts, evaluator files or Gold data."""
