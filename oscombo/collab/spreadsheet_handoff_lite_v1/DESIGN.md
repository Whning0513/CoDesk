# Spreadsheet Handoff Lite v1 design

The original Case 6 has four SKUs, multiple sheets, a lease/CAS workflow, forecast review and budget totals. This independent Lite case keeps the forecast-to-order handoff and case-pack arithmetic for one SKU. A needs two Calc cells, B needs two Calc cells. Both outputs are already open. B can inspect pack/price/cap while A calculates; B's final order must follow A's saved revision and message. Shared still exposes natural Calc-window focus competition; Isolated uses two Guests and read-only peer copies.

The public source data intentionally yields a non-multiple net need, so B must round to the next case pack. The evaluator derives the expected need and cost from the immutable public source cells. It checks both output workbooks and source preservation, while a separate trace audit checks actual peer-message and file-version use. Scripted controls may use evaluator Gold to exercise GUI plumbing; model Actors never receive Gold or Oracle.
