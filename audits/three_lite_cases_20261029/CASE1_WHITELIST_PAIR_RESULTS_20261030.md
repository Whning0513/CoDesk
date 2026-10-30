# Case 1 Data-to-Deck Lite v2.1: clean Actor tool pair

Protocol: [CASE1_WHITELIST_PAIR_PROTOCOL.md](CASE1_WHITELIST_PAIR_PROTOCOL.md). Both episodes used the same v2.1 public Fixture and A/B prompts, `gpt-6-astra` medium, 25 desktop calls and 1200 seconds per role, the same public handoff bridge and independent v2.1 Oracle. The request relay exposed only desktop/collaboration tools to both Actors. Shared used one Ubuntu desktop without a GUI input lock; Isolated used two Guests. The older v2.0.0 formal pair and retrospective v2.1 rescore are separate evidence, not part of this pair.

| Metric | Shared | Isolated |
|---|---:|---:|
| Run ID | `cdd-lite-v2p1-whitelist-shared-20261030T120834Z` | `cdd-lite-v2p1-whitelist-isolated-20261030T120834Z` |
| Complete result; Oracle A/B/joint | PASS; PASS/PASS/PASS | FAIL; FAIL/FAIL/FAIL |
| Desktop calls A/B | 10 / 10 | 6 / 13 |
| Total upstream tokens A/B | 112,165 / 268,218 | 92,422 / 342,975 |
| Setup until Actor start | 386.613 s | 733.454 s |
| Actor active overlap | 284.020 s | 260.019 s |
| Model request overlap | 75.147 s | 136.902 s |
| GUI action overlap | 0 s | 0 s |
| Total wall time including setup/reopen/reset | 1128.570 s | 1909.900 s |
| Peak summed QEMU process RSS | 5.035 GiB | 9.948 GiB |
| Sampled QEMU CPU delta | 3851.60 s | 7863.23 s |
| Bridge transfers / sync errors | 0 / 0 | 1 / 0 |
| Scored files GUI reopened byte-identically | A and B | A and B, including peer read-only opens |
| Clean Guest resets | 1 | 2 |
| Outside-contract Actor tools | 0 | 0 |

Shared: A edited Calc, saved two distinct revisions, and sent the operating-profit change and source range. B spent several desktop calls on `wait(30s)`, then read the public handoff, edited the one-slide Impress conclusion and saved revision 1. The Oracle verified signed `-11`, source evidence, the saved workbook and slide wording/consistency. Both documents reopened with the same bytes and the run reset cleanly. There was concurrent model activity but zero simultaneous GUI action time; this sample gives no concrete focus collision. B did not suspend, so the lifecycle feature was available but unused.

Isolated: A's message claimed the correct `-11 USD thousands` and `B3:E4` source, and A revision 1 transferred to B's Guest with matching SHA and read-only permission. The actual saved Calc row 6 was `['Change Q3-Q2', -11, 'Evidence']`: the evidence text overwrote the output label in C6 and D6 remained empty. The Oracle correctly rejected A despite the correct message. B's GUI screenshot showed a sensible replacement sentence in Impress, followed by `Ctrl+S` and a later wait, but the scored output ODP remained the original 1840-byte draft with `[await A result]`. B never published revision 1. Independent GUI reopen in both Guests reproduced that saved draft, and bridge sync reported zero errors. Thus the text visible in the editor was not a delivered saved artifact. The trace supports an A cell-localization error and a B GUI save/delivery failure; the exact LibreOffice internal reason for B's unsaved output is not established. There is no evidence that peer sync dropped a valid B revision.

Both outcomes are valid, retained model episodes. One pair cannot estimate topology success rates or show that a Shared input lock is beneficial or ineffective. The Isolated failure occurred without a shared desktop; the Shared success had no simultaneous GUI actions. Actor token counts include screenshot-heavy input context, and Isolated's two Guest boots and aggregate QEMU resources must be separated from model execution cost. Full screenshots, actions, model requests, messages, revision events, final files, Oracle, reopen and reset are in the exact local `runs/<run_id>/` directories.
