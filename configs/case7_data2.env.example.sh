# Non-secret paths for the standalone Case 7 v2.2 data2 launcher.
# Copy to the checkout root as env.local.sh and adjust only after review.
export OSWORLD_DIR=/data3/whn/Project2/OSWorld-V2
export OSCOMBO_GUEST_IMAGE=/data3/whn/Project2/images/osworld-v2-ubuntu-x86.qcow2
export OSCOMBO_RUNTIME_IMAGE=oscombo/qemu-runtime:local
export DOCKER_HOST=unix:///data2/whn/codesk-runs/case7-docker-data2/docker.sock
