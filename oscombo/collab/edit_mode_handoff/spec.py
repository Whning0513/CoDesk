"""Actor-visible contract for EDIT-1 Lite v1."""

from __future__ import annotations

from . import CASE_ID, CASE_VERSION

PUBLIC_FILE = "release_notice.fodt"
ACTOR_OUTPUTS = {"A": "release_notice_A.fodt", "B": "release_notice_B.fodt"}
SHARED_OUTPUT = "release_notice.fodt"
ROLE_BUDGET = {"steps_per_actor": 30, "model_tokens_per_actor": 4000,
               "calibrated": False}

ACTOR_A_INSTRUCTION = """You are the release coordinator. In your Writer document, insert the word READY and a following space immediately before HOLD-FOR-REVIEW on the Release status line. Preserve the entire hold phrase, reviewer code, and guard line exactly. Save your document and tell your teammate when the status update is saved. You may begin before the reviewer's edit is complete."""

ACTOR_B_INSTRUCTION = """You are the document reviewer. Change the fixed-width four-character code on the Reviewer code line from ____ to AB12. Preserve every other character and line. Use the ordinary Writer editing controls, save your document, and tell the release coordinator when the reviewer code is saved. You may begin before the status update is complete."""

EXPECTED_LINES = (
    "Release status: STATUS | READY HOLD-FOR-REVIEW",
    "Reviewer code: AB12; fixed-width field",
    "Guard phrase: DO-NOT-ALTER-THIS-LINE",
)
