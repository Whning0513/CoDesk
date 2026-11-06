from pathlib import Path


def test_case7_driver_disables_external_provider_bytecode_writes() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "audits/three_lite_cases_20261029/run_case7_v2_one.sh").read_text()
    setting = script.index("export PYTHONDONTWRITEBYTECODE=1")
    interpreter = script.index('python="${OSWORLD_DIR%/}/.venv/bin/python"')
    assert setting < interpreter
