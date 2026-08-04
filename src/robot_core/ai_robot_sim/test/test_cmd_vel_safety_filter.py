import importlib.util
import math
from pathlib import Path

from geometry_msgs.msg import Twist


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'cmd_vel_safety_filter.py'
SPEC = importlib.util.spec_from_file_location('cmd_vel_safety_filter', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_accepts_finite_twist():
    message = Twist()
    message.linear.x = 100.0
    message.angular.z = -100.0
    assert MODULE.is_finite_twist(message)


def test_rejects_every_non_finite_twist_component():
    fields = (
        ('linear', 'x'), ('linear', 'y'), ('linear', 'z'),
        ('angular', 'x'), ('angular', 'y'), ('angular', 'z'),
    )
    for value in (math.nan, math.inf, -math.inf):
        for vector, component in fields:
            message = Twist()
            setattr(getattr(message, vector), component, value)
            assert not MODULE.is_finite_twist(message)
