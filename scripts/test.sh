#!/usr/bin/env bash

source /opt/ros/humble/setup.bash
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/install/setup.bash"
set -euo pipefail
cd "$repo_root"

export ROS_LOG_DIR="$repo_root/log/ros"
mkdir -p "$ROS_LOG_DIR"

colcon test --event-handlers console_direct+
colcon test-result --verbose

python3 scripts/check_interface_contract.py
python3 scripts/check_robot_model.py
python3 scripts/check_sensor_model.py
python3 scripts/check_robot_description.py
python3 scripts/check_sim_assets.py
python3 -m pytest -q \
  tests/unit \
  tests/node \
  tests/contract \
  tests/integration \
  tests/simulation
