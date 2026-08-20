#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
OUTPUT_ROOT="$ROOT_DIR/artifacts/roa_w4/roa-data-v0.1"
START_DOMAIN=213
PLAN=""
PREVIEW=0
START_INDEX=1
CAMPAIGN_ID="002"

usage() {
  echo "用法：$0 [--output-root PATH] [--start-domain ID] [--start-index 1..5] [--campaign-id ID] [--preview]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-root) OUTPUT_ROOT=$2; shift 2 ;;
    --start-domain) START_DOMAIN=$2; shift 2 ;;
    --start-index) START_INDEX=$2; shift 2 ;;
    --campaign-id) CAMPAIGN_ID=$2; shift 2 ;;
    --preview) PREVIEW=1; shift ;;
    *) usage; exit 2 ;;
  esac
done

if [[ ! "$START_INDEX" =~ ^[1-5]$ ]]; then
  echo "--start-index必须位于1～5"; exit 2
fi
if [[ ! "$START_DOMAIN" =~ ^([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-2][0-9]|23[0-2])$ ]] ||
   (( START_DOMAIN + 5 - START_INDEX > 232 )); then
  echo "起始ROS域必须保证剩余环境使用的连续域均位于0～232"; exit 2
fi
if [[ ! "$CAMPAIGN_ID" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "--campaign-id只能使用字母、数字、下划线或连字符"; exit 2
fi

OUTPUT_ROOT=$(realpath -m "$OUTPUT_ROOT")
mkdir -p "$OUTPUT_ROOT"
PLAN="$OUTPUT_ROOT/low-obstacle-campaign-plan.jsonl"
cd "$ROOT_DIR"
python3 -m portfolio.robot_ops_analytics.orchestrator.generate_w4_matrix \
  --output "$PLAN"

# 每行：批次后缀|任务列表。短路线重复必须各用新环境复位；长出与返回首尾连续，可成对执行。
RUN_GROUPS=(
  "002|w4-0020"
  "003|w4-0021"
  "004|w4-0073 w4-0127"
  "005|w4-0074 w4-0128"
  "006|w4-0075 w4-0129"
)

campaign_log="$OUTPUT_ROOT/low-obstacle-campaign-${CAMPAIGN_ID}-results.tsv"
if [[ -e "$campaign_log" ]]; then
  echo "Campaign结果已存在，拒绝覆盖：$campaign_log"; exit 2
fi
printf 'batch_id\tdomain_id\ttasks\tresult\n' >"$campaign_log"

selected_groups=$((6 - START_INDEX))
selected_tasks=0
for count_index in "${!RUN_GROUPS[@]}"; do
  if (( count_index + 1 < START_INDEX )); then continue; fi
  IFS='|' read -r _ count_task_text <<<"${RUN_GROUPS[$count_index]}"
  read -r -a count_tasks <<<"$count_task_text"
  selected_tasks=$((selected_tasks + ${#count_tasks[@]}))
done

for index in "${!RUN_GROUPS[@]}"; do
  group_number=$((index + 1))
  if (( group_number < START_INDEX )); then continue; fi
  IFS='|' read -r suffix task_text <<<"${RUN_GROUPS[$index]}"
  batch_id="low-pilot-$suffix"
  batch_dir="$OUTPUT_ROOT/$batch_id"
  domain_id=$((START_DOMAIN + group_number - START_INDEX))
  partition="roa_w4_low_pilot_${suffix}"
  if [[ -e "$batch_dir/rosbag/w4_pilot_bag" ||
        -e "$batch_dir/batch_runner/run_results.jsonl" ]]; then
    retry=1
    while [[ -e "$OUTPUT_ROOT/${batch_id}-retry-$(printf '%03d' "$retry")" ]]; do
      retry=$((retry + 1))
    done
    batch_id="${batch_id}-retry-$(printf '%03d' "$retry")"
    batch_dir="$OUTPUT_ROOT/$batch_id"
    echo "原批次已有产物，本次使用新目录：$batch_id"
  fi
  mkdir -p "$batch_dir"
  cp "$PLAN" "$batch_dir/plan.jsonl"
  command=(bash portfolio/robot_ops_analytics/scripts/run_w4_safe_group.sh
    --batch-dir "$batch_dir" --domain-id "$domain_id"
    --partition "$partition" --experiment-id "roa-w4-$batch_id"
    --plan "$batch_dir/plan.jsonl"
    --environment-profile natural__low__none__baseline
    --obstacle-profile low)
  for task_id in $task_text; do command+=(--task-id "$task_id"); done

  echo "[$group_number/${#RUN_GROUPS[@]}] 执行$batch_id：$task_text"
  if [[ "$PREVIEW" -eq 1 ]]; then
    printf '%s\t%s\t%s\tpreview\n' "$batch_id" "$domain_id" "$task_text" \
      >>"$campaign_log"
    continue
  fi
  if "${command[@]}"; then
    printf '%s\t%s\t%s\tpassed\n' "$batch_id" "$domain_id" "$task_text" \
      >>"$campaign_log"
  else
    printf '%s\t%s\t%s\tfailed\n' "$batch_id" "$domain_id" "$task_text" \
      >>"$campaign_log"
    echo "$batch_id失败；Campaign停止，不启动下一套环境" >&2
    exit 1
  fi
done

if [[ "$PREVIEW" -eq 1 ]]; then
  echo "低障碍Campaign预览完成：${selected_groups}套环境、${selected_tasks}项任务；未启动ROS/Gazebo。"
else
  echo "低障碍Campaign完成：${selected_tasks}项任务全部执行，${selected_groups}套环境均已通过清理门禁。"
fi
