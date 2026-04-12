"""Tests for the live venue-state reconciliation cache."""

from bot.market import Market
from bot.venue_state import VenueStateCache, venue_state_allows_entry


def _market(interval_start: int = 1_700_000_000) -> Market:
    return Market(
        slug=f"btc-updown-5m-{interval_start}",
        condition_id="cond_1",
        up_token_id="up_token",
        down_token_id="down_token",
        interval_start=interval_start,
        price_to_beat=95_000.0,
    )


def test_fresh_balances_allow_entry():
    market = _market()
    cache = VenueStateCache()
    cache.update_balances(
        market=market,
        up_balance=0.0,
        down_balance=0.0,
        collateral_balance=100.0,
        refreshed_at_us=1_000_000,
    )
    allowed, reason = venue_state_allows_entry(
        cache.snapshot(),
        market=market,
        now_value_us=1_500_000,
    )
    assert allowed is True
    assert reason == ""


def test_ambiguous_dual_side_blocks_entry():
    market = _market()
    cache = VenueStateCache()
    cache.update_balances(
        market=market,
        up_balance=5.0,
        down_balance=2.0,
        collateral_balance=100.0,
        refreshed_at_us=1_000_000,
    )
    allowed, reason = venue_state_allows_entry(
        cache.snapshot(),
        market=market,
        now_value_us=1_500_000,
    )
    assert allowed is False
    assert "dual_side_inventory" in reason


def test_stale_but_unambiguous_still_allows_entry():
    market = _market()
    cache = VenueStateCache()
    cache.update_balances(
        market=market,
        up_balance=0.0,
        down_balance=0.0,
        collateral_balance=100.0,
        refreshed_at_us=1_000_000,
    )
    allowed, reason = venue_state_allows_entry(
        cache.snapshot(),
        market=market,
        now_value_us=10_000_000,
        token_max_age_us=500_000,
    )
    assert allowed is True
    assert reason == "venue_stale_unambiguous"


def test_apply_fill_updates_balances_and_marks_dual_side_inventory():
    market = _market()
    cache = VenueStateCache()
    cache.update_balances(
        market=market,
        up_balance=0.0,
        down_balance=0.0,
        collateral_balance=100.0,
        refreshed_at_us=1_000_000,
    )

    cache.apply_fill(
        market=market,
        side="UP",
        token_delta=10.0,
        collateral_delta=-5.0,
        refreshed_at_us=1_500_000,
    )
    snap = cache.snapshot()
    assert snap.up_balance == 10.0
    assert snap.down_balance == 0.0
    assert snap.collateral_balance == 95.0
    assert snap.ambiguous is False

    cache.apply_fill(
        market=market,
        side="DOWN",
        token_delta=4.0,
        collateral_delta=-2.0,
        refreshed_at_us=2_000_000,
    )
    snap = cache.snapshot()
    assert snap.up_balance == 10.0
    assert snap.down_balance == 4.0
    assert snap.collateral_balance == 93.0
    assert snap.ambiguous is True
    assert snap.ambiguity_reason == "dual_side_inventory"


def test_market_rotation_clears_prior_market_ambiguity():
    market_a = _market(1_700_000_000)
    market_b = _market(1_700_000_300)
    cache = VenueStateCache()
    cache.update_balances(
        market=market_a,
        up_balance=0.0,
        down_balance=0.0,
        collateral_balance=100.0,
        refreshed_at_us=1_000_000,
    )
    cache.mark_ambiguous("buy_timeout")

    cache.set_active_market(market_b)
    snap = cache.snapshot()
    assert snap.matches_market(market_b)
    assert snap.startup_ready is False
    assert snap.ambiguous is False
    assert snap.ambiguity_reason == ""

    allowed, reason = venue_state_allows_entry(
        snap,
        market=market_b,
        now_value_us=10_000_000,
        token_max_age_us=500_000,
    )
    assert allowed is False
    assert reason == "venue_startup_pending"
