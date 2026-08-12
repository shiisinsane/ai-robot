"""M6任务Action、状态机、错误码与时间规则契约测试。"""

from copy import deepcopy

import pytest

from scripts.check_m6_task_contract import TaskContractError, load, validate
from tests.conftest import REPO_ROOT


CONTRACT = REPO_ROOT / 'config/common/m6_task_contract.yaml'
ACTION = REPO_ROOT / 'src/robot_interfaces/action/ExecuteRobotTask.action'


def test_m6_task_contract_is_valid():
    validate(load(CONTRACT), ACTION)


def test_m6_task_contract_rejects_concurrent_execution():
    contract = load(CONTRACT)
    assert contract['action']['single_active_goal'] is True
    assert contract['action']['concurrent_goal_policy'] == 'reject'


def test_m6_task_contract_rejects_duplicate_error_codes():
    contract = deepcopy(load(CONTRACT))
    contract['error_codes']['busy'] = contract['error_codes']['invalid_target']
    with pytest.raises(TaskContractError, match='错误码必须唯一'):
        validate(contract, ACTION)


def test_m6_task_contract_prioritizes_safety_stop():
    contract = load(CONTRACT)
    assert contract['precedence'][0] == 'safety_stop'
    assert contract['result_invariants']['rejected_goal_has_no_motion'] is True
