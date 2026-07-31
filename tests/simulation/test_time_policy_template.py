"""仿真场景模板：验证仿真与实体时间策略不会混用。"""

from scripts.check_interface_contract import load_contract
from tests.conftest import REPO_ROOT


CONTRACT_PATH = REPO_ROOT / "config/common/interface_contract.yaml"


def test_simulation_has_one_global_clock():
    time_rules = load_contract(CONTRACT_PATH)["time"]
    assert time_rules["sim"] == {
        "use_sim_time": True,
        "clock_topic": "/clock",
        "single_clock_authority": True,
        "clock_qos": {
            "history": "keep_last",
            "depth": 1,
            "reliability": "best_effort",
            "durability": "volatile",
        },
    }


def test_real_mode_does_not_use_simulation_clock():
    time_rules = load_contract(CONTRACT_PATH)["time"]
    assert time_rules["real"]["use_sim_time"] is False
    assert time_rules["watchdog_clock"] == "steady"
