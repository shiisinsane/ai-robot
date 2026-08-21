#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
OUTPUT_ROOT="$ROOT_DIR/artifacts/roa_w4/roa-data-v0.1"
START_DOMAIN=227
PREVIEW=0
CAMPAIGN_ID="001"
START_INDEX=1

usage() {
  echo "用法：$0 [--output-root PATH] [--start-domain ID] [--start-index 1..6] [--campaign-id ID] [--preview]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-root) OUTPUT_ROOT=$2; shift 2 ;;
    --start-domain) START_DOMAIN=$2; shift 2 ;;
    --campaign-id) CAMPAIGN_ID=$2; shift 2 ;;
    --start-index) START_INDEX=$2; shift 2 ;;
    --preview) PREVIEW=1; shift ;;
    *) usage; exit 2 ;;
  esac
done

if [[ ! "$START_INDEX" =~ ^[1-6]$ ]]; then
  echo "--start-index必须位于1～6"; exit 2
fi
if [[ ! "$START_DOMAIN" =~ ^([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-2][0-9]|23[0-2])$ ]] ||
   (( START_DOMAIN + 6 - START_INDEX > 232 )); then
  echo "起始ROS域必须保证剩余环境使用的连续域均位于0～232"; exit 2
fi
if [[ ! "$CAMPAIGN_ID" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "--campaign-id只能使用字母、数字、下划线或连字符"; exit 2
fi

OUTPUT_ROOT=$(realpath -m "$OUTPUT_ROOT")
mkdir -p "$OUTPUT_ROOT"
PLAN="$OUTPUT_ROOT/medium-obstacle-campaign-plan.jsonl"
cd "$ROOT_DIR"
python3 -m portfolio.robot_ops_analytics.orchestrator.generate_w4_matrix --output "$PLAN"

# 三次短路线各需新环境；两组长出+返回可连续执行。返回第1次先用公共导航Action做非样本起点准备。
RUN_GROUPS=(
  "001|none|w4-0037"
  "002|none|w4-0038"
  "003|none|w4-0039"
  "004|none|w4-0092 w4-0146"
  "005|none|w4-0093 w4-0147"
  "006|return_start|w4-0145"
)

campaign_log="$OUTPUT_ROOT/medium-obstacle-campaign-${CAMPAIGN_ID}-results.tsv"
if [[ -e "$campaign_log" ]]; then
  echo "Campaign结果已存在，拒绝覆盖：$campaign_log"; exit 2
fi
printf 'batch_id\tdomain_id\ttasks\tresult\n' >"$campaign_log"

for index in "${!RUN_GROUPS[@]}"; do
  group_number=$((index + 1))
  if (( group_number < START_INDEX )); then continue; fi
  IFS='|' read -r suffix preparation task_text <<<"${RUN_GROUPS[$index]}"
  batch_id="medium-pilot-campaign-$suffix"
  batch_dir="$OUTPUT_ROOT/$batch_id"
  domain_id=$((START_DOMAIN + group_number - START_INDEX))
  partition="roa_w4_medium_campaign_${suffix}"
  if [[ -e "$batch_dir" ]]; then
    retry=1
    while [[ -e "$OUTPUT_ROOT/${batch_id}-retry-$(printf '%03d' "$retry")" ]]; do
      retry=$((retry + 1))
    done
    batch_id="${batch_id}-retry-$(printf '%03d' "$retry")"
    batch_dir="$OUTPUT_ROOT/$batch_id"
    echo "原批次已有证据，本次使用新目录：$batch_id"
  fi
  mkdir -p "$batch_dir"
  cp "$PLAN" "$batch_dir/plan.jsonl"
  command=(bash portfolio/robot_ops_analytics/scripts/run_w4_safe_group.sh
    --batch-dir "$batch_dir" --domain-id "$domain_id" --partition "$partition"
    --experiment-id "roa-w4-$batch_id" --plan "$batch_dir/plan.jsonl"
    --environment-profile natural__medium__none__baseline --obstacle-profile medium)
  if [[ "$preparation" == "return_start" ]]; then
    command+=(--prepare-start 0.8 0.0 0.0)
  fi
  for task_id in $task_text; do command+=(--task-id "$task_id"); done
  echo "[$group_number/${#RUN_GROUPS[@]}] 执行$batch_id：$task_text"
  if [[ "$PREVIEW" -eq 1 ]]; then
    printf '%s\t%s\t%s\tpreview\n' "$batch_id" "$domain_id" "$task_text" >>"$campaign_log"
  elif "${command[@]}"; then
    printf '%s\t%s\t%s\tpassed\n' "$batch_id" "$domain_id" "$task_text" >>"$campaign_log"
  else
    printf '%s\t%s\t%s\tfailed\n' "$batch_id" "$domain_id" "$task_text" >>"$campaign_log"
    echo "$batch_id失败；Campaign停止，不启动下一套环境" >&2
    exit 1
  fi
done

if [[ "$PREVIEW" -eq 1 ]]; then
  echo "中障碍Campaign预览完成：6套环境、8项正式任务；未启动ROS/Gazebo。"
else
  echo "中障碍Campaign完成：8项正式任务全部执行，6套环境均通过清理门禁。"
fi
