"""Durable live recovery helpers for ambiguous orders and settlement."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from concurrent.futures import Executor
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from typing import Any

import aiohttp
import sqlalchemy as sa

from bot.db import (
    ambiguous_orders_table,
    create_engine,
    create_tables,
    pending_settlements_table,
)
from bot.market import Market
from bot.trade_ledger import record_order
from bot.utils import now_us

logger = logging.getLogger(__name__)

FAST_AMBIGUITY_DELAYS_SEC = (0.25, 0.5, 1.0, 2.0)
AMBIGUOUS_RETRY_SEC = 5.0
SETTLEMENT_RETRY_SEC = 5.0
SETTLEMENT_SPOT_MAX_AGE_US = 10_000_000
BALANCE_DUST_THRESHOLD = 0.01
RECOVERY_POLL_SEC = 0.25
RECOVERY_BATCH_LIMIT = max(1, int(os.getenv("PM_RECOVERY_BATCH_LIMIT", "10")))
RECOVERY_CALL_CONCURRENCY = max(1, int(os.getenv("PM_RECOVERY_CALL_CONCURRENCY", "4")))
RECOVERY_INTER_ROW_DELAY_SEC = max(0.0, float(os.getenv("PM_RECOVERY_INTER_ROW_DELAY_SEC", "0.02")))
LONG_LIVED_INTERVAL_START = 0

GAMMA_API_URL = "https://gamma-api.polymarket.com"
GAMMA_RESOLUTION_TIMEOUT_SEC = 10

TERMINAL_AMBIGUOUS_STATES = {"filled", "not_filled", "manual_review"}
TERMINAL_SETTLEMENT_STATES = {"settled", "manual_review"}
NON_WORKING_ORDER_STATUSES = {
    "cancelled",
    "canceled",
    "rejected",
    "failed",
    "unmatched",
}


def _bot_variant() -> str:
    return os.getenv("BOT_VARIANT", "").strip()


def _bot_variant_clause(column):
    bot_variant = _bot_variant()
    if bot_variant:
        return column == bot_variant
    return column.is_(None)


def _order_snapshot_status(order_snapshot: Any) -> str:
    if order_snapshot is None:
        return ""
    if isinstance(order_snapshot, dict):
        return str(order_snapshot.get("status") or "").strip().lower()
    return str(getattr(order_snapshot, "status", "") or "").strip().lower()


def _expected_trade_side(phase: str) -> str:
    return "SELL" if str(phase).strip().lower() == "flip_sell" else "BUY"


def _to_dt(ts: float | None = None) -> datetime:
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc)


async def _run_blocking(executor: Executor | None, fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, partial(fn, *args, **kwargs))


def _normalize_db_url(database_url: str | None) -> str | None:
    if not database_url:
        return None
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def _parse_trade_timestamp_us(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        # Accept seconds, milliseconds, or microseconds.
        raw = float(value)
        if raw > 1e15:
            return int(raw)
        if raw > 1e12:
            return int(raw * 1_000)
        return int(raw * 1_000_000)
    text = str(value).strip()
    if not text:
        return 0
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return int(datetime.fromisoformat(text).timestamp() * 1_000_000)
    except ValueError:
        return 0


async def _check_gamma_resolution(market_slug: str) -> str | None:
    """Query Gamma API for market resolution. Returns 'UP' or 'DOWN', or None.

    Only returns a winner when exactly one outcome has price == 1.0,
    which is the definitive signal that Polymarket has resolved the market.
    Markets that are closed but not yet resolved (e.g. outcomePrices=["0","0"])
    return None so the settlement worker retries later.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{GAMMA_API_URL}/markets",
                params={"slug": market_slug},
                timeout=aiohttp.ClientTimeout(total=GAMMA_RESOLUTION_TIMEOUT_SEC),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data or not isinstance(data, list) or len(data) == 0:
                    return None
                market_data = data[0]
                if not market_data.get("closed", False):
                    return None
                raw_outcomes = market_data.get("outcomes", "[]")
                raw_prices = market_data.get("outcomePrices", "[]")
                outcomes = json.loads(raw_outcomes) if isinstance(raw_outcomes, str) else raw_outcomes
                prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
                if len(outcomes) >= 2 and len(prices) >= 2:
                    for i, p in enumerate(prices):
                        if float(p) == 1.0:
                            return outcomes[i].strip().upper()
                # No outcome at 1.0 — market is closed but not definitively
                # resolved yet (e.g. outcomePrices=["0","0"]).  Return None
                # so the settlement worker retries later.
                return None
    except Exception as exc:
        logger.debug("gamma_resolution_check_failed: %s %s", market_slug, exc)
    return None


@dataclass(frozen=True)
class ResolvedAmbiguousOrder:
    market_slug: str
    interval_start: int
    phase: str
    side: str
    token_id: str
    outcome: str
    filled_shares: float
    spent_usd: float
    received_usd: float
    fill_price: float
    row_id: int


@dataclass(frozen=True)
class ResolvedPositionContext:
    spent_usd: float
    filled_shares: float
    fill_price: float
    source: str


class LiveRecoveryCoordinator:
    """Persists unresolved live order state and settles completed intervals."""

    def __init__(self, database_url: str | None, *, background_executor: Executor | None = None) -> None:
        self._database_url = _normalize_db_url(database_url)
        self._background_executor = background_executor
        self._engine: sa.Engine | None = None
        if self._database_url:
            self._engine = create_engine(self._database_url)
            create_tables(self._engine)
        self._resolved_lock = threading.Lock()
        self._resolved_by_market: dict[tuple[str, int], list[ResolvedAmbiguousOrder]] = {}
        self._ambiguous_tasks: dict[int, asyncio.Task] = {}
        self._settlement_tasks: dict[int, asyncio.Task] = {}
        self._venue_call_semaphore: asyncio.Semaphore | None = None

    @property
    def enabled(self) -> bool:
        return self._engine is not None

    def _push_resolved(self, resolution: ResolvedAmbiguousOrder) -> None:
        key = (resolution.market_slug, resolution.interval_start)
        with self._resolved_lock:
            self._resolved_by_market.setdefault(key, []).append(resolution)

    def pop_market_resolutions(self, market_slug: str, interval_start: int) -> list[ResolvedAmbiguousOrder]:
        key = (market_slug, int(interval_start))
        with self._resolved_lock:
            return self._resolved_by_market.pop(key, [])

    def fetch_latest_ambiguous_buy_rows(
        self,
        *,
        interval_start: int | None = None,
    ) -> list[dict[str, Any]]:
        if self._engine is None:
            return []
        stmt = sa.select(ambiguous_orders_table).where(
            ambiguous_orders_table.c.phase == "buy",
            _bot_variant_clause(ambiguous_orders_table.c.bot_variant),
        ).order_by(ambiguous_orders_table.c.id.desc())
        if interval_start is not None:
            stmt = stmt.where(ambiguous_orders_table.c.interval_start == int(interval_start))
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        latest_by_slug: dict[str, dict[str, Any]] = {}
        for row in rows:
            mapped = dict(row)
            slug = str(mapped.get("market_slug") or "")
            if not slug or slug in latest_by_slug:
                continue
            latest_by_slug[slug] = mapped
        return list(latest_by_slug.values())

    def _with_conn(self):
        if self._engine is None:
            raise RuntimeError("LiveRecoveryCoordinator is disabled")
        return self._engine.begin()

    def create_pending_settlement(
        self,
        *,
        market_slug: str,
        interval_start: int,
        open_side: str,
        token_id: str,
        entry_spent_usd: float,
        entry_shares: float,
        open_notional_usd: float,
        strike: float,
        strike_source: str,
        flip_count: int,
        trade_count: int,
        ready_at_ts: float,
    ) -> int | None:
        if self._engine is None:
            return None
        ts = time.time()
        with self._with_conn() as conn:
            result = conn.execute(
                pending_settlements_table.insert().values(
                    market_slug=market_slug,
                    interval_start=int(interval_start),
                    open_side=open_side,
                    token_id=token_id,
                    entry_spent_usd=float(entry_spent_usd),
                    entry_shares=float(entry_shares),
                    open_notional_usd=float(open_notional_usd),
                    strike=float(strike),
                    strike_source=strike_source,
                    flip_count=int(flip_count),
                    trade_count=int(trade_count),
                    state="pending",
                    attempt_count=0,
                    ready_at_ts=float(ready_at_ts),
                    next_retry_at_ts=float(ready_at_ts),
                    bot_variant=_bot_variant() or None,
                    created_at=_to_dt(ts),
                    updated_at=_to_dt(ts),
                )
            )
            return int(result.inserted_primary_key[0])

    def restore_risk_controller(self, risk, *, now_value_us: int) -> None:
        if self._engine is None:
            return
        day_start = datetime.fromtimestamp(now_value_us / 1_000_000.0, tz=timezone.utc).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        with self._engine.connect() as conn:
            open_rows = conn.execute(
                sa.select(
                    pending_settlements_table.c.market_slug,
                    pending_settlements_table.c.open_notional_usd,
                ).where(
                    pending_settlements_table.c.state.not_in(tuple(TERMINAL_SETTLEMENT_STATES)),
                    _bot_variant_clause(pending_settlements_table.c.bot_variant),
                )
            ).all()
            settled_rows = conn.execute(
                sa.select(pending_settlements_table.c.pnl_usd).where(
                    pending_settlements_table.c.state == "settled",
                    pending_settlements_table.c.updated_at >= day_start,
                    _bot_variant_clause(pending_settlements_table.c.bot_variant),
                )
            ).all()
        risk.open_exposure_total_usd = 0.0
        risk.open_exposure_by_market = {}
        for market_slug, open_notional_usd in open_rows:
            notional = float(open_notional_usd or 0.0)
            if notional <= 0.0:
                continue
            risk.open_exposure_total_usd += notional
            risk.open_exposure_by_market[str(market_slug)] = (
                risk.open_exposure_by_market.get(str(market_slug), 0.0) + notional
            )
        risk.daily_realized_pnl_usd = sum(float(row[0] or 0.0) for row in settled_rows)
        logger.info(
            "risk_controller_restored",
            extra={
                "open_exposure_total_usd": risk.open_exposure_total_usd,
                "open_markets": len(risk.open_exposure_by_market),
                "daily_realized_pnl_usd": risk.daily_realized_pnl_usd,
            },
        )
        record_order(
            action="risk_restored",
            market_slug="",
            side="",
            token_id="",
            amount=risk.daily_realized_pnl_usd,
            open_exposure_total=risk.open_exposure_total_usd,
            open_markets=len(risk.open_exposure_by_market),
        )

    def create_ambiguous_order(
        self,
        *,
        market: Market,
        phase: str,
        side: str,
        token_id: str,
        requested_amount: float,
        reference_price: float | None,
        order_id: str = "",
        initial_error: str = "",
    ) -> int | None:
        if self._engine is None:
            return None
        ts = time.time()
        with self._with_conn() as conn:
            result = conn.execute(
                ambiguous_orders_table.insert().values(
                    market_slug=market.slug,
                    interval_start=int(market.interval_start),
                    phase=phase,
                    side=side,
                    token_id=token_id,
                    up_token_id=market.up_token_id,
                    down_token_id=market.down_token_id,
                    requested_amount=float(requested_amount),
                    reference_price=None if reference_price is None else float(reference_price),
                    order_id=order_id or None,
                    state="pending",
                    attempt_count=0,
                    fast_retries_done=0,
                    next_retry_at_ts=ts + FAST_AMBIGUITY_DELAYS_SEC[0],
                    last_error=initial_error or None,
                    bot_variant=_bot_variant() or None,
                    created_at_ts=ts,
                    created_at=_to_dt(ts),
                    updated_at=_to_dt(ts),
                )
            )
            return int(result.inserted_primary_key[0])

    def get_latest_resolved_context(
        self,
        *,
        market_slug: str,
        interval_start: int,
        token_id: str,
        side: str,
    ) -> ResolvedPositionContext | None:
        if self._engine is None:
            return None
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(
                    ambiguous_orders_table.c.resolved_spent_usd,
                    ambiguous_orders_table.c.resolved_filled_shares,
                    ambiguous_orders_table.c.resolved_fill_price,
                ).where(
                    ambiguous_orders_table.c.market_slug == market_slug,
                    ambiguous_orders_table.c.interval_start == int(interval_start),
                    ambiguous_orders_table.c.token_id == token_id,
                    ambiguous_orders_table.c.side == side,
                    ambiguous_orders_table.c.phase == "buy",
                    ambiguous_orders_table.c.state == "filled",
                    _bot_variant_clause(ambiguous_orders_table.c.bot_variant),
                ).order_by(ambiguous_orders_table.c.id.desc())
            ).first()
        if row is None:
            return None
        spent_usd = float(row[0] or 0.0)
        filled_shares = float(row[1] or 0.0)
        fill_price = float(row[2] or 0.0)
        if spent_usd <= 0.0 and filled_shares <= 0.0:
            return None
        return ResolvedPositionContext(
            spent_usd=spent_usd,
            filled_shares=filled_shares,
            fill_price=fill_price,
            source="ambiguous_order",
        )

    def _fetch_due_ambiguous_rows(self) -> list[dict[str, Any]]:
        if self._engine is None:
            return []
        now_ts = time.time()
        # Short-lived interval bots only need recent rows, but long-lived
        # strategies (interval_start == 0) must stay recoverable across restarts.
        cutoff_ts = now_ts - 600
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(ambiguous_orders_table).where(
                    ambiguous_orders_table.c.state.not_in(tuple(TERMINAL_AMBIGUOUS_STATES)),
                    ambiguous_orders_table.c.next_retry_at_ts <= now_ts,
                    _bot_variant_clause(ambiguous_orders_table.c.bot_variant),
                    sa.or_(
                        ambiguous_orders_table.c.interval_start == LONG_LIVED_INTERVAL_START,
                        ambiguous_orders_table.c.created_at >= _to_dt(cutoff_ts),
                    ),
                ).order_by(ambiguous_orders_table.c.next_retry_at_ts.asc())
            ).mappings().all()
        return [dict(row) for row in rows]

    def _fetch_due_settlement_rows(self) -> list[dict[str, Any]]:
        if self._engine is None:
            return []
        now_ts = time.time()
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(pending_settlements_table).where(
                    pending_settlements_table.c.state.not_in(tuple(TERMINAL_SETTLEMENT_STATES)),
                    pending_settlements_table.c.next_retry_at_ts <= now_ts,
                    _bot_variant_clause(pending_settlements_table.c.bot_variant),
                ).order_by(pending_settlements_table.c.next_retry_at_ts.asc())
            ).mappings().all()
        return [dict(row) for row in rows]

    def _update_ambiguous_row(self, row_id: int, **values: Any) -> None:
        if self._engine is None:
            return
        values["updated_at"] = _to_dt()
        with self._with_conn() as conn:
            conn.execute(
                ambiguous_orders_table.update()
                .where(ambiguous_orders_table.c.id == int(row_id))
                .values(**values)
            )

    def _update_settlement_row(self, row_id: int, **values: Any) -> None:
        if self._engine is None:
            return
        values["updated_at"] = _to_dt()
        with self._with_conn() as conn:
            conn.execute(
                pending_settlements_table.update()
                .where(pending_settlements_table.c.id == int(row_id))
                .values(**values)
            )

    async def schedule_fast_ambiguity_resolution(
        self,
        row_id: int | None,
        *,
        exchange,
        venue_state,
        background_executor: Executor | None,
    ) -> None:
        if row_id is None or self._engine is None:
            return
        if row_id in self._ambiguous_tasks:
            return
        task = asyncio.create_task(
            self._fast_resolve_loop(
                row_id,
                exchange=exchange,
                venue_state=venue_state,
                background_executor=background_executor,
            ),
            name=f"ambiguous-fast-{row_id}",
        )
        self._ambiguous_tasks[row_id] = task
        task.add_done_callback(lambda _: self._ambiguous_tasks.pop(row_id, None))

    async def _fast_resolve_loop(
        self,
        row_id: int,
        *,
        exchange,
        venue_state,
        background_executor: Executor | None,
    ) -> None:
        for delay in FAST_AMBIGUITY_DELAYS_SEC:
            await asyncio.sleep(delay)
            resolved = await self._process_ambiguous_row_id(
                row_id,
                exchange=exchange,
                venue_state=venue_state,
                background_executor=background_executor,
                fast_mode=True,
            )
            if resolved:
                return

    async def run_ambiguous_worker(
        self,
        *,
        exchange,
        venue_state,
        background_executor: Executor | None = None,
    ) -> None:
        if self._engine is None:
            while True:
                await asyncio.sleep(1.0)
        while True:
            try:
                rows = await _run_blocking(background_executor, self._fetch_due_ambiguous_rows)
                for row in rows[:RECOVERY_BATCH_LIMIT]:
                    row_id = int(row["id"])
                    if row_id in self._ambiguous_tasks:
                        continue
                    task = asyncio.create_task(
                        self._process_ambiguous_row(
                            row,
                            exchange=exchange,
                            venue_state=venue_state,
                            background_executor=background_executor,
                            fast_mode=False,
                        ),
                        name=f"ambiguous-worker-{row_id}",
                    )
                    self._ambiguous_tasks[row_id] = task
                    task.add_done_callback(lambda _, rid=row_id: self._ambiguous_tasks.pop(rid, None))
                    if RECOVERY_INTER_ROW_DELAY_SEC > 0.0:
                        await asyncio.sleep(RECOVERY_INTER_ROW_DELAY_SEC)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("ambiguous_worker_failed: %s", exc)
            await asyncio.sleep(RECOVERY_POLL_SEC)

    async def run_settlement_worker(
        self,
        *,
        exchange,
        risk,
        background_executor: Executor | None = None,
    ) -> None:
        if self._engine is None:
            while True:
                await asyncio.sleep(1.0)
        while True:
            try:
                rows = await _run_blocking(background_executor, self._fetch_due_settlement_rows)
                for row in rows:
                    row_id = int(row["id"])
                    if row_id in self._settlement_tasks:
                        continue
                    task = asyncio.create_task(
                        self._process_settlement_row(
                            row,
                            exchange=exchange,
                            risk=risk,
                            background_executor=background_executor,
                        ),
                        name=f"settlement-worker-{row_id}",
                    )
                    self._settlement_tasks[row_id] = task
                    task.add_done_callback(lambda _, rid=row_id: self._settlement_tasks.pop(rid, None))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("settlement_worker_failed: %s", exc)
            await asyncio.sleep(RECOVERY_POLL_SEC)

    async def _process_ambiguous_row_id(
        self,
        row_id: int,
        *,
        exchange,
        venue_state,
        background_executor: Executor | None,
        fast_mode: bool,
    ) -> bool:
        if self._engine is None:
            return False
        row = None
        with self._engine.connect() as conn:
            mapped = conn.execute(
                sa.select(ambiguous_orders_table).where(ambiguous_orders_table.c.id == int(row_id))
            ).mappings().first()
            if mapped is not None:
                row = dict(mapped)
        if row is None:
            return False
        return await self._process_ambiguous_row(
            row,
            exchange=exchange,
            venue_state=venue_state,
            background_executor=background_executor,
            fast_mode=fast_mode,
        )

    async def _process_ambiguous_row(
        self,
        row: dict[str, Any],
        *,
        exchange,
        venue_state,
        background_executor: Executor | None,
        fast_mode: bool,
    ) -> bool:
        row_id = int(row["id"])
        if row["state"] in TERMINAL_AMBIGUOUS_STATES:
            return True
        attempt_count = int(row["attempt_count"] or 0) + 1
        fast_retries_done = int(row["fast_retries_done"] or 0)
        await _run_blocking(
            background_executor,
            self._update_ambiguous_row,
            row_id,
            state="processing",
            attempt_count=attempt_count,
        )

        market = Market(
            slug=row["market_slug"],
            condition_id="",
            up_token_id=row.get("up_token_id") or "",
            down_token_id=row.get("down_token_id") or "",
            interval_start=int(row["interval_start"]),
        )
        target_side = str(row["side"] or "")
        target_token = str(row["token_id"] or "")
        expected_trade_side = _expected_trade_side(str(row["phase"] or ""))
        created_after_us = int(float(row.get("created_at_ts") or time.time()) * 1_000_000)

        try:
            if self._venue_call_semaphore is None:
                self._venue_call_semaphore = asyncio.Semaphore(RECOVERY_CALL_CONCURRENCY)
            async with self._venue_call_semaphore:
                up_task = _run_blocking(background_executor, exchange.get_conditional_balance, market.up_token_id)
                dn_task = _run_blocking(background_executor, exchange.get_conditional_balance, market.down_token_id)
                collateral_task = _run_blocking(background_executor, exchange.get_collateral_balance)
                trades_task = _run_blocking(background_executor, exchange.get_trades, target_token, None)
                order_task = None
                if row.get("order_id"):
                    order_task = _run_blocking(background_executor, exchange.get_order, row["order_id"])
                up_bal, dn_bal, collateral_balance, trades = await asyncio.gather(
                    up_task,
                    dn_task,
                    collateral_task,
                    trades_task,
                )
                order_snapshot = await order_task if order_task is not None else None
        except Exception as exc:
            await _run_blocking(
                background_executor,
                self._update_ambiguous_row,
                row_id,
                state="retry",
                next_retry_at_ts=time.time() + AMBIGUOUS_RETRY_SEC,
                last_error=str(exc),
            )
            return False

        if venue_state is not None:
            venue_state.update_balances(
                market=market,
                up_balance=float(up_bal),
                down_balance=float(dn_bal),
                collateral_balance=float(collateral_balance),
                refreshed_at_us=now_us(),
            )

        matching_trades = []
        for trade in trades or []:
            if trade.token_id != target_token:
                continue
            if trade.side.value != expected_trade_side:
                continue
            trade_ts_us = _parse_trade_timestamp_us(trade.timestamp)
            if trade_ts_us and trade_ts_us + 5_000_000 < created_after_us:
                continue
            matching_trades.append(trade)

        filled_shares = sum(float(trade.size) for trade in matching_trades)
        gross_value = sum(float(trade.price) * float(trade.size) for trade in matching_trades)
        avg_price = (gross_value / filled_shares) if filled_shares > 0 else 0.0
        token_balance = float(up_bal if target_side == "UP" else dn_bal)

        explicit_no_fill = False
        order_status = _order_snapshot_status(order_snapshot)
        if order_status:
            explicit_no_fill = order_status in NON_WORKING_ORDER_STATUSES

        resolved: ResolvedAmbiguousOrder | None = None
        if row["phase"] == "buy" and (filled_shares > BALANCE_DUST_THRESHOLD or token_balance > BALANCE_DUST_THRESHOLD):
            if filled_shares <= BALANCE_DUST_THRESHOLD:
                filled_shares = token_balance
                avg_price = float(row.get("reference_price") or 0.0)
                gross_value = float(row.get("requested_amount") or 0.0)
            outcome = "filled"
            spent_usd = gross_value if row["phase"] == "buy" else 0.0
            received_usd = gross_value if row["phase"] == "flip_sell" else 0.0
            if row["phase"] == "buy" and spent_usd <= 0.0:
                spent_usd = float(row.get("requested_amount") or 0.0)
            await _run_blocking(
                background_executor,
                self._update_ambiguous_row,
                row_id,
                state="filled",
                fast_retries_done=fast_retries_done + (1 if fast_mode else 0),
                resolved_filled_shares=filled_shares,
                resolved_spent_usd=spent_usd if row["phase"] == "buy" else None,
                resolved_received_usd=received_usd if row["phase"] == "flip_sell" else None,
                resolved_fill_price=avg_price or row.get("reference_price"),
                next_retry_at_ts=time.time(),
                last_error=None,
            )
            resolved = ResolvedAmbiguousOrder(
                market_slug=row["market_slug"],
                interval_start=int(row["interval_start"]),
                phase=str(row["phase"]),
                side=target_side,
                token_id=target_token,
                outcome=outcome,
                filled_shares=float(filled_shares),
                spent_usd=float(spent_usd),
                received_usd=float(received_usd),
                fill_price=float(avg_price or row.get("reference_price") or 0.0),
                row_id=row_id,
            )
        elif row["phase"] == "flip_sell" and (
            filled_shares > BALANCE_DUST_THRESHOLD
            or (float(row.get("requested_amount") or 0.0) - token_balance) > BALANCE_DUST_THRESHOLD
        ):
            requested_shares = max(0.0, float(row.get("requested_amount") or 0.0))
            if filled_shares <= BALANCE_DUST_THRESHOLD:
                filled_shares = max(0.0, requested_shares - token_balance)
                avg_price = float(row.get("reference_price") or 0.0)
                gross_value = filled_shares * avg_price
            await _run_blocking(
                background_executor,
                self._update_ambiguous_row,
                row_id,
                state="filled",
                fast_retries_done=fast_retries_done + (1 if fast_mode else 0),
                resolved_filled_shares=filled_shares,
                resolved_received_usd=gross_value,
                resolved_fill_price=avg_price or row.get("reference_price"),
                next_retry_at_ts=time.time(),
                last_error=None,
            )
            resolved = ResolvedAmbiguousOrder(
                market_slug=row["market_slug"],
                interval_start=int(row["interval_start"]),
                phase=str(row["phase"]),
                side=target_side,
                token_id=target_token,
                outcome="filled",
                filled_shares=float(filled_shares),
                spent_usd=0.0,
                received_usd=float(gross_value),
                fill_price=float(avg_price or row.get("reference_price") or 0.0),
                row_id=row_id,
            )
        elif explicit_no_fill or (
            fast_mode and fast_retries_done + 1 >= len(FAST_AMBIGUITY_DELAYS_SEC)
        ):
            await _run_blocking(
                background_executor,
                self._update_ambiguous_row,
                row_id,
                state="not_filled",
                fast_retries_done=fast_retries_done + (1 if fast_mode else 0),
                next_retry_at_ts=time.time(),
                last_error=None,
            )
            resolved = ResolvedAmbiguousOrder(
                market_slug=row["market_slug"],
                interval_start=int(row["interval_start"]),
                phase=str(row["phase"]),
                side=target_side,
                token_id=target_token,
                outcome="not_filled",
                filled_shares=0.0,
                spent_usd=0.0,
                received_usd=0.0,
                fill_price=0.0,
                row_id=row_id,
            )
        else:
            next_retry = time.time() + (
                FAST_AMBIGUITY_DELAYS_SEC[min(fast_retries_done, len(FAST_AMBIGUITY_DELAYS_SEC) - 1)]
                if fast_mode
                else AMBIGUOUS_RETRY_SEC
            )
            await _run_blocking(
                background_executor,
                self._update_ambiguous_row,
                row_id,
                state="retry",
                fast_retries_done=fast_retries_done + (1 if fast_mode else 0),
                next_retry_at_ts=next_retry,
                last_error=None,
            )
            return False

        if resolved is not None:
            if venue_state is not None and resolved.outcome != "filled":
                # Only clear quarantine immediately for not_filled resolutions.
                # For filled resolutions, keep the quarantine until the strategy
                # processes the resolution and updates open_side — otherwise a
                # new buy can fire before the position state is applied, causing
                # double exposure.
                venue_state.clear_ambiguous(market=market)
            self._push_resolved(resolved)
            record_order(
                action="ambiguity_resolved",
                market_slug=resolved.market_slug,
                side=resolved.side,
                token_id=resolved.token_id,
                amount=resolved.filled_shares or resolved.received_usd or 0.0,
                interval_start=resolved.interval_start,
                order_status=resolved.outcome,
                resolved_spent_usd=resolved.spent_usd,
                resolved_received_usd=resolved.received_usd,
                resolved_fill_price=resolved.fill_price,
            )
            return True
        return False

    async def _process_settlement_row(
        self,
        row: dict[str, Any],
        *,
        exchange,
        risk,
        background_executor: Executor | None,
    ) -> bool:
        row_id = int(row["id"])
        ready_at_ts = float(row["ready_at_ts"] or 0.0)
        if time.time() < ready_at_ts:
            return False
        attempt_count = int(row["attempt_count"] or 0) + 1
        await _run_blocking(
            background_executor,
            self._update_settlement_row,
            row_id,
            state="processing",
            attempt_count=attempt_count,
        )

        # Primary: Gamma API resolution (definitive, uses Polymarket's oracle)
        winner = await _check_gamma_resolution(row["market_slug"])

        if winner is None:
            await _run_blocking(
                background_executor,
                self._update_settlement_row,
                row_id,
                state="retry",
                next_retry_at_ts=time.time() + SETTLEMENT_RETRY_SEC,
                last_error="gamma_not_resolved",
            )
            return False

        open_side = str(row["open_side"] or "")
        entry_spent_usd = float(row["entry_spent_usd"] or 0.0)
        entry_shares = float(row["entry_shares"] or 0.0)
        open_notional_usd = float(row["open_notional_usd"] or 0.0)
        won = (winner == open_side)
        if won:
            pnl_usd = entry_shares - entry_spent_usd
            settle_status = "win_resolved"
        else:
            pnl_usd = -entry_spent_usd
            settle_status = "loss_resolved"

        risk.on_close_trade(
            market_slug=row["market_slug"],
            notional_usd=open_notional_usd,
            pnl_usd=pnl_usd,
            now_us=now_us(),
        )
        record_order(
            action="done",
            market_slug=row["market_slug"],
            side=open_side,
            token_id=str(row["token_id"] or ""),
            amount=pnl_usd,
            interval_start=int(row["interval_start"]),
            settle_status=settle_status,
            flip_count=int(row["flip_count"] or 0),
            entry_spent_usd=entry_spent_usd,
            entry_shares=entry_shares,
            open_notional_usd=open_notional_usd,
            resolution_source="gamma_api",
            resolution_winner=winner,
        )
        await _run_blocking(
            background_executor,
            self._update_settlement_row,
            row_id,
            state="settled",
            next_retry_at_ts=time.time(),
            settle_status=settle_status,
            pnl_usd=pnl_usd,
            last_error=None,
        )
        logger.info(
            "live_settlement_completed",
            extra={
                "market_slug": row["market_slug"],
                "interval_start": int(row["interval_start"]),
                "open_side": open_side,
                "winner": winner,
                "pnl_usd": pnl_usd,
                "settle_status": settle_status,
                "resolution_source": "gamma_api",
                "bot_variant": _bot_variant(),
            },
        )
        return True
