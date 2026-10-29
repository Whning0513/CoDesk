"""Deterministic public static browser fixture; no executable host service."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import spec


def source_html() -> str:
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>OrderDesk Lite</title>
<style>body{font:20px sans-serif;max-width:900px;margin:60px auto}input,select,button{font:inherit;margin:8px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #777;padding:10px}</style>
</head><body><h1>OrderDesk</h1><label>Search <input id="query"></label>
<label>Status <select id="status"><option value="all">All</option><option value="processing">Processing</option><option value="shipped">Shipped</option><option value="delievered">Delivered</option></select></label>
<button id="apply">Apply filter</button><p id="result">3 orders shown</p>
<table><thead><tr><th>Order ID</th><th>Region</th><th>Status</th></tr></thead><tbody>
<tr data-region="north" data-status="delivered"><td>OD-104</td><td>North</td><td>Delivered</td></tr>
<tr data-region="south" data-status="processing"><td>OD-105</td><td>South</td><td>Processing</td></tr>
<tr data-region="north" data-status="shipped"><td>OD-106</td><td>North</td><td>Shipped</td></tr>
</tbody></table>
<script>
document.getElementById("apply").addEventListener("click", () => {
  const q = document.getElementById("query").value.trim().toLowerCase();
  const status = document.getElementById("status").value;
  let count = 0;
  for (const row of document.querySelectorAll("tbody tr")) {
    const match = row.dataset.region.includes(q) && (status === "all" || row.dataset.status === status);
    row.hidden = !match;
    if (match) count++;
  }
  document.getElementById("result").textContent = `${count} orders shown`;
});
</script></body></html>
'''


def qa_template() -> str:
    return "Query: [pending]\nStatus: [pending]\nVisible order IDs: [pending]\nSaved source: [pending]\n"


def build_fixture(root: str | Path) -> dict:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise FileExistsError(f"Lite fixture destination is not empty: {root}")
    (root / spec.FIXTURE_NAMES["source"]).write_text(source_html(), encoding="utf-8")
    (root / spec.FIXTURE_NAMES["qa"]).write_text(qa_template(), encoding="utf-8")
    (root / spec.FIXTURE_NAMES["brief"]).write_text(
        "OrderDesk is an offline static page. A repairs the Delivered filter option in the source through the GUI. "
        "B uses the saved source revision in a real browser and reports the North + Delivered result. "
        "The source and QA output are already open. Save, publish and communicate in both topologies.\n",
        encoding="utf-8")
    files = {name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                    "bytes": (root / name).stat().st_size}
             for name in spec.FIXTURE_NAMES.values()}
    manifest = {"case_id": spec.CASE_ID, "case_version": spec.CASE_VERSION,
                "fixture_sha256": files, "conditions": spec.CONDITIONS,
                "outputs": spec.OUTPUTS, "role_budgets": spec.ROLE_BUDGET}
    (root / "fixture_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
