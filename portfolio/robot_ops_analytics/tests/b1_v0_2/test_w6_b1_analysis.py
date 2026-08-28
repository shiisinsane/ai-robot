import random
from pathlib import Path

from portfolio.robot_ops_analytics.pipelines.b1_v0_2.analyze_w6_b1 import (
    bootstrap_median_difference, fisher_two_sided, quantile, wilson,
)


def test_b1_statistical_helpers():
    assert quantile([1, 2, 3, 4], .5) == 2.5
    assert fisher_two_sided(0, 15, 0, 15) == 1.0
    interval = wilson(0, 15)
    assert interval[0] == 0.0
    assert 0.20 < interval[1] < 0.21


def test_b1_bootstrap_is_seeded_and_reports_observed_difference():
    first = bootstrap_median_difference([3, 4, 5], [1, 2, 3], random.Random(7), 100)
    second = bootstrap_median_difference([3, 4, 5], [1, 2, 3], random.Random(7), 100)
    assert first == second
    assert first["estimate"] == 2


def test_b1_sql_catalog_has_gate_kpis_features_and_guardrails():
    sql_dir = Path(__file__).resolve().parents[2] / "sql/b1_v0_2"
    expected = {
        "00_data_contract_checks.sql", "01_obstacle_kpis.sql",
        "02_task_telemetry_features.sql", "03_obstacle_guardrails.sql",
        "04_cross_version_comparison.sql",
    }
    assert expected <= {path.name for path in sql_dir.glob("*.sql")}
    gate = (sql_dir / "00_data_contract_checks.sql").read_text(encoding="utf-8")
    for token in ("task_count=45", "none_count=15", "low_count=15",
                  "medium_count=15", "quality_gate_passed"):
        assert token in gate
    features = (sql_dir / "02_task_telemetry_features.sql").read_text(encoding="utf-8")
    assert "GROUP BY task_id" in features
    assert "MAX(ABS(pose_y_m))" in features
    comparison = (sql_dir / "04_cross_version_comparison.sql").read_text(encoding="utf-8")
    assert "legacy.fact_task_execution" in comparison
    assert "UNION ALL" in comparison
    assert "分别聚合" in comparison
