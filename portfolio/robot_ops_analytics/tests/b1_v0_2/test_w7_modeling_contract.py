from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_w7_contract_blocks_existing_data_pooling_and_label_leakage():
    contract = yaml.safe_load(
        (ROOT / "config/w7_modeling_contract_v0.1.yaml").read_text(encoding="utf-8"))
    assert contract["status"] == "draft_pending_b2_design_and_user_approval"
    assert contract["decision"]["prediction_time"] == "before_task_acceptance"
    assert contract["existing_data_admission"]["pooled_training"] == "forbidden"
    assert contract["split_policy"]["row_random_split"] == "forbidden"
    assert contract["split_policy"]["test_used_once_after_threshold_freeze"] is True
    forbidden = set(contract["feature_policy"]["forbidden"])
    assert {"terminal_status", "final_error_code", "cycle_time_sec"} <= forbidden


def test_w7_b2_candidate_is_not_execution_authorization():
    contract = yaml.safe_load(
        (ROOT / "config/w7_modeling_contract_v0.1.yaml").read_text(encoding="utf-8"))
    design = contract["b2_design_candidate"]
    assert design["status"] == "not_preregistered_not_authorized_for_execution"
    assert design["qualification_requires_user_gui_confirmation"] is True
    assert design["outcome_based_sample_extension"] == "forbidden"
