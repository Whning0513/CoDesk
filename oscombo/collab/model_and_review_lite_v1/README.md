# Model-and-Review Lite v1

Independent short Blender scene review case (`CDD-MAR-LITE-001`). The original `CDD-MAR-001` files are unchanged. Read [TASK_CARD_ZH.md](TASK_CARD_ZH.md) for the task contract.

The public fixture is `fixtures/Lamp_Review.blend`; the private Gold is `fixtures/private/gold.blend` and is never staged in an Actor Guest. Both were generated and reopened with Blender 5.0.0, matching the OSWorld Guest's observed version. The official archive checksum and fixture hashes are in `fixtures/manifest.json`.

Rebuild the two `.blend` files with a verified Blender 5.0 executable:

```bash
blender --background --factory-startup -t 2 --python oscombo/collab/model_and_review_lite_v1/blender_build.py -- \
  --output oscombo/collab/model_and_review_lite_v1/fixtures/Lamp_Review.blend --variant initial
blender --background --factory-startup -t 2 --python oscombo/collab/model_and_review_lite_v1/blender_build.py -- \
  --output oscombo/collab/model_and_review_lite_v1/fixtures/private/gold.blend --variant gold
```

Offline real-file control:

```bash
CODESK_BLENDER_BIN=/path/to/blender python -m pytest -q tests/test_model_and_review_lite_v1.py
```

The real Guest entry point is `python -m oscombo.collab.model_and_review_lite_v1.live_pilot` with the same provider/image/runtime arguments as the other Lite cases, plus `--blender-bin` for independent host scoring. Model runs should also pass `--yield-wait-lifecycle --actor-mcp-only` in both Shared and Isolated. GUI scripted controls and model feasibility evidence are reported separately; background Blender tests alone do not establish GUI success.
