#!/usr/bin/env python3
"""连续运行隔离的M2仿真回归并生成最小rosbag证据。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
TOPICS = (
    '/clock', '/robot/cmd_vel', '/robot/odom', '/robot/joint_states',
    '/tf', '/tf_static',
)


def _run(command, environment, timeout=60.0):
    return subprocess.run(
        command, cwd=ROOT, env=environment, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=timeout, check=False,
    )


def _stop(process, timeout=20.0):
    if process.poll() is not None:
        return process.returncode
    os.killpg(process.pid, signal.SIGINT)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        return process.wait(timeout=5.0)


def _wait_ready(environment, launch_process):
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if launch_process.poll() is not None:
            raise RuntimeError('Gazebo Launch在就绪前退出')
        result = _run([
            'ros2', 'control', 'list_controllers',
            '--controller-manager', '/robot/controller_manager',
        ], environment, timeout=5.0)
        output = result.stdout
        if ('joint_state_broadcaster' in output and
                'diff_drive_base_controller' in output and
                output.count('active') >= 2):
            return
        time.sleep(0.5)
    raise RuntimeError('等待控制器active超时')


def _check_graph(environment):
    public_info = _run(
        ['ros2', 'topic', 'info', '-v', '/robot/cmd_vel'], environment)
    private_info = _run(
        ['ros2', 'topic', 'info', '-v', '/robot/controller_cmd_vel'],
        environment,
    )
    if public_info.returncode or private_info.returncode:
        raise RuntimeError('读取速度命令运行图失败')
    if ('cmd_vel_safety_filter' not in public_info.stdout or
            'diff_drive_base_controller' in public_info.stdout):
        raise RuntimeError('公共速度命令未被安全过滤节点独占')
    if ('cmd_vel_safety_filter' not in private_info.stdout or
            'diff_drive_base_controller' not in private_info.stdout):
        raise RuntimeError('控制器私有速度命令链不完整')


def _bag_summary(bag_path):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from check_rosbag import inspect_bag
    summary = inspect_bag(bag_path, 'sqlite3', set(TOPICS))
    hashes = {}
    for path in sorted(bag_path.iterdir()):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            hashes[path.name] = {'size_bytes': path.stat().st_size,
                                 'sha256': digest}
    return summary, hashes


def _run_once(index, output_root):
    domain_id = 80 + (os.getpid() + index) % 100
    run_dir = output_root / f'run_{index}'
    run_dir.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment.update({
        'ROS_DOMAIN_ID': str(domain_id),
        'ROS2CLI_DISABLE_DAEMON': '1',
        'IGN_PARTITION': f'ai_robot_m2_w8_{os.getpid()}_{index}',
        'IGN_HOME': str(run_dir / 'ign'),
        'ROS_LOG_DIR': str(run_dir / 'ros_logs'),
    })
    launch_log = (run_dir / 'launch.log').open('w', encoding='utf-8')
    launch = subprocess.Popen(
        ['ros2', 'launch', 'ai_robot_sim', 'fortress.launch.py'],
        cwd=ROOT, env=environment, stdout=launch_log,
        stderr=subprocess.STDOUT, text=True, start_new_session=True,
    )
    bag = None
    results = {'run': index, 'ros_domain_id': domain_id, 'passed': False}
    try:
        _wait_ready(environment, launch)
        _check_graph(environment)
        bag_path = run_dir / 'm2_minimal_bag'
        bag_log = (run_dir / 'rosbag.log').open('w', encoding='utf-8')
        bag = subprocess.Popen(
            ['ros2', 'bag', 'record', '--storage', 'sqlite3',
             '--qos-profile-overrides-path',
             str(ROOT / 'config' / 'common' / 'm2_rosbag_qos.yaml'),
             '--output', str(bag_path), *TOPICS],
            cwd=ROOT, env=environment, stdout=bag_log,
            stderr=subprocess.STDOUT, text=True, start_new_session=True,
        )
        time.sleep(2.0)
        checks = []
        for script in ('check_m2_motion.py', 'check_m2_w7_safety.py'):
            result = _run(
                ['python3', str(ROOT / 'scripts' / script)],
                environment, timeout=120.0,
            )
            checks.append({'script': script, 'returncode': result.returncode,
                           'output': result.stdout.strip()})
            if result.returncode:
                raise RuntimeError(f'{script}失败：{result.stdout.strip()}')
        _stop(bag)
        bag_log.close()
        bag = None
        summary, hashes = _bag_summary(bag_path)
        results.update({'passed': True, 'checks': checks,
                        'bag_summary': summary, 'artifacts': hashes})
        return results
    finally:
        if bag is not None:
            _stop(bag)
        _stop(launch)
        launch_log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=2)
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs必须至少为1')
    stamp = time.strftime('%Y%m%d_%H%M%S')
    output_root = args.output_root or ROOT / 'artifacts' / 'm2_w8' / stamp
    output_root.mkdir(parents=True, exist_ok=False)
    report = {'command': 'scripts/run_m2_regression.sh', 'runs': [],
              'passed': False}
    try:
        for index in range(1, args.runs + 1):
            print(f'开始M2回归：第{index}/{args.runs}轮', flush=True)
            result = _run_once(index, output_root)
            report['runs'].append(result)
            print(f'第{index}轮通过', flush=True)
        report['passed'] = True
        return_code = 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        report['error'] = str(error)
        print(f'M2回归失败：{error}', file=sys.stderr)
        return_code = 1
    finally:
        report_path = output_root / 'summary.json'
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
        print(f'证据摘要：{report_path}')
    return return_code


if __name__ == '__main__':
    raise SystemExit(main())
