"""One run-owned OSWorld GUI diagnostic for Ubuntu's Blender 3.0 package.

This does not score a benchmark case or enter Actor time. It checks whether
an older Blender can draw a visible GUI on the same TCG Guest.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from oscombo.collab.data_to_deck import live_pilot as core
from oscombo.collab.data_to_deck.provenance import RunLedger
from oscombo.collab.lite_file_guest_pilot import _blender_frame_ready


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--runtime", required=True)
    args = parser.parse_args()
    root = args.run_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "ownership.json").write_text(json.dumps({
        "run_id": root.name, "resources": [],
        "cleanup": "only exact owned oscombo.run label and full container ID"}, indent=2) + "\n")
    ledger = RunLedger(root, {"run_id": root.name, "purpose": "Blender 3 GUI graphics diagnostic",
                              "model_called": False, "case_score": None})
    guest_env = None
    try:
        guest_env, guest, container_id = core._boot_guest(root, root.name, "graphics",
            args.image, args.provider.resolve(), args.runtime, ledger)
        install = guest.env.controller.run_bash_script(
            "set -e\n"
            "printf 'osworld-public-evaluation\\n' | sudo -S apt-get update\n"
            "printf 'osworld-public-evaluation\\n' | sudo -S DEBIAN_FRONTEND=noninteractive "
            "apt-get install -y blender", timeout=900)
        (root / "blender3_install.json").write_text(json.dumps(install, indent=2) + "\n")
        if install.get("status") != "success" or install.get("returncode"):
            raise RuntimeError("Guest Blender 3 package install failed; see blender3_install.json")
        binary = core._shell(guest, "command -v /usr/bin/blender && /usr/bin/blender --version | head -n 1")
        (root / "blender3_version.json").write_text(json.dumps(binary, indent=2) + "\n")
        command = (f"mkdir -p /tmp/{root.name}; nohup env LIBGL_ALWAYS_SOFTWARE=1 "
                   "GALLIUM_DRIVER=llvmpipe /usr/bin/blender --factory-startup "
                   f"> /tmp/{root.name}/blender3.log 2>&1 </dev/null &")
        core._shell(guest, command)
        for seconds in (15, 45, 90, 150):
            time.sleep(seconds if seconds == 15 else seconds - previous)
            shot = guest.screenshot(patience=45)
            label = f"blender3-after-{seconds}s"
            (root / "screenshots" / f"{label}.png").write_bytes(shot)
            (root / f"{label}.json").write_text(json.dumps({
                "active_window": guest.active_window(),
                "frame_ready": _blender_frame_ready(shot)}, indent=2) + "\n")
            previous = seconds
        log = core._shell(guest, f"cat /tmp/{root.name}/blender3.log")
        (root / "blender3_guest.log").write_text(log.get("output", ""))
        print(json.dumps({"run_id": root.name, "container_id": container_id,
                          "last_frame": f"screenshots/blender3-after-150s.png"}))
    finally:
        if guest_env is not None:
            guest_env.close()


if __name__ == "__main__":
    main()
