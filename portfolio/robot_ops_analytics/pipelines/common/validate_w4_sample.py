"""验证单任务W4批次是否形成可保留的完整成功或失败样本。"""

import argparse
import json
from pathlib import Path

import yaml


def validate(batch_dir: Path, task_id: str):
    results_path = batch_dir / "batch_runner/run_results.jsonl"
    records_path = batch_dir / "structured/records.jsonl"
    residue_path = batch_dir / "process/residue_check.txt"
    metadata_path = batch_dir / "rosbag/w4_pilot_bag/metadata.yaml"
    for path in (results_path, records_path, residue_path, metadata_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"缺少或为空：{path}")
    results = [json.loads(line) for line in results_path.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    matches = [row for row in results if row.get("task_id") == task_id]
    if len(matches) != 1:
        raise ValueError(f"{task_id}执行索引数量不是1：{len(matches)}")
    records = [json.loads(line) for line in records_path.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    terminals = [row for row in records if row.get("task_id") == task_id and
                 row.get("record_type") == "task_context" and
                 row.get("event") == "terminal"]
    telemetry = [row for row in records if row.get("task_id") == task_id and
                 row.get("record_type") == "task_telemetry_1s"]
    if len(terminals) != 1:
        raise ValueError(f"{task_id}终态数量不是1：{len(terminals)}")
    if not telemetry or not all(row.get("required_topics_present") and
                                row.get("timestamp_valid") for row in telemetry):
        raise ValueError(f"{task_id}缺少完整有效遥测")
    if any(row.get("safety_stop_active") for row in telemetry):
        raise ValueError(f"{task_id}任务窗口出现安全停车，需人工复核")
    if "本批进程组残留检查：通过" not in residue_path.read_text(encoding="utf-8"):
        raise ValueError("进程残留门禁未通过")
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    bagfiles = list((batch_dir / "rosbag/w4_pilot_bag").glob("*.db3"))
    if not bagfiles or not all(path.stat().st_size > 0 for path in bagfiles):
        raise ValueError("rosbag数据库缺失或为空")
    message_count = int(metadata.get("rosbag2_bagfile_information", {}).get(
        "message_count", 0))
    if message_count <= 0:
        raise ValueError("rosbag消息数为0")
    success = bool(terminals[0].get("success"))
    expected_return = 0 if success else 1
    if matches[0].get("return_code") != expected_return:
        raise ValueError("Runner返回码与Action终态不一致")
    return "valid_success" if success else "valid_failure"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()
    try:
        result = validate(args.batch_dir, args.task_id)
    except (ValueError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise SystemExit(str(error)) from error
    print(result)


if __name__ == "__main__":
    main()
