# Design

This Lite task removes backend setup, server testing, framework navigation and multi-file edits. A repairs one HTML option value; B retests one combined filter in Chrome and records what the browser actually shows. The source is a static local page, so edited code is never executed by the host coordinator. The real browser executes the fixture's unchanged filter script inside the Guest. Both roles can begin concurrently and naturally compete for editor/browser focus in Shared. The required handoff is A's saved HTML revision plus message, followed by B's browser reload and QA note. The artifact Oracle is intentionally separate from the temporal GUI trace audit.

Patch 1.0.1 accepts harmless line indentation and trailing blank lines added by the Guest text editor. It still requires the same ordered non-whitespace source lines with only the Delivered value repaired. A browser screenshot showing one visible result after A's saved revision is required for an end-to-end PASS.
