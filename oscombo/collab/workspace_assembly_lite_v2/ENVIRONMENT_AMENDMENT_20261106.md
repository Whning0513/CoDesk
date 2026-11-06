# Case 7 v2.2 external Python write-policy amendment

Status: offline source amendment only. It does not change the Task Card,
prompts, Fixture, Gold, Oracle, budget, Guest topology, or scoring conditions.

The v2.2 one-run shell driver invokes the OSWorld interpreter from the external
`OSWORLD_DIR`. In the current layout that provider tree can reside on data3,
which is nearly full. The driver now exports `PYTHONDONTWRITEBYTECODE=1` before
invoking that interpreter, preventing Python bytecode cache writes into the
provider tree. Experiment output, Guest cache and overlays remain owned by the
run root.

The standalone clone also has a separate campaign launcher that sources the
gitignored, non-secret `env.local.sh`, requires the dedicated data2 Docker
socket, and verifies the Docker data-root with a read-only `docker info` query
before invoking the campaign scheduler. It will fail closed instead of falling
back to a default data3 Docker context. The dedicated socket/data-root has not
been created or started. `configs/case7_data2.env.example.sh` contains the
non-secret paths to copy into the ignored local file; it contains no API key.

These source edits change the frozen source commit. The prior v2.2 freeze and
historical records remain tied to their original commit and are not reusable
for a formal cohort. Before any Guest run, commit this amendment, rerun the
scripted positive/negative controls on both topologies, review the screenshots
and mount/overlay ownership, then create a new freeze. No Guest, Docker daemon,
QEMU process, or model API was started for this offline amendment.
