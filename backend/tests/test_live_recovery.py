import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa

from bot.db import ambiguous_orders_table, pending_settlements_table
from bot.live_recovery import LiveRecoveryCoordinator
from bot.market import Market
from bot.models import OpenOrder, Side, Trade
from bot.risk_controls import RiskConfig, RiskController
from bot.utils import now_us
from bot.venue_state import VenueStateCache


def _make_market() -> Market:
    return Market(
        slug="btc-updown-5m-test",
        condition_id="cond",
        up_token_id="up_token",
        down_token_id="down_token",
        interval_start=1_770_000_000,
        price_to_beat=95_000.0,
        price_to_beat_source="test",
    )


def _make_nh_market() -> Market:
    return Market(
        slug="long-lived-nh-market",
        condition_id="cond",
        up_token_id="yes_token",
        down_token_id="no_token",
        interval_start=0,
        price_to_beat=0.0,
        price_to_beat_source="test",
    )


def _make_coordinator(tmp_path) -> LiveRecoveryCoordinator:
    return LiveRecoveryCoordinator(f"sqlite:///{tmp_path / 'live_recovery.sqlite'}")


def _make_risk() -> RiskController:
    return RiskController(
        RiskConfig(
            max_total_open_exposure_usd=1_000.0,
            max_market_open_exposure_usd=1_000.0,
        )
    )


@pytest.mark.asyncio
async def test_ambiguous_buy_resolution_records_fill_context_and_clears_ambiguity(tmp_path):
    market = _make_market()
    recovery = _make_coordinator(tmp_path)
    venue_state = VenueStateCache()
    venue_state.set_active_market(market)
    venue_state.mark_ambiguous("buy_timeout")

    exchange = MagicMock()
    exchange.get_conditional_balance = MagicMock(side_effect=lambda token_id: 10.0 if token_id == market.up_token_id else 0.0)
    exchange.get_collateral_balance = MagicMock(return_value=95.0)
    exchange.get_trades = MagicMock(
        return_value=[
            Trade(
                trade_id="t1",
                order_id="ord1",
                token_id=market.up_token_id,
                side=Side.BUY,
                price=0.5,
                size=10.0,
                timestamp=time.time(),
            )
        ]
    )
    exchange.get_order = MagicMock(
        return_value=OpenOrder(
            order_id="ord1",
            token_id=market.up_token_id,
            side=Side.BUY,
            price=0.5,
            status="matched",
        )
    )

    row_id = recovery.create_ambiguous_order(
        market=market,
        phase="buy",
        side="UP",
        token_id=market.up_token_id,
        requested_amount=5.0,
        reference_price=0.5,
        order_id="ord1",
        initial_error="buy_timeout",
    )

    with patch("bot.live_recovery.record_order"):
        resolved = await recovery._process_ambiguous_row_id(
            row_id,
            exchange=exchange,
            venue_state=venue_state,
            background_executor=None,
            fast_mode=True,
        )

    assert resolved is True
    snapshot = venue_state.snapshot()
    # Filled resolutions keep the quarantine until the strategy processes
    # the resolution and updates open_side (prevents double-entry race).
    assert snapshot.ambiguous is True
    assert snapshot.up_balance == pytest.approx(10.0)
    context = recovery.get_latest_resolved_context(
        market_slug=market.slug,
        interval_start=market.interval_start,
        token_id=market.up_token_id,
        side="UP",
    )
    assert context is not None
    assert context.spent_usd == pytest.approx(5.0)
    assert context.filled_shares == pytest.approx(10.0)
    resolutions = recovery.pop_market_resolutions(market.slug, market.interval_start)
    assert [r.outcome for r in resolutions] == ["filled"]


@pytest.mark.asyncio
async def test_ambiguous_buy_resolution_marks_not_filled_and_clears_market(tmp_path):
    market = _make_market()
    recovery = _make_coordinator(tmp_path)
    venue_state = VenueStateCache()
    venue_state.set_active_market(market)
    venue_state.mark_ambiguous("buy_timeout")

    exchange = MagicMock()
    exchange.get_conditional_balance = MagicMock(return_value=0.0)
    exchange.get_collateral_balance = MagicMock(return_value=100.0)
    exchange.get_trades = MagicMock(return_value=[])
    exchange.get_order = MagicMock(
        return_value=OpenOrder(
            order_id="ord1",
            token_id=market.up_token_id,
            side=Side.BUY,
            price=0.5,
            status="unmatched",
        )
    )

    row_id = recovery.create_ambiguous_order(
        market=market,
        phase="buy",
        side="UP",
        token_id=market.up_token_id,
        requested_amount=5.0,
        reference_price=0.5,
        order_id="ord1",
        initial_error="buy_timeout",
    )

    with patch("bot.live_recovery.record_order"):
        resolved = await recovery._process_ambiguous_row_id(
            row_id,
            exchange=exchange,
            venue_state=venue_state,
            background_executor=None,
            fast_mode=True,
        )

    assert resolved is True
    snapshot = venue_state.snapshot()
    assert snapshot.ambiguous is False
    resolutions = recovery.pop_market_resolutions(market.slug, market.interval_start)
    assert len(resolutions) == 1
    assert resolutions[0].outcome == "not_filled"
    assert recovery.get_latest_resolved_context(
        market_slug=market.slug,
        interval_start=market.interval_start,
        token_id=market.up_token_id,
        side="UP",
    ) is None


def test_fetch_due_ambiguous_rows_keeps_long_lived_interval_zero_rows(tmp_path):
    market = _make_nh_market()
    recovery = _make_coordinator(tmp_path)
    row_id = recovery.create_ambiguous_order(
        market=market,
        phase="buy",
        side="DOWN",
        token_id=market.down_token_id,
        requested_amount=5.0,
        reference_price=0.5,
        initial_error="buy_timeout",
    )
    assert row_id is not None

    stale_ts = time.time() - 7200
    with recovery._engine.begin() as conn:
        conn.execute(
            ambiguous_orders_table.update()
            .where(ambiguous_orders_table.c.id == int(row_id))
            .values(
                created_at=datetime.fromtimestamp(stale_ts, tz=timezone.utc),
                next_retry_at_ts=stale_ts,
            )
        )

    rows = recovery._fetch_due_ambiguous_rows()

    assert any(int(row["id"]) == int(row_id) for row in rows)


def test_fetch_latest_ambiguous_buy_rows_filters_by_bot_variant(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_VARIANT", "pm-nothing")
    market = _make_nh_market()
    recovery = _make_coordinator(tmp_path)
    own_row_id = recovery.create_ambiguous_order(
        market=market,
        phase="buy",
        side="DOWN",
        token_id=market.down_token_id,
        requested_amount=5.0,
        reference_price=0.5,
        initial_error="buy_timeout",
    )
    assert own_row_id is not None

    with recovery._engine.begin() as conn:
        conn.execute(
            ambiguous_orders_table.insert().values(
                market_slug="other-bot-market",
                interval_start=0,
                phase="buy",
                side="DOWN",
                token_id="other-token",
                up_token_id="other-up",
                down_token_id="other-down",
                requested_amount=5.0,
                reference_price=0.5,
                state="pending",
                attempt_count=0,
                fast_retries_done=0,
                next_retry_at_ts=time.time() - 1.0,
                last_error="buy_timeout",
                bot_variant="other-bot",
                created_at_ts=time.time() - 1.0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    rows = recovery.fetch_latest_ambiguous_buy_rows(interval_start=0)

    assert [str(row["market_slug"]) for row in rows] == [market.slug]


def test_fetch_due_ambiguous_rows_filters_by_bot_variant(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_VARIANT", "pm-nothing")
    market = _make_nh_market()
    recovery = _make_coordinator(tmp_path)
    own_row_id = recovery.create_ambiguous_order(
        market=market,
        phase="buy",
        side="DOWN",
        token_id=market.down_token_id,
        requested_amount=5.0,
        reference_price=0.5,
        initial_error="buy_timeout",
    )
    assert own_row_id is not None

    with recovery._engine.begin() as conn:
        conn.execute(
            ambiguous_orders_table.update()
            .where(ambiguous_orders_table.c.id == int(own_row_id))
            .values(next_retry_at_ts=time.time() - 1.0)
        )
        conn.execute(
            ambiguous_orders_table.insert().values(
                market_slug="other-bot-market",
                interval_start=0,
                phase="buy",
                side="DOWN",
                token_id="other-token",
                up_token_id="other-up",
                down_token_id="other-down",
                requested_amount=5.0,
                reference_price=0.5,
                state="pending",
                attempt_count=0,
                fast_retries_done=0,
                next_retry_at_ts=time.time() - 1.0,
                last_error="buy_timeout",
                bot_variant="other-bot",
                created_at_ts=time.time() - 1.0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    rows = recovery._fetch_due_ambiguous_rows()

    assert [str(row["market_slug"]) for row in rows] == [market.slug]


@pytest.mark.asyncio
async def test_pending_settlement_retries_without_gamma_then_releases_exposure(tmp_path):
    market = _make_market()
    recovery = _make_coordinator(tmp_path)
    risk = _make_risk()
    risk.on_open_trade(market.slug, 5.0, now_us())
    row_id = recovery.create_pending_settlement(
        market_slug=market.slug,
        interval_start=market.interval_start,
        open_side="UP",
        token_id=market.up_token_id,
        entry_spent_usd=5.0,
        entry_shares=10.0,
        open_notional_usd=5.0,
        strike=95_000.0,
        strike_source="test",
        flip_count=0,
        trade_count=1,
        ready_at_ts=0.0,
    )
    with recovery._engine.connect() as conn:
        row = dict(
            conn.execute(
                sa.select(pending_settlements_table).where(pending_settlements_table.c.id == row_id)
            ).mappings().first()
        )

    # Gamma returns None (not resolved yet) — should retry
    with patch("bot.live_recovery.record_order"), \
         patch("bot.live_recovery._check_gamma_resolution", return_value=None):
        settled = await recovery._process_settlement_row(
            row,
            exchange=MagicMock(),
            risk=risk,
            background_executor=None,
        )
    assert settled is False
    assert risk.open_exposure_total_usd == pytest.approx(5.0)

    with recovery._engine.connect() as conn:
        row = dict(
            conn.execute(
                sa.select(pending_settlements_table).where(pending_settlements_table.c.id == row_id)
            ).mappings().first()
        )

    # Gamma now returns "UP" — should settle as win
    async def mock_gamma_up(slug):
        return "UP"

    with patch("bot.live_recovery.record_order"), \
         patch("bot.live_recovery._check_gamma_resolution", side_effect=mock_gamma_up):
        settled = await recovery._process_settlement_row(
            row,
            exchange=MagicMock(),
            risk=risk,
            background_executor=None,
        )

    assert settled is True
    assert risk.open_exposure_total_usd == pytest.approx(0.0)
    assert risk.daily_realized_pnl_usd == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_pending_settlement_loss_resolved_via_gamma(tmp_path):
    market = _make_market()
    recovery = _make_coordinator(tmp_path)
    risk = _make_risk()
    risk.on_open_trade(market.slug, 5.0, now_us())
    row_id = recovery.create_pending_settlement(
        market_slug=market.slug,
        interval_start=market.interval_start,
        open_side="UP",
        token_id=market.up_token_id,
        entry_spent_usd=5.0,
        entry_shares=10.0,
        open_notional_usd=5.0,
        strike=95_000.0,
        strike_source="test",
        flip_count=0,
        trade_count=1,
        ready_at_ts=0.0,
    )
    with recovery._engine.connect() as conn:
        row = dict(
            conn.execute(
                sa.select(pending_settlements_table).where(pending_settlements_table.c.id == row_id)
            ).mappings().first()
        )

    # Gamma returns "DOWN" — our UP position loses
    async def mock_gamma_down(slug):
        return "DOWN"

    with patch("bot.live_recovery.record_order"), \
         patch("bot.live_recovery._check_gamma_resolution", side_effect=mock_gamma_down):
        settled = await recovery._process_settlement_row(
            row,
            exchange=MagicMock(),
            risk=risk,
            background_executor=None,
        )

    assert settled is True
    assert risk.open_exposure_total_usd == pytest.approx(0.0)
    assert risk.daily_realized_pnl_usd == pytest.approx(-5.0)


@pytest.mark.asyncio
async def test_gamma_resolution_rejects_unresolved_closed_market():
    """Closed markets with outcomePrices=["0","0"] must NOT be treated as resolved.
    This guards against booking PnL before Gamma has truly resolved the market."""
    from bot.live_recovery import _check_gamma_resolution
    from aiohttp import web

    async def _gamma_handler(request):
        return web.json_response([{
            "closed": True,
            "umaResolutionStatus": None,
            "outcomes": '["Up", "Down"]',
            "outcomePrices": '["0", "0"]',
        }])

    app = web.Application()
    app.router.add_get("/markets", _gamma_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    import bot.live_recovery as lr
    original_url = lr.GAMMA_API_URL
    lr.GAMMA_API_URL = f"http://127.0.0.1:{port}"
    try:
        result = await _check_gamma_resolution("some-slug")
        assert result is None, (
            f"Expected None for unresolved market (prices=['0','0']), got {result!r}"
        )
    finally:
        lr.GAMMA_API_URL = original_url
        await runner.cleanup()


@pytest.mark.asyncio
async def test_gamma_resolution_accepts_definitive_winner():
    """When one outcome has price 1.0, the market is definitively resolved."""
    from bot.live_recovery import _check_gamma_resolution
    from aiohttp import web

    async def _gamma_handler(request):
        return web.json_response([{
            "closed": True,
            "outcomes": '["Up", "Down"]',
            "outcomePrices": '["1", "0"]',
        }])

    app = web.Application()
    app.router.add_get("/markets", _gamma_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    import bot.live_recovery as lr
    original_url = lr.GAMMA_API_URL
    lr.GAMMA_API_URL = f"http://127.0.0.1:{port}"
    try:
        result = await _check_gamma_resolution("some-slug")
        assert result == "UP"
    finally:
        lr.GAMMA_API_URL = original_url
        await runner.cleanup()


def test_restore_risk_controller_loads_exposure_and_pnl(tmp_path):
    recovery = _make_coordinator(tmp_path)
    market = _make_market()
    risk = _make_risk()

    # Create an open (unsettled) position
    recovery.create_pending_settlement(
        market_slug=market.slug,
        interval_start=market.interval_start,
        open_side="UP",
        token_id=market.up_token_id,
        entry_spent_usd=5.0,
        entry_shares=10.0,
        open_notional_usd=5.0,
        strike=95_000.0,
        strike_source="test",
        flip_count=0,
        trade_count=1,
        ready_at_ts=time.time() + 300,
    )

    # Create a settled position with PnL
    import sqlalchemy as sa_local
    from bot.db import pending_settlements_table as pst
    from datetime import datetime, timezone
    with recovery._engine.begin() as conn:
        conn.execute(
            pst.insert().values(
                market_slug="settled-market",
                interval_start=market.interval_start - 300,
                open_side="DOWN",
                token_id=market.down_token_id,
                entry_spent_usd=5.0,
                entry_shares=10.0,
                open_notional_usd=5.0,
                strike=95_000.0,
                strike_source="test",
                flip_count=0,
                trade_count=1,
                state="settled",
                pnl_usd=3.50,
                attempt_count=1,
                ready_at_ts=time.time(),
                next_retry_at_ts=time.time(),
                created_at=datetime.now(tz=timezone.utc),
                updated_at=datetime.now(tz=timezone.utc),
            )
        )

    now_value_us = int(time.time() * 1_000_000)
    recovery.restore_risk_controller(risk, now_value_us=now_value_us)

    assert risk.open_exposure_total_usd == pytest.approx(5.0)
    assert risk.open_exposure_by_market[market.slug] == pytest.approx(5.0)
    assert risk.daily_realized_pnl_usd == pytest.approx(3.50)
