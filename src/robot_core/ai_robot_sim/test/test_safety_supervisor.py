import math

from geometry_msgs.msg import Twist

from safety_supervisor import is_finite_twist, is_zero_twist


def test_zero_twist_is_finite_and_zero():
    message = Twist()
    assert is_finite_twist(message)
    assert is_zero_twist(message)


def test_motion_twist_is_not_zero():
    message = Twist()
    message.linear.x = 0.1
    assert is_finite_twist(message)
    assert not is_zero_twist(message)


def test_non_finite_component_is_rejected():
    message = Twist()
    message.angular.z = math.nan
    assert not is_finite_twist(message)
    assert not is_zero_twist(message)
