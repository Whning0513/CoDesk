"""The shared Guest: a booted OSWorld ``DesktopEnv`` plus direct calls to its in-VM HTTP server.

Several agents use one ``Guest`` from different threads; every call here is a stateless HTTP request.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests


class InfraError(RuntimeError):
    """The Guest or the host failed, not the agent. Messages start with "INFRA" so result filters can find them."""

    def __init__(self, message: str):
        super().__init__(message if message.startswith("INFRA") else f"INFRA: {message}")


class Guest:
    def __init__(self, env: Any):
        self.env = env

    @property
    def url(self) -> str:
        """Base URL of the in-VM server (screenshot, execute, ...), e.g. for an external harness or MCP server."""
        return f"http://{self.env.vm_ip}:{self.env.server_port}"

    def execute(self, argv: list[str], timeout: float = 60) -> dict:
        r = requests.post(f"{self.url}/execute", json={"command": argv, "shell": False, "timeout": 30},
                          timeout=(5, timeout))
        r.raise_for_status()
        return r.json()

    def active_window(self) -> str | None:
        """Title of the focused window, recorded before every action (cross-agent interference metric)."""
        try:
            out = self.execute(["bash", "-lc", "xdotool getactivewindow getwindowname 2>/dev/null || true"], 30)
            return (out.get("output") or "").strip() or None
        except Exception:
            return None

    def screenshot(self, patience: float | None = None) -> bytes:
        """Get image bytes with a bounded local wall time, including retries.

        A run-owned helper is terminated and reaped on timeout/interruption;
        an already-started read-only request may still finish in the Guest.
        """
        patience = float(os.environ.get("OSCOMBO_SHOT_PATIENCE", "120")) if patience is None else patience
        deadline = time.monotonic() + patience
        if patience <= 0:
            raise InfraError("Guest screenshot deadline expired")
        worker = Path(__file__).with_name("guest_screenshot_worker.py")
        # Keep provider/model keys out of the helper.  The in-Guest endpoint
        # is local HTTP and requires no upstream provider credentials.
        env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
        proc = subprocess.Popen([sys.executable, "-I", str(worker), self.env.controller.http_server, str(patience)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(proc.args, patience)
            shot, _ = proc.communicate(timeout=remaining)
            if proc.returncode == 0 and shot:
                return shot
        except subprocess.TimeoutExpired as exc:
            raise InfraError(f"Guest screenshot exceeded {patience:.1f} s deadline") from exc
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
        raise InfraError(f"no Guest screenshot within {patience:.1f} s")

    def accessibility_tree(self) -> str | None:
        return self.env.controller.get_accessibility_tree()

    def run_pyautogui(self, code: str) -> Any:
        return self.env.controller.execute_python_command(code)

    def quiet_notifications(self) -> None:
        """GNOME notification banners (e.g. "Low Disk Space") can cover click targets; turn them off."""
        self.execute(["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", "false"])
