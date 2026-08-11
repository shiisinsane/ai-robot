import math
from types import SimpleNamespace

import pytest

from scripts.check_m5_local_control import angle_error, yaw_from_quaternion


def test_yaw_from_planar_quaternion():
    yaw = 0.7
    quaternion = SimpleNamespace(x=0.0, y=0.0, z=math.sin(yaw / 2.0),
                                 w=math.cos(yaw / 2.0))
    assert yaw_from_quaternion(quaternion) == pytest.approx(yaw)


def test_angle_error_wraps_at_pi():
    assert angle_error(-math.pi + 0.1, math.pi - 0.1) == pytest.approx(0.2)
