"""Runtime risk controls for live strategy loops.

Implements:
  - Max total and per-market open exposure caps
  - Daily drawdown circuit-breaker (USDC balance vs high-water mark)
  - Kill switch with configurable cooldown

The daily drawdown check is active when PM_RISK_MAX_DAILY_DRAWDOWN_USD > 0.
It queries the actual USDC balance each interval and compares against
the daily high-water mark.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os


@dataclass
class RiskConfig:
    max_total_open_exposure_usd: float = 1_500.0
    max_market_open_exposure_usd: float = 1_000.0
    max_daily_drawdown_usd: float = 0.0  # 0 = disabled
    kill_switch_cooldown_sec: float = 900.0
    drawdown_arm_after_sec: float = 1800.0
    drawdown_min_fresh_observations: int = 3

    @classmethod
    def from_env(cls) -> "RiskConfig":
        def _f(name: str, default: float) -> float:
            v = os.environ.get(name)
            if v is None:
                return default
            try:
                return float(v)
            except ValueError:
                return default

        return cls(
            max_total_open_exposure_usd=_f(
                "PM_RISK_MAX_TOTAL_OPEN_EXPOSURE_USD", cls.max_total_open_exposure_usd
            ),
            max_market_open_exposure_usd=_f(
                "PM_RISK_MAX_MARKET_OPEN_EXPOSURE_USD", cls.max_market_open_exposure_usd
            ),
            max_daily_drawdown_usd=_f(
                "PM_RISK_MAX_DAILY_DRAWDOWN_USD", cls.max_daily_drawdown_usd
            ),
            kill_switch_cooldown_sec=max(1.0, _f("PM_RISK_KILL_COOLDOWN_SEC", cls.kill_switch_cooldown_sec)),
            drawdown_arm_after_sec=max(0.0, _f("PM_RISK_DRAWDOWN_ARM_AFTER_SEC", cls.drawdown_arm_after_sec)),
            drawdown_min_fresh_observations=max(
                1,
                int(_f("PM_RISK_DRAWDOWN_MIN_FRESH_OBS", float(cls.drawdown_min_fresh_observations))),
            ),
        )


class RiskController:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg
        self._day_key: str = ""
        self.daily_realized_pnl_usd: float = 0.0
        self.open_exposure_total_usd: float = 0.0
        self.open_exposure_by_market: dict[str, float] = {}
        self._kill_until_us: int = 0
        self._kill_reason: str = ""

        # Balance-based daily drawdown tracking (audit fix F1)
        self._balance_hwm: float = 0.0  # high-water mark, set on first observation
        self._balance_hwm_day: str = ""  # resets on day roll
        self._drawdown_obs_count: int = 0
        self._drawdown_first_obs_us: int = 0

    def _current_day_key(self, now_us: int) -> str:
        dt = datetime.fromtimestamp(now_us / 1_000_000.0, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")

    def _roll_day_if_needed(self, now_us: int) -> None:
        k = self._current_day_key(now_us)
        if self._day_key == "":
            self._day_key = k
            return
        if k != self._day_key:
            self._day_key = k
            self.daily_realized_pnl_usd = 0.0
            self._balance_hwm = 0.0  # reset high-water mark for new day
            self._balance_hwm_day = ""
            self._drawdown_obs_count = 0
            self._drawdown_first_obs_us = 0

    def seed_balance_hwm(self, now_us: int, balance_usd: float) -> None:
        """Set the daily high-water mark directly, bypassing the arm period.

        Called at startup to establish the HWM from current balance so the
        drawdown check has a valid baseline immediately.
        """
        if self.cfg.max_daily_drawdown_usd <= 0:
            return
        self._roll_day_if_needed(now_us)
        day = self._current_day_key(now_us)
        self._balance_hwm = balance_usd
        self._balance_hwm_day = day

    def check_balance_drawdown(self, now_us: int, balance_usd: float, *, ambiguous: bool = False) -> None:
        """Check USDC balance against daily high-water mark.

        Activates kill switch if drawdown exceeds max_daily_drawdown_usd.
        Disabled when max_daily_drawdown_usd <= 0. (Audit fix F1)
        """
        if self.cfg.max_daily_drawdown_usd <= 0:
            return
        self._roll_day_if_needed(now_us)
        day = self._current_day_key(now_us)
        if self._drawdown_first_obs_us <= 0:
            self._drawdown_first_obs_us = now_us
        self._drawdown_obs_count += 1
        if (
            (now_us - self._drawdown_first_obs_us) < int(self.cfg.drawdown_arm_after_sec * 1_000_000)
            or self._drawdown_obs_count < self.cfg.drawdown_min_fresh_observations
        ):
            return
        if self._balance_hwm_day != day:
            # New day or first observation: set high-water mark
            self._balance_hwm = balance_usd
            self._balance_hwm_day = day
            return
        if ambiguous:
            return
        elif balance_usd > self._balance_hwm:
            self._balance_hwm = balance_usd
        drawdown = self._balance_hwm - balance_usd
        if drawdown >= self.cfg.max_daily_drawdown_usd:
            self._activate_kill_switch(
                now_us,
                f"daily_drawdown=${drawdown:.2f}_exceeds_${self.cfg.max_daily_drawdown_usd:.2f}"
                f"_hwm=${self._balance_hwm:.2f}_bal=${balance_usd:.2f}",
            )

    def _activate_kill_switch(self, now_us: int, reason: str) -> None:
        if self.kill_switch_active(now_us):
            return  # Already active — don't extend the cooldown
        cooldown_us = int(self.cfg.kill_switch_cooldown_sec * 1_000_000)
        self._kill_until_us = now_us + cooldown_us
        self._kill_reason = reason

    def kill_switch_active(self, now_us: int) -> bool:
        return now_us < self._kill_until_us

    def kill_switch_reason(self) -> str:
        return self._kill_reason

    def can_open_trade(self, now_us: int, market_slug: str, notional_usd: float) -> tuple[bool, str]:
        self._roll_day_if_needed(now_us)
        if self.kill_switch_active(now_us):
            return False, f"kill_switch_active:{self._kill_reason}"
        notional = max(0.0, float(notional_usd))
        market_open = self.open_exposure_by_market.get(market_slug, 0.0)
        if self.open_exposure_total_usd + notional > self.cfg.max_total_open_exposure_usd:
            return False, "max_total_open_exposure"
        if market_open + notional > self.cfg.max_market_open_exposure_usd:
            return False, "max_market_open_exposure"
        return True, ""

    def on_open_trade(self, market_slug: str, notional_usd: float, now_us: int) -> None:
        self._roll_day_if_needed(now_us)
        notional = max(0.0, float(notional_usd))
        self.open_exposure_total_usd += notional
        self.open_exposure_by_market[market_slug] = self.open_exposure_by_market.get(market_slug, 0.0) + notional

    def reduce_open_exposure(self, market_slug: str, notional_usd: float, now_us: int) -> None:
        self._roll_day_if_needed(now_us)
        notional = max(0.0, float(notional_usd))
        self.open_exposure_total_usd = max(0.0, self.open_exposure_total_usd - notional)
        self.open_exposure_by_market[market_slug] = max(
            0.0, self.open_exposure_by_market.get(market_slug, 0.0) - notional
        )

    def on_partial_close_trade(
        self,
        market_slug: str,
        notional_usd: float,
        pnl_usd: float,
        now_us: int,
    ) -> None:
        self._roll_day_if_needed(now_us)
        self.reduce_open_exposure(market_slug, notional_usd, now_us)
        self.daily_realized_pnl_usd += float(pnl_usd)

    def on_close_trade(
        self,
        market_slug: str,
        notional_usd: float,
        pnl_usd: float,
        now_us: int,
    ) -> None:
        self._roll_day_if_needed(now_us)
        notional = max(0.0, float(notional_usd))
        self.open_exposure_total_usd = max(0.0, self.open_exposure_total_usd - notional)
        self.open_exposure_by_market[market_slug] = max(
            0.0, self.open_exposure_by_market.get(market_slug, 0.0) - notional
        )
        self.daily_realized_pnl_usd += float(pnl_usd)

    def snapshot(self, now_us: int) -> dict[str, float | bool | str]:
        self._roll_day_if_needed(now_us)
        return {
            "daily_realized_pnl_usd": float(self.daily_realized_pnl_usd),
            "open_exposure_total_usd": float(self.open_exposure_total_usd),
            "kill_switch_active": bool(self.kill_switch_active(now_us)),
            "kill_switch_reason": str(self.kill_switch_reason()),
        }
