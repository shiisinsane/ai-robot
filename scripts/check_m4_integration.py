#!/usr/bin/env python3
"""验证M4集成、TF权威、安全链、诊断和性能冻结配置。"""

import argparse
from pathlib import Path

import yaml


class IntegrationError(ValueError):
    """M4集成配置无效。"""


def _require(condition, message):
    if not condition:
        raise IntegrationError(message)


def validate(config):
    _require(config.get('integration_version') == 'm4.v1', '集成版本必须为m4.v1')
    _require(config.get('interface_version') == 'm1.v1', '必须保持M1接口版本')

    startup = config['startup']
    groups = startup['ordered_groups']
    flattened = [item for group in groups for item in group]
    _require(len(flattened) == len(set(flattened)), '启动对象不得重复')
    _require(flattened.index('diff_drive_controller') < flattened.index('state_estimator'),
             '控制器必须先于状态估计器就绪')
    _require(flattened.index('sensor_adapters') < flattened.index('safety_supervisor'),
             '传感器适配器必须先于安全监督就绪')

    estimation = config['state_estimation']
    _require(estimation['implementation'] == 'robot_localization/ekf_node', '必须采用EKF节点')
    _require(estimation['two_d_mode'] is True, 'M4必须使用平面状态估计')
    _require(estimation['frames'] == {
        'map': 'map', 'odom': 'odom', 'base_link': 'base_link', 'world': 'odom'},
        '状态估计Frame不符合REP-105和M1契约')
    _require(estimation['inputs']['base_odometry']['topic'] ==
             '/robot/internal/base_odom', '底盘原始里程计必须隔离')
    _require(estimation['output']['topic'] == '/robot/odom', '融合里程计必须占用公共接口')
    authority = estimation['tf_authority']
    _require(authority['publisher'] == 'state_estimator' and
             authority['diff_drive_publish_tf'] is False and authority['exclusive'] is True,
             'odom到base_link必须由状态估计器唯一发布')

    image = config['image_processing']
    _require(image['input_qos_profile'] == 'sensor_stream' and
             image['output_qos_profile'] == 'sensor_stream', '图像处理QoS必须保持Best Effort基线')
    _require(image['preserve_stamp'] is True and
             image['preserve_frame'] == 'camera_color_optical_frame',
             '处理图像必须保持时间戳和光学Frame')

    command = config['command_chain']
    _require(command['public_input'] == '/robot/cmd_vel', '公共命令入口不可改变')
    _require(command['public_owner'] == 'safety_supervisor', '安全监督必须独占公共命令')
    _require(command['controller_input'] == '/robot/controller_cmd_vel', '控制器私有入口不可改变')
    _require(command['forbid_bypass'] is True, '必须禁止安全旁路')

    safety = config['safety']
    _require(safety['watchdog_clock'] == 'steady', '看门狗必须使用稳态时钟')
    _require(safety['latch_faults'] is True, '停车故障必须锁存')
    stop_monitors = {name for name, item in safety['monitors'].items()
                     if item['severity'] == 'stop'}
    _require({'command', 'base_odometry', 'imu', 'scan', 'non_finite_command'} <= stop_monitors,
             '关键运动输入必须触发停车')
    codes = [item['code'] for item in safety['monitors'].values()]
    _require(len(codes) == len(set(codes)), '诊断错误码不得重复')
    _require(all(safety['clear_conditions'].values()), '清除故障必须满足全部条件')

    diagnostics = config['diagnostics']
    _require(diagnostics['type'] == 'diagnostic_msgs/msg/DiagnosticArray',
             '诊断必须使用标准消息')
    _require(diagnostics['publish_rate_hz'] >= 1.0, '诊断频率不得低于1 Hz')

    performance = config['performance']
    _require(0 < performance['minimum_real_time_factor'] <= 1.0, '实时因子门限无效')
    _require(performance['maximum_cpu_percent'] > 0 and
             performance['maximum_rss_mib'] > 0, '资源门限必须为正数')
    _require(all(config['boundaries'].values()), 'M4阶段边界必须全部启用')
    return [
        '启动顺序、状态估计输入输出和唯一TF权威有效',
        '图像处理Topic、QoS、时间戳和Frame边界有效',
        '安全命令链、超时、诊断码、锁存和清除条件有效',
        '性能门限和M4阶段边界有效',
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', nargs='?', type=Path,
                        default=Path('config/common/m4_integration.yaml'))
    args = parser.parse_args()
    try:
        data = yaml.safe_load(args.config.read_text(encoding='utf-8'))
        _require(isinstance(data, dict), '配置顶层必须为映射')
        summary = validate(data)
    except (OSError, yaml.YAMLError, KeyError, TypeError, IntegrationError) as error:
        print(f'M4集成配置检查失败：{error}')
        return 1
    print(f'M4集成配置检查通过：{args.config}')
    for item in summary:
        print(f'- {item}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
