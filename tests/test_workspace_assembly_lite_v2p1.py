"""Version isolation and independent, evidence-based v2.1 scoring."""
from pathlib import Path
import pytest
from oscombo.collab import lite_file_guest_pilot as runner
from oscombo.collab.workspace_assembly_lite_v2 import oracle as old_oracle, spec as old_spec
from oscombo.collab.workspace_assembly_lite_v2p1 import fixtures, oracle, spec


@pytest.fixture
def setup_case(tmp_path):
    root = tmp_path / 'fixture'
    manifest = fixtures.build_fixture(root, inspection_tag='BIRCH-42')
    delivery = tmp_path / 'inspection_note.txt'
    delivery.write_bytes((root / 'inspection_note.txt').read_bytes())
    report = tmp_path / 'report.odt'
    def score(audience, attachment, scorer=oracle):
        fixtures.report_odt(report, audience, attachment)
        return scorer.evaluate(root / 'inspection_note.txt', tmp_path / 'incoming-missing', delivery,
                               root / 'handoff_report.odt', report)
    return manifest, score


def test_version_isolation_and_runner_profile(setup_case):
    manifest, score = setup_case
    assert spec.CASE_ID != old_spec.CASE_ID and spec.CASE_VERSION == '2.1.0'
    assert manifest['case_id'] == spec.CASE_ID and manifest['case_version'] == spec.CASE_VERSION
    assert runner._profile('workspace_assembly_v2p1') == (spec, fixtures, oracle)
    assert runner._profile('workspace_assembly_v2')[2] is old_oracle
    assert spec.AGENT_A_INSTRUCTION == old_spec.AGENT_A_INSTRUCTION
    assert spec.AGENT_B_INSTRUCTION == old_spec.AGENT_B_INSTRUCTION
    assert score('Audience: operations reviewers', None)['actors']['B']['checks']['draft_text_preserved']
    assert not score('Audience: operations reviewers', None, old_oracle)['actors']['B']['checks']['draft_text_preserved']


@pytest.mark.parametrize('audience', ['Audience: Operations', 'Audience: operations team',
                                     'Audience: operations reviewers', 'For: Operations reviewers.'])
def test_valid_audience_equivalents_and_correct_handoff(setup_case, audience):
    _, score = setup_case
    result = score(audience, 'Attachment: inspection_note.txt; tag BIRCH-42.')
    assert result['actors']['A']['success'] and result['actors']['B']['success'] and result['joint_success']


@pytest.mark.parametrize('audience', ['Audience: finance reviewers', 'Audience: non-operations reviewers',
                                     'Audience: operations and finance reviewers', 'Audience: operations review',
                                     'Audience: operations reviewers and managers'])
def test_incorrect_or_mixed_audience_rejected(setup_case, audience):
    _, score = setup_case
    result = score(audience, 'Attachment: inspection_note.txt; tag BIRCH-42.')
    assert not result['actors']['B']['checks']['audience_matches_draft'] and not result['joint_success']


def test_partial_checks_are_independent_and_missing_attachment_and_tag_rejected(setup_case):
    _, score = setup_case
    result = score('Audience: operations reviewers', None)
    checks = result['actors']['B']['checks']
    assert checks['draft_text_preserved'] and checks['audience_matches_draft']
    assert not checks['attachment_not_empty'] and not result['joint_success']
    result = score('Audience: Operations', 'Attachment: inspection_note.txt')
    assert result['actors']['B']['checks']['attachment_named']
    assert not result['actors']['B']['checks']['tag_matches_delivered'] and not result['joint_success']
    result = score('Audience: Operations', 'Attachment: inspection_note.txt; tag WRONG-00')
    assert not result['actors']['B']['checks']['tag_matches_delivered'] and not result['joint_success']
    result = score('Audience: Operations', 'Attachment: fakeinspection_note.txt; tag BIRCH-42')
    assert not result['actors']['B']['checks']['attachment_named'] and not result['joint_success']


def test_a_delivery_and_b_local_content_scored_independently(tmp_path):
    root = tmp_path / 'fixture'
    fixtures.build_fixture(root, inspection_tag='BIRCH-42')
    delivered = tmp_path / 'inspection_note.txt'
    altered = (root / 'inspection_note.txt').read_text().replace('BIRCH-42', 'CEDAR-17')
    delivered.write_text(altered)
    report = tmp_path / 'report.odt'
    fixtures.report_odt(report, 'Audience: Operations reviewers', 'inspection_note.txt has tag CEDAR-17.')
    result = oracle.evaluate(root / 'inspection_note.txt', tmp_path / 'incoming-missing', delivered,
                             root / 'handoff_report.odt', report)
    assert result['actors']['A']['success'] is False
    assert result['actors']['B']['success'] is True
    assert result['actors']['B']['global_checks']['tag_matches_source'] is False
    assert result['joint_success'] is False
    delivered.unlink()
    result = oracle.evaluate(root / 'inspection_note.txt', tmp_path / 'incoming-missing', delivered,
                             root / 'handoff_report.odt', report)
    assert result['actors']['B']['success'] is None and not result['actors']['B']['handoff_verifiable']
    assert result['actors']['B']['checks']['draft_text_preserved'] is True
    assert result['actors']['B']['checks']['audience_matches_draft'] is True
