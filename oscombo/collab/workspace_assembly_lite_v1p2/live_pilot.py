"""Workspace Assembly Lite v1.0.2 real Guest entry point."""
from __future__ import annotations
import sys
from oscombo.collab.lite_file_guest_pilot import main as shared_main


if __name__ == "__main__":
    shared_main(["--case", "workspace_assembly_v1p2", *sys.argv[1:]])
