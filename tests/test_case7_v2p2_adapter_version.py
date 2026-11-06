"""Task and adapter version provenance must remain distinct and fail closed."""
from __future__ import annotations

import json

import pytest

from oscombo.collab.workspace_assembly_lite_v2p2 import campaign, freeze, spec


@pytest.mark.parametrize("bad_record", ["provenance", "result", "artifact_manifest"])
def test_freeze_rejects_missing_or_old_adapter_version(tmp_path, bad_record):
    run = tmp_path / "run-001"
    run.mkdir()
    records = {
        "provenance": spec.version_manifest(),
        "result": spec.version_manifest(),
        "artifact_manifest": spec.version_manifest(),
    }
    if bad_record == "artifact_manifest":
        records[bad_record]["adapter_version"] = "2.2.0"
    else:
        records[bad_record].pop("adapter_version")
    for name, record in records.items():
        filename = {"provenance": "provenance.json", "result": "result.json",
                    "artifact_manifest": "artifact_manifest.json"}[name]
        (run / filename).write_text(json.dumps(record))

    with pytest.raises(ValueError, match="wrong or missing adapter version"):
        freeze._common(run, "source-commit", "fixture-seed", "isolated")


def test_campaign_refuses_old_adapter_freeze_before_reserving_slot(tmp_path):
    freeze_path = tmp_path / "freeze.json"
    frozen = {**spec.version_manifest(), "formal_sequence": freeze.SEQUENCE,
              "source_commit": "unused"}
    frozen["adapter_version"] = "2.2.0"
    freeze_path.write_text(json.dumps(frozen))
    state_path = tmp_path / "campaign-state.json"

    with pytest.raises(ValueError, match="freeze task/adapter version mismatch"):
        campaign.run_next(freeze_path, state_path)
    assert not state_path.exists()

    state_path.write_text(json.dumps({}))
    with pytest.raises(RuntimeError, match="campaign freeze task/adapter version mismatch"):
        campaign.verify_reservation(state_path, freeze_path, "run", "round1", "isolated")
