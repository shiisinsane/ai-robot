#!/usr/bin/env python3
"""验证M6任务契约、状态机、错误码和Action定义的一致性。"""

import argparse
from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[1]


class TaskContractError(ValueError):
    """任务契约不满足冻结规则。"""


def require(condition, message):
    if not condition:
        raise TaskContractError(message)


def load(path):
    with path.open(encoding='utf-8') as stream:
        value = yaml.safe_load(stream)
    require(isinstance(value, dict), '任务契约顶层必须是映射')
    return value


def action_constants(path):
    constants = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'(?:uint8|uint16)\s+([A-Z0-9_]+)=(\d+)', line)
        if match:
            constants[match.group(1)] = int(match.group(2))
    return constants


def validate(contract, action_path):
    require(contract.get('contract_version') == 'm6.task.v1',
            '任务契约版本必须为m6.task.v1')
    require(contract.get('interface_version') == 'm1.v2',
            '公共接口版本必须为m1.v2')
    action = contract.get('action', {})
    require(action.get('name') == 'task/execute', '任务Action名称错误')
    require(action.get('type') ==
            'robot_interfaces/action/ExecuteRobotTask', '任务Action类型错误')
    require(action.get('single_active_goal') is True, '必须限制单活动任务')
    require(action.get('concurrent_goal_policy') == 'reject',
            '并发任务必须明确拒绝')

    states = contract.get('states', [])
    transitions = contract.get('transitions', {})
    require(set(states) == set(transitions), '每个状态必须定义迁移')
    terminals = {'succeeded', 'failed', 'canceled'}
    for state, targets in transitions.items():
        require(isinstance(targets, list), f'{state}迁移必须是列表')
        require(set(targets) <= set(states), f'{state}包含未知目标状态')
        if state in terminals:
            require(not targets, f'终态{state}不得继续迁移')
    require(transitions['accepted'] == ['validating', 'canceling', 'failed'],
            'accepted迁移未冻结')
    require('sensing' in transitions['navigating'], '导航成功后必须进入感知')

    codes = contract.get('error_codes', {})
    require(codes.get('none') == 0, '成功错误码必须为0')
    require(len(set(codes.values())) == len(codes), '错误码必须唯一')
    require(all(isinstance(value, int) and 0 <= value <= 65535
                for value in codes.values()), '错误码必须为uint16')
    constants = action_constants(action_path)
    for name, value in codes.items():
        require(constants.get(f'ERROR_{name.upper()}') == value,
                f'Action错误码与契约不一致：{name}')

    timeouts = contract.get('timeouts', {})
    require(timeouts.get('watchdog_clock') == 'steady',
            '任务看门狗必须使用稳态时钟')
    require(timeouts.get('stamped_data_clock') == 'ros',
            '数据新鲜度必须使用ROS时间戳')
    require(timeouts.get('cancel_propagation_sec', 0) > 0,
            '必须定义取消传播门限')
    require(contract.get('precedence', [None])[0] == 'safety_stop',
            '安全停车优先级必须最高')
    return [f'{len(states)}个状态及迁移有效',
            f'{len(codes)}个错误码与Action一致',
            '单任务、取消、时间与安全优先级规则有效']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contract', nargs='?', type=Path,
                        default=ROOT / 'config/common/m6_task_contract.yaml')
    parser.add_argument('--action', type=Path,
                        default=ROOT / 'src/robot_interfaces/action/ExecuteRobotTask.action')
    args = parser.parse_args()
    try:
        summary = validate(load(args.contract), args.action)
    except (OSError, yaml.YAMLError, TaskContractError) as error:
        print(f'M6任务契约检查失败：{error}')
        return 1
    print(f'M6任务契约检查通过：{args.contract}')
    for item in summary:
        print(f'- {item}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
