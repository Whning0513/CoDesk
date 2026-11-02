"""Independent v2 offline controls, not a substitute for real Guest GUI."""
from copy import deepcopy
from io import BytesIO
import hashlib
import os
from pathlib import Path

import pytest
from PIL import Image

from oscombo.collab.model_and_review_lite_v2 import fixtures, gold, oracle, spec
from oscombo.collab.lite_file_guest_pilot import _blender_xy_dimension_candidate, _profile, _scripted_actions


def test_v2_blender_candidate_real_frames_and_negative_controls():
    evidence = Path(__file__).resolve().parent / 'fixtures/case5_v2_blender'
    old = (evidence / 'pre_handoff.png').read_bytes()
    new = (evidence / 'reverted.png').read_bytes()
    assert not _blender_xy_dimension_candidate(old, old)['candidate']
    observed = _blender_xy_dimension_candidate(old, new)
    assert observed['candidate'] and min(observed['changed_pixels']) >= 4
    assert observed['mask_overlap'] >= .7
    assert 'not' in observed['scope']
    # Completely unpainted and one-axis-only frames cannot pass merely because
    # some bytes differ. Numeric interpretation remains human review.
    for color in (0, 255):
        out = BytesIO()
        Image.new('L', (1920, 1080), color).save(out, format='PNG')
        assert not _blender_xy_dimension_candidate(old, out.getvalue())['candidate']
    with Image.open(BytesIO(new)) as newer, Image.open(BytesIO(old)) as older:
        frame = newer.convert('RGB')
        frame.paste(older.crop((1500, 484, 1550, 503)), (1500, 484))
        out = BytesIO()
        frame.save(out, format='PNG')
    assert not _blender_xy_dimension_candidate(old, out.getvalue())['candidate']


def test_v2_blender_candidate_rejects_geometry_changes():
    old = BytesIO(); new = BytesIO()
    Image.new('L', (1920, 1080), 50).save(old, format='PNG')
    Image.new('L', (1280, 720), 50).save(new, format='PNG')
    with pytest.raises(RuntimeError, match='changed resolution'):
        _blender_xy_dimension_candidate(old.getvalue(), new.getvalue())


def test_v2_public_fixture_and_prompts_do_not_disclose_private_gold(tmp_path):
    fixtures.build_fixture(tmp_path / "public")
    public = tmp_path / "public"
    assert {p.name for p in public.iterdir()} == set(spec.FIXTURE_NAMES.values())
    assert not (public / "private").exists()
    assert "1.25" not in spec.AGENT_B_INSTRUCTION and "1.50" not in spec.AGENT_B_INSTRUCTION
    assert "1.25" not in spec.PUBLIC_BRIEF and "1.50" not in spec.PUBLIC_BRIEF
    assert "1.25" in spec.AGENT_A_INSTRUCTION
    assert _profile("model_review_v2")[0].CASE_ID == "CDD-MAR-LITE-002"
    actions = _scripted_actions("model_review_v2", "A", "/tmp/test", fixtures, False)
    assert any("'1.25'" in action for action in actions)
    assert spec.CASE_ID != "CDD-MAR-LITE-001"


def test_v2_saved_scene_and_review_must_agree():
    common = {"Lamp_Base": {"type": "MESH"}, "Lamp_Bulb": {"type": "MESH", "dimensions": [.5,.5,.5]},
              "Camera_Main": {"type": "CAMERA"},
              "Lamp_Shade": {"dimensions": [1.2,1.2,.6], "mesh_sha256": "mesh",
                             "materials": ["green"], "location": [0,0,1.7], "rotation": [0,0,0]}}
    initial = {"scene_name": gold.SCENE_NAME, "objects": common}
    final = deepcopy(initial)
    final["objects"]["Lamp_Shade"]["dimensions"] = [1.5,1.5,.6]
    assert oracle.evaluate_snapshots(initial, final, "Shade width: 1.50\nRadial clearance: 0.50\nVerdict: PASS")['joint_success']
    assert not oracle.evaluate_snapshots(initial, final, "Shade width: 1.20\nRadial clearance: 0.35\nVerdict: FAIL")['actor_subscores']['B']
    final["objects"]["Lamp_Shade"]["dimensions"][1] = 1.3
    assert not oracle.evaluate_snapshots(initial, final, "Shade width: 1.50\nRadial clearance: 0.50\nVerdict: PASS")['actor_subscores']['A']


def test_v2_real_blender_gold_and_wrong_width_controls(tmp_path):
    binary = os.environ.get("CODESK_BLENDER_BIN")
    if not binary:
        pytest.skip("matching host Blender required")
    fixture = Path(fixtures.ROOT)
    report = tmp_path / "report.txt"
    report.write_text("Shade width: 1.50 m\nRadial clearance: 0.50 m\nVerdict: PASS\n")
    initial, gold_path = fixture / "Lamp_Review.blend", fixture / "private/gold.blend"
    good = oracle.evaluate(initial, gold_path, fixture / "shade_review.txt", report, binary)
    assert good['actor_subscores'] == {'A': True, 'B': True}
    report.write_text("Shade width: 1.30 m\nRadial clearance: 0.40 m\nVerdict: PASS\n")
    wrong = oracle.evaluate(initial, fixture / "private/wrong_width.blend", fixture / "shade_review.txt", report, binary)
    assert wrong['actor_subscores'] == {'A': False, 'B': True}
    assert not wrong['joint_success']
    assert hashlib.sha256(initial.read_bytes()).hexdigest() != hashlib.sha256(gold_path.read_bytes()).hexdigest()
