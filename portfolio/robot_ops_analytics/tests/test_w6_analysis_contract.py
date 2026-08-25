from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


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
