"""Unit tests for the level formula (pure function, no DB needed)."""

from bot.engines.points import compute_level


def test_level_at_zero():
    assert compute_level(0) == 1


def test_level_at_thresholds():
    assert compute_level(99) == 1
    assert compute_level(100) == 2
    assert compute_level(399) == 2
    assert compute_level(400) == 3
    assert compute_level(899) == 3
    assert compute_level(900) == 4


def test_level_at_large_values():
    assert compute_level(10_000) == compute_level(100 * 99) + 1  # sqrt(100) + 1 = 11
    assert compute_level(10_000) == 11
    assert compute_level(1_000_000) == 101


def test_level_never_decreases():
    assert compute_level(500) >= compute_level(200)
    assert compute_level(0) == 1
    assert compute_level(10_000_000) > compute_level(0)
