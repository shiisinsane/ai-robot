from portfolio.robot_ops_analytics.pipelines.b1_v0_2.audit_w7_b2_static_design import audit


def test_w7_b2_static_design_has_five_routes_and_balanced_whole_blocks():
    import yaml
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / "config/w7_b2_design_draft_v0.1.yaml").read_text())
    result = audit(config)
    assert result["static_geometry_passed"] is True
    assert result["matrix_passed"] is True
    assert result["scenario_cells"] == 45
    assert result["candidate_total_tasks"] == 360
    assert len(result["routes"]) == 5


def test_runner_publishes_snapshot_before_requested_and_action_dispatch():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    text = (root / "pipelines/common/run_experiment.py").read_text(encoding="utf-8")
    snapshot = text.index('self._publish_context(True, "preacceptance_snapshot"')
    requested = text.index('self._publish_context(True, "requested"')
    dispatch = text.index("self.client.send_goal_async(goal")
    assert snapshot < requested < dispatch
    assert "--preacceptance-snapshot-required" in text
