# Model-and-Review Lite v2

Independent version `CDD-MAR-LITE-002`; see [task card](TASK_CARD_ZH.md). The v1 case is untouched. Actor B receives neither the scale factor nor target width in its instruction or public brief. The user-provided initial Blender scene and blank report are available equally to both topologies; A's factor is in A's instruction only. Gold remains on the scoring side.

The existing real Guest adapter is selected by `python -m oscombo.collab.model_and_review_lite_v2.live_pilot`. The underlying implementation supports the same isolated, shared and optional single-call shared lock conditions as v1. Offline host Blender tests establish only file/scorer behavior; real GUI positive/negative controls and model Pilot are separate gates.
