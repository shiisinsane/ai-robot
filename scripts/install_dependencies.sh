#!/usr/bin/env bash

source /opt/ros/humble/setup.bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
  printf '%s\n' \
    "rosdep 尚未初始化，请执行一次以下命令：" \
    "  sudo rosdep init" \
    "  rosdep update" >&2
  exit 2
fi

rosdep update
rosdep install --from-paths src --ignore-src --rosdistro humble -y
