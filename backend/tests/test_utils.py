"""Tests for bot.utils: interval math, taker fee, backoff."""

import time

from bot.utils import (
    backoff_sleep,
    current_interval_start,
    next_interval_start,
    polymarket_taker_fee,
    seconds_until_interval_end,
)


def test_current_interval_start_aligned():
    now = int(time.time())
    start = current_interval_start(300)
    assert now - start < 300
    assert start % 300 == 0


def test_current_interval_start_custom_interval():
    start = current_interval_start(60)
    assert start % 60 == 0


def test_next_interval_start_is_one_interval_ahead():
    current = current_interval_start(300)
    nxt = next_interval_start(300)
    assert nxt == current + 300


def test_seconds_until_interval_end_in_range():
    secs = seconds_until_interval_end(300)
    assert 0.0 < secs <= 300.0


def test_taker_fee_at_midpoint():
    fee = polymarket_taker_fee(0.50, 100.0)
    # q = 2*0.5*0.5 = 0.5, q^2 = 0.25, rate = 0.0624*0.25 = 0.0156
    assert abs(fee - 1.56) < 0.01


def test_taker_fee_at_extremes():
    assert polymarket_taker_fee(0.0, 100.0) == 0.0
    assert polymarket_taker_fee(1.0, 100.0) == 0.0


def test_taker_fee_symmetric():
    fee_30 = polymarket_taker_fee(0.30, 100.0)
    fee_70 = polymarket_taker_fee(0.70, 100.0)
    assert abs(fee_30 - fee_70) < 1e-10


def test_taker_fee_negative_price():
    assert polymarket_taker_fee(-0.1, 100.0) == 0.0


def test_backoff_sleep_adds_jitter():
    results = [backoff_sleep(10.0) for _ in range(50)]
    assert all(10.0 <= r <= 12.5 for r in results)
    # Should have some variance (not all identical)
    assert len(set(results)) > 1
