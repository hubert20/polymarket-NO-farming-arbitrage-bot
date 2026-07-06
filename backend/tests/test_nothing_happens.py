import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from bot.config import NothingHappensConfig
from bot.models import OrderBookLevel, OrderBookSnapshot
from bot.nothing_happens_control import NothingHappensControlState
from bot.portfolio_state import PositionSnapshot
from bot.risk_controls import RiskConfig, RiskController
from bot.standalone_markets import build_standalone_market
from bot.standalone_markets import filter_standalone_markets
from bot.standalone_markets import StandaloneMarket
from bot.standalone_markets import fetch_all_open_markets
from bot.standalone_markets import fetch_candidate_markets
from bot.strategy.nothing_happens import (
    NothingHappensRuntime,
    _fetch_open_positions,
    _max_notional_within_price,
)


_FUTURE_END_DT = (datetime.now(timezone.utc) + timedelta(days=30)).replace(microsecond=0)
_FUTURE_END_DATE = _FUTURE_END_DT.strftime("%Y-%m-%dT%H:%M:%SZ")
_FUTURE_END_TS = _FUTURE_END_DT.timestamp()


class StubExchange:
    def __init__(
        self,
        *,
        collateral_balance: float = 100.0,
        conditional_balance: float = 0.0,
        order_books: dict[str, OrderBookSnapshot] | None = None,
        place_market_order_result=None,
        place_market_order_error: Exception | None = None,
    ) -> None:
        self.collateral_balance = collateral_balance
        self.conditional_balance = conditional_balance
        self.order_books = order_books or {}
        self.place_market_order_result = place_market_order_result
        self.place_market_order_error = place_market_order_error
        self.market_orders = []
        self.warmed_tokens = []

    def get_collateral_balance(self) -> float:
        return self.collateral_balance

    def get_conditional_balance(self, token_id: str) -> float:
        return self.conditional_balance

    def get_order_book(self, token_id: str) -> OrderBookSnapshot:
        return self.order_books[token_id]

    def warm_token_cache(self, token_id: str) -> None:
        self.warmed_tokens.append(token_id)

    def place_market_order(self, intent):
        self.market_orders.append(intent)
        if self.place_market_order_error is not None:
            raise self.place_market_order_error
        if self.place_market_order_result is not None:
            return self.place_market_order_result
        return SimpleNamespace(
            status="matched",
            order_id="order-1",
            raw={
                "_fill_price": str(intent.reference_price),
                "makingAmount": str(intent.amount),
                "takingAmount": str(intent.amount / max(intent.reference_price, 0.01)),
            },
        )


class SequencedExchange(StubExchange):
    def __init__(self, *, order_steps: list, **kwargs) -> None:
        super().__init__(**kwargs)
        self._order_steps = list(order_steps)

    def place_market_order(self, intent):
        self.market_orders.append(intent)
        if not self._order_steps:
            return super().place_market_order(intent)
        step = self._order_steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class StubRecoveryCoordinator:
    def __init__(self) -> None:
        self.created = []
        self.scheduled = []
        self._resolutions = {}
        self.rows = []

    def create_ambiguous_order(self, **kwargs):
        self.created.append(kwargs)
        row_id = len(self.created)
        market = kwargs["market"]
        self.rows.append(
            {
                "id": row_id,
                "market_slug": market.slug,
                "interval_start": getattr(market, "interval_start", 0),
                "state": "pending",
                "requested_amount": kwargs.get("requested_amount", 0.0),
                "reference_price": kwargs.get("reference_price", 0.0),
                "order_id": kwargs.get("order_id", ""),
            }
        )
        return row_id

    async def schedule_fast_ambiguity_resolution(self, row_id, **kwargs) -> None:
        self.scheduled.append((row_id, kwargs))

    def pop_market_resolutions(self, market_slug: str, interval_start: int):
        return self._resolutions.pop((market_slug, interval_start), [])

    def fetch_latest_ambiguous_buy_rows(self, *, interval_start: int | None = None):
        rows = list(self.rows)
        if interval_start is None:
            return rows
        filtered = []
        for row in rows:
            value = row.get("interval_start")
            if value is None:
                continue
            if int(value) == int(interval_start):
                filtered.append(row)
        return filtered


def _make_market(*, slug: str = "will-it-rain") -> StandaloneMarket:
    return StandaloneMarket(
        question="Will it rain?",
        slug=slug,
        condition_id=f"cond-{slug}",
        yes_token_id=f"yes-{slug}",
        no_token_id=f"no-{slug}",
        yes_price=0.25,
        no_price=0.75,
        volume=1000.0,
        liquidity=1000.0,
        min_order_size=5.0,
        end_date=_FUTURE_END_DATE,
        end_ts=_FUTURE_END_TS,
        category="Weather",
        event_slug=slug,
    )


def _make_book(
    *,
    token_id: str,
    ask_price: float = 0.60,
    ask_size: float = 20.0,
    bid_price: float = 0.59,
    min_order_size: float = 1.0,
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        token_id=token_id,
        bids=(OrderBookLevel(price=bid_price, size=ask_size),),
        asks=(OrderBookLevel(price=ask_price, size=ask_size),),
        tick_size=0.01,
        min_order_size=min_order_size,
    )


def _make_runtime(
    *,
    wallet_address: str | None = None,
    exchange: StubExchange | None = None,
    cfg: NothingHappensConfig | None = None,
    control_state: NothingHappensControlState | None = None,
    recovery_coordinator=None,
) -> NothingHappensRuntime:
    return NothingHappensRuntime(
        exchange=exchange or StubExchange(),
        session=SimpleNamespace(),
        cfg=cfg or NothingHappensConfig(),
        risk=RiskController(
            RiskConfig(max_total_open_exposure_usd=1_000.0, max_market_open_exposure_usd=1_000.0)
        ),
        background_executor=None,
        shutdown_event=asyncio.Event(),
        portfolio_state=None,
        control_state=control_state,
        recovery_coordinator=recovery_coordinator,
        wallet_address=wallet_address,
    )


def test_build_standalone_market_maps_yes_and_no_tokens() -> None:
    market = build_standalone_market(
        {
            "question": "Will it rain?",
            "slug": "will-it-rain",
            "conditionId": "cond-1",
            "outcomes": '["Yes", "No"]',
            "clobTokenIds": '["yes-token", "no-token"]',
            "outcomePrices": "[0.31, 0.69]",
            "volume": "1234",
            "liquidity": "4321",
            "orderMinSize": "5",
            "endDate": _FUTURE_END_DATE,
        }
    )

    assert market is not None
    assert market.yes_token_id == "yes-token"
    assert market.no_token_id == "no-token"
    assert market.yes_price == 0.31
    assert market.no_price == 0.69


def test_filter_standalone_markets_excludes_nothing_ever_happens_titles() -> None:
    filtered = filter_standalone_markets(
        [
            {
                "question": "Nothing Ever Happens in Canada before June?",
                "slug": "nothing-ever-happens-canada",
                "conditionId": "cond-neh",
                "outcomes": '["Yes", "No"]',
                "clobTokenIds": '["yes-neh", "no-neh"]',
                "outcomePrices": "[0.10, 0.90]",
                "volume": "100",
                "liquidity": "100",
                "orderMinSize": "5",
                "endDate": _FUTURE_END_DATE,
            },
            {
                "question": "Will it rain?",
                "slug": "will-it-rain",
                "conditionId": "cond-rain",
                "outcomes": '["Yes", "No"]',
                "clobTokenIds": '["yes-rain", "no-rain"]',
                "outcomePrices": "[0.31, 0.69]",
                "volume": "1234",
                "liquidity": "4321",
                "orderMinSize": "5",
                "endDate": _FUTURE_END_DATE,
            },
        ]
    )

    assert [market["slug"] for market in filtered] == ["will-it-rain"]


class StubGammaResponse:
    def __init__(self, *, payload, status: int = 200, headers: dict | None = None) -> None:
        self._payload = payload
        self.status = status
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self) -> None:
        if self.status < 400:
            return
        raise aiohttp.ClientResponseError(
            request_info=SimpleNamespace(real_url="https://gamma-api.polymarket.com/markets"),
            history=(),
            status=self.status,
            message="Too Many Requests" if self.status == 429 else "HTTP error",
            headers=self.headers,
        )

    async def json(self):
        return self._payload


class StubGammaSession:
    def __init__(self, responses: list[StubGammaResponse]) -> None:
        self._responses = responses
        self.calls = 0

    def get(self, *args, **kwargs):
        response = self._responses[self.calls]
        self.calls += 1
        return response


def test_max_notional_within_price_only_counts_safe_asks() -> None:
    book = OrderBookSnapshot(
        token_id="token-1",
        bids=(),
        asks=(
            OrderBookLevel(price=0.60, size=10.0),
            OrderBookLevel(price=0.65, size=20.0),
            OrderBookLevel(price=0.66, size=30.0),
        ),
        tick_size=0.01,
        min_order_size=5.0,
    )

    assert _max_notional_within_price(book, 0.65) == 19.0


@pytest.mark.asyncio
async def test_sync_positions_preserves_existing_holdings_on_fetch_failure() -> None:
    runtime = _make_runtime(wallet_address="0xwallet")
    market = _make_market(slug="preserved-market")
    runtime._markets_by_slug[market.slug] = market
    runtime._positions_by_slug[market.slug] = PositionSnapshot(
        slug=market.slug,
        title=market.question,
        outcome="No",
        asset=market.no_token_id,
        condition_id=market.condition_id,
        size=20.0,
        avg_price=0.5,
        initial_value=10.0,
        current_price=0.55,
        current_value=11.0,
        pnl_usd=1.0,
        pnl_pct=10.0,
        end_date=market.end_date,
        eta_seconds=3600.0,
        source="data_api",
    )
    runtime._remote_positions_ready = True

    with patch(
        "bot.strategy.nothing_happens._fetch_open_positions",
        new=AsyncMock(side_effect=RuntimeError("positions unavailable")),
    ):
        await runtime._sync_positions()

    assert list(runtime._positions_by_slug) == [market.slug]
    assert runtime.risk.open_exposure_total_usd == pytest.approx(10.0)
    assert runtime.risk.open_exposure_by_market[market.slug] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_run_price_cycle_waits_for_initial_remote_position_sync() -> None:
    runtime = _make_runtime(wallet_address="0xwallet")
    market = _make_market(slug="wait-for-sync")
    runtime._markets_by_slug[market.slug] = market
    runtime._cash_balance = 100.0
    runtime._evaluate_market = AsyncMock()

    await runtime._run_price_cycle()

    runtime._evaluate_market.assert_not_awaited()


@pytest.mark.asyncio
async def test_recover_balance_fill_updates_cash_and_risk_immediately() -> None:
    runtime = _make_runtime(exchange=StubExchange(conditional_balance=20.0))
    runtime._cash_balance = 100.0
    market = _make_market(slug="recovered-fill")

    recovered = await runtime._recover_balance_fill(market, 10.0)

    assert recovered is True
    assert runtime._cash_balance == pytest.approx(90.0)
    assert runtime.risk.open_exposure_total_usd == pytest.approx(10.0)
    assert runtime.risk.open_exposure_by_market[market.slug] == pytest.approx(10.0)
    assert runtime._positions_by_slug[market.slug].initial_value == pytest.approx(10.0)
    assert runtime._positions_by_slug[market.slug].size == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_evaluate_market_queues_pending_buy_instead_of_buying_immediately() -> None:
    market = _make_market(slug="queued-buy")
    exchange = StubExchange(order_books={market.no_token_id: _make_book(token_id=market.no_token_id)})
    runtime = _make_runtime(
        exchange=exchange,
        cfg=NothingHappensConfig(fixed_trade_amount=5.0, buy_retry_count=1),
    )
    runtime._cash_balance = 100.0

    await runtime._evaluate_market(market)

    assert market.slug in runtime._pending_entries_by_slug
    assert exchange.market_orders == []


@pytest.mark.asyncio
async def test_evaluate_market_respects_live_target_capacity() -> None:
    control_state = NothingHappensControlState()
    control_state.set_target_open_positions(1)
    market_one = _make_market(slug="queued-limit-one")
    market_two = _make_market(slug="queued-limit-two")
    exchange = StubExchange(
        order_books={
            market_one.no_token_id: _make_book(token_id=market_one.no_token_id),
            market_two.no_token_id: _make_book(token_id=market_two.no_token_id),
        }
    )
    runtime = _make_runtime(
        exchange=exchange,
        cfg=NothingHappensConfig(fixed_trade_amount=5.0, buy_retry_count=1),
        control_state=control_state,
    )
    runtime._cash_balance = 100.0

    await runtime._evaluate_market(market_one)
    await runtime._evaluate_market(market_two)

    assert set(runtime._pending_entries_by_slug) == {market_one.slug}


@pytest.mark.asyncio
async def test_dispatch_next_pending_entry_submits_only_one_queued_order() -> None:
    market_one = _make_market(slug="queued-one")
    market_two = _make_market(slug="queued-two")
    exchange = StubExchange(
        order_books={
            market_one.no_token_id: _make_book(token_id=market_one.no_token_id),
            market_two.no_token_id: _make_book(token_id=market_two.no_token_id),
        }
    )
    runtime = _make_runtime(
        exchange=exchange,
        cfg=NothingHappensConfig(fixed_trade_amount=5.0, buy_retry_count=1),
    )
    runtime._cash_balance = 100.0
    runtime._enqueue_pending_entry(market_one)
    runtime._enqueue_pending_entry(market_two)

    attempted = await runtime._dispatch_next_pending_entry()

    assert attempted is True
    assert len(exchange.market_orders) == 1
    assert market_one.slug in runtime._positions_by_slug
    assert market_one.slug not in runtime._pending_entries_by_slug
    assert market_two.slug in runtime._pending_entries_by_slug


@pytest.mark.asyncio
async def test_dispatch_failed_order_requeues_pending_buy() -> None:
    market = _make_market(slug="retry-me")
    exchange = StubExchange(
        order_books={market.no_token_id: _make_book(token_id=market.no_token_id)},
        place_market_order_error=RuntimeError("couldn't be fully filled"),
    )
    runtime = _make_runtime(
        exchange=exchange,
        cfg=NothingHappensConfig(
            fixed_trade_amount=5.0,
            buy_retry_count=1,
            order_dispatch_interval_sec=60,
        ),
    )
    runtime._cash_balance = 100.0
    runtime._enqueue_pending_entry(market)

    attempted = await runtime._dispatch_next_pending_entry()

    assert attempted is True
    assert len(exchange.market_orders) == 1
    assert market.slug in runtime._pending_entries_by_slug
    pending = runtime._pending_entries_by_slug[market.slug]
    assert pending.dispatch_failures == 1
    assert pending.last_error == "order_attempt_failed"
    assert pending.next_attempt_monotonic > asyncio.get_running_loop().time()
    assert market.slug not in runtime._positions_by_slug
    assert runtime._cash_balance == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_dispatch_ambiguous_order_failure_quarantines_without_immediate_retry() -> None:
    market = _make_market(slug="ambiguous-retry")
    recovery = StubRecoveryCoordinator()
    exchange = SequencedExchange(
        order_books={market.no_token_id: _make_book(token_id=market.no_token_id)},
        order_steps=[RuntimeError("Request exception!")],
    )
    runtime = _make_runtime(
        exchange=exchange,
        cfg=NothingHappensConfig(
            fixed_trade_amount=5.0,
            buy_retry_count=3,
            order_dispatch_interval_sec=60,
            position_sync_interval_sec=60,
        ),
        recovery_coordinator=recovery,
    )
    runtime._cash_balance = 100.0
    runtime._enqueue_pending_entry(market)

    attempted = await runtime._dispatch_next_pending_entry()

    assert attempted is True
    assert len(exchange.market_orders) == 1
    assert market.slug in runtime._pending_entries_by_slug
    pending = runtime._pending_entries_by_slug[market.slug]
    assert pending.dispatch_failures == 1
    assert pending.last_error == "ambiguous_order_attempt_failed"
    assert pending.next_attempt_monotonic - asyncio.get_running_loop().time() >= 64.0
    assert market.slug not in runtime._positions_by_slug
    assert runtime._ambiguous_reserved_notional_by_slug[market.slug] == pytest.approx(5.0)
    assert runtime._available_cash_balance() == pytest.approx(95.0)
    assert len(recovery.created) == 1
    assert recovery.created[0]["market"].slug == market.slug
    assert recovery.created[0]["side"] == "DOWN"
    assert len(recovery.scheduled) == 1


@pytest.mark.asyncio
async def test_ambiguous_reservation_blocks_second_full_size_entry() -> None:
    market_one = _make_market(slug="ambiguous-one")
    market_two = _make_market(slug="ambiguous-two")
    recovery = StubRecoveryCoordinator()
    exchange = SequencedExchange(
        order_books={
            market_one.no_token_id: _make_book(token_id=market_one.no_token_id),
            market_two.no_token_id: _make_book(token_id=market_two.no_token_id),
        },
        order_steps=[
            RuntimeError("Request exception!"),
            SimpleNamespace(
                status="matched",
                order_id="order-2",
                raw={
                    "_fill_price": "0.5",
                    "makingAmount": "5.0",
                    "takingAmount": "10.0",
                },
            ),
        ],
    )
    runtime = _make_runtime(
        exchange=exchange,
        cfg=NothingHappensConfig(
            fixed_trade_amount=5.0,
            buy_retry_count=1,
            order_dispatch_interval_sec=60,
            position_sync_interval_sec=60,
        ),
        recovery_coordinator=recovery,
    )
    runtime._cash_balance = 5.0
    runtime._enqueue_pending_entry(market_one)
    runtime._enqueue_pending_entry(market_two)

    attempted_one = await runtime._dispatch_next_pending_entry()
    attempted_two = await runtime._dispatch_next_pending_entry()

    assert attempted_one is True
    assert attempted_two is False
    assert len(exchange.market_orders) == 1
    assert market_one.slug in runtime._recovery_blocked_slugs
    assert market_two.slug not in runtime._positions_by_slug
    assert runtime._available_cash_balance() == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_dispatch_clean_rejection_retries_within_attempt_loop() -> None:
    market = _make_market(slug="clean-rejection")
    exchange = SequencedExchange(
        order_books={market.no_token_id: _make_book(token_id=market.no_token_id)},
        order_steps=[
            RuntimeError("couldn't be fully filled"),
            RuntimeError("couldn't be fully filled"),
            RuntimeError("couldn't be fully filled"),
        ],
    )
    runtime = _make_runtime(
        exchange=exchange,
        cfg=NothingHappensConfig(
            fixed_trade_amount=5.0,
            buy_retry_count=3,
            order_dispatch_interval_sec=60,
        ),
    )
    runtime._cash_balance = 100.0
    runtime._enqueue_pending_entry(market)
    runtime._sleep_or_shutdown = AsyncMock()

    attempted = await runtime._dispatch_next_pending_entry()

    assert attempted is True
    assert len(exchange.market_orders) == 3
    pending = runtime._pending_entries_by_slug[market.slug]
    assert pending.last_error == "order_attempt_failed"


@pytest.mark.asyncio
async def test_success_without_fill_quantities_quarantines_instead_of_fabricating_position() -> None:
    market = _make_market(slug="missing-fill-data")
    recovery = StubRecoveryCoordinator()
    exchange = SequencedExchange(
        order_books={market.no_token_id: _make_book(token_id=market.no_token_id)},
        order_steps=[
            SimpleNamespace(
                status="matched",
                order_id="order-1",
                raw={"_fill_price": "0.5"},
            )
        ],
    )
    runtime = _make_runtime(
        exchange=exchange,
        cfg=NothingHappensConfig(
            fixed_trade_amount=5.0,
            buy_retry_count=1,
            order_dispatch_interval_sec=60,
            position_sync_interval_sec=60,
        ),
        recovery_coordinator=recovery,
    )
    runtime._cash_balance = 100.0
    runtime._enqueue_pending_entry(market)

    attempted = await runtime._dispatch_next_pending_entry()

    assert attempted is True
    assert market.slug not in runtime._positions_by_slug
    assert market.slug in runtime._pending_entries_by_slug
    assert runtime._ambiguous_reserved_notional_by_slug[market.slug] == pytest.approx(5.0)
    assert runtime._available_cash_balance() == pytest.approx(95.0)
    assert recovery.created[0]["order_id"] == "order-1"
    pending = runtime._pending_entries_by_slug[market.slug]
    assert pending.last_error == "ambiguous_fill_data_missing"


@pytest.mark.asyncio
async def test_fetch_open_positions_paginates_all_pages() -> None:
    first_page = [{"slug": f"market-{index}"} for index in range(100)]
    second_page = [{"slug": "market-100"}]
    session = StubGammaSession(
        [
            StubGammaResponse(payload=first_page, status=200),
            StubGammaResponse(payload=second_page, status=200),
        ]
    )

    positions = await _fetch_open_positions(session, "0xwallet")

    assert len(positions) == 101
    assert session.calls == 2


@pytest.mark.asyncio
async def test_fetch_open_positions_rejects_unexpected_success_payload() -> None:
    session = StubGammaSession([StubGammaResponse(payload={"unexpected": []}, status=200)])

    with pytest.raises(ValueError, match="missing data/positions"):
        await _fetch_open_positions(session, "0xwallet")


@pytest.mark.asyncio
async def test_refresh_markets_preserves_existing_universe_on_fetch_failure() -> None:
    runtime = _make_runtime()
    existing_market = _make_market(slug="existing-market")
    pending_market = _make_market(slug="pending-market")
    runtime._markets_by_slug = {
        existing_market.slug: existing_market,
        pending_market.slug: pending_market,
    }
    runtime._enqueue_pending_entry(pending_market)

    with patch("bot.strategy.nothing_happens.fetch_candidate_markets", new=AsyncMock(side_effect=RuntimeError("gamma failed"))):
        await runtime._refresh_markets()

    assert set(runtime._markets_by_slug) == {existing_market.slug, pending_market.slug}
    assert pending_market.slug in runtime._pending_entries_by_slug
    assert runtime._last_error.startswith("markets_refresh_failed:")


@pytest.mark.asyncio
async def test_refresh_recovery_state_restores_filled_row_without_pending_queue() -> None:
    market = _make_market(slug="restart-fill")
    recovery = StubRecoveryCoordinator()
    recovery.rows = [
        {
            "market_slug": market.slug,
            "interval_start": 0,
            "state": "filled",
            "resolved_filled_shares": 8.0,
            "resolved_spent_usd": 5.0,
            "resolved_fill_price": 0.625,
            "reference_price": 0.62,
        }
    ]
    runtime = _make_runtime(recovery_coordinator=recovery)
    runtime._markets_by_slug[market.slug] = market
    runtime._cash_balance = 100.0

    await runtime._refresh_recovery_state()

    assert market.slug in runtime._positions_by_slug
    assert runtime._positions_by_slug[market.slug].initial_value == pytest.approx(5.0)
    assert runtime.risk.open_exposure_by_market[market.slug] == pytest.approx(5.0)
    assert runtime._cash_balance == pytest.approx(100.0)
    assert runtime._available_cash_balance() == pytest.approx(95.0)
    assert market.slug not in runtime._recovery_blocked_slugs


@pytest.mark.asyncio
async def test_refresh_recovery_state_blocks_unresolved_slug_after_restart() -> None:
    market = _make_market(slug="restart-pending")
    recovery = StubRecoveryCoordinator()
    recovery.rows = [
        {
            "market_slug": market.slug,
            "interval_start": 0,
            "state": "retry",
        }
    ]
    runtime = _make_runtime(recovery_coordinator=recovery)
    runtime._markets_by_slug[market.slug] = market

    await runtime._refresh_recovery_state()

    assert market.slug in runtime._recovery_blocked_slugs
    assert runtime._remaining_queue_capacity() is None


@pytest.mark.asyncio
async def test_refresh_recovery_state_releases_reservation_after_not_filled_resolution() -> None:
    market = _make_market(slug="retry-cleared")
    recovery = StubRecoveryCoordinator()
    recovery.rows = [
        {
            "market_slug": market.slug,
            "interval_start": 0,
            "state": "not_filled",
            "requested_amount": 5.0,
        }
    ]
    runtime = _make_runtime(recovery_coordinator=recovery)
    runtime._cash_balance = 100.0
    runtime._ambiguous_reserved_notional_by_slug[market.slug] = 5.0

    await runtime._refresh_recovery_state()

    assert market.slug not in runtime._ambiguous_reserved_notional_by_slug
    assert runtime._available_cash_balance() == pytest.approx(100.0)


def test_initialize_target_defaults_to_existing_positions_plus_max_new_positions() -> None:
    control_state = NothingHappensControlState()
    runtime = _make_runtime(
        cfg=NothingHappensConfig(max_new_positions=5),
        control_state=control_state,
    )
    market = _make_market(slug="existing-one")
    runtime._positions_by_slug[market.slug] = PositionSnapshot(
        slug=market.slug,
        title=market.question,
        outcome="No",
        asset=market.no_token_id,
        condition_id=market.condition_id,
        size=10.0,
        avg_price=0.5,
        initial_value=5.0,
        current_price=0.5,
        current_value=5.0,
        pnl_usd=0.0,
        pnl_pct=0.0,
        end_date=market.end_date,
        eta_seconds=3600.0,
        source="data_api",
    )

    runtime._initialize_target_open_positions()

    assert control_state.snapshot().target_open_positions == 6


@pytest.mark.asyncio
async def test_sync_positions_recomputes_auto_target_after_initial_fetch_failure() -> None:
    control_state = NothingHappensControlState()
    runtime = _make_runtime(
        wallet_address="0xabc",
        cfg=NothingHappensConfig(max_new_positions=5),
        control_state=control_state,
    )
    fetched_positions = [
        {
            "slug": "existing-one",
            "outcome": "No",
            "asset": "asset-one",
            "conditionId": "cond-one",
            "size": 10.0,
            "avgPrice": 0.5,
            "initialValue": 5.0,
            "curPrice": 0.5,
            "currentValue": 5.0,
            "cashPnl": 0.0,
            "percentPnl": 0.0,
        },
        {
            "slug": "existing-two",
            "outcome": "No",
            "asset": "asset-two",
            "conditionId": "cond-two",
            "size": 10.0,
            "avgPrice": 0.5,
            "initialValue": 5.0,
            "curPrice": 0.5,
            "currentValue": 5.0,
            "cashPnl": 0.0,
            "percentPnl": 0.0,
        },
    ]

    with patch(
        "bot.strategy.nothing_happens._fetch_open_positions",
        new=AsyncMock(side_effect=[RuntimeError("boom"), fetched_positions]),
    ):
        await runtime._sync_positions()
        runtime._initialize_target_open_positions()
        assert control_state.snapshot().target_open_positions == 5

        await runtime._sync_positions()

    assert len(runtime._positions_by_slug) == 2
    assert control_state.snapshot().target_open_positions == 7


def test_initialize_target_preserves_manual_override_until_reset() -> None:
    control_state = NothingHappensControlState()
    runtime = _make_runtime(
        cfg=NothingHappensConfig(max_new_positions=5),
        control_state=control_state,
    )
    market = _make_market(slug="existing-one")
    runtime._positions_by_slug[market.slug] = PositionSnapshot(
        slug=market.slug,
        title=market.question,
        outcome="No",
        asset=market.no_token_id,
        condition_id=market.condition_id,
        size=10.0,
        avg_price=0.5,
        initial_value=5.0,
        current_price=0.5,
        current_value=5.0,
        pnl_usd=0.0,
        pnl_pct=0.0,
        end_date=market.end_date,
        eta_seconds=3600.0,
        source="data_api",
    )
    control_state.set_target_open_positions(9)

    runtime._initialize_target_open_positions()

    assert control_state.snapshot().target_open_positions == 9

    control_state.set_target_open_positions(None)
    runtime._initialize_target_open_positions()

    assert control_state.snapshot().target_open_positions == 6


def test_max_new_positions_remains_spent_after_position_leaves_book() -> None:
    runtime = _make_runtime(cfg=NothingHappensConfig(max_new_positions=2))

    runtime._record_local_fill(
        market=_make_market(slug="opened-one"),
        size=10.0,
        avg_price=0.5,
        initial_value=5.0,
        current_price=0.5,
        source="live_fill",
    )
    runtime._record_local_fill(
        market=_make_market(slug="opened-two"),
        size=10.0,
        avg_price=0.5,
        initial_value=5.0,
        current_price=0.5,
        source="live_fill",
    )

    runtime._positions_by_slug.pop("opened-one", None)
    runtime._local_positions.pop("opened-one", None)

    assert runtime._opened_position_count == 2
    assert runtime._remaining_queue_capacity() == 0
    assert runtime._position_target_reached() is True


def test_max_new_positions_zero_blocks_new_entries() -> None:
    runtime = _make_runtime(cfg=NothingHappensConfig(max_new_positions=0))

    assert runtime._current_target_open_positions() == 0
    assert runtime._remaining_queue_capacity() == 0
    assert runtime._position_target_reached() is True


def test_max_new_positions_negative_one_is_unbounded() -> None:
    runtime = _make_runtime(cfg=NothingHappensConfig(max_new_positions=-1))

    assert runtime._current_target_open_positions() is None
    assert runtime._remaining_queue_capacity() is None
    assert runtime._position_target_reached() is False


def test_target_notional_uses_fixed_trade_amount_when_configured() -> None:
    runtime = _make_runtime(
        cfg=NothingHappensConfig(
            cash_pct_per_trade=0.5,
            min_trade_amount=5.0,
            fixed_trade_amount=5.0,
        )
    )

    target_notional = runtime._target_notional(
        cash_balance=100.0,
        submitted_price=0.5,
        market_min_order_size=1.0,
        book_min_order_size=1.0,
    )

    assert target_notional == pytest.approx(5.0)


def test_target_notional_converts_share_minimums_to_usd() -> None:
    runtime = _make_runtime(
        cfg=NothingHappensConfig(
            cash_pct_per_trade=0.01,
            min_trade_amount=5.0,
            fixed_trade_amount=0.0,
        )
    )

    target_notional = runtime._target_notional(
        cash_balance=100.0,
        submitted_price=0.5,
        market_min_order_size=20.0,
        book_min_order_size=10.0,
    )

    assert target_notional == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_build_entry_plan_uses_submitted_price_for_share_minimums() -> None:
    market = _make_market(slug="share-minimum")
    exchange = StubExchange(
        order_books={
            market.no_token_id: _make_book(
                token_id=market.no_token_id,
                ask_price=0.50,
                ask_size=20.0,
                min_order_size=1.0,
            )
        }
    )
    runtime = _make_runtime(
        exchange=exchange,
        cfg=NothingHappensConfig(
            fixed_trade_amount=5.0,
            max_entry_price=0.65,
            allowed_slippage=0.30,
        ),
    )
    runtime._cash_balance = 100.0
    market = StandaloneMarket(
        question=market.question,
        slug=market.slug,
        condition_id=market.condition_id,
        yes_token_id=market.yes_token_id,
        no_token_id=market.no_token_id,
        yes_price=market.yes_price,
        no_price=market.no_price,
        volume=market.volume,
        liquidity=market.liquidity,
        min_order_size=10.0,
        end_date=market.end_date,
        end_ts=market.end_ts,
        category=market.category,
        event_slug=market.event_slug,
    )

    plan = await runtime._build_entry_plan(
        market,
        exchange.order_books[market.no_token_id],
        enforce_risk=False,
    )

    assert plan is not None
    assert plan.no_ask == pytest.approx(0.50)
    assert plan.target_notional == pytest.approx(6.5)


def test_record_local_fill_sets_shutdown_after_max_new_positions() -> None:
    shutdown_event = asyncio.Event()
    runtime = NothingHappensRuntime(
        exchange=StubExchange(),
        session=SimpleNamespace(),
        cfg=NothingHappensConfig(
            fixed_trade_amount=5.0,
            max_new_positions=2,
            shutdown_on_max_new_positions=True,
        ),
        risk=RiskController(
            RiskConfig(max_total_open_exposure_usd=1_000.0, max_market_open_exposure_usd=1_000.0)
        ),
        background_executor=None,
        shutdown_event=shutdown_event,
        portfolio_state=None,
        control_state=None,
        recovery_coordinator=None,
        wallet_address=None,
    )
    runtime._cash_balance = 20.0

    runtime._record_local_fill(
        market=_make_market(slug="smoke-one"),
        size=10.0,
        avg_price=0.5,
        initial_value=5.0,
        current_price=0.5,
        source="live_fill",
    )
    assert shutdown_event.is_set() is False

    runtime._record_local_fill(
        market=_make_market(slug="smoke-two"),
        size=10.0,
        avg_price=0.5,
        initial_value=5.0,
        current_price=0.5,
        source="live_fill",
    )

    assert runtime._opened_position_count == 2
    assert shutdown_event.is_set() is True


@pytest.mark.asyncio
async def test_fetch_all_open_markets_retries_rate_limited_page() -> None:
    session = StubGammaSession(
        [
            StubGammaResponse(payload=[], status=429, headers={"Retry-After": "3.5"}),
            StubGammaResponse(payload=[{"slug": "market-1"}], status=200),
        ]
    )

    with patch("bot.standalone_markets.asyncio.sleep", new=AsyncMock()) as sleep_mock:
        markets = await fetch_all_open_markets(session)

    assert markets == [{"slug": "market-1"}]
    assert session.calls == 2
    assert sleep_mock.await_count >= 1
    assert sleep_mock.await_args_list[0].args == (3.5,)


@pytest.mark.asyncio
async def test_fetch_candidate_markets_streams_batches_without_full_snapshot() -> None:
    batch = [
        {
            "question": "Duplicate event market one",
            "slug": "dup-one",
            "conditionId": "cond-dup-one",
            "events": [{"slug": "duplicate-event"}],
            "outcomes": '["Yes", "No"]',
            "clobTokenIds": '["yes-dup-one", "no-dup-one"]',
            "outcomePrices": "[0.10, 0.90]",
            "volume": "50",
            "liquidity": "50",
            "orderMinSize": "5",
            "endDate": _FUTURE_END_DATE,
        },
        {
            "question": "Duplicate event market two",
            "slug": "dup-two",
            "conditionId": "cond-dup-two",
            "events": [{"slug": "duplicate-event"}],
            "outcomes": '["Yes", "No"]',
            "clobTokenIds": '["yes-dup-two", "no-dup-two"]',
            "outcomePrices": "[0.10, 0.90]",
            "volume": "55",
            "liquidity": "55",
            "orderMinSize": "5",
            "endDate": _FUTURE_END_DATE,
        },
        {
            "question": "Will it rain?",
            "slug": "will-it-rain",
            "conditionId": "cond-rain",
            "events": [{"slug": "single-event"}],
            "outcomes": '["Yes", "No"]',
            "clobTokenIds": '["yes-rain", "no-rain"]',
            "outcomePrices": "[0.31, 0.69]",
            "volume": "1234",
            "liquidity": "4321",
            "orderMinSize": "5",
            "endDate": _FUTURE_END_DATE,
        },
    ]
    session = StubGammaSession([StubGammaResponse(payload=batch, status=200)])

    with patch("bot.standalone_markets.asyncio.sleep", new=AsyncMock()):
        markets = await fetch_candidate_markets(session)

    assert [market.slug for market in markets] == ["will-it-rain"]
    assert session.calls == 1
