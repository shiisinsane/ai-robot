#!/usr/bin/env python3
"""运行M5-W10自动回归，生成最小rosbag、回放、日志、快照和哈希证据。"""

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
QOS_PATH = ROOT / 'config' / 'common' / 'm5_rosbag_qos.yaml'
CONFIG_PATHS = (
    ROOT / 'config' / 'common' / 'interface_contract.yaml',
    ROOT / 'config' / 'common' / 'm5_navigation.yaml', QOS_PATH,
    ROOT / 'src' / 'robot_core' / 'ai_robot_sim' / 'config' / 'amcl_localization.yaml',
    ROOT / 'src' / 'robot_core' / 'ai_robot_sim' / 'config' / 'nav2_global_planning.yaml',
    ROOT / 'src' / 'robot_core' / 'ai_robot_sim' / 'config' / 'nav2_local_control.yaml',
    ROOT / 'src' / 'robot_core' / 'ai_robot_sim' / 'config' / 'behavior_trees' / 'navigate_recovery.xml',
    ROOT / 'src' / 'robot_core' / 'ai_robot_sim' / 'launch' / 'm5_recovery_navigation.launch.py',
)
BAG_TOPICS = (
    '/clock', '/tf', '/tf_static', '/robot/map', '/robot/pose', '/robot/odom',
    '/robot/scan', '/robot/imu/data', '/robot/diagnostics',
    '/robot/safety/stop_active',
)


def run(command, environment, timeout=300.0):
    return subprocess.run(command, cwd=ROOT, env=environment, text=True,
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
    result = os.environ.copy()
    result.update({'ROS_DOMAIN_ID': str(domain), 'ROS2CLI_DISABLE_DAEMON': '1',
                   'IGN_PARTITION': name, 'IGN_HOME': str(run_dir / 'ign'),
                   'ROS_LOG_DIR': str(run_dir / 'ros_logs')})
    return result


def make_map(snapshot):
    """按m5_slam.sdf固定结构生成确定性地图，避免依赖临时建图文件。"""
    pgm = snapshot / 'm5_w10_map.pgm'
    size = 400
    resolution = 0.05
    origin = -10.0
    pixels = bytearray([254]) * (size * size)

    def occupy(x_min, x_max, y_min, y_max):
        column_min = max(0, int((x_min - origin) / resolution))
        column_max = min(size - 1, int((x_max - origin) / resolution))
        row_min = max(0, size - 1 - int((y_max - origin) / resolution))
        row_max = min(size - 1, size - 1 - int((y_min - origin) / resolution))
        for row in range(row_min, row_max + 1):
            start = row * size + column_min
            pixels[start:start + column_max - column_min + 1] = bytes(
                [0]) * (column_max - column_min + 1)

    # 四面围墙、一个偏转方形地标和一个圆柱地标。
    occupy(-3.25, 3.25, 2.925, 3.075)
    occupy(-3.25, 3.25, -3.075, -2.925)
    occupy(3.175, 3.325, -3.0, 3.0)
    occupy(-3.325, -3.175, -3.0, 3.0)
    occupy(1.35, 2.05, 1.10, 1.70)
    occupy(-1.90, -1.30, -1.50, -0.90)
    pgm.write_bytes(b'P5\n400 400\n255\n' + pixels)
    data = {'image': pgm.name, 'mode': 'trinary', 'resolution': resolution,
            'origin': [-10.0, -10.0, 0.0], 'negate': 0,
            'occupied_thresh': 0.65, 'free_thresh': 0.25}
    path = snapshot / 'm5_w10_map.yaml'
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
    return path


def start_launch(run_dir, env, map_path):
    handle = (run_dir / 'launch.log').open('w', encoding='utf-8')
    process = subprocess.Popen(
        ['ros2', 'launch', 'ai_robot_sim', 'm5_recovery_navigation.launch.py',
         'gui:=false', f'map:={map_path}'], cwd=ROOT, env=env,
        stdout=handle, stderr=subprocess.STDOUT, text=True,
        start_new_session=True)
    return process, handle


def wait_navigation(env, launch):
    deadline = time.monotonic() + 75.0
    while time.monotonic() < deadline:
        if launch.poll() is not None:
            raise RuntimeError('Launch在导航Action就绪前退出')
        result = run(['ros2', 'action', 'info',
                      '/robot/navigation/navigate_to_pose'], env, 6.0)
        if result.returncode == 0 and 'Action servers: 1' in result.stdout:
            time.sleep(3.0)
            return
        time.sleep(0.5)
    raise RuntimeError('等待公共导航Action超时')


def write_check(run_dir, name, command, env, timeout=360.0):
    result = run(command, env, timeout)
    (run_dir / f'{name}.log').write_text(result.stdout, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(f'{name}失败，见{run_dir / (name + ".log")}')
    return {'name': name, 'returncode': result.returncode}


def record_start(run_dir, env):
    path = run_dir / 'minimal_bag'
    handle = (run_dir / 'rosbag.log').open('w', encoding='utf-8')
    process = subprocess.Popen(
        ['ros2', 'bag', 'record', '--storage', 'sqlite3',
         '--qos-profile-overrides-path', str(QOS_PATH), '--output', str(path),
         *BAG_TOPICS], cwd=ROOT, env=env, stdout=handle,
        stderr=subprocess.STDOUT, text=True, start_new_session=True)
    time.sleep(3.0)
    if process.poll() is not None:
        handle.close()
        raise RuntimeError('rosbag录制进程提前退出')
    return process, handle, path


def inspect_bag(path):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from check_rosbag import inspect_bag as inspect
    return inspect(path, 'sqlite3', set(BAG_TOPICS))


def replay_bag(run_dir, path, env, domain):
    replay_env = env.copy()
    replay_env['ROS_DOMAIN_ID'] = str(domain)
    result = run(['ros2', 'bag', 'play', str(path), '--rate', '20.0'],
                 replay_env, 120.0)
    (run_dir / 'replay.log').write_text(result.stdout, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('rosbag隔离回放失败')
    return result.returncode


def normal_round(output, map_path):
    run_dir = output / 'normal_navigation'
    run_dir.mkdir()
    env = environment(220, f'ai_robot_m5_w10_{os.getpid()}_normal', run_dir)
    launch, launch_log = start_launch(run_dir, env, map_path)
    bag = bag_log = None
    try:
        wait_navigation(env, launch)
        bag, bag_log, bag_path = record_start(run_dir, env)
        checks = [write_check(
            run_dir, 'repeated_navigation',
            ['python3', 'scripts/check_m5_repeated_navigation.py', '--count', '5',
             '--timeout', '180'], env, 900.0)]
        stop(bag)
        bag_log.close()
        bag = bag_log = None
        summary = inspect_bag(bag_path)
        replay = replay_bag(run_dir, bag_path, env, 229)
        checks.append(write_check(
            run_dir, 'performance',
            ['python3', 'scripts/check_m5_navigation_performance.py',
             '--duration', '30'], env, 120.0))
        return {'passed': True, 'checks': checks, 'bag_summary': summary,
                'replay_returncode': replay}
    finally:
        stop(bag)
        if bag_log is not None:
            bag_log.close()
        stop(launch)
        launch_log.close()


def scenario(output, map_path, name, domain, command, timeout=240.0):
    run_dir = output / name
    run_dir.mkdir()
    env = environment(domain, f'ai_robot_m5_w10_{os.getpid()}_{name}', run_dir)
    launch, launch_log = start_launch(run_dir, env, map_path)
    try:
        wait_navigation(env, launch)
        check = write_check(run_dir, name, command, env, timeout)
        return {'name': name, 'passed': True, 'check': check}
    finally:
        stop(launch)
        launch_log.close()


def preflight(output):
    results = []
    for name, command in (
            ('build', ['bash', 'scripts/build.sh']),
            ('test', ['bash', 'scripts/test.sh'])):
        result = run(command, os.environ.copy(), 360.0)
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
                'configuration' if 'config_snapshot' in relative.parts else 'test_log')
        artifacts.append({'type': kind, 'location': str(relative),
                          'size_bytes': path.stat().st_size,
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                          'contains_sensitive_data': False})
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    stamp = time.strftime('%Y%m%d_%H%M%S')
    output = args.output_root or ROOT / 'artifacts' / 'm5_w10' / stamp
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / 'config_snapshot'
    snapshot.mkdir()
    for path in CONFIG_PATHS:
        shutil.copy2(path, snapshot / path.name)
    map_path = make_map(snapshot)
    report = {'command': './scripts/run_m5_regression.sh', 'passed': False,
              'scenarios': []}
    try:
        report['preflight'] = preflight(output)
        print('开始5次固定路线与最小rosbag回归', flush=True)
        report['normal_navigation'] = normal_round(output, map_path)
        print('开始动态障碍严格绕行回归', flush=True)
        report['scenarios'].append(scenario(
            output, map_path, 'dynamic_obstacle', 221,
            ['python3', 'scripts/check_m5_dynamic_obstacle_gui.py',
             '--navigation-timeout', '180'], 420.0))
        for index, fault in enumerate(('scan', 'imu', 'odom', 'localization')):
            print(f'开始{fault}断流回归', flush=True)
            report['scenarios'].append(scenario(
                output, map_path, f'fault_{fault}', 222 + index,
                ['python3', 'scripts/check_m5_navigation_fault.py', fault], 180.0))
        report['passed'] = True
        code = 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        report['error'] = str(error)
        print(f'M5-W10回归失败：{error}', file=sys.stderr)
        code = 1
    finally:
        artifacts = hash_artifacts(output)
        report['artifacts'] = artifacts
        commit = run(['git', 'rev-parse', 'HEAD'], os.environ.copy()).stdout.strip()
        manifest = {
            'evidence_version': 'm1.v1',
            'identity': {'evidence_id': f'M5-W10-{stamp}', 'milestone': 'M5',
                         'test_name': 'm5_navigation_regression',
                         'executed_at': datetime.now().astimezone().isoformat(),
                         'operator': 'Codex'},
            'source': {'repository': str(ROOT), 'git_commit': commit,
                       'git_dirty': True, 'interface_version': 'm1.v1',
                       'configuration': [str(p.relative_to(ROOT)) for p in CONFIG_PATHS]},
            'environment': {'os': platform.platform(), 'ros_distro': 'humble',
                            'rmw_implementation': os.environ.get(
                                'RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp'),
                            'ros_domain_id': '220-229', 'mode': 'sim'},
            'execution': {'command': './scripts/run_m5_regression.sh',
                          'result': 'passed' if report['passed'] else 'failed',
                          'passed': (6 if report['passed'] else 0),
                          'failed': (0 if report['passed'] else 1), 'skipped': 0,
                          'notes': '隔离无GUI仿真；rosbag不含cmd_vel，回放域与运行域隔离'},
            'artifacts': artifacts, 'known_issues': [],
            'manual_checks': ['W7、W8 GUI人工验证已在对应阶段完成'],
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
