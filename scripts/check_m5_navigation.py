#!/usr/bin/env python3
"""验证M5导航接口、TF权威、生命周期、安全链和验收门限。"""

import argparse
from pathlib import Path

import yaml


class NavigationError(ValueError):
    """M5导航契约无效。"""


def _require(condition, message):
    if not condition:
        raise NavigationError(message)


def validate(config):
    _require(config.get('navigation_version') == 'm5.v1', '导航版本必须为m5.v1')
    _require(config.get('interface_version') == 'm1.v1', '必须保持M1接口版本')
    _require(config.get('input_baseline') == 'm4.accepted', '必须基于已验收M4')

    deps = config['dependencies']
    _require({'slam_toolbox', 'navigation2', 'nav2_bringup', 'nav2_msgs'} <= set(deps),
             '导航依赖不完整')
    _require(deps['slam_toolbox']['version'].startswith('2.6.10-'), 'SLAM版本未冻结')
    _require(all(deps[name]['version'].startswith('1.1.20-')
                 for name in ('navigation2', 'nav2_bringup', 'nav2_msgs')),
             'Nav2版本必须统一为1.1.20系列')

    frames = config['frames']
    _require(frames['required_chain'] == ['map', 'odom', 'base_link'],
             'TF主链必须为map到odom到base_link')
    tf = config['tf_authority']
    map_tf = tf['map_to_odom']
    _require(map_tf['exclusive'] and map_tf['simultaneous_owners_forbidden'],
             'map到odom必须为唯一权威')
    _require(map_tf['mapping_owner'] == 'slam_toolbox' and
             map_tf['localization_owner'] == 'amcl', 'map到odom模式权威无效')
    _require(tf['odom_to_base_link']['owner'] == 'state_estimator' and
             tf['odom_to_base_link']['exclusive'], 'M4状态估计器必须独占odom到base_link')
    modes = config['modes']
    _require(modes['mapping']['map_to_odom_owner'] == 'slam_toolbox' and
             'amcl' in modes['mapping']['disabled'], '建图模式不得同时启用AMCL')
    _require(modes['localization']['map_to_odom_owner'] == 'amcl' and
             'slam_toolbox' in modes['localization']['disabled'], '定位模式不得同时启用SLAM')

    interfaces = config['interfaces']
    expected_topics = {
        'scan': '/robot/scan', 'odom': '/robot/odom', 'map': '/robot/map',
        'initialpose': '/robot/initialpose', 'pose': '/robot/pose',
        'navigation_command': '/robot/cmd_vel'}
    _require(all(interfaces['topics'][key]['name'] == value
                 for key, value in expected_topics.items()), '公共Topic偏离M1契约')
    _require(interfaces['services']['save_map'] == {
        'name': '/robot/map/save_map', 'type': 'nav2_msgs/srv/SaveMap'},
        '地图保存Service偏离M1契约')
    _require(interfaces['actions']['navigate_to_pose']['name'] ==
             '/robot/navigation/navigate_to_pose', '单目标Action偏离M1契约')
    _require(interfaces['actions']['follow_waypoints']['name'] ==
             '/robot/navigation/follow_waypoints', '航点Action偏离M1契约')

    command = config['command_chain']
    _require(command['nav2_output'] == '/robot/cmd_vel' and
             command['safety_owner'] == 'safety_supervisor', 'Nav2必须进入公共安全入口')
    _require(command['controller_input'] == '/robot/controller_cmd_vel' and
             command['direct_controller_access_forbidden'], '必须禁止Nav2绕过安全监督器')

    lifecycle = config['lifecycle']
    flat = [node for group in lifecycle['ordered_groups'] for node in group]
    _require(len(flat) == len(set(flat)), '生命周期对象不得重复')
    _require(flat.index('safety_supervisor') < flat.index('map_provider') <
             flat.index('planner_server') < flat.index('bt_navigator'), '生命周期顺序无效')
    _require(lifecycle['autostart'] is False, '基线验证必须显式管理生命周期')

    geometry = config['geometry']
    _require(len(geometry['footprint_m']) >= 4, '必须冻结多边形足迹')
    _require(0 < geometry['maximum_linear_velocity_mps'] <= 0.6 and
             0 < geometry['maximum_angular_velocity_rps'] <= 1.5,
             '导航速度不得超过M2底盘限制')
    _require(config['costmaps']['obstacle_source'] == '/robot/scan',
             '代价地图必须使用冻结雷达Topic')

    acceptance = config['acceptance']
    _require(acceptance['repeated_goal_count'] >= 5 and
             acceptance['required_success_rate'] == 1.0, '重复导航门限不足')
    _require(0 < acceptance['maximum_position_error_m'] <= 0.15 and
             0 < acceptance['maximum_cancel_to_stop_sec'] <= 0.5,
             '精度或取消停车门限无效')
    _require(0 < acceptance['minimum_real_time_factor'] <= 1.0 and
             acceptance['maximum_cpu_percent'] > 0 and acceptance['maximum_rss_mib'] > 0,
             '性能门限无效')

    faults = config['fault_matrix']
    _require({'scan_timeout', 'odom_timeout', 'imu_timeout', 'localization_lost',
              'map_missing', 'unreachable_goal', 'obstacle_blocked'} <= set(faults),
             '故障矩阵不完整')
    _require(all(faults[name]['response'] == 'cancel_and_controlled_stop'
                 for name in ('scan_timeout', 'odom_timeout', 'imu_timeout',
                              'localization_lost')), '运动关键故障必须取消并停车')
    _require(all(config['boundaries'].values()), 'M5阶段边界必须全部启用')
    return [
        '依赖版本、公共Topic、Service和Action契约有效',
        '建图/定位模式互斥，TF主链和唯一权威有效',
        '生命周期顺序、足迹、速度和安全命令链有效',
        '验收门限、故障矩阵和阶段边界有效',
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', nargs='?', type=Path,
                        default=Path('config/common/m5_navigation.yaml'))
    args = parser.parse_args()
    try:
        data = yaml.safe_load(args.config.read_text(encoding='utf-8'))
        _require(isinstance(data, dict), '配置顶层必须为映射')
        summary = validate(data)
    except (OSError, yaml.YAMLError, KeyError, TypeError, NavigationError) as error:
        print(f'M5导航契约检查失败：{error}')
        return 1
    print(f'M5导航契约检查通过：{args.config}')
    for item in summary:
        print(f'- {item}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
