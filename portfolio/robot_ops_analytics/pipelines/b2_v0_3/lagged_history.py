"""为B2第N项任务只使用前N-1项有效结果计算严格滞后历史。"""

from __future__ import annotations


def lagged_history(valid_results: list[dict], current_plan_index: int,
                   window: int = 10) -> dict:
    if current_plan_index < 1:
        raise ValueError("plan_index必须从1开始")
    prior = [row for row in valid_results if int(row["plan_index"]) < current_plan_index]
    if any(int(row["plan_index"]) >= current_plan_index for row in prior):
        raise AssertionError("历史窗口包含当前或未来任务")
    by_index = {}
    for row in prior:
        index = int(row["plan_index"])
        if index in by_index:
            raise ValueError(f"前序有效结果plan_index重复：{index}")
        if not row.get("valid", False):
            continue
        by_index[index] = row
    expected_prior = set(range(1, current_plan_index))
    if set(by_index) != expected_prior:
        missing = sorted(expected_prior - set(by_index))
        raise ValueError(f"前序有效结果不连续，拒绝构造历史：missing={missing[:10]}")
    selected = [by_index[index] for index in sorted(by_index)[-window:]]
    if not selected:
        return {"prior_task_count_window_10": 0, "prior_failure_count_window_10": 0,
                "prior_timeout_count_window_10": 0, "no_history": True}
    return {
        "prior_task_count_window_10": len(selected),
        "prior_failure_count_window_10": sum(
            row["terminal_status"] in {"failed", "timeout"} for row in selected),
        "prior_timeout_count_window_10": sum(
            row["terminal_status"] == "timeout" for row in selected),
        "no_history": False,
    }
