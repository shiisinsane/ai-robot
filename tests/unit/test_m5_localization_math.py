import math

import pytest

from scripts.check_m5_localization import angle_error, relative_pose_error


def test_angle_error_wraps_at_pi():
    assert angle_error(-math.pi + 0.1, math.pi - 0.1) == pytest.approx(0.2)


def test_relative_pose_error_compares_motion_not_absolute_offset():
    amcl_start = (3.0, -2.0, 0.2)
    amcl_end = (4.0, -2.0, 0.7)
    odom_start = (0.0, 0.0, -0.1)
    odom_end = (1.0, 0.0, 0.4)
    assert relative_pose_error(amcl_start, amcl_end, odom_start, odom_end) == pytest.approx((0.0, 0.0))


def test_relative_pose_error_reports_translation_and_rotation_disagreement():
    error = relative_pose_error((0.0, 0.0, 0.0), (0.8, 0.0, 0.3),
                                (0.0, 0.0, 0.0), (1.0, 0.0, 0.5))
    assert error == pytest.approx((0.2, 0.2))
