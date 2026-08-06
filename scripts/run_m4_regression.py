#!/usr/bin/env python3
"""连续两轮运行M4整机回归，并生成rosbag、日志、清单和哈希证据。"""

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
QOS_PATH = ROOT / 'config' / 'common' / 'm4_rosbag_qos.yaml'
CONFIG_PATHS = (
    ROOT / 'config' / 'common' / 'interface_contract.yaml',
    ROOT / 'config' / 'common' / 'robot_model.yaml',
    ROOT / 'config' / 'common' / 'sensor_model.yaml',
    ROOT / 'config' / 'common' / 'm4_integration.yaml',
    QOS_PATH,
    ROOT / 'src' / 'robot_core' / 'ai_robot_sim' / 'config' / 'controllers_m4.yaml',
    ROOT / 'src' / 'robot_core' / 'ai_robot_sim' / 'config' / 'ekf_m4.yaml',
)
BAG_TOPICS = (
    '/clock', '/robot/odom', '/robot/joint_states', '/robot/scan',
    '/robot/imu/data', '/robot/camera/color/image_raw',
    '/robot/camera/color/image_rect', '/robot/diagnostics',
    '/robot/safety/stop_active',
)
NORMAL_CHECKS = (
    ('performance', ['python3', 'scripts/check_m4_performance.py', '--duration', '30']),
    ('image_processing', ['python3', 'scripts/check_m4_image_processing.py']),
    ('lidar_tf', ['python3', 'scripts/check_m4_lidar_tf.py']),
    ('state_estimation', ['python3', 'scripts/check_m4_state_estimation.py']),
    ('safety', ['python3', 'scripts/check_m4_safety_supervisor.py', '--scenario', 'normal']),
)


def _run(command, environment, timeout=240.0):
    return subprocess.run(
        command, cwd=ROOT, env=environment, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=timeout, check=False,
    )


def _stop(process, timeout=25.0):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5.0)


def _environment(domain, partition, run_dir):
    environment = os.environ.copy()
    environment.update({
        'ROS_DOMAIN_ID': str(domain), 'ROS2CLI_DISABLE_DAEMON': '1',
        'IGN_PARTITION': partition, 'IGN_HOME': str(run_dir / 'ign'),
        'ROS_LOG_DIR': str(run_dir / 'ros_logs'),
    })
    return environment


def _start_launch(run_dir, environment, extra_arguments=()):
    launch_log = (run_dir / 'launch.log').open('w', encoding='utf-8')
    process = subprocess.Popen(
        ['ros2', 'launch', 'ai_robot_sim', 'integrated_bringup.launch.py',
         *extra_arguments], cwd=ROOT, env=environment, stdout=launch_log,
        stderr=subprocess.STDOUT, text=True, start_new_session=True)
    return process, launch_log


def _wait_topic(environment, launch, topic, timeout=45.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if launch.poll() is not None:
            raise RuntimeError(f'Launch在{topic}就绪前退出')
        result = _run(['ros2', 'topic', 'info', topic], environment, 5.0)
        if result.returncode == 0 and 'Publisher count: 0' not in result.stdout:
            return
        time.sleep(0.5)
    raise RuntimeError(f'等待{topic}发布者超时')


def _wait_controllers(environment, launch):
    deadline = time.monotonic() + 45.0
    while time.monotonic() < deadline:
        if launch.poll() is not None:
            raise RuntimeError('Launch在控制器就绪前退出')
        result = _run([
            'ros2', 'control', 'list_controllers',
            '--controller-manager', '/robot/controller_manager'], environment, 5.0)
        if (result.stdout.count('active') >= 2
                and 'joint_state_broadcaster' in result.stdout
                and 'diff_drive_base_controller' in result.stdout):
            return
        time.sleep(0.5)
    raise RuntimeError('等待两个控制器active超时')


def _hash_artifacts(run_dir):
    artifacts = []
    for path in sorted(run_dir.rglob('*')):
        if not path.is_file() or path.name in {'manifest.yaml', 'summary.json'}:
            continue
        artifacts.append({
            'type': 'rosbag' if 'minimal_bag' in path.parts else 'test_log',
            'location': str(path.relative_to(run_dir)),
            'size_bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'contains_sensitive_data': False,
        })
    return artifacts


def _bag_summary(path):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from check_rosbag import inspect_bag
    return inspect_bag(path, 'sqlite3', set(BAG_TOPICS))


def _record_bag(run_dir, environment):
    bag_path = run_dir / 'minimal_bag'
    bag_log = (run_dir / 'rosbag.log').open('w', encoding='utf-8')
    bag = subprocess.Popen([
        'ros2', 'bag', 'record', '--storage', 'sqlite3',
        '--qos-profile-overrides-path', str(QOS_PATH),
        '--output', str(bag_path), *BAG_TOPICS,
    ], cwd=ROOT, env=environment, stdout=bag_log,
        stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        time.sleep(7.0)
    finally:
        _stop(bag)
        bag_log.close()
    return bag_path, _bag_summary(bag_path)


def _replay_bag(run_dir, bag_path, environment, domain):
    replay_environment = environment.copy()
    replay_environment['ROS_DOMAIN_ID'] = str(domain)
    replay = _run(
        ['ros2', 'bag', 'play', str(bag_path), '--rate', '20.0'],
        replay_environment, 60.0)
    (run_dir / 'replay.log').write_text(replay.stdout, encoding='utf-8')
    if replay.returncode:
        raise RuntimeError(f'rosbag回放失败：{replay.stdout.strip()}')
    return replay.returncode


def _normal_round(index, output_root):
    run_dir = output_root / f'round_{index}'
    run_dir.mkdir()
    environment = _environment(
        180 + index, f'ai_robot_m4_w9_{os.getpid()}_round_{index}', run_dir)
    launch, launch_log = _start_launch(run_dir, environment)
    result = {'round': index, 'checks': [], 'passed': False}
    try:
        _wait_topic(environment, launch, '/robot/camera/color/image_rect')
        _wait_controllers(environment, launch)
        bag_path, bag_summary = _record_bag(run_dir, environment)
        result['bag_summary'] = bag_summary
        result['replay_returncode'] = _replay_bag(
            run_dir, bag_path, environment, 220 + index)
        for name, command in NORMAL_CHECKS:
            check = _run(command, environment, 300.0)
            (run_dir / f'{name}.log').write_text(check.stdout, encoding='utf-8')
            result['checks'].append({'name': name, 'returncode': check.returncode,
                                     'output': check.stdout.strip()})
            if check.returncode:
                raise RuntimeError(f'第{index}轮{name}失败：{check.stdout.strip()}')
        result['passed'] = True
        return result
    finally:
        _stop(launch)
        launch_log.close()


def _fault_scenario(name, domain, arguments, checker_arguments, output_root):
    run_dir = output_root / f'fault_{name}'
    run_dir.mkdir()
    environment = _environment(
        domain, f'ai_robot_m4_w9_{os.getpid()}_fault_{name}', run_dir)
    launch, launch_log = _start_launch(run_dir, environment, arguments)
    try:
        _wait_topic(environment, launch, '/robot/odom')
        _wait_controllers(environment, launch)
        check = _run(
            ['python3', 'scripts/check_m4_safety_supervisor.py',
             *checker_arguments], environment, 120.0)
        (run_dir / 'fault_check.log').write_text(check.stdout, encoding='utf-8')
        if check.returncode:
            raise RuntimeError(f'{name}故障场景失败：{check.stdout.strip()}')
        return {'name': name, 'passed': True, 'output': check.stdout.strip()}
    finally:
        _stop(launch)
        launch_log.close()


def _preflight(output_root):
    results = []
    for name, command in (
            ('build', ['bash', 'scripts/build.sh']),
            ('test', ['bash', 'scripts/test.sh'])):
        result = _run(command, os.environ.copy(), 300.0)
        (output_root / f'{name}.log').write_text(result.stdout, encoding='utf-8')
        results.append({'name': name, 'returncode': result.returncode})
        if result.returncode:
            raise RuntimeError(f'{name}预检失败，见{name}.log')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    stamp = time.strftime('%Y%m%d_%H%M%S')
    output_root = args.output_root or ROOT / 'artifacts' / 'm4_w9' / stamp
    output_root.mkdir(parents=True, exist_ok=False)
    snapshot = output_root / 'config_snapshot'
    snapshot.mkdir()
    for path in CONFIG_PATHS:
        shutil.copy2(path, snapshot / path.name)
    report = {'command': './scripts/run_m4_regression.sh', 'passed': False,
              'rounds': [], 'faults': []}
    try:
        report['preflight'] = _preflight(output_root)
        for index in (1, 2):
            print(f'开始M4整机回归第{index}轮', flush=True)
            report['rounds'].append(_normal_round(index, output_root))
            print(f'第{index}轮通过', flush=True)
        print('开始M4故障注入回归', flush=True)
        report['faults'].append(_fault_scenario(
            'scan', 191, ('enable_lidar_pipeline:=false',),
            ('--scenario', 'scan'), output_root))
        report['faults'].append(_fault_scenario(
            'camera', 192,
            ('safety_camera_topic:=/robot/fault/missing_camera',),
            ('--scenario', 'camera'), output_root))
        report['passed'] = True
        return_code = 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        report['error'] = str(error)
        print(f'M4回归失败：{error}', file=sys.stderr)
        return_code = 1
    finally:
        report['artifacts'] = _hash_artifacts(output_root)
        commit = _run(['git', 'rev-parse', 'HEAD'], os.environ.copy()).stdout.strip()
        manifest = {
            'evidence_version': 'm1.v1',
            'identity': {'evidence_id': f'M4-W9-{stamp}', 'milestone': 'M4',
                         'test_name': 'm4_integrated_regression',
                         'executed_at': datetime.now().astimezone().isoformat(),
                         'operator': 'Codex'},
            'source': {'repository': str(ROOT), 'git_commit': commit,
                       'git_dirty': True, 'interface_version': 'm1.v1',
                       'configuration': [str(path.relative_to(ROOT))
                                         for path in CONFIG_PATHS]},
            'environment': {'os': platform.platform(), 'ros_distro': 'humble',
                            'rmw_implementation': os.environ.get(
                                'RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp'),
                            'ros_domain_id': '181-182,191-192,221-222',
                            'mode': 'sim'},
            'execution': {'command': './scripts/run_m4_regression.sh',
                          'result': 'passed' if report['passed'] else 'failed',
                          'passed': len(report['rounds']) + len(report['faults']),
                          'failed': 0 if report['passed'] else 1, 'skipped': 0,
                          'notes': '仅使用隔离无GUI Gazebo仿真，不连接实体设备或AI Agent'},
            'artifacts': report['artifacts'], 'known_issues': [],
            'manual_checks': ['W9为自动回归与证据固化，不新增GUI人工验证'],
        }
        (output_root / 'summary.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (output_root / 'manifest.yaml').write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
            encoding='utf-8')
        print(f'证据目录：{output_root}')
    return return_code


if __name__ == '__main__':
    raise SystemExit(main())
