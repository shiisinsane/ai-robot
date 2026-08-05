#!/usr/bin/env python3
"""隔离运行M3四类传感器回归，并生成最小rosbag、日志、清单和哈希。"""

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
QOS_PATH = ROOT / 'config' / 'common' / 'm3_rosbag_qos.yaml'
CONFIG_PATHS = (
    ROOT / 'config' / 'common' / 'interface_contract.yaml',
    ROOT / 'config' / 'common' / 'robot_model.yaml',
    ROOT / 'config' / 'common' / 'sensor_model.yaml',
    QOS_PATH,
)
SCENARIOS = {
    'lidar': {
        'launch': 'lidar.launch.py',
        'check': ('check_m3_lidar.py',),
        'topics': ('/clock', '/robot/scan'),
        'type': 'sensor_msgs/msg/LaserScan',
        'reliability': 'BEST_EFFORT',
    },
    'camera': {
        'launch': 'camera.launch.py',
        'check': ('check_m3_camera.py',),
        'topics': ('/clock', '/robot/camera/color/image_raw',
                   '/robot/camera/color/camera_info'),
        'type': 'sensor_msgs/msg/Image',
        'reliability': 'BEST_EFFORT',
    },
    'imu': {
        'launch': 'imu.launch.py',
        'check': ('check_m3_imu.py',),
        'topics': ('/clock', '/robot/imu/data'),
        'type': 'sensor_msgs/msg/Imu',
        'reliability': 'BEST_EFFORT',
    },
    'encoder': {
        'launch': 'encoder.launch.py',
        'check': ('check_m3_encoder.py', 'check_m2_motion.py',
                  'check_m2_w7_safety.py'),
        'topics': ('/clock', '/robot/joint_states', '/robot/odom'),
        'type': 'sensor_msgs/msg/JointState',
        'reliability': 'RELIABLE',
    },
}


def _run(command, environment, timeout=180.0):
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


def _wait_topic(environment, launch, topic, timeout=40.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if launch.poll() is not None:
            raise RuntimeError('Launch在Topic就绪前退出')
        result = _run(['ros2', 'topic', 'info', topic], environment, 5.0)
        if result.returncode == 0 and 'Publisher count: 0' not in result.stdout:
            return
        time.sleep(0.5)
    raise RuntimeError(f'等待{topic}发布者超时')


def _wait_controllers(environment, launch):
    deadline = time.monotonic() + 40.0
    while time.monotonic() < deadline:
        if launch.poll() is not None:
            raise RuntimeError('编码器Launch在控制器就绪前退出')
        result = _run([
            'ros2', 'control', 'list_controllers',
            '--controller-manager', '/robot/controller_manager',
        ], environment, 5.0)
        if (result.stdout.count('active') >= 2 and
                'joint_state_broadcaster' in result.stdout and
                'diff_drive_base_controller' in result.stdout):
            return
        time.sleep(0.5)
    raise RuntimeError('等待编码器控制器active超时')


def _check_endpoint(environment, topic, expected_type, reliability):
    result = _run(['ros2', 'topic', 'info', '-v', topic], environment, 10.0)
    output = result.stdout.upper()
    if result.returncode or expected_type.upper() not in output:
        raise RuntimeError(f'{topic}消息类型或运行图错误')
    if reliability not in output:
        raise RuntimeError(f'{topic}可靠性不符合契约：期望{reliability}')
    return result.stdout.strip()


def _hash_artifacts(run_dir):
    artifacts = []
    for path in sorted(run_dir.rglob('*')):
        if not path.is_file() or path.name in {'manifest.yaml', 'summary.json'}:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        artifacts.append({
            'type': 'rosbag' if 'minimal_bag' in path.parts else 'test_log',
            'location': str(path.relative_to(run_dir)),
            'size_bytes': path.stat().st_size,
            'sha256': digest,
            'contains_sensitive_data': False,
        })
    return artifacts


def _bag_summary(path, topics):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from check_rosbag import inspect_bag
    return inspect_bag(path, 'sqlite3', set(topics))


def _scenario(index, name, specification, output_root):
    run_dir = output_root / f'{index:02d}_{name}'
    run_dir.mkdir()
    environment = os.environ.copy()
    environment.update({
        'ROS_DOMAIN_ID': str(120 + index),
        'ROS2CLI_DISABLE_DAEMON': '1',
        'IGN_PARTITION': f'ai_robot_m3_w7_{os.getpid()}_{index}_{name}',
        'IGN_HOME': str(run_dir / 'ign'),
        'ROS_LOG_DIR': str(run_dir / 'ros_logs'),
    })
    launch_log = (run_dir / 'launch.log').open('w', encoding='utf-8')
    launch = subprocess.Popen(
        ['ros2', 'launch', 'ai_robot_sim', specification['launch']],
        cwd=ROOT, env=environment, stdout=launch_log,
        stderr=subprocess.STDOUT, text=True, start_new_session=True,
    )
    bag = None
    bag_log = None
    started = datetime.now().astimezone()
    checks = []
    try:
        _wait_topic(environment, launch, specification['topics'][-1])
        if name == 'encoder':
            _wait_controllers(environment, launch)
        graph = _check_endpoint(
            environment, specification['topics'][1],
            specification['type'], specification['reliability'])
        (run_dir / 'topic_info.txt').write_text(graph + '\n', encoding='utf-8')

        bag_path = run_dir / 'minimal_bag'
        bag_log = (run_dir / 'rosbag.log').open('w', encoding='utf-8')
        bag = subprocess.Popen([
            'ros2', 'bag', 'record', '--storage', 'sqlite3',
            '--qos-profile-overrides-path', str(QOS_PATH),
            '--output', str(bag_path), *specification['topics'],
        ], cwd=ROOT, env=environment, stdout=bag_log,
            stderr=subprocess.STDOUT, text=True, start_new_session=True)
        time.sleep(1.5)
        for script in specification['check']:
            result = _run(['python3', str(ROOT / 'scripts' / script)],
                          environment)
            checks.append({'script': script, 'returncode': result.returncode,
                           'output': result.stdout.strip()})
            (run_dir / f'{Path(script).stem}.log').write_text(
                result.stdout, encoding='utf-8')
            if result.returncode:
                raise RuntimeError(f'{script}失败：{result.stdout.strip()}')
        _stop(bag)
        bag = None
        bag_log.close()
        bag_log = None
        summary = _bag_summary(bag_path, specification['topics'])
        replay_environment = environment.copy()
        replay_environment['ROS_DOMAIN_ID'] = str(220 + index)
        replay = _run(
            ['ros2', 'bag', 'play', str(bag_path), '--rate', '20.0'],
            replay_environment, timeout=60.0)
        (run_dir / 'replay.log').write_text(replay.stdout, encoding='utf-8')
        if replay.returncode:
            raise RuntimeError(f'{name} rosbag回放失败：{replay.stdout.strip()}')
        return {'name': name, 'passed': True, 'checks': checks,
                'bag_summary': summary, 'replay_returncode': replay.returncode,
                'started_at': started.isoformat(),
                'finished_at': datetime.now().astimezone().isoformat()}
    finally:
        _stop(bag)
        if bag_log is not None:
            bag_log.close()
        _stop(launch)
        launch_log.close()


def _preflight(environment, output_root):
    commands = (
        ('build', ['bash', 'scripts/build.sh']),
        ('test', ['bash', 'scripts/test.sh']),
    )
    results = []
    for name, command in commands:
        result = _run(command, environment, 240.0)
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
    output_root = args.output_root or ROOT / 'artifacts' / 'm3_w7' / stamp
    output_root.mkdir(parents=True, exist_ok=False)
    config_dir = output_root / 'config_snapshot'
    config_dir.mkdir()
    for config_path in CONFIG_PATHS:
        shutil.copy2(config_path, config_dir / config_path.name)
    report = {'command': './scripts/run_m3_regression.sh', 'passed': False,
              'scenarios': []}
    try:
        report['preflight'] = _preflight(os.environ.copy(), output_root)
        for index, (name, specification) in enumerate(SCENARIOS.items(), 1):
            print(f'开始M3回归：{name}', flush=True)
            result = _scenario(index, name, specification, output_root)
            report['scenarios'].append(result)
            print(f'{name}通过', flush=True)
        report['passed'] = True
        return_code = 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        report['error'] = str(error)
        print(f'M3回归失败：{error}', file=sys.stderr)
        return_code = 1
    finally:
        report['artifacts'] = _hash_artifacts(output_root)
        commit = _run(['git', 'rev-parse', 'HEAD'], os.environ.copy()).stdout.strip()
        manifest = {
            'evidence_version': 'm1.v1',
            'identity': {'evidence_id': f'M3-W7-{stamp}', 'milestone': 'M3',
                         'test_name': 'm3_sensor_regression',
                         'executed_at': datetime.now().astimezone().isoformat(),
                         'operator': 'Codex'},
            'source': {'repository': str(ROOT), 'git_commit': commit,
                       'git_dirty': True, 'interface_version': 'm1.v1',
                       'configuration': ['config/common/interface_contract.yaml',
                                         'config/common/sensor_model.yaml']},
            'environment': {'os': platform.platform(), 'ros_distro': 'humble',
                            'rmw_implementation': os.environ.get(
                                'RMW_IMPLEMENTATION', 'rmw_fastrtps_cpp'),
                            'ros_domain_id': '121-124', 'mode': 'sim'},
            'execution': {'command': './scripts/run_m3_regression.sh',
                          'result': 'passed' if report['passed'] else 'failed',
                          'passed': len(report['scenarios']),
                          'failed': 0 if report['passed'] else 1, 'skipped': 0,
                          'notes': '仅使用隔离Gazebo仿真，不连接实体设备或AI Agent'},
            'artifacts': report['artifacts'], 'known_issues': [],
            'manual_checks': ['M3-W7按用户决定不增加GUI验证'],
        }
        (output_root / 'summary.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')
        (output_root / 'manifest.yaml').write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
            encoding='utf-8')
        print(f'证据目录：{output_root}')
    return return_code


if __name__ == '__main__':
    raise SystemExit(main())
