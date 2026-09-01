import json

import pytest

from portfolio.robot_ops_analytics.pipelines.b2_v0_3.run_w7_b2_train_block import prior_counts


def test_first_slot_has_explicit_empty_history(tmp_path):
    assert prior_counts(1, tmp_path / "missing.jsonl") == (0, 0, 0)


def test_history_uses_only_contiguous_prior_valid_slots(tmp_path):
    path = tmp_path / "valid_slots.jsonl"
    rows = [{"plan_index": index,
             "terminal_status": "timeout" if index == 3 else
             ("failed" if index == 7 else "success")} for index in range(1, 12)]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    assert prior_counts(12, path) == (10, 2, 1)


def test_missing_prior_slot_fails_closed(tmp_path):
    path = tmp_path / "valid_slots.jsonl"
    path.write_text(json.dumps({"plan_index": 1, "terminal_status": "success"}) + "\n")
    with pytest.raises(ValueError, match="不连续"):
        prior_counts(3, path)
