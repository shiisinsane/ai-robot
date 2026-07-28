#!/usr/bin/env bash

set -u

failures=0

check_command() {
  local command_name="$1"
  shift

  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf '%-24s %-8s %s\n' "$command_name" "MISSING" "command not found"
    failures=$((failures + 1))
    return
  fi

  local output
  output="$("$command_name" "$@" 2>&1 | head -n 1)"
  printf '%-24s %-8s %s\n' "$command_name" "OK" "$output"
}

printf '%-24s %-8s %s\n' "CHECK" "STATUS" "DETAIL"

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  printf '%-24s %-8s %s\n' "Operating system" "INFO" "${PRETTY_NAME:-unknown}"
else
  printf '%-24s %-8s %s\n' "Operating system" "WARN" "/etc/os-release unavailable"
fi

check_command git --version
check_command python3 --version
check_command cmake --version
check_command ros2 --help
check_command colcon version-check
check_command rviz2 --help
check_command gz --version

if command -v ros2 >/dev/null 2>&1; then
  ros_distro="${ROS_DISTRO:-unset}"
  if [ "$ros_distro" = "humble" ]; then
    printf '%-24s %-8s %s\n' "ROS_DISTRO" "OK" "$ros_distro"
  else
    printf '%-24s %-8s %s\n' "ROS_DISTRO" "WARN" "$ros_distro (expected humble)"
  fi
fi

free_kb="$(df -Pk . | awk 'NR==2 {print $4}')"
if [ -n "$free_kb" ]; then
  free_gb=$((free_kb / 1024 / 1024))
  disk_status="OK"
  if [ "$free_gb" -lt 20 ]; then
    disk_status="WARN"
  fi
  printf '%-24s %-8s %s\n' "Workspace disk free" "$disk_status" "${free_gb} GB"
fi

exit "$failures"
