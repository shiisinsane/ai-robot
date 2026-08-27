import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).parents[2]


def load_generator():
    path = ROOT / "pipelines/legacy_v0_1/generate_w4_matrix.py"
    spec = importlib.util.spec_from_file_location("w4_generator", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def load_environment_configurator():
    path = ROOT / "pipelines/common/configure_w4_environment.py"
    spec = importlib.util.spec_from_file_location("w4_environment", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def load_sample_validator():
    path = ROOT / "pipelines/common/validate_w4_sample.py"
    spec = importlib.util.spec_from_file_location("w4_sample_validator", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_matrix_has_expected_counts_and_unique_ids():
    config = yaml.safe_load((ROOT / "config/w4_matrix_v1.yaml").read_text(encoding="utf-8"))
    cases = load_generator().generate(config)
    assert len(cases) == 312
    assert len({x["task_id"] for x in cases}) == 312
    assert sum(x["run_origin"] == "natural" for x in cases) == 162
    assert sum(x["run_origin"] == "fault_injection" for x in cases) == 150
    assert sum(x["environment_ready"] for x in cases) == 81
    qualification = [x for x in cases if x["qualification_ready"]]
    assert qualification == []
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
        sys.executable, "-m", "portfolio.robot_ops_analytics.pipelines.legacy_v0_1.generate_w4_matrix",
        "--output", str(plan)], cwd=ROOT.parents[1], text=True, capture_output=True)
    assert generated.returncode == 0
    assert len(plan.read_text(encoding="utf-8").splitlines()) == 312
    preview = subprocess.run([
        sys.executable, "-m", "portfolio.robot_ops_analytics.pipelines.common.run_w4_batch",
        "--plan", str(plan), "--environment-profile", "natural__none__none__baseline",
        "--experiment-id", "test", "--output-dir", str(tmp_path / "out"), "--limit", "3"],
        cwd=ROOT.parents[1], text=True, capture_output=True)
    assert preview.returncode == 0
    assert "当前为预览" in preview.stdout
    assert not (tmp_path / "out").exists()


def test_unready_environment_is_rejected_even_in_preview(tmp_path):
    config = yaml.safe_load((ROOT / "config/w4_matrix_v1.yaml").read_text(encoding="utf-8"))
    next(item for item in config["initial_perturbations"]
         if item["id"] == "medium")["environment_ready"] = False
    plan = tmp_path / "plan.jsonl"
    plan.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n"
                            for x in load_generator().generate(config)), encoding="utf-8")
    result = subprocess.run([
        sys.executable, "-m", "portfolio.robot_ops_analytics.pipelines.common.run_w4_batch",
        "--plan", str(plan), "--environment-profile", "natural__none__medium__baseline",
        "--experiment-id", "test", "--output-dir", str(tmp_path / "out")],
        cwd=ROOT.parents[1], text=True, capture_output=True)
    assert result.returncode != 0
    assert "环境配置尚未冻结" in result.stderr


def test_medium_qualification_preview_requires_exact_single_task(tmp_path):
    config = yaml.safe_load((ROOT / "config/w4_matrix_v1.yaml").read_text(encoding="utf-8"))
    next(item for item in config["obstacle_profiles"]
         if item["id"] == "medium")["environment_ready"] = False
    plan = tmp_path / "plan.jsonl"
    cases = load_generator().generate(config)
    plan.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in cases),
                    encoding="utf-8")
    medium = next(x for x in cases if x["environment_profile"] ==
                  "natural__medium__none__baseline")
    result = subprocess.run([
        sys.executable, "-m", "portfolio.robot_ops_analytics.pipelines.common.run_w4_batch",
        "--plan", str(plan), "--environment-profile", medium["environment_profile"],
        "--experiment-id", "qualification", "--task-id", medium["task_id"],
        "--qualification-pilot", "--output-dir", str(tmp_path / "out")],
        cwd=ROOT.parents[1], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "资格Pilot模式" in result.stdout
    assert "任务数：1" in result.stdout


def test_environment_launcher_has_process_group_cleanup_contract():
    script = ROOT / "scripts/common/run_w4_environment.sh"
    checked = subprocess.run(["bash", "-n", str(script)], text=True, capture_output=True)
    assert checked.returncode == 0
    text = script.read_text(encoding="utf-8")
    for required in ("setsid", "PGIDS", 'kill -INT -- "-$pgid"',
                     "residue_check.txt", "group_alive", "trap cleanup",
                     "Gazebo分区只能使用", 'kill -KILL -- "-$pgid"',
                     "navigation Ready", "任务Action Ready", '"gui:=$GUI"',
                     "/robot/pose --once", "nav2_lifecycle_ready",
                     "/robot/planner_server", "/robot/controller_server",
                     "/robot/bt_navigator", '"$state" != active*'):
        assert required in text
    for forbidden in ("pkill", "killall", "pkill python3", "pkill ros2"):
        assert forbidden not in text


def test_batch_can_select_exact_task(tmp_path):
    config = yaml.safe_load((ROOT / "config/w4_matrix_v1.yaml").read_text(encoding="utf-8"))
    plan = tmp_path / "plan.jsonl"
    plan.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n"
                            for x in load_generator().generate(config)), encoding="utf-8")
    result = subprocess.run([
        sys.executable, "-m", "portfolio.robot_ops_analytics.pipelines.common.run_w4_batch",
        "--plan", str(plan), "--environment-profile", "natural__none__none__baseline",
        "--experiment-id", "test", "--task-id", "w4-0002",
        "--output-dir", str(tmp_path / "out")], cwd=ROOT.parents[1],
        text=True, capture_output=True)
    assert result.returncode == 0
    assert "w4-0002" in result.stdout
    assert "w4-0001" not in result.stdout


def test_contiguous_route_validation():
    spec = importlib.util.spec_from_file_location(
        "w4_batch", ROOT / "pipelines/common/run_w4_batch.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    outbound = {"target_x": 0.8, "target_y": 0.0, "target_yaw": 0.0}
    return_home = {"start_x": 0.8, "start_y": 0.0, "start_yaw": 0.0}
    wrong_start = {"start_x": 0.0, "start_y": 0.0, "start_yaw": 0.0}
    assert module.contiguous([outbound, return_home])
    assert not module.contiguous([outbound, wrong_start])


def test_safe_group_launcher_has_cleanup_and_safety_gates():
    script = ROOT / "scripts/common/run_w4_safe_group.sh"
    checked = subprocess.run(["bash", "-n", str(script)], text=True, capture_output=True)
    assert checked.returncode == 0
    text = script.read_text(encoding="utf-8")
    for required in ("run_w4_environment.sh", "ENV_PID", "trap cleanup",
                     "clear_faults", "stop_active", "--auto-contiguous",
                     "residue_check.txt", "preflight_process_check.txt",
                     "发现同类ROS/Gazebo进程", 'kill -TERM "$ENV_PID"',
                     '"$child_state" == Z*', "configure_w4_environment",
                     "obstacle_environment.json", "任务前最终Ready门禁",
                     'set +u', 'source "$ROOT_DIR/install/setup.bash"', 'set -u',
                     "nav2_lifecycle_ready", "/robot/planner_server",
                     "/robot/controller_server", "/robot/bt_navigator",
                     '"$state" != active*',
                     "clear_faults调用超时或失败，继续下一次尝试"):
        assert required in text
    for forbidden in ("pkill", "killall"):
        assert forbidden not in text
    assert text.index("任务前最终Ready门禁：通过") < text.index(
        "最终清除安全故障并确认stop_active=false")
    assert text.index("最终清除安全故障并确认stop_active=false") < text.index(
        "开始顺序执行")


def test_w6_a1_plan_and_campaign_preview_follow_frozen_sequence(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "w6_a1_plan", ROOT / "pipelines/legacy_v0_1/generate_w6_a1_plan.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    config = yaml.safe_load(
        (ROOT / "config/w6_a1_validation_v0.1.yaml").read_text(encoding="utf-8"))
    cases = module.generate(config)
    assert len(cases) == 30
    assert [case["task_id"] for case in cases] == [f"a1-{i:04d}" for i in range(1, 31)]
    assert sum(case["obstacle_profile"] == "low" for case in cases) == 15
    assert sum(case["obstacle_profile"] == "medium" for case in cases) == 15
    assert all(case["route_id"] == "return_home" for case in cases)

    script = ROOT / "scripts/legacy_v0_1/run_w6_a1_validation_campaign.sh"
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    result = subprocess.run([
        "bash", str(script), "--output-root", str(tmp_path),
        "--start-domain", "180", "--preview"], cwd=ROOT.parents[1],
        text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    rows = (tmp_path / "a1-campaign-001-results.tsv").read_text(
        encoding="utf-8").splitlines()
    assert len(rows) == 31
    assert all(row.endswith("preview") for row in rows[1:])
    assert "a1-0001" in rows[1] and "\tlow\t" in rows[1]
    assert "a1-0030" in rows[-1] and "\tlow\t" in rows[-1]


def test_low_perturbation_campaign_preview_covers_26_remaining_tasks(tmp_path):
    script = ROOT / "scripts/legacy_v0_1/run_w4_low_perturbation_campaign.sh"
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    result = subprocess.run([
        "bash", str(script), "--output-root", str(tmp_path),
        "--start-domain", "200", "--preview"], cwd=ROOT.parents[1],
        text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    rows = (tmp_path / "low-perturbation-campaign-001-results.tsv").read_text(
        encoding="utf-8").splitlines()
    assert len(rows) == 27
    assert all(row.endswith("preview") for row in rows[1:])
    assert "w4-0007" not in "\n".join(rows)
    assert "w4-0008" in rows[1] and "w4-0153" in rows[-1]


def test_medium_perturbation_campaign_preview_covers_26_remaining_tasks(tmp_path):
    script = ROOT / "scripts/legacy_v0_1/run_w4_medium_perturbation_campaign.sh"
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    result = subprocess.run([
        "bash", str(script), "--output-root", str(tmp_path),
        "--start-domain", "200", "--preview"], cwd=ROOT.parents[1],
        text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    rows = (tmp_path / "medium-perturbation-campaign-001-results.tsv").read_text(
        encoding="utf-8").splitlines()
    assert len(rows) == 27
    assert all(row.endswith("preview") for row in rows[1:])
    assert "w4-0013" not in "\n".join(rows)
    assert "w4-0014" in rows[1] and "w4-0159" in rows[-1]
    assert not list(tmp_path.glob("initial-medium-campaign-*"))


def test_sample_validator_accepts_complete_failure(tmp_path):
    batch = tmp_path / "batch"
    for relative in ("batch_runner", "structured", "process",
                     "rosbag/w4_pilot_bag"):
        (batch / relative).mkdir(parents=True, exist_ok=True)
    (batch / "batch_runner/run_results.jsonl").write_text(
        json.dumps({"task_id": "w4-test", "return_code": 1}) + "\n")
    records = [
        {"task_id": "w4-test", "record_type": "task_telemetry_1s",
         "required_topics_present": True, "timestamp_valid": True,
         "safety_stop_active": False},
        {"task_id": "w4-test", "record_type": "task_context",
         "event": "terminal", "success": False},
    ]
    (batch / "structured/records.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in records))
    (batch / "process/residue_check.txt").write_text(
        "本批进程组残留检查：通过\n")
    (batch / "rosbag/w4_pilot_bag/metadata.yaml").write_text(
        "rosbag2_bagfile_information:\n  message_count: 5\n")
    (batch / "rosbag/w4_pilot_bag/sample.db3").write_bytes(b"evidence")
    assert load_sample_validator().validate(batch, "w4-test") == "valid_failure"


def test_low_obstacle_campaign_is_serial_and_covers_remaining_tasks():
    script = ROOT / "scripts/legacy_v0_1/run_w4_low_obstacle_campaign.sh"
    checked = subprocess.run(["bash", "-n", str(script)], text=True, capture_output=True)
    assert checked.returncode == 0
    text = script.read_text(encoding="utf-8")
    for task_id in ("w4-0020", "w4-0021", "w4-0073", "w4-0074", "w4-0075",
                    "w4-0127", "w4-0128", "w4-0129"):
        assert text.count(task_id) == 1
    assert "run_w4_safe_group.sh" in text
    assert "Campaign停止，不启动下一套环境" in text
    assert " &\n" not in text


def test_low_obstacle_campaign_preview_expands_five_real_groups(tmp_path):
    script = ROOT / "scripts/legacy_v0_1/run_w4_low_obstacle_campaign.sh"
    result = subprocess.run([
        "bash", str(script), "--output-root", str(tmp_path),
        "--start-domain", "213", "--preview"], cwd=ROOT.parents[1],
        text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[1/5] 执行low-pilot-002：w4-0020" in result.stdout
    assert "[5/5] 执行low-pilot-006：w4-0075 w4-0129" in result.stdout
    rows = (tmp_path / "low-obstacle-campaign-002-results.tsv").read_text(
        encoding="utf-8").splitlines()
    assert len(rows) == 6
    assert all(row.endswith("preview") for row in rows[1:])


def test_low_obstacle_campaign_can_resume_with_retry_directory(tmp_path):
    failed = tmp_path / "low-pilot-003" / "batch_runner"
    failed.mkdir(parents=True)
    (failed / "run_results.jsonl").write_text("failed\n", encoding="utf-8")
    script = ROOT / "scripts/legacy_v0_1/run_w4_low_obstacle_campaign.sh"
    result = subprocess.run([
        "bash", str(script), "--output-root", str(tmp_path),
        "--start-domain", "214", "--start-index", "2",
        "--campaign-id", "retry-test", "--preview"], cwd=ROOT.parents[1],
        text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "low-pilot-002" not in result.stdout
    assert "使用新目录：low-pilot-003-retry-001" in result.stdout
    assert "[2/5] 执行low-pilot-003-retry-001：w4-0021" in result.stdout


def test_low_obstacle_profile_uses_frozen_pose_and_set_pose_service():
    module = load_environment_configurator()
    profile = module.load_profile(ROOT / "config/w4_matrix_v1.yaml", "low")
    calls = []

    class Result:
        returncode = 0
        stdout = "data: true"
        stderr = ""

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    command, output, pose = module.set_pose(profile, runner=fake_runner)
    assert pose == (0.4, 0.9, 0.45)
    assert "/world/m5_slam/set_pose" in command
    assert 'name: "temporary_obstacle"' in command[-1]
    assert "data: true" in output
    assert calls[0][1]["timeout"] == 8.0


def test_medium_profile_uses_qualified_frozen_pose():
    module = load_environment_configurator()
    config = ROOT / "config/w4_matrix_v1.yaml"
    profile = module.load_profile(config, "medium")
    assert module.desired_pose(profile) == (0.4, 0.56, 0.45)


def test_medium_campaign_is_serial_and_covers_remaining_eight_tasks(tmp_path):
    script = ROOT / "scripts/legacy_v0_1/run_w4_medium_obstacle_campaign.sh"
    checked = subprocess.run(["bash", "-n", str(script)], text=True,
                             capture_output=True)
    assert checked.returncode == 0
    text = script.read_text(encoding="utf-8")
    for task_id in ("w4-0037", "w4-0038", "w4-0039", "w4-0092",
                    "w4-0093", "w4-0145", "w4-0146", "w4-0147"):
        assert text.count(task_id) == 1
    assert "--prepare-start 0.8 0.0 0.0" in text
    assert "Campaign停止，不启动下一套环境" in text
    result = subprocess.run([
        "bash", str(script), "--output-root", str(tmp_path),
        "--start-domain", "227", "--preview"], cwd=ROOT.parents[1],
        text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "6套环境、8项正式任务" in result.stdout
    rows = (tmp_path / "medium-obstacle-campaign-001-results.tsv").read_text(
        encoding="utf-8").splitlines()
    assert len(rows) == 7
    assert all(row.endswith("preview") for row in rows[1:])


def test_start_preparer_uses_public_navigation_and_no_velocity_topic():
    text = (ROOT / "pipelines/common/prepare_w4_start.py").read_text(encoding="utf-8")
    assert "/robot/navigation/navigate_to_pose" in text
    assert "/robot/safety/clear_faults" in text
    assert "/robot/cmd_vel" not in text
    assert "NavigateToPose" in text
