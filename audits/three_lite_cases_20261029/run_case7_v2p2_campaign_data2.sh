#!/usr/bin/env bash
# Fail-closed campaign launcher for the standalone data2 Case 7 clone.
set -euo pipefail
case7_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$case7_root"
[[ -f env.local.sh ]] || { echo 'Missing gitignored env.local.sh.' >&2; exit 3; }
source env.local.sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$case7_root${PYTHONPATH:+:$PYTHONPATH}"

case7_expected_docker_host='unix:///data2/whn/codesk-runs/case7-docker-data2/docker.sock'
case7_expected_docker_root='/data2/whn/codesk-runs/case7-docker-data2/data'
[[ "${DOCKER_HOST:-}" == "$case7_expected_docker_host" ]] || {
    echo 'Case 7 must use its dedicated data2 Docker socket.' >&2; exit 3;
}
case7_socket="${case7_expected_docker_host#unix://}"
[[ -S "$case7_socket" && -r "$case7_socket" && -w "$case7_socket" ]] || {
    echo 'Dedicated data2 Docker socket is unavailable; no run was started.' >&2; exit 3;
}
command -v docker >/dev/null || { echo 'Docker CLI is unavailable.' >&2; exit 3; }
case7_actual_docker_root="$(DOCKER_HOST="$DOCKER_HOST" docker info --format '{{.DockerRootDir}}' 2>/dev/null)" || {
    echo 'Read-only DockerRootDir query failed; no run was started.' >&2; exit 3;
}
[[ "$(realpath -e "$case7_actual_docker_root")" == "$(realpath -m "$case7_expected_docker_root")" ]] || {
    echo 'Docker data root differs from the dedicated Case 7 data2 root.' >&2; exit 3;
}

case7_python="$OSWORLD_DIR/.venv/bin/python"
[[ -x "$case7_python" ]] || { echo 'OSWorld Python is unavailable.' >&2; exit 3; }
exec "$case7_python" -m oscombo.collab.workspace_assembly_lite_v2.campaign "$@"
