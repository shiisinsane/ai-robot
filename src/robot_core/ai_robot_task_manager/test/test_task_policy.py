import math
from types import SimpleNamespace

from ai_robot_task_manager.task_policy import MapBounds, validate_goal


def goal(task_id='task-1', task_type=1, sensing_mode=1, frame='map',
         x=0.0, y=0.0, timeout=60.0, quaternion=(0.0, 0.0, 0.0, 1.0)):
    position = SimpleNamespace(x=x, y=y, z=0.0)
    orientation = SimpleNamespace(
        x=quaternion[0], y=quaternion[1], z=quaternion[2], w=quaternion[3])
    pose = SimpleNamespace(position=position, orientation=orientation)
    target = SimpleNamespace(header=SimpleNamespace(frame_id=frame), pose=pose)
    return SimpleNamespace(task_id=task_id, task_type=task_type,
                           sensing_mode=sensing_mode, target_pose=target,
                           task_timeout_sec=timeout)


def test_valid_goal_passes():
    assert validate_goal(goal(), 1, 1, MapBounds(-1, 1, -1, 1))[0] == 0


def test_invalid_id_and_unsupported_task_are_distinct():
    assert validate_goal(goal(task_id='bad id'), 1, 1)[0] == 100
    assert validate_goal(goal(task_type=9), 1, 1)[0] == 101


def test_target_frame_numeric_quaternion_and_bounds_are_checked():
    assert validate_goal(goal(frame='odom'), 1, 1)[0] == 102
    assert validate_goal(goal(x=math.nan), 1, 1)[0] == 102
    assert validate_goal(goal(quaternion=(0, 0, 0, 0)), 1, 1)[0] == 102
    assert validate_goal(goal(x=2), 1, 1, MapBounds(-1, 1, -1, 1))[0] == 102


def test_timeout_bounds_are_checked():
    assert validate_goal(goal(timeout=9.9), 1, 1)[0] == 102
    assert validate_goal(goal(timeout=300.1), 1, 1)[0] == 102
