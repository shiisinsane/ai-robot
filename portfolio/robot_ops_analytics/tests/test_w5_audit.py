import json
from pathlib import Path

import yaml

from portfolio.robot_ops_analytics.etl.audit_baseline import audit_batch, audit_dataset


def make_batch(root: Path, name="batch-1", task_id="task-1", success=True):
    batch = root / name
    (batch / "batch_runner").mkdir(parents=True)
    (batch / "structured").mkdir()
    (batch / "process").mkdir()
    bag = batch / "rosbag/w4_pilot_bag"
    bag.mkdir(parents=True)
    result = {
        "task_id": task_id, "experiment_id": f"exp-{task_id}",
        "return_code": 0 if success else 1, "run_origin": "natural",
        "route_id": "short_out", "obstacle_profile": "none",
        "initial_perturbation": "none", "parameter_profile": "baseline",
        "repetition": 1,
    }
    (batch / "batch_runner/run_results.jsonl").write_text(
        json.dumps(result) + "\n", encoding="utf-8")
    records = [
        {"task_id": task_id, "record_type": "task_telemetry_1s",
         "bucket_start_sim": 1.0, "required_topics_present": True,
         "timestamp_valid": True},
        {"task_id": task_id, "record_type": "task_context", "event": "terminal",
         "success": success, "action_status": 4 if success else 6,
         "error_code": 0 if success else 201},
    ]
    (batch / "structured/records.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    (batch / "process/residue_check.txt").write_text(
        "本批进程组残留检查：通过\n", encoding="utf-8")
    metadata = {"rosbag2_bagfile_information": {"message_count": 10}}
    (bag / "metadata.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
    (bag / "bag.db3").write_bytes(b"data")
    return batch


def test_audit_batch_accepts_complete_success_and_failure(tmp_path):
    assert audit_batch(make_batch(tmp_path, success=True))[0][
        "terminal_status"] == "success"
    assert audit_batch(make_batch(tmp_path, "batch-2", "task-2", False))[0][
        "terminal_status"] == "failed"


def test_audit_dataset_rejects_duplicate_task_ids(tmp_path):
    make_batch(tmp_path, "batch-1", "same")
    make_batch(tmp_path, "batch-2", "same")
    report = audit_dataset(tmp_path, "test-v1")
    assert report["quality_gate_passed"] is False
    assert report["counts"]["valid_tasks"] == 0
    assert "重复任务ID" in report["quality_failures"][0]["reason"]


def test_audit_dataset_reports_incomplete_telemetry(tmp_path):
    batch = make_batch(tmp_path)
    path = batch / "structured/records.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["required_topics_present"] = False
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    report = audit_dataset(tmp_path, "test-v1")
    assert report["counts"]["invalid_batches"] == 1
    assert "不完整" in report["quality_failures"][0]["reason"]
