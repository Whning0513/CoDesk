# Case 5 endpoint compatibility probe, 2026-10-31

`case5-endpoint-probe-20261031T084930Z` sent the same public desktop screenshot and forced function-call request to `https://api.haogpt.net/v1` and `https://docode.cc/v1`, using `gpt-6-astra`, medium reasoning, streaming and the fixed order haogpt → docode → docode → haogpt. Only response metadata, token counts, timings and exception types were retained; no key, tool arguments or model output text was written to the evidence.

| Endpoint | HTTP 200 | Completed streams | Expected function call | Reported model | Elapsed seconds |
|---|---:|---:|---:|---|---|
| haogpt | 2/2 | 2/2 | 2/2 | gpt-6-astra, 2/2 | 17.216, 17.238 |
| docode | 2/2 | 2/2 | 2/2 | gpt-6-astra, 2/2 | 31.399, 4.104 |

The probe is a compatibility check with only two short requests per endpoint; it cannot establish long-stream reliability or a statistically meaningful speed difference. Both endpoints passed this limited check. The previously selected haogpt endpoint remains the single frozen endpoint for all three Case 5 arms. The separate `075509Z` model attempt contained stream interruptions and remains preserved as invalid for the independently found setup screenshot collision; the short probe does not erase that network evidence.

[Sanitized attempt records](evidence/case5_endpoint_probe_084930/attempts.jsonl), [summary](evidence/case5_endpoint_probe_084930/summary.json) and [SHA manifest](evidence/case5_endpoint_probe_084930/sha256_manifest.json) are retained.
