from pathlib import Path
import importlib.util

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]

ANALYSIS_SPEC = importlib.util.spec_from_file_location(
    "analyze_w6_a1_validation", ROOT / "pipelines/legacy_v0_1/analyze_w6_a1_validation.py")
ANALYSIS_MODULE = importlib.util.module_from_spec(ANALYSIS_SPEC)
assert ANALYSIS_SPEC.loader is not None
ANALYSIS_SPEC.loader.exec_module(ANALYSIS_MODULE)


def test_w6_a1_statistical_helpers_cover_extreme_separation():
    interval = ANALYSIS_MODULE.wilson(15, 15)
    assert interval[0] == pytest.approx(0.796116, abs=1e-6)
    assert interval[1] == pytest.approx(1.0)
    assert ANALYSIS_MODULE.fisher_two_sided(15, 0, 0, 15) == pytest.approx(
        1.289345e-08, rel=1e-5)


def test_w6_contract_is_frozen_before_sql_and_has_business_outputs():
    contract = yaml.safe_load(
        (ROOT / "config/w6_analysis_contract.yaml").read_text(encoding="utf-8"))
    assert contract["status"] == "frozen_before_query"
    assert contract["dataset_version"] == "roa-data-v0.1"
    assert contract["cohort"] == {
        "run_origin": "natural", "data_quality_valid": True, "task_count": 81}
    assert {"task_count", "failure_rate", "failure_contribution"} <= set(
        contract["required_group_outputs"])
    assert contract["causal_language_rule"] == (
        "sql_observations_are_not_causal_without_controlled_validation")


def test_w6_sql_catalog_covers_required_analysis_families():
    catalog = (ROOT / "sql/README.md").read_text(encoding="utf-8")
    expected = {
        "00_data_contract_checks.sql", "01_overall_kpis.sql",
        "02_cycle_time_distribution.sql", "03_scenario_failure_breakdown.sql",
        "04_failure_pareto.sql", "05_stage_duration.sql",
        "06_preterminal_telemetry.sql", "07_safety_guardrails.sql",
        "08_failure_streaks.sql", "09_anomaly_candidates.sql",
    }
    assert all(name in catalog for name in expected)
    assert "COUNT(DISTINCT task_id)" in catalog
    assert "控制变量实验完成前不写“导致”" in catalog


def test_w6_data_contract_sql_has_frozen_cohort_and_fail_closed_gate():
    sql = (ROOT / "sql/legacy_v0_1/00_data_contract_checks.sql").read_text(encoding="utf-8")
    for token in (
        "dataset_version = 'roa-data-v0.1'", "run_origin = 'natural'",
        "data_quality_valid = TRUE", "task_count = 81", "event_count = 7391",
        "telemetry_bucket_count = 1368", "orphan_event_rows = 0",
        "orphan_telemetry_rows = 0", "quality_gate_passed",
    ):
        assert token in sql


@pytest.mark.skipif(not importlib.util.find_spec("duckdb"), reason="需要DuckDB分析环境")
def test_w6_data_contract_sql_executes_and_passes_frozen_shape():
    import duckdb

    connection = duckdb.connect(":memory:")
    try:
        connection.execute("""
            CREATE TABLE fact_task_execution AS
            SELECT
                'task-' || i AS task_id, 'roa-data-v0.1' AS dataset_version,
                'batch' AS source_batch_id, 'experiment' AS experiment_id,
                'request-' || i AS request_id, 'route' AS route_id,
                'none' AS obstacle_profile, 'none' AS localization_perturbation_level,
                'baseline' AS parameter_version, 'natural' AS run_origin,
                TRUE AS data_quality_valid, 'success' AS terminal_status, TRUE AS success,
                0.0 AS accepted_at_sim, 1.0 AS terminal_at_sim, 1.0 AS cycle_time_sec,
                CAST(16 + (i <= 72) AS BIGINT) AS telemetry_bucket_count,
                CAST(16 + (i <= 72) AS BIGINT) AS valid_telemetry_bucket_count
            FROM generate_series(1, 81) AS ids(i);
            CREATE TABLE fact_task_event AS
            SELECT
                'task-' || (((i - 1) % 81) + 1) AS task_id,
                CAST(FLOOR((i - 1) / 81) + 1 AS BIGINT) AS event_sequence,
                CAST(i AS DOUBLE) AS event_time_sim, 'feedback' AS event_type
            FROM generate_series(1, 7391) AS rows(i);
            CREATE TABLE fact_task_telemetry_1s AS
            SELECT
                'task-' || (((i - 1) % 81) + 1) AS task_id,
                CAST(FLOOR((i - 1) / 81) AS DOUBLE) AS bucket_start_sim,
                CAST(FLOOR((i - 1) / 81) + 1 AS DOUBLE) AS bucket_end_sim,
                TRUE AS required_topics_present, TRUE AS timestamp_valid,
                0 AS stale_sensor_mask
            FROM generate_series(1, 1368) AS rows(i);
        """)
        sql = (ROOT / "sql/legacy_v0_1/00_data_contract_checks.sql").read_text(encoding="utf-8")
        row = connection.execute(sql).fetchone()
        columns = [item[0] for item in connection.description]
        result = dict(zip(columns, row))
        assert result["quality_gate_passed"] is True
        assert result["task_count"] == 81
        assert result["event_count"] == 7391
        assert result["telemetry_bucket_count"] == 1368
    finally:
        connection.close()


def test_w6_overall_kpi_sql_uses_task_grain_and_required_statistics():
    sql = (ROOT / "sql/legacy_v0_1/01_overall_kpis.sql").read_text(encoding="utf-8")
    for token in (
        "dataset_version = 'roa-data-v0.1'", "run_origin = 'natural'",
        "data_quality_valid = TRUE", "GROUPING SETS", "task_count", "success_count",
        "failure_count", "completion_rate", "failure_rate",
        "quantile_cont(cycle_time_sec, 0.50)",
        "quantile_cont(cycle_time_sec, 0.90)",
        "quantile_cont(cycle_time_sec, 0.95)",
    ):
        assert token in sql
    assert "fact_task_event" not in sql
    assert "fact_task_telemetry_1s" not in sql


def test_w6_cycle_distribution_sql_has_required_grains_and_small_sample_flag():
    sql = (ROOT / "sql/legacy_v0_1/02_cycle_time_distribution.sql").read_text(encoding="utf-8")
    for token in (
        "'overall' AS dimension_type", "'terminal_status'", "'route_id'",
        "task_count", "success_count", "failure_count",
        "quantile_cont(cycle_time_sec, 0.50)",
        "quantile_cont(cycle_time_sec, 0.90)",
        "quantile_cont(cycle_time_sec, 0.95)",
        "task_count < 10", "small_sample", "控制变量实验完成前不得解释为路线导致",
    ):
        assert token in sql
    assert "fact_task_event" not in sql
    assert "fact_task_telemetry_1s" not in sql


def test_w6_scenario_breakdown_separates_risk_from_failure_contribution():
    sql = (ROOT / "sql/legacy_v0_1/03_scenario_failure_breakdown.sql").read_text(encoding="utf-8")
    for token in (
        "'route_id' AS dimension_type", "'obstacle_profile'",
        "'localization_perturbation_level'", "'scenario_combination'",
        "task_count", "success_count", "failure_count", "failure_rate",
        "failure_contribution", "total_failure_count", "task_count < 5",
        "结果只表示相关性，不证明场景因素导致失败",
    ):
        assert token in sql
    assert "fact_task_event" not in sql
    assert "fact_task_telemetry_1s" not in sql


def test_w6_failure_pareto_ranks_error_codes_and_scenarios_separately():
    sql = (ROOT / "sql/legacy_v0_1/04_failure_pareto.sql").read_text(encoding="utf-8")
    for token in (
        "'error_code' AS pareto_type", "'scenario_combination' AS pareto_type",
        "failure_count", "failure_rate", "failure_contribution",
        "cumulative_failure_contribution", "PARTITION BY i.pareto_type",
        "ROW_NUMBER()", "distinct_message_count", "exposure_count < 5",
        "不构成障碍、路线或定位扰动导致失败的因果证据",
    ):
        assert token in sql
    assert "fact_task_event" not in sql
    assert "fact_task_telemetry_1s" not in sql


def test_w6_stage_duration_preaggregates_events_to_task_stage():
    sql = (ROOT / "sql/legacy_v0_1/05_stage_duration.sql").read_text(encoding="utf-8")
    for token in (
        "LEAD(e.event_time_sim)", "PARTITION BY e.task_id",
        "ORDER BY e.event_sequence", "GROUP BY task_id, event_type",
        "approx_dwell_sec", "negative_interval_count", "event_count",
        "first_event_sequence", "stage_error_code",
        "不等同于Nav2内部规划器或控制器的真实执行时长",
    ):
        assert token in sql
    assert "COUNT(DISTINCT" not in sql


def test_w6_preterminal_telemetry_uses_fixed_windows_and_task_grain():
    sql = (ROOT / "sql/legacy_v0_1/06_preterminal_telemetry.sql").read_text(encoding="utf-8")
    for token in (
        "accepted_at_sim + 3.0", "terminal_at_sim - 3.0",
        "GROUP BY task_id", "early_bucket_count", "preterminal_bucket_count",
        "valid_telemetry_coverage_rate", "minimum_scan_range_m",
        "safety_stop_bucket_count", "stale_sensor_bucket_count",
        "overlapping_window_bucket_count", "cycle_time_sec < 6.0 AS windows_may_overlap",
        "不证明遥测差异导致导航失败",
    ):
        assert token in sql
    assert "LEFT JOIN task_telemetry" in sql


def test_w6_safety_guardrails_preaggregate_and_do_not_overclaim_safety():
    sql = (ROOT / "sql/legacy_v0_1/07_safety_guardrails.sql").read_text(encoding="utf-8")
    for token in (
        "GROUP BY m.task_id", "'overall' AS dimension_type", "'terminal_status'",
        "'obstacle_profile'", "'route_obstacle'", "safety_stop_task_rate",
        "stale_sensor_task_rate", "valid_telemetry_coverage_rate",
        "minimum_obstacle_distance_m", "p05_minimum_obstacle_distance_m",
        "observed_telemetry_bucket_count", "declared_telemetry_bucket_count",
        "不以“未停车”替代安全通过",
    ):
        assert token in sql


def test_w6_failure_streaks_use_deterministic_wall_order_and_contiguous_runs():
    sql = (ROOT / "sql/legacy_v0_1/08_failure_streaks.sql").read_text(encoding="utf-8")
    for token in (
        "CAST(started_at_wall AS TIMESTAMP)",
        "ORDER BY started_at_wall, task_id", "LAG(is_failure, 1, FALSE)",
        "starts_failure_streak", "failure_streak_id", "consecutive_failure_count",
        "COUNT(DISTINCT source_batch_id)", "multi_failure_streak",
        "isolated_failure", "采集顺序并非随机化顺序",
    ):
        assert token in sql


def test_w6_anomaly_candidates_enforce_preregistration_gate():
    sql = (ROOT / "sql/legacy_v0_1/09_anomaly_candidates.sql").read_text(encoding="utf-8")
    for token in (
        "A1_return_home_medium_navigation_failure",
        "A2_medium_obstacle_failure_concentration",
        "A3_early_low_speed_association", "failure_rate", "failure_contribution",
        "reproducible_sql", "not_single_task", "data_quality_cleared",
        "single_factor_experiment_possible", "metric_pre_registered",
        "eligible_for_preregistration", "supporting_parent_candidate",
        "supporting_mechanism_only", "未完成预注册前不得据此启动补采",
    ):
        assert token in sql


def test_w6_a1_validation_preregistration_is_balanced_and_frozen():
    config = yaml.safe_load(
        (ROOT / "config/w6_a1_validation_v0.1.yaml").read_text(encoding="utf-8"))
    assert config["status"] == "frozen_before_execution"
    assert config["candidate_id"] == "A1_return_home_medium_navigation_failure"
    assert config["fixed_conditions"]["route_id"] == "return_home"
    assert config["fixed_conditions"]["localization_perturbation_level"] == "none"
    assert config["groups"]["control"]["required_valid_tasks"] == 15
    assert config["groups"]["treatment"]["required_valid_tasks"] == 15
    sequence = config["assignment"]["sequence"]
    assert [item["run_order"] for item in sequence] == list(range(1, 31))
    assert sum(item["obstacle_profile"] == "low" for item in sequence) == 15
    assert sum(item["obstacle_profile"] == "medium" for item in sequence) == 15
    for block in range(1, 16):
        assert {item["obstacle_profile"] for item in sequence if item["block"] == block} == {
            "low", "medium"}
    assert config["stopping_rules"]["statistical_early_stop"] == "forbidden"
    assert config["stopping_rules"]["outcome_based_sample_extension"] == "forbidden"
    assert config["execution_boundary"][
        "requires_explicit_user_authorization_after_preregistration"] is True
