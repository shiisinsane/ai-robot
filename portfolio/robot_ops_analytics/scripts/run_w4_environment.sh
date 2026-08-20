#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
BATCH_DIR=""
DOMAIN_ID=""
PARTITION=""
MAP_PATH="$ROOT_DIR/artifacts/m5_w10/20260812_112602/config_snapshot/m5_w10_map.yaml"

usage() {
  echo "用法：$0 --batch-dir PATH --domain-id ID --partition NAME [--map PATH]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --batch-dir) BATCH_DIR=$2; shift 2 ;;
    --domain-id) DOMAIN_ID=$2; shift 2 ;;
    --partition) PARTITION=$2; shift 2 ;;
    --map) MAP_PATH=$2; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done

if [[ -z "$BATCH_DIR" || -z "$DOMAIN_ID" || -z "$PARTITION" ]]; then
  usage; exit 2
fi
if [[ ! "$DOMAIN_ID" =~ ^([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-2][0-9]|23[0-2])$ ]]; then
  echo "ROS_DOMAIN_ID必须在0～232之间"; exit 2
fi
if [[ ! "$PARTITION" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$ ]]; then
  echo "Gazebo分区只能使用2～64位字母、数字、下划线或连字符"; exit 2
fi
if [[ ! -f "$MAP_PATH" ]]; then
  echo "地图不存在：$MAP_PATH"; exit 2
fi
if ! command -v setsid >/dev/null; then
  echo "缺少setsid，无法可靠管理进程组"; exit 2
fi

BATCH_DIR=$(realpath -m "$BATCH_DIR")
PROCESS_DIR="$BATCH_DIR/process"
LOG_DIR="$BATCH_DIR/runtime_logs"
STRUCTURED_DIR="$BATCH_DIR/structured"
BAG_PARENT="$BATCH_DIR/rosbag"
BAG_DIR="$BAG_PARENT/w4_pilot_bag"
mkdir -p "$PROCESS_DIR" "$LOG_DIR" "$STRUCTURED_DIR" "$BAG_PARENT"
if [[ -e "$BAG_DIR" ]]; then
  echo "rosbag目标已经存在，拒绝覆盖：$BAG_DIR"; exit 2
fi

export ROS_DOMAIN_ID="$DOMAIN_ID"
export ROS2CLI_DISABLE_DAEMON=1
export IGN_PARTITION="$PARTITION"
export IGN_HOME="$BATCH_DIR/ign"
export ROS_LOG_DIR="$BATCH_DIR/ros_logs"
mkdir -p "$IGN_HOME" "$ROS_LOG_DIR"

PROCESS_FILE="$PROCESS_DIR/process_groups.tsv"
ENV_FILE="$PROCESS_DIR/environment.txt"
: > "$PROCESS_FILE"
{
  echo "controller_pid=$$"
  echo "ros_domain_id=$ROS_DOMAIN_ID"
  echo "ign_partition=$IGN_PARTITION"
  echo "batch_dir=$BATCH_DIR"
  echo "started_at=$(date --iso-8601=seconds)"
} > "$ENV_FILE"

declare -a COMPONENTS=()
declare -a PIDS=()
declare -a PGIDS=()
CLEANED=0

start_component() {
  local name=$1
  local log=$2
  shift 2
  setsid "$@" > "$log" 2>&1 &
  local pid=$!
  local pgid
  pgid=$(ps -o pgid= -p "$pid" | tr -d ' ')
  if [[ -z "$pgid" || "$pgid" != "$pid" ]]; then
    echo "组件$name未建立独立进程组" >&2
    kill -TERM "$pid" 2>/dev/null || true
    return 1
  fi
  COMPONENTS+=("$name"); PIDS+=("$pid"); PGIDS+=("$pgid")
  printf '%s\t%s\t%s\t%s\n' "$name" "$pid" "$pgid" "$log" >> "$PROCESS_FILE"
  echo "已启动$name：PID=$pid PGID=$pgid"
}

group_alive() {
  ps -eo pgid= | awk -v wanted="$1" '$1 == wanted {found=1} END {exit !found}'
}

cleanup() {
  local status=$?
  if [[ "$CLEANED" -eq 1 ]]; then return; fi
  CLEANED=1
  trap - EXIT INT TERM HUP
  echo "开始清理本批进程组..."
  for pgid in "${PGIDS[@]}"; do
    kill -INT -- "-$pgid" 2>/dev/null || true
  done
  local deadline=$((SECONDS + 25))
  while [[ "$SECONDS" -lt "$deadline" ]]; do
    local alive=0
    for pgid in "${PGIDS[@]}"; do
      if group_alive "$pgid"; then alive=1; fi
    done
    [[ "$alive" -eq 0 ]] && break
    sleep 1
  done
  for pgid in "${PGIDS[@]}"; do
    if group_alive "$pgid"; then kill -TERM -- "-$pgid" 2>/dev/null || true; fi
  done
  local term_deadline=$((SECONDS + 5))
  while [[ "$SECONDS" -lt "$term_deadline" ]]; do
    local alive_after_term=0
    for pgid in "${PGIDS[@]}"; do
      if group_alive "$pgid"; then alive_after_term=1; fi
    done
    [[ "$alive_after_term" -eq 0 ]] && break
    sleep 1
  done
  for pgid in "${PGIDS[@]}"; do
    if group_alive "$pgid"; then
      echo "PGID=$pgid未响应SIGTERM，执行精确SIGKILL"
      kill -KILL -- "-$pgid" 2>/dev/null || true
    fi
  done
  sleep 1
  for pid in "${PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
  local residue=0
  : > "$PROCESS_DIR/residue_check.txt"
  for index in "${!PGIDS[@]}"; do
    if group_alive "${PGIDS[$index]}"; then
      echo "残留：${COMPONENTS[$index]} PGID=${PGIDS[$index]}" | tee -a "$PROCESS_DIR/residue_check.txt"
      ps -eo pid,ppid,pgid,sid,etimes,comm,args | awk -v wanted="${PGIDS[$index]}" '$3 == wanted' >> "$PROCESS_DIR/residue_check.txt"
      residue=1
    fi
  done
  if [[ "$residue" -eq 0 ]]; then
    echo "本批进程组残留检查：通过" | tee "$PROCESS_DIR/residue_check.txt"
  else
    echo "本批仍有残留进程；不得启动下一批" >&2
    status=1
  fi
  echo "finished_at=$(date --iso-8601=seconds)" >> "$ENV_FILE"
  exit "$status"
}
trap cleanup EXIT INT TERM HUP

cd "$ROOT_DIR"
start_component navigation "$LOG_DIR/navigation.log" \
  ros2 launch ai_robot_sim m5_recovery_navigation.launch.py gui:=false "map:=$MAP_PATH"

echo "等待navigation产生里程计和公共导航Action（最长150秒）..."
navigation_ready=0
navigation_deadline=$((SECONDS + 150))
while [[ "$SECONDS" -lt "$navigation_deadline" ]]; do
  if ! kill -0 "${PIDS[0]}" 2>/dev/null; then
    echo "navigation在Ready前退出" >&2
    exit 1
  fi
  if timeout 5 ros2 topic echo /robot/odom --once >/dev/null 2>&1 && \
     timeout 5 ros2 action info /robot/navigation/navigate_to_pose 2>/dev/null \
       | grep -q 'Action servers: 1'; then
    navigation_ready=1
    break
  fi
  sleep 2
done
if [[ "$navigation_ready" -ne 1 ]]; then
  echo "navigation在150秒内未Ready，拒绝启动其余组件" >&2
  exit 1
fi
echo "navigation Ready"

start_component task_manager "$LOG_DIR/task_manager.log" \
  ros2 launch ai_robot_task_manager task_manager.launch.py

echo "等待公共任务Action（最长30秒）..."
task_ready=0
task_deadline=$((SECONDS + 30))
while [[ "$SECONDS" -lt "$task_deadline" ]]; do
  if timeout 5 ros2 action info /robot/task/execute 2>/dev/null \
       | grep -q 'Action servers: 1'; then
    task_ready=1
    break
  fi
  sleep 1
done
if [[ "$task_ready" -ne 1 ]]; then
  echo "任务Action未Ready，拒绝启动采集和录包" >&2
  exit 1
fi
echo "任务Action Ready"

start_component collector "$LOG_DIR/collector.log" \
  python3 -m portfolio.robot_ops_analytics.collector.ros_collector \
  --ros-args -r __ns:=/robot -p use_sim_time:=true \
  "-p" "output_path:=$STRUCTURED_DIR/records.jsonl"
start_component rosbag "$LOG_DIR/rosbag.log" \
  ros2 bag record --storage sqlite3 --include-hidden-topics \
  --qos-profile-overrides-path config/common/m6_rosbag_qos.yaml --output "$BAG_DIR" \
  /clock /tf /tf_static /robot/map /robot/pose /robot/odom /robot/scan \
  /robot/diagnostics /robot/safety/stop_active \
  /robot/task/execute/_action/feedback /robot/task/execute/_action/status

echo "W4环境已启动。请在另一终端完成Ready检查和pilot任务。"
echo "完成后在本终端按Ctrl-C，脚本会清理并复查全部进程组。"
while true; do
  for index in "${!PIDS[@]}"; do
    if ! kill -0 "${PIDS[$index]}" 2>/dev/null; then
      echo "组件异常退出：${COMPONENTS[$index]}，开始清理" >&2
      exit 1
    fi
  done
  sleep 2
done
