from oscombo.collab.workspace_assembly_lite_v1.fixtures import build_fixture, report_odt
from oscombo.collab.workspace_assembly_lite_v1.oracle import evaluate


def test_positive_and_negative_artifacts(tmp_path):
    fixture = tmp_path / "fixture"
    build_fixture(fixture)
    incoming = tmp_path / "incoming" / "inspection_note.txt"
    incoming.parent.mkdir()
    incoming.write_bytes((fixture / "inspection_note.txt").read_bytes())
    delivered = tmp_path / "delivery" / "inspection_note.txt"
    delivered.parent.mkdir()
    final = tmp_path / "final.odt"
    report_odt(final, "Delivered inspection_note.txt carries inspection tag RIVER-27.")
    incoming.rename(delivered)
    positive = evaluate(fixture / "inspection_note.txt", incoming, delivered,
                        fixture / "handoff_report.odt", final)
    assert positive["joint_success"]
    incoming.write_bytes(delivered.read_bytes())
    assert not evaluate(fixture / "inspection_note.txt", incoming, delivered,
                        fixture / "handoff_report.odt", final)["actors"]["A"]["success"]
    incoming.unlink()
    report_odt(final, "Delivered inspection_note.txt carries inspection tag WRONG.")
    assert not evaluate(fixture / "inspection_note.txt", incoming, delivered,
                        fixture / "handoff_report.odt", final)["actors"]["B"]["success"]
