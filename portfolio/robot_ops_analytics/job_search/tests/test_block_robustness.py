import random

import pytest

from portfolio.robot_ops_analytics.job_search.analysis.analyze_block_robustness import (
    block_bootstrap, by_block, exact_paired_randomization_p, validate_blocks,
)


def rows():
    result = []
    for block in range(1, 16):
        for profile, value in (("none", block), ("low", block + 2), ("medium", block + 4)):
            result.append({"validation_block": block, "obstacle_profile": profile,
                           "cycle_time_sec": float(value),
                           "max_abs_lateral_deviation_m": float(value) / 10})
    return result


def test_complete_blocks_are_required():
    incomplete = rows()[:-1]
    with pytest.raises(ValueError, match="完整三臂"):
        validate_blocks(incomplete)


def test_block_bootstrap_is_seeded_and_preserves_observed_effect():
    blocks = by_block(rows())
    first = block_bootstrap(blocks, "low", "cycle_time_sec", random.Random(7), 100)
    second = block_bootstrap(blocks, "low", "cycle_time_sec", random.Random(7), 100)
    assert first == second
    assert first["estimate_marginal_median_difference"] == 2
    assert first["paired_block_difference_median"] == 2


def test_exact_randomization_detects_uniform_paired_shift():
    blocks = by_block(rows())
    p_value = exact_paired_randomization_p(blocks, "medium", "cycle_time_sec")
    # 中位数统计量存在并列极端排列；精确枚举结果仍应明确拒绝零效应。
    assert p_value == pytest.approx(0.015625)
