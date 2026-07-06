"""Paper-trading flag: fake balance, no real Polymarket orders — real market data otherwise."""

from __future__ import annotations

import os


def is_demo_mode() -> bool:
    """True when using simulated balance and not sending live orders."""
    raw = (os.getenv("DEMO_MODE") or "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def demo_balance() -> float:
    """Simulated wallet balance shown in demo mode."""
    return _env_float("DEMO_BALANCE", 7535.0)


def demo_session_pnl_usd() -> float:
    """Fixed session PnL for demo mode display."""
    return _env_float("DEMO_SESSION_PNL", 732.0)


def demo_session_starting_balance() -> float:
    """Session start balance implied by demo balance and session PnL."""
    return round(demo_balance() - demo_session_pnl_usd(), 2)


def demo_session_pnl_message() -> dict:
    starting = demo_session_starting_balance()
    current = demo_balance()
    pnl = demo_session_pnl_usd()
    pnl_pct = (pnl / starting * 100.0) if starting > 0 else 0.0
    return {
        "type": "session_pnl",
        "starting_balance": starting,
        "current_balance": current,
        "pnl_usd": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
    }
