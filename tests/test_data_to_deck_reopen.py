"""Postscore reopen must tolerate an Actor closing a saved peer window."""
from types import SimpleNamespace
from io import BytesIO

import pytest
from PIL import Image

from oscombo.collab.data_to_deck import live_pilot


def test_saved_model_file_is_reopened_if_its_window_was_closed(monkeypatch):
    calls = []

    def activate(guest, path, phase):
        calls.append(("activate", phase))
        if len([event for event in calls if event[0] == "activate"]) == 1:
            raise RuntimeError("could not activate 'forecast.ods'; active window is 'order_plan.ods'")

    monkeypatch.setattr(live_pilot, "_activate_ready_document", activate)
    monkeypatch.setattr(live_pilot, "_launch",
                        lambda guest, app, path, log: calls.append(("launch", app, path)))
    guest = SimpleNamespace(active_window=lambda: "order_plan.ods - LibreOffice Calc")
    assert live_pilot._prepare_saved_document_reopen(
        guest, "/task/forecast.ods", "reopen-A-before", "calc", "/tmp/reopen.log", True)
    assert calls == [("activate", "reopen-A-before"),
                     ("launch", "calc", "/task/forecast.ods"),
                     ("activate", "reopen-A-before-restored")]


def test_postscore_discard_clears_modal_before_reopen(monkeypatch):
    calls = []
    state = {"window": "Save Document?"}

    def discard(*_args):
        calls.append("discard")
        state["window"] = "Desktop"
        return True

    def activate(guest, path, phase):
        calls.append("activate")
        if len([x for x in calls if x == "activate"]) == 1:
            raise RuntimeError("could not activate 'forecast.ods'; active window is 'Desktop'")

    monkeypatch.setattr(live_pilot, "_discard_postscore_unsaved_dialog", discard)
    monkeypatch.setattr(live_pilot, "_activate_ready_document", activate)
    monkeypatch.setattr(live_pilot, "_launch",
                        lambda *_args: calls.append("launch"))
    guest = SimpleNamespace(active_window=lambda: state["window"])
    assert live_pilot._prepare_saved_document_reopen(
        guest, "/task/forecast.ods", "reopen-A-before", "calc", "/tmp/reopen.log", True)
    assert calls == ["discard", "activate", "launch", "activate"]


def test_postscore_cancels_stale_open_chooser_before_reopening(monkeypatch):
    calls = []
    state = {"window": "Open"}

    def press(script):
        calls.append("escape")
        state["window"] = "order_plan.ods - LibreOffice Calc"

    guest = SimpleNamespace(active_window=lambda: state["window"], run_pyautogui=press)
    monkeypatch.setattr(live_pilot, "_activate_ready_document",
                        lambda *_args: calls.append("activate"))
    monkeypatch.setattr(live_pilot, "_launch",
                        lambda *_args: pytest.fail("document is already open"))
    assert not live_pilot._prepare_saved_document_reopen(
        guest, "/task/order_plan.ods", "reopen-B-before", "calc", "/tmp/reopen.log", True)
    assert calls == ["escape", "activate"]


def test_postscore_unsaved_dialog_is_captured_then_discarded(tmp_path):
    (tmp_path / "screenshots").mkdir()
    image = BytesIO()
    Image.new("RGB", (1920, 1080), "white").save(image, format="PNG")
    state = {"window": "Save Document?"}
    calls = []

    def click(script):
        calls.append(script)
        state["window"] = "Desktop"

    guest = SimpleNamespace(root=tmp_path, guest_key="shared", actor="A",
                            active_window=lambda: state["window"],
                            screenshot=lambda patience: image.getvalue(),
                            run_pyautogui=click)
    assert live_pilot._discard_postscore_unsaved_dialog(guest, "reopen-B-close")
    assert "pyautogui.click(783, 614)" in calls[0]
    assert (tmp_path / "screenshots/reopen-B-close-unsaved-dialog.png").exists()
    assert guest.actor == "system"
