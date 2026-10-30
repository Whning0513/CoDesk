"""Real Guest scripted control for a stale LibreOffice Open dialog after scoring.

The injection occurs after the scripted Actors and Oracle finish; it never
changes the saved scored bytes or an Actor's desktop during execution.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from oscombo.collab.data_to_deck import live_pilot


def main() -> None:
    args = sys.argv[1:]
    run_root = Path(args[args.index("--run-root") + 1]).resolve()
    original = live_pilot._prepare_saved_document_reopen

    def inject_then_reopen(guest, path, phase, application, log_path, model_episode):
        if phase == "reopen-B-before":
            guest.actor = "system"
            guest.run_pyautogui("import pyautogui, time; pyautogui.hotkey('ctrl','o'); time.sleep(2)")
            active = guest.active_window()
            shot = run_root / "screenshots" / "postscore-open-control.png"
            shot.write_bytes(guest.screenshot(patience=45))
            (run_root / "postscore_open_control.json").write_text(json.dumps({
                "phase": phase, "active_window_after_ctrl_o": active,
                "screenshot": str(shot.relative_to(run_root)),
                "scored_document": Path(path).name}, indent=2) + "\n")
            # Apply the same postscore recovery policy as a model episode.
            return original(guest, path, phase, application, log_path, True)
        return original(guest, path, phase, application, log_path, model_episode)

    live_pilot._prepare_saved_document_reopen = inject_then_reopen
    live_pilot.main(["--case-spreadsheet-lite-v1", *args])


if __name__ == "__main__":
    main()
