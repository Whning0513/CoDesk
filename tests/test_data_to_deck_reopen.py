"""Postscore reopen must tolerate an Actor closing a saved peer window."""
from types import SimpleNamespace

import pytest

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


def test_unsaved_dialog_is_not_answered_by_postscore_reopen(monkeypatch):
    def activate(guest, path, phase):
        raise RuntimeError("could not activate 'forecast.ods'; active window is 'Save Document?'")

    monkeypatch.setattr(live_pilot, "_activate_ready_document", activate)
    monkeypatch.setattr(live_pilot, "_launch",
                        lambda *args: pytest.fail("must not reopen through an unsaved dialog"))
    guest = SimpleNamespace(active_window=lambda: "Save Document?")
    with pytest.raises(RuntimeError, match="could not activate"):
        live_pilot._prepare_saved_document_reopen(
            guest, "/task/forecast.ods", "reopen-A-before", "calc", "/tmp/reopen.log", True)
