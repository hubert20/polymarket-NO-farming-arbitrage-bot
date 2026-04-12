"""Background venue-state reconciliation cache for live market positions."""

from __future__ import annotations

import asyncio
import time
from asyncio import AbstractEventLoop, Event
from concurrent.futures import Executor
from dataclasses import dataclass
from functools import partial
from threading import Lock

from bot.latency import log_latency_event, monotonic_us
from bot.utils import current_interval_start, next_interval_start, now_us

BALANCE_DUST_THRESHOLD = 0.01
DEFAULT_TOKEN_MAX_AGE_US = 2_000_000
DEFAULT_COLLATERAL_MAX_AGE_US = 5_000_000


async def _run_blocking(executor: Executor | None, fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, partial(fn, *args))


@dataclass(frozen=True)
class VenueStateSnapshot:
    market_slug: str = ""
    interval_start: int = 0
    up_token_id: str = ""
    down_token_id: str = ""
    up_balance: float = 0.0
    down_balance: float = 0.0
    collateral_balance: float | None = None
    token_refreshed_at_us: int = 0
    collateral_refreshed_at_us: int = 0
    startup_ready: bool = False
    ambiguous: bool = True
    ambiguity_reason: str = "startup_pending"
    version: int = 0

    def matches_market(self, market) -> bool:
        return (
            market is not None
            and self.market_slug == market.slug
            and self.interval_start == int(market.interval_start)
            and self.up_token_id == market.up_token_id
            and self.down_token_id == market.down_token_id
        )

    def token_age_us(self, now_value_us: int) -> int:
        if self.token_refreshed_at_us <= 0:
            return 10**18
        return max(0, int(now_value_us) - int(self.token_refreshed_at_us))

    def collateral_age_us(self, now_value_us: int) -> int:
        if self.collateral_refreshed_at_us <= 0:
            return 10**18
        return max(0, int(now_value_us) - int(self.collateral_refreshed_at_us))


class VenueStateCache:
    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot = VenueStateSnapshot()
        self._notifiers: list[tuple[Event, AbstractEventLoop]] = []

    def _notify(self) -> None:
        for event, loop in list(self._notifiers):
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                continue

    def register_notifier(self, event: Event, loop: AbstractEventLoop) -> None:
        with self._lock:
            self._notifiers.append((event, loop))

    def unregister_notifier(self, event: Event) -> None:
        with self._lock:
            self._notifiers = [(ev, loop) for ev, loop in self._notifiers if ev is not event]

    def snapshot(self) -> VenueStateSnapshot:
        with self._lock:
            return self._snapshot

    def version(self) -> int:
        with self._lock:
            return self._snapshot.version

    def set_active_market(self, market) -> None:
        if market is None:
            return
        with self._lock:
            current = self._snapshot
            if current.matches_market(market):
                return
            self._snapshot = VenueStateSnapshot(
                market_slug=market.slug,
                interval_start=int(market.interval_start),
                up_token_id=market.up_token_id,
                down_token_id=market.down_token_id,
                collateral_balance=current.collateral_balance,
                collateral_refreshed_at_us=current.collateral_refreshed_at_us,
                startup_ready=False,
                ambiguous=False,
                ambiguity_reason="",
                version=current.version + 1,
            )
        self._notify()

    def mark_ambiguous(self, reason: str) -> None:
        with self._lock:
            current = self._snapshot
            self._snapshot = VenueStateSnapshot(
                market_slug=current.market_slug,
                interval_start=current.interval_start,
                up_token_id=current.up_token_id,
                down_token_id=current.down_token_id,
                up_balance=current.up_balance,
                down_balance=current.down_balance,
                collateral_balance=current.collateral_balance,
                token_refreshed_at_us=current.token_refreshed_at_us,
                collateral_refreshed_at_us=current.collateral_refreshed_at_us,
                startup_ready=current.startup_ready,
                ambiguous=True,
                ambiguity_reason=reason,
                version=current.version + 1,
            )
        self._notify()

    def clear_ambiguous(self, *, market=None) -> None:
        with self._lock:
            current = self._snapshot
            if market is not None and not current.matches_market(market):
                return
            dual_side = (
                current.up_balance > BALANCE_DUST_THRESHOLD
                and current.down_balance > BALANCE_DUST_THRESHOLD
            )
            ambiguity_reason = "dual_side_inventory" if dual_side else ""
            self._snapshot = VenueStateSnapshot(
                market_slug=current.market_slug,
                interval_start=current.interval_start,
                up_token_id=current.up_token_id,
                down_token_id=current.down_token_id,
                up_balance=current.up_balance,
                down_balance=current.down_balance,
                collateral_balance=current.collateral_balance,
                token_refreshed_at_us=current.token_refreshed_at_us,
                collateral_refreshed_at_us=current.collateral_refreshed_at_us,
                startup_ready=current.startup_ready,
                ambiguous=dual_side,
                ambiguity_reason=ambiguity_reason,
                version=current.version + 1,
            )
        self._notify()

    def update_balances(
        self,
        *,
        market,
        up_balance: float,
        down_balance: float,
        collateral_balance: float | None,
        refreshed_at_us: int,
    ) -> None:
        with self._lock:
            current = self._snapshot
            ambiguous = current.ambiguous
            ambiguity_reason = current.ambiguity_reason
            if up_balance > BALANCE_DUST_THRESHOLD and down_balance > BALANCE_DUST_THRESHOLD:
                ambiguous = True
                ambiguity_reason = "dual_side_inventory"
            elif ambiguity_reason in {"dual_side_inventory", "startup_pending"}:
                ambiguous = False
                ambiguity_reason = ""
            self._snapshot = VenueStateSnapshot(
                market_slug=market.slug,
                interval_start=int(market.interval_start),
                up_token_id=market.up_token_id,
                down_token_id=market.down_token_id,
                up_balance=float(up_balance),
                down_balance=float(down_balance),
                collateral_balance=None if collateral_balance is None else float(collateral_balance),
                token_refreshed_at_us=int(refreshed_at_us),
                collateral_refreshed_at_us=(
                    current.collateral_refreshed_at_us
                    if collateral_balance is None
                    else int(refreshed_at_us)
                ),
                startup_ready=True,
                ambiguous=ambiguous,
                ambiguity_reason=ambiguity_reason,
                version=current.version + 1,
            )
        self._notify()

    def update_collateral(self, collateral_balance: float, refreshed_at_us: int) -> None:
        with self._lock:
            current = self._snapshot
            self._snapshot = VenueStateSnapshot(
                market_slug=current.market_slug,
                interval_start=current.interval_start,
                up_token_id=current.up_token_id,
                down_token_id=current.down_token_id,
                up_balance=current.up_balance,
                down_balance=current.down_balance,
                collateral_balance=float(collateral_balance),
                token_refreshed_at_us=current.token_refreshed_at_us,
                collateral_refreshed_at_us=int(refreshed_at_us),
                startup_ready=current.startup_ready,
                ambiguous=current.ambiguous,
                ambiguity_reason=current.ambiguity_reason,
                version=current.version + 1,
            )
        self._notify()

    def apply_fill(
        self,
        *,
        market,
        side: str,
        token_delta: float = 0.0,
        collateral_delta: float = 0.0,
        refreshed_at_us: int,
    ) -> None:
        with self._lock:
            current = self._snapshot
            if current.matches_market(market):
                up_balance = current.up_balance
                down_balance = current.down_balance
                collateral_balance = current.collateral_balance
                startup_ready = current.startup_ready
                ambiguous = current.ambiguous
                ambiguity_reason = current.ambiguity_reason
                version = current.version
            else:
                up_balance = 0.0
                down_balance = 0.0
                collateral_balance = current.collateral_balance
                startup_ready = current.startup_ready
                ambiguous = current.ambiguous
                ambiguity_reason = current.ambiguity_reason
                version = current.version

            if side == "UP":
                up_balance = max(0.0, float(up_balance) + float(token_delta))
            elif side == "DOWN":
                down_balance = max(0.0, float(down_balance) + float(token_delta))

            if collateral_balance is not None:
                collateral_balance = max(0.0, float(collateral_balance) + float(collateral_delta))

            dual_side = (
                up_balance > BALANCE_DUST_THRESHOLD and down_balance > BALANCE_DUST_THRESHOLD
            )
            if dual_side:
                ambiguous = True
                ambiguity_reason = "dual_side_inventory"
            elif ambiguity_reason == "dual_side_inventory":
                ambiguous = False
                ambiguity_reason = ""

            self._snapshot = VenueStateSnapshot(
                market_slug=market.slug,
                interval_start=int(market.interval_start),
                up_token_id=market.up_token_id,
                down_token_id=market.down_token_id,
                up_balance=up_balance,
                down_balance=down_balance,
                collateral_balance=collateral_balance,
                token_refreshed_at_us=int(refreshed_at_us),
                collateral_refreshed_at_us=(
                    current.collateral_refreshed_at_us
                    if collateral_balance is None
                    else int(refreshed_at_us)
                ),
                startup_ready=startup_ready,
                ambiguous=ambiguous,
                ambiguity_reason=ambiguity_reason,
                version=version + 1,
            )
        self._notify()


async def run_venue_reconciler(
    exchange,
    market_tracker,
    venue_state: VenueStateCache,
    *,
    background_executor: Executor | None = None,
) -> None:
    # Balance-allowance UPDATE is rate-limited to 50 req/10s (5/s).
    # Each sync cycle does 3 UPDATEs (up, down, collateral).
    # Sync every SYNC_INTERVAL_SEC to stay well under the limit,
    # and use read-only GETs (200 req/10s) for fast polling.
    SYNC_INTERVAL_SEC = 5.0
    POLL_INTERVAL_SEC = 2.0
    POLL_FAST_SEC = 0.5  # Near interval boundary

    last_sync_time = 0.0
    last_sync_market_slug = ""

    while True:
        market = market_tracker.active_market
        if market is not None:
            venue_state.set_active_market(market)
            started_us = monotonic_us()
            fetch_started_us = now_us()
            loop_now = time.monotonic()

            # Sync (UPDATE) on first call, market rotation, or every SYNC_INTERVAL_SEC
            needs_sync = (
                last_sync_time == 0.0
                or market.slug != last_sync_market_slug
                or (loop_now - last_sync_time) >= SYNC_INTERVAL_SEC
            )

            try:
                if needs_sync:
                    log_latency_event(
                        "balance_reconcile_start",
                        market_slug=market.slug,
                        interval_start=int(market.interval_start),
                        mode="sync",
                    )
                    # Full sync: UPDATE + GET (existing get_conditional_balance / get_collateral_balance)
                    up_task = _run_blocking(background_executor, exchange.get_conditional_balance, market.up_token_id)
                    dn_task = _run_blocking(background_executor, exchange.get_conditional_balance, market.down_token_id)
                    collateral_task = _run_blocking(background_executor, exchange.get_collateral_balance)
                    up_balance, down_balance, collateral_balance = await asyncio.gather(
                        up_task, dn_task, collateral_task,
                    )
                    last_sync_time = time.monotonic()
                    last_sync_market_slug = market.slug
                else:
                    # Read-only: just GET cached balances (no UPDATE call)
                    up_task = _run_blocking(background_executor, exchange._get_balance_allowance, exchange._asset_type.CONDITIONAL, market.up_token_id)
                    dn_task = _run_blocking(background_executor, exchange._get_balance_allowance, exchange._asset_type.CONDITIONAL, market.down_token_id)
                    collateral_task = _run_blocking(background_executor, exchange._get_balance_allowance, exchange._asset_type.COLLATERAL, None)
                    up_raw, dn_raw, col_raw = await asyncio.gather(
                        up_task, dn_task, collateral_task,
                    )
                    up_balance = up_raw["balance"]
                    down_balance = dn_raw["balance"]
                    collateral_balance = col_raw["balance"]

                venue_state.update_balances(
                    market=market,
                    up_balance=float(up_balance),
                    down_balance=float(down_balance),
                    collateral_balance=float(collateral_balance),
                    refreshed_at_us=fetch_started_us,
                )
                log_latency_event(
                    "balance_reconcile_done",
                    market_slug=market.slug,
                    interval_start=int(market.interval_start),
                    elapsed_ms=round((monotonic_us() - started_us) / 1_000.0, 3),
                    up_balance=float(up_balance),
                    down_balance=float(down_balance),
                    collateral_balance=float(collateral_balance),
                )
            except Exception as exc:
                log_latency_event(
                    "balance_reconcile_done",
                    market_slug=market.slug,
                    interval_start=int(market.interval_start),
                    elapsed_ms=round((monotonic_us() - started_us) / 1_000.0, 3),
                    error=str(exc),
                )
        boundary_in = max(0.0, next_interval_start(300) - time.time())
        sleep_sec = POLL_FAST_SEC if boundary_in <= 3.0 else POLL_INTERVAL_SEC
        await asyncio.sleep(sleep_sec)


def venue_state_allows_entry(
    snapshot: VenueStateSnapshot,
    *,
    market,
    now_value_us: int,
    token_max_age_us: int = DEFAULT_TOKEN_MAX_AGE_US,
    collateral_max_age_us: int = DEFAULT_COLLATERAL_MAX_AGE_US,
) -> tuple[bool, str]:
    if market is None:
        return False, "no_market"
    if not snapshot.startup_ready:
        return False, "venue_startup_pending"
    if snapshot.ambiguous:
        if snapshot.matches_market(market) and snapshot.token_age_us(now_value_us) <= token_max_age_us:
            return False, f"venue_ambiguous:{snapshot.ambiguity_reason}"
        return False, f"venue_ambiguous_stale:{snapshot.ambiguity_reason}"
    if snapshot.matches_market(market):
        if snapshot.token_age_us(now_value_us) <= token_max_age_us:
            return True, ""
        return True, "venue_stale_unambiguous"
    return True, "venue_market_pending"
