"""Run the versioned case through the shared OSWorld runner."""
from __future__ import annotations
import sys
from oscombo.collab.data_to_deck.live_pilot import main as shared_runner_main


def main(argv: list[str] | None = None) -> None:
    shared_runner_main(["--case-spreadsheet-lite-v1-2", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    main()
