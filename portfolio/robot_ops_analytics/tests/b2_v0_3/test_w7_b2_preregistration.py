import copy
from pathlib import Path

import yaml

from portfolio.robot_ops_analytics.pipelines.b2_v0_3.audit_w7_b2_preregistration import audit


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/w7_b2_preregistration_v0.3.yaml"


def load_config():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_frozen_preregistration_passes_after_first_block_scope_is_exhausted():
    result = audit(load_config())
    assert result["passed"] is True
    assert result["formal_collection_authorized"] is False
    assert result["split_counts"] == {"train": 180, "validation": 90, "sealed_test": 90}
    assert all(result["gates"].values())


def test_hash_change_fails_closed():
    config = copy.deepcopy(load_config())
    config["frozen_plan"]["sha256"] = "0" * 64
    result = audit(config)
    assert result["passed"] is False
    assert result["gates"]["plan_hash_matches"] is False


def test_retry_and_feasibility_rules_are_frozen():
    config = load_config()
    retry = config["validity_and_retry"]
    feasibility = config["stopping_rules"]["feasibility_after_fixed_collection"]
    assert retry["selective_retry_by_outcome"] == "forbidden"
    assert retry["replacement_rule"] == "only_first_subsequent_valid_attempt_fills_slot"
    assert feasibility == {"development_positive_minimum": 30,
                           "sealed_test_positive_minimum": 10,
                           "if_not_met": "declare_modeling_infeasible_for_roa-risk-b2-v0.3"}
