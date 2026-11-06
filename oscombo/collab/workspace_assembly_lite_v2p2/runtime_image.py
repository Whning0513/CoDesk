"""Resolve a configured Docker runtime reference to its immutable image ID."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path
import sys


_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
DATA2_DOCKER_HOST = "unix:///data2/whn/codesk-runs/case7-docker-data2/docker.sock"
DATA2_DOCKER_ROOT = "/data2/whn/codesk-runs/case7-docker-data2/data"


class RuntimeImageError(RuntimeError):
    """The selected Docker daemon could not verify the requested image."""


def verify_data2_docker_daemon() -> None:
    """Require the dedicated data2 endpoint and its expected writable data root."""
    docker_host = os.environ.get("DOCKER_HOST")
    if docker_host != DATA2_DOCKER_HOST:
        raise RuntimeImageError("DOCKER_HOST is not the dedicated Case 7 data2 socket")
    socket_path = Path(DATA2_DOCKER_HOST.removeprefix("unix://"))
    if not socket_path.is_socket() or not os.access(socket_path, os.R_OK | os.W_OK):
        raise RuntimeImageError("dedicated Case 7 data2 Docker socket is unavailable")
    # Docker's DOCKER_CONTEXT can override DOCKER_HOST. Remove it for every
    # CLI call and explicitly pin the endpoint so the resolver cannot inspect
    # a different daemon selected by the caller's current context.
    docker_env = os.environ.copy()
    docker_env.pop("DOCKER_CONTEXT", None)
    docker_env["DOCKER_HOST"] = DATA2_DOCKER_HOST
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.DockerRootDir}}"],
            check=False, capture_output=True, text=True, timeout=15,
            env=docker_env)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeImageError("Docker data-root query failed") from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeImageError("Docker data-root query failed")
    try:
        actual_root = Path(result.stdout.strip()).resolve(strict=True)
        expected_root = Path(DATA2_DOCKER_ROOT).resolve(strict=True)
    except OSError as exc:
        raise RuntimeImageError("Case 7 data2 Docker root is unavailable") from exc
    if actual_root != expected_root or not actual_root.is_dir() or not os.access(actual_root, os.W_OK | os.X_OK):
        raise RuntimeImageError("Docker daemon is not using the dedicated Case 7 data2 root")


def resolve_runtime_image(image_ref: str, expected_id: str | None = None) -> str:
    """Return a pinned image ID from the verified data2 daemon used by Guest startup."""
    if not image_ref:
        raise RuntimeImageError("runtime image reference is empty")
    if expected_id is not None and not _IMAGE_ID.fullmatch(expected_id):
        raise RuntimeImageError("expected runtime image ID is malformed")
    verify_data2_docker_daemon()
    docker_env = os.environ.copy()
    docker_env.pop("DOCKER_CONTEXT", None)
    docker_env["DOCKER_HOST"] = DATA2_DOCKER_HOST
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image_ref],
            check=False, capture_output=True, text=True, timeout=15,
            env=docker_env)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeImageError("Docker image inspection failed") from exc
    if result.returncode != 0:
        raise RuntimeImageError("runtime image is unavailable in the selected Docker daemon")
    image_id = result.stdout.strip()
    if not _IMAGE_ID.fullmatch(image_id):
        raise RuntimeImageError("Docker returned no valid immutable image ID")
    if expected_id is not None and image_id != expected_id:
        raise RuntimeImageError("runtime image ID differs from the expected frozen ID")
    return image_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_ref")
    parser.add_argument("--expected-id")
    args = parser.parse_args()
    try:
        print(resolve_runtime_image(args.image_ref, args.expected_id))
    except RuntimeImageError as exc:
        print(f"Case 7 runtime preflight failed: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
