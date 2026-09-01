from portfolio.robot_ops_analytics.pipelines.b2_v0_3 import run_w7_b2_train_chunk


def test_next_slot_counts_only_nonempty_state_rows(tmp_path, monkeypatch):
    state = tmp_path / "valid_slots.jsonl"
    state.write_text("{}\n\n{}\n", encoding="utf-8")
    monkeypatch.setattr(run_w7_b2_train_chunk, "STATE", state)
    assert run_w7_b2_train_chunk.next_slot() == 3


def test_next_attempt_never_overwrites_existing_attempt(tmp_path, monkeypatch):
    (tmp_path / "b2-train-b01-slot-008-attempt-001").mkdir()
    (tmp_path / "b2-train-b01-slot-008-attempt-003").mkdir()
    monkeypatch.setattr(run_w7_b2_train_chunk, "OUTPUT", tmp_path)
    assert run_w7_b2_train_chunk.next_attempt(8) == 4
