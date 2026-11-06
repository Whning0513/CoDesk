"""Actor-visible case contract. The inspection code is only in A's note."""
CASE_ID = "CDD-WA-LITE-002P2"
CASE_VERSION = "2.2.0"
ADAPTER_VERSION = "2.2.1"
CONDITIONS = ("collaborative_shared", "collaborative_isolated")
FIXTURE_NAMES = {"asset": "inspection_note.txt", "report": "handoff_report.odt", "brief": "case_brief.md"}
OUTPUTS = {"A": "outputs/agent_A/inspection_note.txt", "B": "outputs/agent_B/handoff_report.odt"}
ROLE_BUDGET = {"A": {"steps": 25, "model_tokens": None}, "B": {"steps": 25, "model_tokens": None}}
HANDOFF_DEPENDENCIES = {"B": "A"}
PRE_HANDOFF_REVISION_ROLES = frozenset({"B"})
PEER_VIEW_DIRS = {"A": "views/B"}
TASK_ROOT = "/tmp/wa22"


def version_manifest() -> dict[str, str]:
    """Separate task semantics version from the runner/adapter release."""
    return {"case_id": CASE_ID, "case_version": CASE_VERSION,
            "adapter_version": ADAPTER_VERSION}

AGENT_A_INSTRUCTION = """You are A, the asset organizer. In File Manager, move inspection_note.txt from the incoming folder into your output folder outputs/agent_A, preserving the file bytes. The folder contains just this one note, initially selected. Check the selection before moving. Publish your saved output with the collaboration tool, then send B only a notification that the file revision is ready and its revision number. Do not send the note's inspection code or contents in your message. You may work concurrently with B. Do not use Terminal, scripts, evaluator files or Gold data."""

AGENT_B_INSTRUCTION = """You are B, the report editor. Your editable handoff_report.odt is open in Writer. The existing Source line already names inspection_note.txt; keep it. The caret starts at the end of the separate Audience: line. Before A's delivery, read the existing draft to identify its review audience, type only that audience value after Audience:, and save. You may do this while A moves the note. Then wait for A's delivered revision and notification. If it is not available, ask A for availability and end your current turn stating you are waiting; the coordinator will wake this conversation. Do not spend desktop wait calls polling A. After handoff, call list_saved_artifacts and use A's peer_view_path joined to the task root to open that revision in a GUI application. Writer's Open dialog supports Ctrl+L for entering a full path. It is a read-only view; read the three-digit inspection code yourself. Return to your report, go to the end of the separate Inspection code: line, type only the observed three digits and save and publish. Keep the existing title, operations sentence, Source line and separate labeled paragraphs. Do not inspect A's incoming or original output path, edit the peer file, use Terminal, scripts, evaluator files or Gold data."""


def model_instruction(role: str) -> str:
    if role not in {"A", "B"}:
        raise ValueError("unknown actor role")
    task = AGENT_A_INSTRUCTION if role == "A" else AGENT_B_INSTRUCTION
    return (task + f"\nTask root: {TASK_ROOT}. Your output: {TASK_ROOT}/{OUTPUTS[role]}." +
            "\nAfter saving, use publish_saved_artifact and send_message; "
            "use list_saved_artifacts/read_messages for handoff. The peer_view_path in "
            "the published revision is relative to the task root. B reads that view "
            "without editing it. Perform task edits only through GUI applications.")
