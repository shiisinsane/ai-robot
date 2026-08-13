#!/usr/bin/env python3
"""运行M6-W9自动回归，生成日志、rosbag、回放、快照和哈希证据。"""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time

import yaml


ROOT = Path(__file__).resolve().parents[1]
QOS_PATH = ROOT / 'config/common/m6_rosbag_qos.yaml'
M5_MAP = (ROOT / 'artifacts/m5_w10/20260812_112602/config_snapshot/'
          'm5_w10_map.yaml')
CONFIG_PATHS = (
    ROOT / 'config/common/interface_contract.yaml',
    ROOT / 'config/common/m4_integration.yaml',
    ROOT / 'config/common/m5_navigation.yaml',
    ROOT / 'config/common/m6_task_contract.yaml', QOS_PATH,
    ROOT / 'src/robot_core/ai_robot_sim/config/amcl_localization.yaml',
    ROOT / 'src/robot_core/ai_robot_sim/config/nav2_global_planning.yaml',
    ROOT / 'src/robot_core/ai_robot_sim/config/nav2_local_control.yaml',
    ROOT / 'src/robot_core/ai_robot_task_manager/launch/task_manager.launch.py',
)
BAG_TOPICS = (
    '/clock', '/tf', '/tf_static', '/robot/map', '/robot/pose', '/robot/odom',
    '/robot/scan', '/robot/diagnostics', '/robot/safety/stop_active',
    '/robot/task/execute/_action/feedback',
    '/robot/task/execute/_action/status',
)


def run(command, env, timeout=360.0):
    return subprocess.run(command, cwd=ROOT, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=timeout, check=False)


def stop(process, timeout=25.0):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5.0)


def environment(domain, name, run_dir):
    env = os.environ.copy()
    env.update({'ROS_DOMAIN_ID': str(domain), 'ROS2CLI_DISABLE_DAEMON': '1',
                'IGN_PARTITION': name, 'IGN_HOME': str(run_dir / 'ign'),
                'ROS_LOG_DIR': str(run_dir / 'ros_logs')})
    return env


def start_system(run_dir, env):
    launch_log = (run_dir / 'navigation_launch.log').open('w', encoding='utf-8')
    launch = subprocess.Popen([
        'ros2', 'launch', 'ai_robot_sim', 'm5_recovery_navigation.launch.py',
        'gui:=false', f'map:={M5_MAP}'], cwd=ROOT, env=env,
        stdout=launch_log, stderr=subprocess.STDOUT, text=True,
        start_new_session=True)
    task_log = (run_dir / 'task_manager.log').open('w', encoding='utf-8')
    task = subprocess.Popen([
        'ros2', 'launch', 'ai_robot_task_manager', 'task_manager.launch.py'],
        cwd=ROOT, env=env, stdout=task_log, stderr=subprocess.STDOUT,
        text=True, start_new_session=True)
    return launch, launch_log, task, task_log


def wait_ready(env, processes, run_dir):
    deadline = time.monotonic() + 100.0
    nodes = ('planner_server', 'controller_server', 'bt_navigator')
    recovery_log = run_dir / 'lifecycle_recovery.log'
    planner_recovery_attempted = False
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise RuntimeError('系统在任务Action就绪前退出')
        try:
            action = run(['ros2', 'action', 'info', '/robot/task/execute'], env, 6.0)
            states = [run([
                'ros2', 'lifecycle', 'get', f'/robot/{node}'], env, 6.0)
                for node in nodes]
        except subprocess.TimeoutExpired:
            time.sleep(0.5)
            continue
        if (not planner_recovery_attempted and states[0].returncode == 0 and
                'inactive [2]' in states[0].stdout):
            recovered = run([
                'ros2', 'lifecycle', 'set', '/robot/planner_server', 'activate'],
                env, 12.0)
            recovery_log.write_text(
                '检测到planner_server停在inactive，执行一次显式activate：\n' +
                recovered.stdout, encoding='utf-8')
            planner_recovery_attempted = True
            time.sleep(1.0)
            continue
        if ('Action servers: 1' in action.stdout and
                all(item.returncode == 0 and 'active [3]' in item.stdout
                    for item in states)):
            time.sleep(2.0)
            return
        time.sleep(0.5)
    raise RuntimeError('等待任务Action和Nav2生命周期active超时')


def write_check(run_dir, name, command, env, timeout=600.0):
    result = run(command, env, timeout)
    (run_dir / f'{name}.log').write_text(result.stdout, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(f'{name}失败，见{run_dir / (name + ".log")}')
    return {'name': name, 'returncode': result.returncode}


def record_start(run_dir, env):
    path = run_dir / 'minimal_bag'
    handle = (run_dir / 'rosbag.log').open('w', encoding='utf-8')
    process = subprocess.Popen([
        'ros2', 'bag', 'record', '--storage', 'sqlite3',
        '--include-hidden-topics',
        '--qos-profile-overrides-path', str(QOS_PATH), '--output', str(path),
        *BAG_TOPICS], cwd=ROOT, env=env, stdout=handle,
        stderr=subprocess.STDOUT, text=True, start_new_session=True)
    time.sleep(3.0)
    if process.poll() is not None:
        handle.close()
        raise RuntimeError('rosbag录制进程提前退出')
    return process, handle, path


def normal_round(output, domain):
    run_dir = output / 'normal_repeated_performance'
    run_dir.mkdir()
    env = environment(domain, f'ai_robot_m6_w9_{os.getpid()}_normal', run_dir)
    launch, launch_log, task, task_log = start_system(run_dir, env)
    bag = bag_log = None
    try:
        wait_ready(env, (launch, task), run_dir)
        bag, bag_log, bag_path = record_start(run_dir, env)
        checks = [write_check(
            run_dir, 'repeated_tasks',
            ['python3', 'scripts/check_m6_repeated_tasks.py', '--count', '5',
             '--timeout', '90'], env, 600.0)]
        stop(bag); bag_log.close(); bag = bag_log = None
        sys.path.insert(0, str(ROOT / 'scripts'))
        from check_rosbag import inspect_bag
        bag_summary = inspect_bag(bag_path, 'sqlite3', set(BAG_TOPICS))
        replay_env = env.copy(); replay_env['ROS_DOMAIN_ID'] = str(domain + 20)
        replay = run(['ros2', 'bag', 'play', str(bag_path), '--rate', '20.0'],
                     replay_env, 120.0)
        (run_dir / 'replay.log').write_text(replay.stdout, encoding='utf-8')
        if replay.returncode:
            raise RuntimeError('隔离rosbag回放失败')
        checks.append(write_check(
            run_dir, 'performance',
            ['python3', 'scripts/check_m5_navigation_performance.py',
             '--duration', '30'], env, 120.0))
        return {'passed': True, 'checks': checks,
                'bag_summary': bag_summary, 'replay_returncode': 0}
    finally:
        stop(bag)
        if bag_log is not None:
            bag_log.close()
        stop(task); stop(launch); task_log.close(); launch_log.close()


def scenario(output, name, domain, command, timeout=240.0):
    run_dir = output / name
    run_dir.mkdir()
    env = environment(domain, f'ai_robot_m6_w9_{os.getpid()}_{name}', run_dir)
    launch, launch_log, task, task_log = start_system(run_dir, env)
    try:
        wait_ready(env, (launch, task), run_dir)
        check = write_check(run_dir, name, command, env, timeout)
        return {'name': name, 'passed': True, 'check': check}
    finally:
        stop(task); stop(launch); task_log.close(); launch_log.close()


def preflight(output):
    results = []
    for name, command in (('build', ['bash', 'scripts/build.sh']),
                          ('test', ['bash', 'scripts/test.sh'])):
        result = run(command, os.environ.copy(), 420.0)
        (output / f'{name}.log').write_text(result.stdout, encoding='utf-8')
        results.append({'name': name, 'returncode': result.returncode})
        if result.returncode:
            raise RuntimeError(f'{name}预检失败')
    return results


def hash_artifacts(output):
    artifacts = []
    for path in sorted(output.rglob('*')):
        if not path.is_file() or path.name in {'manifest.yaml', 'summary.json'}:
            continue
        relative = path.relative_to(output)
        kind = ('rosbag' if 'minimal_bag' in relative.parts else
                'configuration' if 'config_snapshot' in relative.parts else
                'test_log')
        artifacts.append({
            'type': kind, 'location': str(relative),
            'size_bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'contains_sensitive_data': False})
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    stamp = time.strftime('%Y%m%d_%H%M%S')
    output = args.output_root or ROOT / 'artifacts/m6_w9' / stamp
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / 'config_snapshot'; snapshot.mkdir()
    for path in CONFIG_PATHS:
        shutil.copy2(path, snapshot / path.name)
    shutil.copy2(M5_MAP, snapshot / 'm5_input_map.yaml')
    source_map = M5_MAP.parent / yaml.safe_load(
        M5_MAP.read_text(encoding='utf-8'))['image']
    shutil.copy2(source_map, snapshot / source_map.name)
    report = {'command': './scripts/run_m6_regression.sh', 'passed': False,
              'scenarios': []}
    try:
        report['preflight'] = preflight(output)
        print('开始正常五轮综合任务、最小rosbag和性能回归', flush=True)
        report['normal'] = normal_round(output, 180)
        cases = [
            ('control_semantics', ['python3', 'scripts/check_m6_control_semantics.py'], 360),
            ('input', ['python3', 'scripts/check_m6_fault_scenarios.py', 'input'], 120),
            ('unreachable', ['python3', 'scripts/check_m6_fault_scenarios.py', 'unreachable'], 180),
            ('camera', ['python3', 'scripts/check_m6_fault_scenarios.py', 'camera'], 180),
            ('scan', ['python3', 'scripts/check_m6_fault_scenarios.py', 'scan'], 180),
            ('imu', ['python3', 'scripts/check_m6_fault_scenarios.py', 'imu'], 180),
            ('odom', ['python3', 'scripts/check_m6_fault_scenarios.py', 'odom'], 180),
            ('localization', ['python3', 'scripts/check_m6_fault_scenarios.py', 'localization'], 180),
        ]
        for index, (name, command, timeout) in enumerate(cases):
            print(f'开始{name}场景回归', flush=True)
            report['scenarios'].append(
                scenario(output, name, 181 + index, command, timeout))
        report['passed'] = True
        code = 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        report['error'] = str(error)
        print(f'M6-W9回归失败：{error}', file=sys.stderr)
        code = 1
    finally:
        artifacts = hash_artifacts(output)
        report['artifacts'] = artifacts
        commit = run(['git', 'rev-parse', 'HEAD'], os.environ.copy()).stdout.strip()
        manifest = {
            'evidence_version': 'm1.v1',
            'identity': {'evidence_id': f'M6-W9-{stamp}', 'milestone': 'M6',
                         'test_name': 'm6_integrated_task_regression',
                         'executed_at': datetime.now().astimezone().isoformat(),
                         'operator': 'Codex'},
            'source': {'repository': str(ROOT), 'git_commit': commit,
                       'git_dirty': True, 'interface_version': 'm1.v2',
                       'configuration': [str(p.relative_to(ROOT))
                                         for p in CONFIG_PATHS]},
            'environment': {'os': platform.platform(), 'ros_distro': 'humble',
                            'rmw_implementation': os.environ.get(
                                'RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp'),
                            'ros_domain_id': '180-200', 'mode': 'sim'},
            'execution': {'command': './scripts/run_m6_regression.sh',
                          'result': 'passed' if report['passed'] else 'failed',
                          'passed': (9 if report['passed'] else 0),
                          'failed': 0 if report['passed'] else 1, 'skipped': 0,
                          'notes': '隔离无GUI仿真；rosbag不含速度命令；回放域隔离'},
            'artifacts': artifacts, 'known_issues': [],
            'manual_checks': ['W9为自动证据固化，不新增GUI人工验证'],
        }
        (output / 'summary.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (output / 'manifest.yaml').write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
            encoding='utf-8')
        print(f'证据目录：{output}')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
