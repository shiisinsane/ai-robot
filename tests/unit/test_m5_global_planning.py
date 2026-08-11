from types import SimpleNamespace

import pytest

from scripts.check_m5_global_planning import path_length


def pose(x, y):
    return SimpleNamespace(pose=SimpleNamespace(
        position=SimpleNamespace(x=x, y=y)))


def test_path_length_sums_planar_segments():
    path = SimpleNamespace(poses=[pose(0.0, 0.0), pose(3.0, 4.0), pose(3.0, 6.0)])
    assert path_length(path) == pytest.approx(7.0)


def test_path_length_is_zero_for_single_pose():
    assert path_length(SimpleNamespace(poses=[pose(0.0, 0.0)])) == 0.0
