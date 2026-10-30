"""Model-and-Review Lite v1 real Guest entry point."""
from __future__ import annotations

import sys

from oscombo.collab.lite_file_guest_pilot import main as shared_main


if __name__ == "__main__":
    shared_main(["--case", "model_review", *sys.argv[1:]])
