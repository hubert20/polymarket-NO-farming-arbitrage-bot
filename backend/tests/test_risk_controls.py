"""Tests for bot.risk_controls: exposure caps, kill switch, daily drawdown."""

from bot.risk_controls import RiskConfig, RiskController


def _make_controller(**overrides) -> RiskController:
    defaults = dict(
        max_total_open_exposure_usd=100.0,
        max_market_open_exposure_usd=50.0,
        kill_switch_cooldown_sec=900.0,
    )
    defaults.update(overrides)
    return RiskController(RiskConfig(**defaults))


def test_can_open_trade_allows_within_limits():
    rc = _make_controller()
    allowed, reason = rc.can_open_trade(1_000_000, "btc-5m-123", 10.0)
    assert allowed
    assert reason == ""


def test_can_open_trade_blocks_total_exposure():
    rc = _make_controller(max_total_open_exposure_usd=20.0)
    rc.on_open_trade("market-a", 15.0, 1_000_000)
    allowed, reason = rc.can_open_trade(2_000_000, "market-b", 10.0)
    assert not allowed
    assert reason == "max_total_open_exposure"


def test_can_open_trade_blocks_market_exposure():
    rc = _make_controller(max_market_open_exposure_usd=10.0)
    rc.on_open_trade("market-a", 8.0, 1_000_000)
    allowed, reason = rc.can_open_trade(2_000_000, "market-a", 5.0)
    assert not allowed
    assert reason == "max_market_open_exposure"


def test_on_close_trade_releases_exposure():
    rc = _make_controller(max_total_open_exposure_usd=20.0)
    rc.on_open_trade("market-a", 15.0, 1_000_000)
    rc.on_close_trade(market_slug="market-a", notional_usd=15.0, pnl_usd=1.0, now_us=2_000_000)
    allowed, _ = rc.can_open_trade(3_000_000, "market-a", 15.0)
    assert allowed


def test_on_close_trade_tracks_daily_pnl():
    rc = _make_controller()
    rc.on_close_trade(market_slug="m1", notional_usd=10.0, pnl_usd=2.5, now_us=1_000_000)
    rc.on_close_trade(market_slug="m2", notional_usd=10.0, pnl_usd=-1.0, now_us=2_000_000)
    assert rc.daily_realized_pnl_usd == 1.5


def test_day_roll_resets_daily_pnl():
    rc = _make_controller()
    # Day 1: some PnL
    day1_us = 1_710_000_000_000_000  # ~2024-03-09
    rc.on_close_trade(market_slug="m1", notional_usd=10.0, pnl_usd=5.0, now_us=day1_us)
    assert rc.daily_realized_pnl_usd == 5.0

    # Day 2: PnL should reset
    day2_us = day1_us + 86_400_000_000  # +1 day
    rc._roll_day_if_needed(day2_us)
    assert rc.daily_realized_pnl_usd == 0.0


def test_kill_switch_blocks_trading():
    rc = _make_controller(kill_switch_cooldown_sec=10.0)
    now = 1_000_000_000
    rc._activate_kill_switch(now, "test_reason")

    assert rc.kill_switch_active(now)
    assert rc.kill_switch_reason() == "test_reason"

    allowed, reason = rc.can_open_trade(now, "market", 5.0)
    assert not allowed
    assert "kill_switch_active" in reason


def test_kill_switch_expires_after_cooldown():
    rc = _make_controller(kill_switch_cooldown_sec=10.0)
    now = 1_000_000_000
    rc._activate_kill_switch(now, "test_reason")

    # After cooldown (10s = 10_000_000 us)
    assert not rc.kill_switch_active(now + 10_000_001)
    allowed, _ = rc.can_open_trade(now + 10_000_001, "market", 5.0)
    assert allowed


def test_snapshot_contains_expected_keys():
    rc = _make_controller()
    now = 1_000_000_000
    snap = rc.snapshot(now)
    assert "daily_realized_pnl_usd" in snap
    assert "open_exposure_total_usd" in snap
    assert "kill_switch_active" in snap
    assert "kill_switch_reason" in snap


def test_exposure_does_not_go_negative():
    rc = _make_controller()
    rc.on_open_trade("m1", 10.0, 1_000_000)
    # Close more than opened
    rc.on_close_trade(market_slug="m1", notional_usd=20.0, pnl_usd=0.0, now_us=2_000_000)
    assert rc.open_exposure_total_usd == 0.0
    assert rc.open_exposure_by_market.get("m1", 0.0) == 0.0


def test_balance_drawdown_disabled_by_default():
    """max_daily_drawdown_usd=0 means the check is a no-op."""
    rc = _make_controller(max_daily_drawdown_usd=0.0)
    now = 1_710_000_000_000_000
    rc.check_balance_drawdown(now, 50.0)  # balance dropped from ??? to 50
    assert not rc.kill_switch_active(now)


def test_balance_drawdown_sets_hwm_and_allows_trading():
    """First observation sets high-water mark. No drawdown yet → no kill."""
    rc = _make_controller(
        max_daily_drawdown_usd=50.0,
        drawdown_arm_after_sec=0.0,
        drawdown_min_fresh_observations=1,
    )
    now = 1_710_000_000_000_000
    rc.check_balance_drawdown(now, 200.0)
    assert not rc.kill_switch_active(now)
    assert rc._balance_hwm == 200.0

    # Balance goes up → HWM tracks up
    rc.check_balance_drawdown(now + 1000, 250.0)
    assert rc._balance_hwm == 250.0
    assert not rc.kill_switch_active(now + 1000)


def test_balance_drawdown_triggers_kill_switch():
    """Drawdown exceeding threshold activates kill switch."""
    rc = _make_controller(
        max_daily_drawdown_usd=50.0,
        kill_switch_cooldown_sec=900.0,
        drawdown_arm_after_sec=0.0,
        drawdown_min_fresh_observations=1,
    )
    now = 1_710_000_000_000_000

    # HWM established at 200
    rc.check_balance_drawdown(now, 200.0)

    # Drop to 140 → drawdown = 60 > threshold of 50
    rc.check_balance_drawdown(now + 1_000_000, 140.0)
    assert rc.kill_switch_active(now + 1_000_000)
    assert "daily_drawdown" in rc.kill_switch_reason()

    # Trading should be blocked
    allowed, reason = rc.can_open_trade(now + 1_000_000, "market", 5.0)
    assert not allowed
    assert "kill_switch_active" in reason


def test_balance_drawdown_resets_on_day_roll():
    """High-water mark resets at day boundary so prior-day losses don't persist."""
    rc = _make_controller(
        max_daily_drawdown_usd=50.0,
        kill_switch_cooldown_sec=1.0,
        drawdown_arm_after_sec=0.0,
        drawdown_min_fresh_observations=1,
    )
    day1_us = 1_710_000_000_000_000

    # Day 1: HWM 200, balance drops to 180 (drawdown 20, under threshold)
    rc.check_balance_drawdown(day1_us, 200.0)
    rc.check_balance_drawdown(day1_us + 1_000_000, 180.0)
    assert not rc.kill_switch_active(day1_us + 1_000_000)
    assert rc._balance_hwm == 200.0

    # Day 2: HWM should reset, new HWM = 180
    day2_us = day1_us + 86_400_000_000  # +1 day
    # Kill switch cooldown expired (1s)
    rc.check_balance_drawdown(day2_us, 180.0)
    assert rc._balance_hwm == 180.0
    # Drop to 170 → drawdown only 10, under 50 threshold
    rc.check_balance_drawdown(day2_us + 1_000_000, 170.0)
    assert not rc.kill_switch_active(day2_us + 1_000_000)


def test_multiple_markets_track_independently():
    rc = _make_controller(max_market_open_exposure_usd=20.0)
    rc.on_open_trade("m1", 15.0, 1_000_000)
    rc.on_open_trade("m2", 15.0, 1_000_000)

    # m1 is near limit, m2 is near limit, but they're independent
    allowed_m1, _ = rc.can_open_trade(2_000_000, "m1", 3.0)
    allowed_m2, _ = rc.can_open_trade(2_000_000, "m2", 3.0)
    assert allowed_m1
    assert allowed_m2

    # But total exposure blocks if global limit is tight
    rc3 = _make_controller(max_total_open_exposure_usd=35.0, max_market_open_exposure_usd=30.0)
    rc3.on_open_trade("m1", 15.0, 1_000_000)
    rc3.on_open_trade("m2", 15.0, 1_000_000)
    allowed, reason = rc3.can_open_trade(2_000_000, "m3", 10.0)
    assert not allowed
    assert reason == "max_total_open_exposure"


def test_balance_drawdown_waits_for_arm_conditions():
    rc = _make_controller(
        max_daily_drawdown_usd=50.0,
        drawdown_arm_after_sec=10.0,
        drawdown_min_fresh_observations=3,
    )
    now = 1_710_000_000_000_000

    rc.check_balance_drawdown(now, 200.0)
    rc.check_balance_drawdown(now + 1_000_000, 140.0)
    assert not rc.kill_switch_active(now + 1_000_000)
    assert rc._balance_hwm == 0.0

    rc.check_balance_drawdown(now + 11_000_000, 140.0)
    assert rc._balance_hwm == 140.0
    assert not rc.kill_switch_active(now + 11_000_000)


def test_balance_drawdown_does_not_advance_hwm_while_ambiguous():
    rc = _make_controller(
        max_daily_drawdown_usd=50.0,
        drawdown_arm_after_sec=0.0,
        drawdown_min_fresh_observations=1,
    )
    now = 1_710_000_000_000_000

    rc.check_balance_drawdown(now, 200.0)
    rc.check_balance_drawdown(now + 1_000_000, 250.0, ambiguous=True)

    assert rc._balance_hwm == 200.0
    assert not rc.kill_switch_active(now + 1_000_000)
