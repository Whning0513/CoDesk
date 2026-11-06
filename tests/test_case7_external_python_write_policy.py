from pathlib import Path


def test_case7_driver_disables_external_provider_bytecode_writes() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "audits/three_lite_cases_20261029/run_case7_v2_one.sh").read_text()
    setting = script.index("export PYTHONDONTWRITEBYTECODE=1")
    interpreter = script.index('python="${OSWORLD_DIR%/}/.venv/bin/python"')
    assert setting < interpreter


def test_case7_v2p2_slot_and_relay_disable_external_bytecode_writes(monkeypatch) -> None:
    from oscombo.collab.data_to_deck.live_pilot import _codex_compat_relay_environment

    root = Path(__file__).resolve().parents[1]
    script = (root / "audits/three_lite_cases_20261029/run_case7_v2p2_one.sh").read_text()
    setting = script.index("export PYTHONDONTWRITEBYTECODE=1")
    interpreter = script.index('python="${OSWORLD_DIR%/}/.venv/bin/python"')
    assert setting < interpreter

    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("CASE7_TEST_PROVIDER_KEY", "offline-test-only")
    monkeypatch.setenv("UNRELATED_API_KEY", "must-not-be-forwarded")
    relay_env = _codex_compat_relay_environment(
        "CASE7_TEST_PROVIDER_KEY", "CASE7_TEST_RELAY_TOKEN", "relay-test-only")
    assert relay_env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert relay_env["CASE7_TEST_PROVIDER_KEY"] == "offline-test-only"
    assert relay_env["CASE7_TEST_RELAY_TOKEN"] == "relay-test-only"
    assert "UNRELATED_API_KEY" not in relay_env
