from __future__ import annotations

import json
import multiprocessing
import queue

import pytest


def _hold_input_lock(path, ready, release):
    import oscombo.desktop_tools as dt
    dt.GUI_INPUT_LOCK_PATH = path
    with dt._gui_input_lock() as state:
        ready.put(state["wait_s"])
        release.wait(5)


def _probe_input_lock(path, started, result):
    import oscombo.desktop_tools as dt
    dt.GUI_INPUT_LOCK_PATH = path
    started.put(True)
    with dt._gui_input_lock() as state:
        result.put(state["wait_s"])


def test_gui_input_lock_serializes_separate_mcp_processes(tmp_path):
    ctx = multiprocessing.get_context("fork")
    ready, started, result = ctx.Queue(), ctx.Queue(), ctx.Queue()
    release = ctx.Event()
    path = str(tmp_path / "shared-gui-input.lock")
    first = ctx.Process(target=_hold_input_lock, args=(path, ready, release))
    second = ctx.Process(target=_probe_input_lock, args=(path, started, result))
    try:
        first.start()
        assert ready.get(timeout=5) >= 0
        second.start()
        assert started.get(timeout=5)
        with pytest.raises(queue.Empty):
            result.get(timeout=0.2)
        release.set()
        assert result.get(timeout=5) >= 0.15
    finally:
        release.set()
        for proc in (first, second):
            if proc.pid is not None:
                proc.join(timeout=5)
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=5)
    assert first.exitcode == second.exitcode == 0


def test_screenshot_coordinate_mapping_and_bounds():
    from oscombo.desktop_tools import _coordinate_audit

    assert _coordinate_audit("click", {"x": 1279, "y": 719}, [1.5, 1.5], [1920, 1080])["status"] == "accepted"
    audit = _coordinate_audit("click", {"x": 127, "y": 966}, [1.5, 1.5], [1920, 1080])
    assert audit["status"] == "rejected"
    assert audit["raw_model_coordinates"] == {"x": 127, "y": 966}
    assert audit["mapped_guest_coordinates"] == [190, 1449]
    assert audit["reason"] == "y_outside_model_screenshot_[0,720)"


def test_drag_validates_both_endpoints_and_requires_observation():
    from oscombo.desktop_tools import _coordinate_audit

    audit = _coordinate_audit("drag", {"x1": 10, "y1": 20, "x2": 30, "y2": 800},
                              [1.5, 1.5], [1920, 1080])
    assert audit["status"] == "rejected"
    assert audit["reason"] == "y2_outside_model_screenshot_[0,720)"
    assert audit["mapped_guest_coordinates"] == {"start": [15, 30], "end": [45, 1200]}
    assert _coordinate_audit("move", {"x": 1, "y": 1}, [1.5, 1.5], None)["reason"] == "no_observation_yet"
    assert _coordinate_audit("click", {"x": [195, 314]}, [1.5, 1.5], [1920, 1080])["reason"] == \
        "coordinate_missing_or_non_numeric"


def test_out_of_bounds_action_is_rejected_without_guest_action_and_returns_fresh_image(
        tmp_path, monkeypatch):
    import oscombo.desktop_tools as dt

    log = tmp_path / "actions.jsonl"
    monkeypatch.setattr(dt, "LOG", str(log))
    monkeypatch.setattr(dt, "BUDGET", 10)
    monkeypatch.setattr(dt, "SETTLE", 0)
    monkeypatch.setattr(dt, "_active_window", lambda: "Calc")
    monkeypatch.setattr(dt, "_py", lambda _code: (_ for _ in ()).throw(AssertionError("must not execute")))
    png = b"fresh-observation"
    shots = iter([(png, [1.5, 1.5], [1920, 1080]), (png, [1.5, 1.5], [1920, 1080])])
    monkeypatch.setattr(dt, "_shot", lambda: next(shots))

    assert dt.run_tool("screenshot", {}) == ("OK.", png)
    message, image = dt.run_tool("click", {"x": 127, "y": 966})
    assert image == png
    assert "REJECTED" in message and "No coordinate was clamped or corrected" in message
    records = [json.loads(line) for line in log.read_text().splitlines()]
    reject = records[1]
    assert reject["executed"] is False and reject["code"] is None
    assert reject["coordinate_audit"]["raw_model_coordinates"] == {"x": 127, "y": 966}
    assert reject["coordinate_audit"]["mapped_guest_coordinates"] == [190, 1449]
    assert reject["returned_observation"]["guest_screenshot_size"] == [1920, 1080]
    assert (tmp_path / "shots" / "002.png").read_bytes() == png


def test_in_bounds_action_records_unmodified_raw_and_mapped_coordinates(tmp_path, monkeypatch):
    import oscombo.desktop_tools as dt

    log = tmp_path / "actions.jsonl"
    monkeypatch.setattr(dt, "LOG", str(log))
    monkeypatch.setattr(dt, "BUDGET", 10)
    monkeypatch.setattr(dt, "SETTLE", 0)
    monkeypatch.setattr(dt, "GUI_INPUT_LOCK_PATH", str(tmp_path / "gui-input.lock"))
    monkeypatch.setattr(dt, "_active_window", lambda: "Impress")
    executed = []
    monkeypatch.setattr(dt, "_py", executed.append)
    monkeypatch.setattr(dt, "_shot", lambda: (b"frame", [1.5, 1.5], [1920, 1080]))
    dt.run_tool("screenshot", {})
    dt.run_tool("click", {"x": 100, "y": 416})
    assert executed == ["pyautogui.click(150, 624, clicks=1, interval=0.08, button='left')"]
    record = [json.loads(line) for line in log.read_text().splitlines()][1]
    assert record["coordinate_audit"]["status"] == "accepted"
    assert record["coordinate_audit"]["raw_model_coordinates"] == {"x": 100, "y": 416}
    assert record["coordinate_audit"]["mapped_guest_coordinates"] == [150, 624]
    assert record["input_lock"]["enabled"] is True
    assert record["input_lock"]["held_s"] >= 0


def test_tool_result_cooldown_throttles_model_turns_and_is_observable(monkeypatch):
    import oscombo.desktop_tools as dt

    now = [100.0]
    sleeps = []
    monkeypatch.setattr(dt, "TOOL_RESULT_COOLDOWN", 60.0)
    monkeypatch.setattr(dt, "_last_tool_result_at", None)
    monkeypatch.setattr(dt.time, "monotonic", lambda: now[0])

    def fake_sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(dt.time, "sleep", fake_sleep)
    assert dt._wait_before_tool_result() == 60.0
    now[0] += 10
    assert dt._wait_before_tool_result() == 50.0
    now[0] += 65
    assert dt._wait_before_tool_result() == 0.0
    assert sleeps == [60.0, 50.0]
