from pathlib import Path

import yaml

from portfolio.robot_ops_analytics.pipelines.b2_v0_3.generate_w7_b2_plan import generate
from portfolio.robot_ops_analytics.pipelines.b2_v0_3.lagged_history import lagged_history


ROOT = Path(__file__).resolve().parents[2]


def test_b2_plan_is_deterministic_balanced_and_split_by_whole_block():
    config = yaml.safe_load((ROOT / "config/w7_b2_design_draft_v0.1.yaml").read_text())
    first, second = generate(config), generate(config)
    assert first == second
    assert len(first) == 360
    assert [row["plan_index"] for row in first] == list(range(1, 361))
    assert len({row["task_id"] for row in first}) == 360
    for block in range(1, 9):
        rows = [row for row in first if row["randomized_block"] == block]
        assert len(rows) == 45
        assert len({(row["route_id"], row["obstacle_profile"], row["initial_perturbation"])
                    for row in rows}) == 45
        assert len({row["model_split"] for row in rows}) == 1
    assert {split: len([row for row in first if row["model_split"] == split])
            for split in ("train", "validation", "sealed_test")} == {
                "train": 180, "validation": 90, "sealed_test": 90}
    assert all(row["preacceptance_snapshot_required"] for row in first)
    assert all(not row["environment_ready"] for row in first)
    assert max(row["plan_index"] for row in first if row["model_split"] == "train") < min(
        row["plan_index"] for row in first if row["model_split"] == "validation")
    assert max(row["plan_index"] for row in first if row["model_split"] == "validation") < min(
        row["plan_index"] for row in first if row["model_split"] == "sealed_test")


def test_lagged_history_never_uses_current_or_future_result():
    rows = [{"plan_index": index, "valid": True,
             "terminal_status": "timeout" if index == 5 else
             ("failed" if index % 3 == 0 else "success")} for index in range(1, 13)]
    first = lagged_history([], 1)
    assert first == {"prior_task_count_window_10": 0, "prior_failure_count_window_10": 0,
                     "prior_timeout_count_window_10": 0, "no_history": True}
    history = lagged_history(rows, 13)
    assert history["prior_task_count_window_10"] == 10
    assert history["prior_timeout_count_window_10"] == 1
    assert history["prior_failure_count_window_10"] == 5


def test_lagged_history_fails_when_prior_valid_slot_is_missing():
    rows = [{"plan_index": 1, "valid": True, "terminal_status": "success"}]
    try:
        lagged_history(rows, 3)
    except ValueError as error:
        assert "不连续" in str(error)
    else:
        raise AssertionError("缺少前序槽位时必须失败关闭")


def test_batch_runner_forwards_b2_snapshot_metadata_and_explicit_history():
    text = (ROOT / "pipelines/common/run_w4_batch.py").read_text(encoding="utf-8")
    for token in ("preacceptance_snapshot_required", "--preacceptance-snapshot-required",
                  "--dataset-version", "--source-batch-id", "--route-id",
                  "--prior-task-count-window-10", "--prior-failure-count-window-10",
                  "--prior-timeout-count-window-10"):
        assert token in text
    assert "B2任务必须显式传入严格滞后的三个历史计数" in text
