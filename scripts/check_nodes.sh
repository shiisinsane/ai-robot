#!/usr/bin/env bash

source /opt/ros/humble/setup.bash
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/install/setup.bash"
set -euo pipefail

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-71}"
export ROS2CLI_NO_DAEMON=1
export ROS_LOG_DIR="${ROS_LOG_DIR:-$repo_root/log/ros}"
mkdir -p "$ROS_LOG_DIR"

run_check() {
  local package="$1"
  local executable="$2"
  local topic="$3"
  local expected="$4"
  local pid

  ros2 run "$package" "$executable" &
  pid=$!
  trap 'kill "$pid" 2>/dev/null || true' RETURN

  if ! timeout 15 ros2 topic echo --once "$topic" std_msgs/msg/String |
    grep -F "$expected" >/dev/null; then
    printf '节点验证失败：%s/%s，话题 %s\n' "$package" "$executable" "$topic" >&2
    return 1
  fi

  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  trap - RETURN
  printf '节点验证通过：%s/%s -> %s\n' "$package" "$executable" "$topic"
}

run_check ai_robot_cpp_demo status_publisher /m0/cpp_status \
  "ai-robot M0 C++ 节点已就绪"
run_check ai_robot_py_demo status_publisher /m0/py_status \
  "ai-robot M0 Python 节点已就绪"
