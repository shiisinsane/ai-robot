#!/usr/bin/env bash

source /opt/ros/humble/setup.bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

colcon build --symlink-install --event-handlers console_direct+
