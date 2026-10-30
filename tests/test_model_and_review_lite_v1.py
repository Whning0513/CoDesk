"""Offline Oracle controls; real Blender and Guest checks are recorded separately."""
from copy import deepcopy
from io import BytesIO
import os
from pathlib import Path

import pytest
from PIL import Image

from oscombo.collab.model_and_review_lite_v1.oracle import evaluate_snapshots, evaluate
from oscombo.collab.lite_file_guest_pilot import (
    _blender_frame_ready, _blender_quick_setup_visible, _blender_welcome_visible,
)


def test_blender_readiness_rejects_black_viewport():
    for color, expected in (((0, 0, 0), False), ((255, 255, 255), False),
                            ((66, 66, 66), True)):
        frame = Image.new("RGB", (1280, 720), color)
        buffer = BytesIO()
        frame.save(buffer, format="PNG")
        assert _blender_frame_ready(buffer.getvalue()) is expected


def test_blender_first_run_splash_detection():
    frame = Image.new("RGB", (1920, 1080), (63, 63, 63))
    buffer = BytesIO()
    frame.save(buffer, format="PNG")
    assert not _blender_quick_setup_visible(buffer.getvalue())
    frame.putpixel((800, 350), (1, 15, 30))
    frame.putpixel((900, 450), (15, 30, 45))
    buffer = BytesIO()
    frame.save(buffer, format="PNG")
    assert _blender_quick_setup_visible(buffer.getvalue())


def test_blender_welcome_card_detection():
    frame = Image.new("RGB", (1920, 1080), (63, 63, 63))
    frame.putpixel((800, 350), (248, 248, 248))
    frame.putpixel((900, 450), (10, 28, 42))
    buffer = BytesIO()
    frame.save(buffer, format="PNG")
    assert _blender_welcome_visible(buffer.getvalue())


def scenes():
    common = {
        "Lamp_Base": {"type": "MESH", "dimensions": [1.0, 1.0, 0.12], "location": [0, 0, 0.06],
                      "rotation": [0, 0, 0], "mesh_sha256": "base", "materials": []},
        "Lamp_Bulb": {"type": "MESH", "dimensions": [0.5, 0.5, 0.5], "location": [0, 0, 1.7],
                      "rotation": [0, 0, 0], "mesh_sha256": "bulb", "materials": []},
        "Lamp_Shade": {"type": "MESH", "dimensions": [1.2, 1.2, 0.6], "location": [0, 0, 1.7],
                       "rotation": [0, 0, 0], "mesh_sha256": "shade", "materials": []},
        "Camera_Main": {"type": "CAMERA", "dimensions": [1, 1, 1], "location": [3, -4, 2],
                        "rotation": [0, 0, 0], "lens_mm": 50},
    }
    initial = {"scene_name": "Lamp_Lite_Review", "objects": common}
    final = deepcopy(initial)
    final["objects"]["Lamp_Shade"]["dimensions"] = [1.46, 1.46, 0.6]
    return initial, final


def test_gold_and_equivalent_review_phrasing():
    initial, final = scenes()
    for text in ("Shade width: 1.46 m\nRadial clearance: 0.48 m\nVerdict: PASS",
                 "灯罩宽度：1.46 m\n径向净空：0.48 m\n结论：达标"):
        result = evaluate_snapshots(initial, final, text)
        assert result["joint_success"]
        assert result["actor_subscores"] == {"A": True, "B": True}


def test_wrong_geometry_or_report_fails_independently():
    initial, final = scenes()
    good_report = "Shade width: 1.46 m\nRadial clearance: 0.48 m\nVerdict: adequate"
    wrong_report = "Shade width: 1.20 m\nRadial clearance: 0.35 m\nVerdict: fail"
    assert not evaluate_snapshots(initial, final, wrong_report)["actor_subscores"]["B"]
    final["objects"]["Lamp_Shade"]["dimensions"] = [1.30, 1.30, 0.6]
    result = evaluate_snapshots(initial, final, good_report)
    assert not result["actor_subscores"]["A"]
    assert not result["joint_success"]
    final["objects"]["Lamp_Base"]["location"] = [1, 0, 0.06]
    assert not evaluate_snapshots(initial, final, good_report)["checks"]["protected_objects"]


def test_real_blender_gold_and_initial_negative(tmp_path):
    blender = os.environ.get("CODESK_BLENDER_BIN")
    fixture = Path(__file__).resolve().parents[1] / "oscombo/collab/model_and_review_lite_v1/fixtures"
    if not blender or not (fixture / "Lamp_Review.blend").exists():
        pytest.skip("matching Blender 5.0 and generated Lite fixture are required")
    report = tmp_path / "review.txt"
    report.write_text("Shade width: 1.46 m\nRadial clearance: 0.48 m\nVerdict: PASS\n")
    positive = evaluate(fixture / "Lamp_Review.blend", fixture / "private/gold.blend",
                        fixture / "shade_review.txt", report, blender)
    assert positive["joint_success"]
    negative = evaluate(fixture / "Lamp_Review.blend", fixture / "Lamp_Review.blend",
                        fixture / "shade_review.txt", report, blender)
    assert not negative["joint_success"]
    assert not negative["actor_subscores"]["A"]
    report.write_text("Shade width: 1.30 m\nRadial clearance: 0.40 m\nVerdict: PASS\n")
    wrong_width = evaluate(fixture / "Lamp_Review.blend", fixture / "private/wrong_width.blend",
                           fixture / "shade_review.txt", report, blender)
    assert wrong_width["actor_subscores"] == {"A": False, "B": True}
    bad_review = evaluate(fixture / "Lamp_Review.blend", fixture / "private/gold.blend",
                          fixture / "shade_review.txt", report, blender)
    assert bad_review["actor_subscores"] == {"A": True, "B": False}
