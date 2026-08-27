#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
CONFIG="$ROOT_DIR/portfolio/robot_ops_analytics/config/w6_b1_preregistration_v0.2.yaml"
OBSTACLE_CONFIG="$ROOT_DIR/portfolio/robot_ops_analytics/config/w6_b1_long_route_draft_v0.2.yaml"
OUTPUT_ROOT="$ROOT_DIR/artifacts/roa_b1/roa-validation-b1-v0.2"
START_DOMAIN=100
START_INDEX=1
CAMPAIGN_ID="001"
PREVIEW=0

usage() {
  echo "用法：$0 [--output-root PATH] [--start-domain 0..188] [--start-index 1..45] [--campaign-id ID] [--preview]"
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

if [[ ! "$START_INDEX" =~ ^([1-9]|[1-3][0-9]|4[0-5])$ ]]; then
  echo "--start-index必须位于1～45"; exit 2
fi
if [[ ! "$START_DOMAIN" =~ ^([0-9]|[1-9][0-9]|1[0-8][0-9])$ ]] ||
   (( START_DOMAIN + 45 - START_INDEX > 232 )); then
  echo "起始ROS域必须保证剩余槽位使用的连续域均位于0～232"; exit 2
fi
if [[ ! "$CAMPAIGN_ID" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "--campaign-id格式无效"; exit 2
fi

OUTPUT_ROOT=$(realpath -m "$OUTPUT_ROOT")
mkdir -p "$OUTPUT_ROOT"
PLAN="$OUTPUT_ROOT/frozen-plan.jsonl"
cd "$ROOT_DIR"
execution_state=$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["execution_control"]["state"])' "$CONFIG")
if [[ "$PREVIEW" -eq 0 && "$execution_state" != "active" ]]; then
  echo "B1正式执行当前状态为$execution_state，拒绝启动；需用户明确恢复"; exit 2
fi
python3 -m portfolio.robot_ops_analytics.pipelines.b1_v0_2.generate_w6_b1_formal_plan \
  --config "$CONFIG" --output "$PLAN"

campaign_log="$OUTPUT_ROOT/b1-campaign-${CAMPAIGN_ID}-results.tsv"
if [[ -e "$campaign_log" ]]; then
  echo "Campaign结果已存在，拒绝覆盖：$campaign_log"; exit 2
fi
printf 'run_order\tblock\tobstacle_profile\ttask_id\tbatch_id\tdomain_id\tvalidation\n' >"$campaign_log"

mapfile -t PLAN_ROWS <"$PLAN"
for index in "${!PLAN_ROWS[@]}"; do
  run_order=$((index + 1))
  if (( run_order < START_INDEX )); then continue; fi
  read -r task_id block obstacle profile < <(python3 -c \
    'import json,sys; x=json.loads(sys.argv[1]); print(x["task_id"],x["validation_block"],x["obstacle_profile"],x["environment_profile"])' \
    "${PLAN_ROWS[$index]}")
  suffix=$(printf '%03d' "$run_order")
  batch_id="b1-slot-$suffix"
  batch_dir="$OUTPUT_ROOT/$batch_id"
  if [[ -e "$batch_dir" ]]; then
    retry=1
    while [[ -e "$OUTPUT_ROOT/${batch_id}-retry-$(printf '%03d' "$retry")" ]]; do retry=$((retry + 1)); done
    batch_id="${batch_id}-retry-$(printf '%03d' "$retry")"
    batch_dir="$OUTPUT_ROOT/$batch_id"
  fi
  domain_id=$((START_DOMAIN + run_order - START_INDEX))
  partition="roa_b1_${CAMPAIGN_ID}_${suffix}"

  if [[ "$PREVIEW" -eq 1 ]]; then
    printf '%s\t%s\t%s\t%s\t%s\t%s\tpreview\n' "$run_order" "$block" "$obstacle" "$task_id" "$batch_id" "$domain_id" >>"$campaign_log"
    continue
  fi

  mkdir -p "$batch_dir"
  cp "$PLAN" "$batch_dir/plan.jsonl"
  cp "$CONFIG" "$batch_dir/w6_b1_preregistration.yaml"
  echo "[$run_order/45] 执行$task_id：block=$block obstacle=$obstacle domain=$domain_id"
  if env LIBGL_ALWAYS_SOFTWARE=1 bash portfolio/robot_ops_analytics/scripts/common/run_w4_safe_group.sh \
      --batch-dir "$batch_dir" --domain-id "$domain_id" --partition "$partition" \
      --experiment-id "roa-b1-$batch_id" --plan "$batch_dir/plan.jsonl" \
      --environment-profile "$profile" --obstacle-profile "$obstacle" \
      --obstacle-config "$OBSTACLE_CONFIG" --initial-perturbation none \
      --initial-pose -2.0 0.0 0.0 --task-id "$task_id" --continue-on-task-failure; then
    validation=$(python3 -m portfolio.robot_ops_analytics.pipelines.common.validate_w4_sample \
      --batch-dir "$batch_dir" --task-id "$task_id") || {
        printf '%s\t%s\t%s\t%s\t%s\t%s\tinvalid\n' "$run_order" "$block" "$obstacle" "$task_id" "$batch_id" "$domain_id" >>"$campaign_log"
        echo "$batch_id未通过样本门禁；停止并从同一槽位恢复" >&2; exit 1;
      }
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$run_order" "$block" "$obstacle" "$task_id" "$batch_id" "$domain_id" "$validation" >>"$campaign_log"
  else
    printf '%s\t%s\t%s\t%s\t%s\t%s\tinvalid\n' "$run_order" "$block" "$obstacle" "$task_id" "$batch_id" "$domain_id" >>"$campaign_log"
    echo "$batch_id执行或清理失败；停止且不启动下一槽位" >&2; exit 1
  fi
done

if [[ "$PREVIEW" -eq 1 ]]; then
  echo "B1 Campaign预览完成：45槽位；未启动ROS/Gazebo。"
else
  echo "B1 Campaign完成：45个有效槽位均通过样本与清理门禁。"
fi
