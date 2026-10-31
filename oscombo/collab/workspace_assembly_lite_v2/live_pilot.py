"""Case 7 Lite v2 entry point; the shared runner supplies both topologies."""
import sys
from oscombo.collab.lite_file_guest_pilot import main

if __name__ == "__main__":
    main(["--case", "workspace_assembly_v2", *sys.argv[1:]])
