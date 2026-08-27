#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
CONFIG="$ROOT_DIR/portfolio/robot_ops_analytics/config/w6_a1_validation_v0.1.yaml"
OUTPUT_ROOT="$ROOT_DIR/artifacts/roa_w6/roa-validation-a1-v0.1"
START_DOMAIN=180
START_INDEX=1
CAMPAIGN_ID="001"
PREVIEW=0

usage() {
  echo "用法：$0 [--output-root PATH] [--start-domain 0..203] [--start-index 1..30] [--campaign-id ID] [--preview]"
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

if [[ ! "$START_INDEX" =~ ^([1-9]|[12][0-9]|30)$ ]]; then
  echo "--start-index必须位于1～30"; exit 2
fi
if [[ ! "$START_DOMAIN" =~ ^([0-9]|[1-9][0-9]|1[0-9]{2}|20[0-3])$ ]] ||
   (( START_DOMAIN + 30 - START_INDEX > 232 )); then
  echo "起始ROS域必须保证剩余槽位使用的连续域均位于0～232"; exit 2
fi
if [[ ! "$CAMPAIGN_ID" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "--campaign-id只能使用字母、数字、下划线或连字符"; exit 2
fi

OUTPUT_ROOT=$(realpath -m "$OUTPUT_ROOT")
mkdir -p "$OUTPUT_ROOT"
PLAN="$OUTPUT_ROOT/a1-frozen-plan.jsonl"
cd "$ROOT_DIR"
python3 -m portfolio.robot_ops_analytics.pipelines.legacy_v0_1.generate_w6_a1_plan \
  --config "$CONFIG" --output "$PLAN"

campaign_log="$OUTPUT_ROOT/a1-campaign-${CAMPAIGN_ID}-results.tsv"
if [[ -e "$campaign_log" ]]; then
  echo "Campaign结果已存在，拒绝覆盖：$campaign_log"; exit 2
fi
printf 'run_order\tblock\tobstacle_profile\ttask_id\tbatch_id\tdomain_id\tvalidation\n' \
  >"$campaign_log"

mapfile -t PLAN_ROWS <"$PLAN"
for index in "${!PLAN_ROWS[@]}"; do
  run_order=$((index + 1))
  if (( run_order < START_INDEX )); then continue; fi
  read -r task_id block obstacle profile < <(python3 -c \
    'import json,sys; x=json.loads(sys.argv[1]); print(x["task_id"],x["validation_block"],x["obstacle_profile"],x["environment_profile"])' \
    "${PLAN_ROWS[$index]}")
  suffix=$(printf '%03d' "$run_order")
  batch_id="a1-slot-$suffix"
  batch_dir="$OUTPUT_ROOT/$batch_id"
  if [[ -e "$batch_dir" ]]; then
    retry=1
    while [[ -e "$OUTPUT_ROOT/${batch_id}-retry-$(printf '%03d' "$retry")" ]]; do
      retry=$((retry + 1))
    done
    batch_id="${batch_id}-retry-$(printf '%03d' "$retry")"
    batch_dir="$OUTPUT_ROOT/$batch_id"
  fi
  domain_id=$((START_DOMAIN + run_order - START_INDEX))
  partition="roa_w6_a1_${CAMPAIGN_ID}_${suffix}"

  if [[ "$PREVIEW" -eq 1 ]]; then
    printf '%s\t%s\t%s\t%s\t%s\t%s\tpreview\n' \
      "$run_order" "$block" "$obstacle" "$task_id" "$batch_id" "$domain_id" \
      >>"$campaign_log"
    continue
  fi

  mkdir -p "$batch_dir"
  cp "$PLAN" "$batch_dir/plan.jsonl"
  cp "$CONFIG" "$batch_dir/w6_a1_validation_config.yaml"
  echo "[$run_order/30] 执行$task_id：block=$block obstacle=$obstacle domain=$domain_id"
  if bash portfolio/robot_ops_analytics/scripts/common/run_w4_safe_group.sh \
      --batch-dir "$batch_dir" --domain-id "$domain_id" --partition "$partition" \
      --experiment-id "roa-w6-$batch_id" --plan "$batch_dir/plan.jsonl" \
      --environment-profile "$profile" --obstacle-profile "$obstacle" \
      --initial-perturbation none --prepare-start 0.8 0.0 0.0 \
      --task-id "$task_id" --continue-on-task-failure; then
    validation=$(python3 -m portfolio.robot_ops_analytics.pipelines.common.validate_w4_sample \
      --batch-dir "$batch_dir" --task-id "$task_id") || {
        printf '%s\t%s\t%s\t%s\t%s\t%s\tinvalid\n' \
          "$run_order" "$block" "$obstacle" "$task_id" "$batch_id" "$domain_id" \
          >>"$campaign_log"
        echo "$batch_id未通过样本门禁；停止并保留证据，从同一槽位恢复" >&2
        exit 1
      }
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$run_order" "$block" "$obstacle" "$task_id" "$batch_id" "$domain_id" \
      "$validation" >>"$campaign_log"
  else
    printf '%s\t%s\t%s\t%s\t%s\t%s\tinvalid\n' \
      "$run_order" "$block" "$obstacle" "$task_id" "$batch_id" "$domain_id" \
      >>"$campaign_log"
    echo "$batch_id执行或清理失败；停止且不启动下一槽位" >&2
    exit 1
  fi
done

if [[ "$PREVIEW" -eq 1 ]]; then
  echo "A1 Campaign预览完成：30槽位；未启动ROS/Gazebo。"
else
  echo "A1 Campaign完成：30个有效槽位均执行并通过样本与清理门禁。"
fi
