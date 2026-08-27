import random

from portfolio.robot_ops_analytics.pipelines.b1_v0_2.analyze_w6_b1 import (
    bootstrap_median_difference, fisher_two_sided, quantile, wilson,
)


def test_b1_statistical_helpers():
    assert quantile([1, 2, 3, 4], .5) == 2.5
    assert fisher_two_sided(0, 15, 0, 15) == 1.0
    interval = wilson(0, 15)
    assert interval[0] == 0.0
    assert 0.20 < interval[1] < 0.21


def test_b1_bootstrap_is_seeded_and_reports_observed_difference():
    first = bootstrap_median_difference([3, 4, 5], [1, 2, 3], random.Random(7), 100)
    second = bootstrap_median_difference([3, 4, 5], [1, 2, 3], random.Random(7), 100)
    assert first == second
    assert first["estimate"] == 2
