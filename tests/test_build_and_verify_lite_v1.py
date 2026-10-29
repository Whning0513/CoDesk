from oscombo.collab.build_and_verify_lite_v1.fixtures import build_fixture
from oscombo.collab.build_and_verify_lite_v1.oracle import evaluate


def test_positive_and_negative_artifacts(tmp_path):
    fixture = tmp_path / "fixture"
    build_fixture(fixture)
    source = fixture / "orderdesk.html"
    qa = fixture / "qa_note.txt"
    a = tmp_path / "saved.html"
    b = tmp_path / "note.txt"
    a.write_text(source.read_text().replace('value="delievered"', 'value="delivered"'))
    b.write_text("Query: North\nStatus: Delivered\nVisible order IDs: OD-104\nSaved source: orderdesk.html\n")
    assert evaluate(source, a, qa, b)["joint_success"]
    a.write_text(source.read_text())
    assert not evaluate(source, a, qa, b)["joint_success"]
    a.write_text(source.read_text().replace('value="delievered"', 'value="delivered"'))
    b.write_text("Query: North\nStatus: Delivered\nVisible order IDs: OD-105\nSaved source: orderdesk.html\n")
    assert not evaluate(source, a, qa, b)["actors"]["B"]["success"]
