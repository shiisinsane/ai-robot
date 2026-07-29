#!/usr/bin/env bash

source /opt/ros/humble/setup.bash
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/install/setup.bash"
set -euo pipefail
cd "$repo_root"

colcon test --event-handlers console_direct+
colcon test-result --verbose
