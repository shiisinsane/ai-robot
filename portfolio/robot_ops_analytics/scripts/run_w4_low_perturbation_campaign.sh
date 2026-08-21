#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
OUTPUT_ROOT="$ROOT_DIR/artifacts/roa_w4/roa-data-v0.1"
START_DOMAIN=200
START_INDEX=1
CAMPAIGN_ID="001"
PREVIEW=0

usage() {
  echo "用法：$0 [--output-root PATH] [--start-domain ID] [--start-index 1..26] [--campaign-id ID] [--preview]"
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
if [[ ! "$START_INDEX" =~ ^([1-9]|1[0-9]|2[0-6])$ ]]; then
  echo "--start-index必须位于1～26"; exit 2
fi
if [[ ! "$START_DOMAIN" =~ ^([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-2][0-9]|23[0-2])$ ]] ||
   (( START_DOMAIN + 26 - START_INDEX > 232 )); then
  echo "起始ROS域必须保证剩余环境使用的连续域均位于0～232"; exit 2
fi
if [[ ! "$CAMPAIGN_ID" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "--campaign-id只能使用字母、数字、下划线或连字符"; exit 2
fi

CASES=(
  "w4-0008|none|0.05" "w4-0009|none|0.05"
  "w4-0025|low|0.05" "w4-0026|low|0.05" "w4-0027|low|0.05"
  "w4-0043|medium|0.05" "w4-0044|medium|0.05" "w4-0045|medium|0.05"
  "w4-0061|none|0.05" "w4-0062|none|0.05" "w4-0063|none|0.05"
  "w4-0079|low|0.05" "w4-0080|low|0.05" "w4-0081|low|0.05"
  "w4-0097|medium|0.05" "w4-0098|medium|0.05" "w4-0099|medium|0.05"
  "w4-0115|none|0.85" "w4-0116|none|0.85" "w4-0117|none|0.85"
  "w4-0133|low|0.85" "w4-0134|low|0.85" "w4-0135|low|0.85"
  "w4-0151|medium|0.85" "w4-0152|medium|0.85" "w4-0153|medium|0.85"
)

OUTPUT_ROOT=$(realpath -m "$OUTPUT_ROOT")
mkdir -p "$OUTPUT_ROOT"
REJECTED_ROOT="$(dirname "$OUTPUT_ROOT")/rejected-v0.1"
PLAN="$OUTPUT_ROOT/low-perturbation-campaign-plan.jsonl"
cd "$ROOT_DIR"
python3 -m portfolio.robot_ops_analytics.orchestrator.generate_w4_matrix --output "$PLAN"
campaign_log="$OUTPUT_ROOT/low-perturbation-campaign-${CAMPAIGN_ID}-results.tsv"
if [[ -e "$campaign_log" ]]; then
  echo "Campaign结果已存在，拒绝覆盖：$campaign_log"; exit 2
fi
printf 'batch_id\tdomain_id\ttask\tobstacle\tresult\n' >"$campaign_log"

for index in "${!CASES[@]}"; do
  case_number=$((index + 1))
  if (( case_number < START_INDEX )); then continue; fi
  IFS='|' read -r task_id obstacle spawn_x <<<"${CASES[$index]}"
  suffix=${task_id#w4-}
  batch_id="initial-low-campaign-$suffix"
  batch_dir="$OUTPUT_ROOT/$batch_id"
  if [[ -e "$batch_dir" || -e "$REJECTED_ROOT/$batch_id" ]]; then
    retry=1
    while [[ -e "$OUTPUT_ROOT/${batch_id}-retry-$(printf '%03d' "$retry")" ||
             -e "$REJECTED_ROOT/${batch_id}-retry-$(printf '%03d' "$retry")" ]]; do
      retry=$((retry + 1))
    done
    batch_id="${batch_id}-retry-$(printf '%03d' "$retry")"
    batch_dir="$OUTPUT_ROOT/$batch_id"
  fi
  domain_id=$((START_DOMAIN + case_number - START_INDEX))
  partition="roa_w4_initial_low_${suffix}_${CAMPAIGN_ID}"
  mkdir -p "$batch_dir"
  cp "$PLAN" "$batch_dir/plan.jsonl"
  command=(bash portfolio/robot_ops_analytics/scripts/run_w4_safe_group.sh
    --batch-dir "$batch_dir" --domain-id "$domain_id" --partition "$partition"
    --experiment-id "roa-w4-$batch_id" --plan "$batch_dir/plan.jsonl"
    --environment-profile "natural__${obstacle}__low__baseline"
    --obstacle-profile "$obstacle" --initial-perturbation low
    --initial-pose "$spawn_x" 0.0 0.05 --task-id "$task_id")
  echo "[$case_number/${#CASES[@]}] 执行$batch_id：$task_id obstacle=$obstacle"
  if [[ "$PREVIEW" -eq 1 ]]; then
    result=preview
  else
    set +e
    "${command[@]}"
    runner_status=$?
    set -e
    if ! result=$(python3 -m portfolio.robot_ops_analytics.orchestrator.validate_w4_sample \
        --batch-dir "$batch_dir" --task-id "$task_id"); then
      printf '%s\t%s\t%s\t%s\tinvalid\n' "$batch_id" "$domain_id" "$task_id" "$obstacle" >>"$campaign_log"
      echo "$batch_id未形成完整样本（Runner返回$runner_status）；Campaign停止" >&2
      exit 1
    fi
  fi
  printf '%s\t%s\t%s\t%s\t%s\n' "$batch_id" "$domain_id" "$task_id" "$obstacle" "$result" >>"$campaign_log"
done

if [[ "$PREVIEW" -eq 1 ]]; then
  echo "低档初始扰动Campaign预览完成：26套独立环境、26项任务；未启动ROS/Gazebo。"
else
  echo "低档初始扰动Campaign完成：26项均形成完整成功或失败样本。"
fi
