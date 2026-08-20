"""按一个已人工确认的环境分组调用W3单任务编排器。"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys


def load_cases(path, profile, task_ids=None):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    selected = [row for row in rows if row["environment_profile"] == profile]
    if task_ids:
        selected = [row for row in selected if row["task_id"] in task_ids]
    return selected


def append(path, payload):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def contiguous(cases, tolerance=0.05):
    """检查相邻任务的前一终点是否就是后一任务起点。"""
    for previous, current in zip(cases, cases[1:]):
        for target_key, start_key in (("target_x", "start_x"),
                                      ("target_y", "start_y"),
                                      ("target_yaw", "start_yaw")):
            if abs(previous[target_key] - current[start_key]) > tolerance:
                return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--environment-profile", required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--task-id", action="append",
                        help="只执行指定任务，可重复传入；省略时按环境分组选择")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--execute", action="store_true",
                        help="真正调用ROS Action；省略时只显示计划")
    parser.add_argument("--manual-step", action="store_true",
                        help="逐任务等待用户确认机器人已复位到计划起点")
    parser.add_argument("--auto-contiguous", action="store_true",
                        help="不逐项确认；仅允许显式指定且起终点连续的任务序列")
    parser.add_argument("--continue-on-failure", action="store_true")
    args = parser.parse_args()
    cases = load_cases(args.plan, args.environment_profile, set(args.task_id or []))
    if args.limit is not None:
        cases = cases[:args.limit]
    if not cases:
        raise SystemExit("指定环境分组没有任务")
    if args.task_id:
        found = {x["task_id"] for x in cases}
        missing = sorted(set(args.task_id) - found)
        if missing:
            raise SystemExit("指定任务不属于该环境分组或不存在：" + ",".join(missing))
    blocked = [x["task_id"] for x in cases if not x["environment_ready"]]
    if blocked:
        raise SystemExit("环境配置尚未冻结，拒绝执行：" + ",".join(blocked[:5]))
    print(f"环境分组：{args.environment_profile}；任务数：{len(cases)}")
    for case in cases:
        print(f"- {case['task_id']} 路线={case['route_id']} 重复={case['repetition']}")
    if not args.execute:
        print("当前为预览；确认仿真、采集器和rosbag后添加 --execute")
        return 0
    if args.manual_step == args.auto_contiguous:
        raise SystemExit("正式执行必须且只能选择 --manual-step 或 --auto-contiguous")
    if args.auto_contiguous:
        if not args.task_id:
            raise SystemExit("自动连续模式必须使用 --task-id 显式指定任务")
        requested_order = {task_id: index for index, task_id in enumerate(args.task_id)}
        cases.sort(key=lambda case: requested_order[case["task_id"]])
        if not contiguous(cases):
            raise SystemExit("自动连续模式拒绝执行：相邻任务起终点不连续")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logs = args.output_dir / "task_logs"; logs.mkdir(exist_ok=True)
    result_path = args.output_dir / "run_results.jsonl"
    for case in cases:
        if args.manual_step:
            answer = input(
                f"请确认{case['task_id']}已复位到({case['start_x']}, {case['start_y']}, "
                f"{case['start_yaw']})且环境分组正确，输入RUN继续：")
            if answer.strip() != "RUN":
                print("用户未确认，批次停止；未发送当前任务")
                return 2
        started = datetime.now().astimezone().isoformat()
        command = [sys.executable, "-m",
                   "portfolio.robot_ops_analytics.orchestrator.run_experiment",
                   "--experiment-id", args.experiment_id,
                   "--task-id", case["task_id"], "--x", str(case["target_x"]),
                   "--y", str(case["target_y"]), "--yaw", str(case["target_yaw"]),
                   "--timeout", str(case["timeout_sec"]),
                   "--ros-args", "-r", "__ns:=/robot", "-p", "use_sim_time:=true"]
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, env=os.environ.copy(), check=False)
        log = logs / f"{case['task_id']}.log"; log.write_text(result.stdout, encoding="utf-8")
        append(result_path, {**case, "experiment_id": args.experiment_id,
                             "started_at": started,
                             "finished_at": datetime.now().astimezone().isoformat(),
                             "return_code": result.returncode,
                             "log": str(log)})
        print(f"{case['task_id']}：return_code={result.returncode}", flush=True)
        if result.returncode and not args.continue_on_failure:
            print("任务失败，已停止本批；保留已有数据和日志")
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
