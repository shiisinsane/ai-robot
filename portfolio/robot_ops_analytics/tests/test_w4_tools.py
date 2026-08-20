import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).parents[1]


def load_generator():
    path = ROOT / "orchestrator/generate_w4_matrix.py"
    spec = importlib.util.spec_from_file_location("w4_generator", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_matrix_has_expected_counts_and_unique_ids():
    config = yaml.safe_load((ROOT / "config/w4_matrix_v1.yaml").read_text(encoding="utf-8"))
    cases = load_generator().generate(config)
    assert len(cases) == 312
    assert len({x["task_id"] for x in cases}) == 312
    assert sum(x["run_origin"] == "natural" for x in cases) == 162
    assert sum(x["run_origin"] == "fault_injection" for x in cases) == 150
    assert sum(x["environment_ready"] for x in cases) == 9
    assert all(x["requires_reset_before_task"] for x in cases)
    assert all("start_x" in x and "start_y" in x for x in cases)


def test_fault_types_and_environment_profiles_are_explicit():
    config = yaml.safe_load((ROOT / "config/w4_matrix_v1.yaml").read_text(encoding="utf-8"))
    cases = load_generator().generate(config)
    faults = {x["fault_injection_type"] for x in cases if x["run_origin"] == "fault_injection"}
    assert faults == {"localization", "planning", "control", "perception", "safety"}
    assert all(x["environment_profile"] for x in cases)


def test_generator_cli_and_batch_preview_do_not_require_ros(tmp_path):
    plan = tmp_path / "plan.jsonl"
    generated = subprocess.run([
        sys.executable, "-m", "portfolio.robot_ops_analytics.orchestrator.generate_w4_matrix",
        "--output", str(plan)], cwd=ROOT.parents[1], text=True, capture_output=True)
    assert generated.returncode == 0
    assert len(plan.read_text(encoding="utf-8").splitlines()) == 312
    preview = subprocess.run([
        sys.executable, "-m", "portfolio.robot_ops_analytics.orchestrator.run_w4_batch",
        "--plan", str(plan), "--environment-profile", "natural__none__none__baseline",
        "--experiment-id", "test", "--output-dir", str(tmp_path / "out"), "--limit", "3"],
        cwd=ROOT.parents[1], text=True, capture_output=True)
    assert preview.returncode == 0
    assert "当前为预览" in preview.stdout
    assert not (tmp_path / "out").exists()


def test_unready_environment_is_rejected_even_in_preview(tmp_path):
    config = yaml.safe_load((ROOT / "config/w4_matrix_v1.yaml").read_text(encoding="utf-8"))
    plan = tmp_path / "plan.jsonl"
    plan.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n"
                            for x in load_generator().generate(config)), encoding="utf-8")
    result = subprocess.run([
        sys.executable, "-m", "portfolio.robot_ops_analytics.orchestrator.run_w4_batch",
        "--plan", str(plan), "--environment-profile", "natural__low__none__baseline",
        "--experiment-id", "test", "--output-dir", str(tmp_path / "out")],
        cwd=ROOT.parents[1], text=True, capture_output=True)
    assert result.returncode != 0
    assert "环境配置尚未冻结" in result.stderr


def test_environment_launcher_has_process_group_cleanup_contract():
    script = ROOT / "scripts/run_w4_environment.sh"
    checked = subprocess.run(["bash", "-n", str(script)], text=True, capture_output=True)
    assert checked.returncode == 0
    text = script.read_text(encoding="utf-8")
    for required in ("setsid", "PGIDS", 'kill -INT -- "-$pgid"',
                     "residue_check.txt", "group_alive", "trap cleanup",
                     "Gazebo分区只能使用", 'kill -KILL -- "-$pgid"',
                     "navigation Ready", "任务Action Ready"):
        assert required in text
    for forbidden in ("pkill", "killall", "pkill python3", "pkill ros2"):
        assert forbidden not in text


def test_batch_can_select_exact_task(tmp_path):
    config = yaml.safe_load((ROOT / "config/w4_matrix_v1.yaml").read_text(encoding="utf-8"))
    plan = tmp_path / "plan.jsonl"
    plan.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n"
                            for x in load_generator().generate(config)), encoding="utf-8")
    result = subprocess.run([
        sys.executable, "-m", "portfolio.robot_ops_analytics.orchestrator.run_w4_batch",
        "--plan", str(plan), "--environment-profile", "natural__none__none__baseline",
        "--experiment-id", "test", "--task-id", "w4-0002",
        "--output-dir", str(tmp_path / "out")], cwd=ROOT.parents[1],
        text=True, capture_output=True)
    assert result.returncode == 0
    assert "w4-0002" in result.stdout
    assert "w4-0001" not in result.stdout


def test_contiguous_route_validation():
    spec = importlib.util.spec_from_file_location(
        "w4_batch", ROOT / "orchestrator/run_w4_batch.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    outbound = {"target_x": 0.8, "target_y": 0.0, "target_yaw": 0.0}
    return_home = {"start_x": 0.8, "start_y": 0.0, "start_yaw": 0.0}
    wrong_start = {"start_x": 0.0, "start_y": 0.0, "start_yaw": 0.0}
    assert module.contiguous([outbound, return_home])
    assert not module.contiguous([outbound, wrong_start])


def test_safe_group_launcher_has_cleanup_and_safety_gates():
    script = ROOT / "scripts/run_w4_safe_group.sh"
    checked = subprocess.run(["bash", "-n", str(script)], text=True, capture_output=True)
    assert checked.returncode == 0
    text = script.read_text(encoding="utf-8")
    for required in ("run_w4_environment.sh", "ENV_PID", "trap cleanup",
                     "clear_faults", "stop_active", "--auto-contiguous",
                     "residue_check.txt", "preflight_process_check.txt",
                     "发现同类ROS/Gazebo进程", 'kill -TERM "$ENV_PID"',
                     '"$child_state" == Z*'):
        assert required in text
    for forbidden in ("pkill", "killall"):
        assert forbidden not in text
