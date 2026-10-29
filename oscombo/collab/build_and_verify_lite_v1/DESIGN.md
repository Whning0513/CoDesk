# Design

This Lite task removes backend setup, server testing, framework navigation and multi-file edits. A repairs one HTML option value; B retests one combined filter in Chrome and records what the browser actually shows. The source is a static local page, so edited code is never executed by the host coordinator. The real browser executes the fixture's unchanged filter script inside the Guest. Both roles can begin concurrently and naturally compete for editor/browser focus in Shared. The required handoff is A's saved HTML revision plus message, followed by B's browser reload and QA note. The artifact Oracle is intentionally separate from the temporal GUI trace audit.

Patch 1.0.1 accepts harmless line indentation and trailing blank lines added by the Guest text editor. It still requires the same ordered non-whitespace source lines with only the Delivered value repaired. A browser screenshot showing one visible result after A's saved revision is required for an end-to-end PASS.

Patch 1.0.2 makes B use a hard reload after the saved source revision; the v1.0.1 Guest screenshot showed a stale option value despite a correct saved file and ordinary Ctrl+R. Both desktop conditions receive the same instruction and Adapter behavior.

Patch 1.0.3 opens the original read-only input HTML in Chrome at setup. After A publishes the corrected output file, B navigates to that distinct saved output path in the address bar. The v1.0.2 Shared Guest control still showed the original option after Ctrl+Shift+R, so a new URL is needed to verify the saved revision in the actual browser. Both conditions use the same initial page and navigation instruction.

Patch 1.0.4 separates address-bar focus and URL typing into two GUI actions with waits. The v1.0.3 Guest screenshot showed Chrome searching a truncated URL because typing began before the address bar had focus. The model task, artifacts and Oracle remain the same.
