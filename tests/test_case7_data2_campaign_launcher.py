from pathlib import Path


def test_case7_campaign_launcher_fails_closed_to_the_dedicated_data2_daemon() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "audits/three_lite_cases_20261029/run_case7_v2p2_campaign_data2.sh").read_text()
    assert "source env.local.sh" in script
    assert "export PYTHONDONTWRITEBYTECODE=1" in script
    assert "unix:///data2/whn/codesk-runs/case7-docker-data2/docker.sock" in script
    assert "/data2/whn/codesk-runs/case7-docker-data2/data" in script
    assert script.index("[[ -S \"$case7_socket\"") < script.index("docker info --format")
    assert "exec \"$case7_python\" -m oscombo.collab.workspace_assembly_lite_v2.campaign" in script
