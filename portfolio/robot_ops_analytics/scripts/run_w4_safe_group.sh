#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
BATCH_DIR=""
DOMAIN_ID=""
PARTITION=""
EXPERIMENT_ID=""
PLAN=""
PROFILE="natural__none__none__baseline"
OBSTACLE_PROFILE="none"
GUI="false"
declare -a TASK_IDS=()
ENV_PID=""
ENV_LOG=""
CLEANED=0

usage() {
  echo "用法：$0 --batch-dir PATH --domain-id ID --partition NAME --experiment-id ID --plan PATH --obstacle-profile ID --task-id ID [--task-id ID ...]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --batch-dir) BATCH_DIR=$2; shift 2 ;;
    --domain-id) DOMAIN_ID=$2; shift 2 ;;
    --partition) PARTITION=$2; shift 2 ;;
    --experiment-id) EXPERIMENT_ID=$2; shift 2 ;;
    --plan) PLAN=$2; shift 2 ;;
    --environment-profile) PROFILE=$2; shift 2 ;;
    --obstacle-profile) OBSTACLE_PROFILE=$2; shift 2 ;;
    --gui) GUI=true; shift ;;
    --task-id) TASK_IDS+=("$2"); shift 2 ;;
    *) usage; exit 2 ;;
  esac
done

if [[ -z "$BATCH_DIR" || -z "$DOMAIN_ID" || -z "$PARTITION" ||
      -z "$EXPERIMENT_ID" || -z "$PLAN" || ${#TASK_IDS[@]} -eq 0 ]]; then
  usage; exit 2
fi
if [[ ! -f "$PLAN" ]]; then
  echo "计划不存在：$PLAN"; exit 2
fi
if [[ "$PROFILE" != *"__${OBSTACLE_PROFILE}__"* ]]; then
  echo "environment-profile与obstacle-profile不一致，拒绝运行"; exit 2
fi
if ! command -v ros2 >/dev/null; then
  echo "找不到ros2；请先source ROS 2和工作区环境"; exit 2
fi

BATCH_DIR=$(realpath -m "$BATCH_DIR")
PLAN=$(realpath "$PLAN")
mkdir -p "$BATCH_DIR/process"
ENV_LOG="$BATCH_DIR/process/environment_controller.log"

cleanup() {
  local status=$?
  if [[ "$CLEANED" -eq 1 ]]; then return; fi
  CLEANED=1
  trap - EXIT INT TERM HUP
  if [[ -n "$ENV_PID" ]] && kill -0 "$ENV_PID" 2>/dev/null; then
    echo "通知环境控制器清理本批进程..."
    # 非交互shell的后台任务可能继承忽略SIGINT的状态；SIGTERM可可靠触发环境脚本的trap。
    kill -TERM "$ENV_PID" 2>/dev/null || true
    local deadline=$((SECONDS + 40))
    while [[ "$SECONDS" -lt "$deadline" ]]; do
      local child_state
      child_state=$(ps -o stat= -p "$ENV_PID" 2>/dev/null | tr -d ' ' || true)
      # 已退出的后台子进程在wait前可能处于Z状态，kill -0仍会误报为存活。
      if [[ -z "$child_state" || "$child_state" == Z* ]]; then break; fi
      sleep 1
    done
    local final_state
    final_state=$(ps -o stat= -p "$ENV_PID" 2>/dev/null | tr -d ' ' || true)
    if [[ -n "$final_state" && "$final_state" != Z* ]]; then
      echo "环境控制器未在40秒内退出；拒绝静默继续" >&2
      status=1
    else
      wait "$ENV_PID" 2>/dev/null || true
    fi
  fi
  local residue="$BATCH_DIR/process/residue_check.txt"
  if [[ ! -f "$residue" ]] || ! grep -q '^本批进程组残留检查：通过$' "$residue"; then
    echo "本批无残留验收未通过，请查看：$residue" >&2
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT INT TERM HUP

cd "$ROOT_DIR"
export ROS_DOMAIN_ID="$DOMAIN_ID"
export ROS2CLI_DISABLE_DAEMON=1
export IGN_PARTITION="$PARTITION"

PREFLIGHT_FILE="$BATCH_DIR/process/preflight_process_check.txt"
ps -eo pid,ppid,pgid,sid,stat,etimes,comm,args \
  | grep -Ei '[i]gn gazebo|[g]zserver|[g]zclient|[r]os2 launch|[r]os_gz_bridge|[p]lanner_server|[c]ontroller_server|[b]t_navigator|[b]ehavior_server|[t]ask_manager|[r]os2 bag record|[r]oa_w3_collector|[r]un_w4_environment' \
  >"$PREFLIGHT_FILE" || true
if [[ -s "$PREFLIGHT_FILE" ]]; then
  echo "发现同类ROS/Gazebo进程，拒绝启动。请检查：$PREFLIGHT_FILE" >&2
  # 此时尚未启动环境，避免cleanup把“没有残留记录”误报为失败。
  CLEANED=1
  exit 1
fi
echo "启动前同类进程检查：通过" >"$PREFLIGHT_FILE"

echo "启动W4环境；日志：$ENV_LOG"
bash portfolio/robot_ops_analytics/scripts/run_w4_environment.sh \
  --batch-dir "$BATCH_DIR" --domain-id "$DOMAIN_ID" --partition "$PARTITION" --gui "$GUI" \
  >"$ENV_LOG" 2>&1 &
ENV_PID=$!

echo "等待环境完成分阶段Ready（最长210秒）..."
ready=0
deadline=$((SECONDS + 210))
while [[ "$SECONDS" -lt "$deadline" ]]; do
  if ! kill -0 "$ENV_PID" 2>/dev/null; then
    echo "环境在Ready前退出，请查看：$ENV_LOG" >&2
    exit 1
  fi
  if grep -q 'W4环境已启动' "$ENV_LOG"; then ready=1; break; fi
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "环境未在210秒内Ready" >&2; exit 1
fi
echo "环境Ready"

echo "配置并记录障碍物档位：$OBSTACLE_PROFILE"
python3 -m portfolio.robot_ops_analytics.orchestrator.configure_w4_environment \
  --config portfolio/robot_ops_analytics/config/w4_matrix_v1.yaml \
  --profile "$OBSTACLE_PROFILE" \
  --evidence "$BATCH_DIR/config_snapshot/obstacle_environment.json"

echo "执行任务前最终Ready门禁（pose、scan、diagnostics、任务Action）..."
final_ready=0
final_deadline=$((SECONDS + 60))
while [[ "$SECONDS" -lt "$final_deadline" ]]; do
  if timeout 5 ros2 topic echo /robot/pose --once >/dev/null 2>&1 &&
     timeout 5 ros2 topic echo /robot/scan --once >/dev/null 2>&1 &&
     timeout 5 ros2 topic echo /robot/diagnostics --once >/dev/null 2>&1 &&
     timeout 5 ros2 action info /robot/task/execute 2>/dev/null |
       grep -q 'Action servers: 1'; then
    final_ready=1
    break
  fi
  sleep 2
done
if [[ "$final_ready" -ne 1 ]]; then
  echo "任务前最终Ready门禁未在60秒内通过，拒绝发送任务" >&2
  exit 1
fi
echo "任务前最终Ready门禁：通过"

# 安全监督可能在较长的启动/检查空窗重新锁存command_timeout。必须在所有耗时
# Ready检查之后清除，并立即进入Runner，不能在清除与发任务之间继续等待。
echo "最终清除安全故障并确认stop_active=false..."
timeout 15 ros2 service call /robot/safety/clear_faults std_srvs/srv/Trigger "{}" \
  >"$BATCH_DIR/process/clear_faults.txt"
if ! timeout 15 ros2 topic echo /robot/safety/stop_active --once \
     >"$BATCH_DIR/process/stop_active.txt"; then
  echo "未能读取安全停车状态" >&2; exit 1
fi
if ! grep -q 'data: false' "$BATCH_DIR/process/stop_active.txt"; then
  echo "安全停车仍处于激活状态，拒绝发送任务" >&2; exit 1
fi

command=(python3 -m portfolio.robot_ops_analytics.orchestrator.run_w4_batch
  --plan "$PLAN" --environment-profile "$PROFILE"
  --experiment-id "$EXPERIMENT_ID" --output-dir "$BATCH_DIR/batch_runner"
  --execute --auto-contiguous)
for task_id in "${TASK_IDS[@]}"; do command+=(--task-id "$task_id"); done

echo "开始顺序执行：${TASK_IDS[*]}"
"${command[@]}"
echo "任务组完成；开始统一清理和无残留验收"
