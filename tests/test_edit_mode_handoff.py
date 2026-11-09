from pathlib import Path

from oscombo.collab.edit_mode_handoff.fixtures import (
    INITIAL_LINES,
    build_fixture,
    render_fodt,
)
from oscombo.collab.edit_mode_handoff.oracle import evaluate, evaluate_controls
from oscombo.collab.edit_mode_handoff.spec import EXPECTED_LINES


def test_fixture_positive_and_overwrite_negative_controls(tmp_path: Path) -> None:
    build_fixture(tmp_path)
    result = evaluate_controls(tmp_path)
    assert result["controls_pass"] is True
    assert result["gold_joint_pass"] is True
    assert result["overwrite_negative_fail"] is True
    assert result["overwrite_signature"] == "Release status: STATUS | READY OR-REVIEW"


def test_shared_oracle_requires_all_exact_lines(tmp_path: Path) -> None:
    (tmp_path / "release_notice.fodt").write_bytes(render_fodt(EXPECTED_LINES))
    assert evaluate(tmp_path, "shared")["joint_success"] is True

    negative = list(EXPECTED_LINES)
    negative[0] = "Release status: STATUS | READY OR-REVIEW"
    (tmp_path / "release_notice.fodt").write_bytes(render_fodt(tuple(negative)))
    score = evaluate(tmp_path, "shared")
    assert score["joint_success"] is False
    assert score["actor_success"] == {"A": False, "B": True}


def test_isolated_oracle_scores_assigned_edits_and_guard(tmp_path: Path) -> None:
    a_lines = list(INITIAL_LINES)
    a_lines[0] = EXPECTED_LINES[0]
    b_lines = list(INITIAL_LINES)
    b_lines[1] = EXPECTED_LINES[1]
    (tmp_path / "release_notice_A.fodt").write_bytes(render_fodt(tuple(a_lines)))
    (tmp_path / "release_notice_B.fodt").write_bytes(render_fodt(tuple(b_lines)))
    assert evaluate(tmp_path, "isolated")["joint_success"] is True

    b_lines[2] = "Guard phrase: altered"
    (tmp_path / "release_notice_B.fodt").write_bytes(render_fodt(tuple(b_lines)))
    score = evaluate(tmp_path, "isolated")
    assert score["joint_success"] is False
    assert score["actor_success"] == {"A": True, "B": False}
