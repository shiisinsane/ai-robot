"""W1 指标字典的确定性结构测试。"""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DICTIONARY = ROOT / "schemas" / "common" / "metric_dictionary.yaml"


def load_dictionary():
    return yaml.safe_load(DICTIONARY.read_text(encoding="utf-8"))


def test_contract_identity_and_scope():
    contract = load_dictionary()
    assert contract["metric_contract_version"] == "roa-metrics-v1.0"
    assert contract["status"] == "frozen"
    assert contract["scope"] == "indoor_inspection_robot_simulation"
    assert contract["time_basis"] == "ros_sim_time"


def test_metric_ids_are_unique_and_required_categories_exist():
    metrics = load_dictionary()["metrics"]
    identifiers = [metric["id"] for metric in metrics]
    assert len(identifiers) == len(set(identifiers))
    categories = {metric["category"] for metric in metrics}
    assert {"north_star", "core", "diagnostic", "guardrail"} <= categories


def test_every_metric_has_a_complete_definition():
    required = {
        "id", "name", "category", "business_meaning", "entity",
        "aggregation", "unit", "time_window", "filters", "dimensions",
        "exclusions", "null_policy", "interpretation", "limitations",
        "source_fields",
    }
    for metric in load_dictionary()["metrics"]:
        assert required <= set(metric), metric["id"]
        for field in required - {"exclusions"}:
            assert metric[field] not in (None, "", []), (metric["id"], field)


def test_rate_metrics_define_numerator_and_denominator():
    for metric in load_dictionary()["metrics"]:
        if metric["aggregation"] == "ratio" or metric["aggregation"] == "ratio_by_failure_stage":
            assert metric["numerator"], metric["id"]
            assert metric["denominator"], metric["id"]


def test_sla_is_not_invented_before_baseline():
    parameter = load_dictionary()["parameters"]["task_sla_sec"]
    assert parameter["value"] is None
    assert parameter["status"] == "pending_baseline_freeze"


def test_natural_and_fault_injection_cohorts_are_separate():
    contract = load_dictionary()
    separation = contract["global_filters"]["cohort_separation"]
    assert set(separation["run_origin_values"]) == {"natural", "fault_injection"}
    assert any("separately" in rule for rule in contract["reporting_rules"])


def test_efficiency_metrics_are_paired_with_safety_reporting():
    rules = load_dictionary()["reporting_rules"]
    assert any("safety guardrails" in rule for rule in rules)


def test_status_taxonomy_keeps_rejection_and_cancellation_distinct():
    taxonomy = load_dictionary()["status_taxonomy"]
    assert "canceled" in taxonomy["accepted_values"]
    assert taxonomy["rejected_value"] == "rejected"
    assert "not silently merged" in taxonomy["rule"]
