from portfolio.robot_ops_analytics.job_search.analysis.analyze_decision_scenarios import (
    capacity_scenarios, cross_validated_segmented_budgets, summarize_policy,
)


def rows(outlier=False):
    output = []
    for block in range(1, 16):
        for index, profile in enumerate(("none", "low", "medium")):
            cycle = 10.0 + block + index * 10
            if outlier and block == 15 and profile == "medium":
                cycle = 1000.0
            output.append({
                "task_id": f"b{block}-{profile}",
                "validation_block": block,
                "obstacle_profile": profile,
                "cycle_time_sec": cycle,
                "max_abs_lateral_deviation_m": float(index),
                "safety_stop": False,
                "stale_sensor": False,
                "valid_telemetry_coverage_rate": 1.0,
            })
    return output


def test_lobo_budget_does_not_read_held_out_outlier():
    budgets = cross_validated_segmented_budgets(rows(outlier=True), .95)
    assert budgets["b15-medium"] < 1000
    assert budgets["b14-medium"] > 100


def test_policy_summary_counts_success_task_over_budget():
    data = rows()
    budgets = {row["task_id"]: 30.0 for row in data}
    summary, details = summarize_policy(data, "fixed_30s", budgets)
    overall = next(row for row in summary if row["obstacle_profile"] == "overall")
    assert overall["task_count"] == 45
    assert overall["potential_false_escalation_count"] == sum(
        row["cycle_time_sec"] > 30 for row in data)
    assert len(details) == 45


def test_capacity_worsens_when_complex_tasks_dominate():
    result = {row["scenario"]: row for row in capacity_scenarios(rows(), resamples=100)}
    assert (result["simple_heavy"]["theoretical_tasks_per_hour"] >
            result["balanced"]["theoretical_tasks_per_hour"] >
            result["complex_heavy"]["theoretical_tasks_per_hour"])
