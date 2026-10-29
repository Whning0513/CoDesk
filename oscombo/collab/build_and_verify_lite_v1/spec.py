"""Actor-visible contract; evaluator answers are kept under private/."""

CASE_ID = "CDD-BV-LITE-001"
CASE_VERSION = "1.0.0"
CONDITIONS = ("collaborative_shared", "collaborative_isolated")
FIXTURE_NAMES = {"source": "orderdesk.html", "qa": "qa_note.txt", "brief": "case_brief.md"}
OUTPUTS = {"A": "outputs/agent_A/orderdesk.html", "B": "outputs/agent_B/qa_note.txt"}
ROLE_BUDGET = {"A": {"steps": 25, "model_tokens": None},
               "B": {"steps": 25, "model_tokens": None}}
TOTAL_MODEL_TOKEN_BUDGET = None
HANDOFF_DEPENDENCIES = {"B": "A"}

AGENT_A_INSTRUCTION = """You are A, the GUI developer. The editable OrderDesk HTML file is open in the text editor. The page lists three synthetic orders and has a search field and status dropdown. Its Delivered dropdown option has a value typo, so the combined filter does not show the expected rows. Correct this one defect in the GUI editor, save orderdesk.html, publish_saved_artifact, and tell B which saved revision to retest. Preserve the order data, all other options and the filtering code. B can inspect the browser while you work. Do not use Terminal, scripts, evaluator files or Gold data to edit the source."""

AGENT_B_INSTRUCTION = """You are B, the browser tester. The OrderDesk page is open in a real browser, and qa_note.txt is open in a text editor for your report. You may inspect the initial page while A works. Wait for A's saved source revision and message, then reload the page, search for North, select Delivered and apply the filter. Record the observed visible order ID(s), query, status and saved source filename in qa_note.txt through the GUI editor. Save and publish the note; report if the browser does not match the handoff. Do not edit A's source, use Terminal or scripts, or read evaluator/Gold files."""
