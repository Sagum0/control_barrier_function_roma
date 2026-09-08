#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec conda run --no-capture-output -n zed bash -lc '
  source /opt/ros/humble/setup.bash
  export PYTHONPATH="/opt/ros/humble/local/lib/python3.10/dist-packages:/opt/ros/humble/lib/python3.10/site-packages:${PYTHONPATH:-}"
  exec python3 "$0" "$@"
' "$HERE/fusion_ros2_bridge.py" "$@"
