#!/usr/bin/env bash

set -eo pipefail
source /opt/ros/humble/setup.bash
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/install/setup.bash"
set -u
exec python3 "$repo_root/scripts/run_m6_regression.py" "$@"
