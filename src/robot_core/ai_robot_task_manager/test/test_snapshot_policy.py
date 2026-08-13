import math
from types import SimpleNamespace

from ai_robot_task_manager.snapshot_policy import (
    classify_inputs, message_age, scan_metadata)


def message(stamp=9.5):
    seconds = int(stamp)
    header = SimpleNamespace(stamp=SimpleNamespace(
        sec=seconds, nanosec=int((stamp - seconds) * 1e9)))
    return SimpleNamespace(header=header)


def test_message_age_uses_ros_stamp():
    assert message_age(10.0, message(9.5)) == 0.5
    assert math.isinf(message_age(10.0, message(10.1)))


def test_inputs_distinguish_unavailable_and_stale():
    unavailable, stale = classify_inputs(
        {'scan': None, 'image': message(8.0), 'pose': message(9.5)}, 10.0, 1.0)
    assert unavailable == ['scan']
    assert stale == ['image']


def test_scan_metadata_ignores_invalid_ranges():
    scan = SimpleNamespace(
        ranges=[math.inf, 0.05, 0.4, 2.0, math.nan],
        range_min=0.1, range_max=1.0)
    count, minimum = scan_metadata(scan)
    assert count == 5
    assert minimum == 0.4
