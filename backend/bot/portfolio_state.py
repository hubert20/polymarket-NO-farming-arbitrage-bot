"""Thread-safe portfolio snapshot for the dashboard."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PositionSnapshot:
    slug: str
    title: str
    outcome: str
    asset: str
    condition_id: str
    size: float
    avg_price: float
    initial_value: float
    current_price: float
    current_value: float
    pnl_usd: float
    pnl_pct: float
    end_date: str
    eta_seconds: float
    source: str = ""


@dataclass(frozen=True)
class PortfolioSnapshot:
    updated_at_us: int = 0
    monitored_markets: int = 0
    eligible_markets: int = 0
    in_range_markets: int = 0
    positions: tuple[PositionSnapshot, ...] = field(default_factory=tuple)
    cash_balance: float | None = None
    last_market_refresh_ts: float = 0.0
    last_position_sync_ts: float = 0.0
    last_price_cycle_ts: float = 0.0
    last_error: str = ""


class PortfolioState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version = 0
        self._snapshot = PortfolioSnapshot()

    def version(self) -> int:
        with self._lock:
            return self._version

    def update(
        self,
        *,
        updated_at_us: int,
        monitored_markets: int,
        eligible_markets: int,
        in_range_markets: int,
        positions: list[PositionSnapshot],
        cash_balance: float | None,
        last_market_refresh_ts: float,
        last_position_sync_ts: float,
        last_price_cycle_ts: float,
        last_error: str = "",
    ) -> None:
        ordered = tuple(
            sorted(
                positions,
                key=lambda position: (
                    position.eta_seconds if position.eta_seconds > 0 else float("inf"),
                    position.slug,
                ),
            )
        )
        with self._lock:
            self._snapshot = PortfolioSnapshot(
                updated_at_us=int(updated_at_us),
                monitored_markets=int(monitored_markets),
                eligible_markets=int(eligible_markets),
                in_range_markets=int(in_range_markets),
                positions=ordered,
                cash_balance=None if cash_balance is None else float(cash_balance),
                last_market_refresh_ts=float(last_market_refresh_ts),
                last_position_sync_ts=float(last_position_sync_ts),
                last_price_cycle_ts=float(last_price_cycle_ts),
                last_error=str(last_error or ""),
            )
            self._version += 1

    def snapshot(self) -> PortfolioSnapshot:
        with self._lock:
            return self._snapshot
