"""Shared helpers: timestamps, interval math, fast JSON."""

import random
import time

try:
    import orjson
    json_loads = orjson.loads
except ImportError:
    import json as _json
    json_loads = _json.loads


def now_ms() -> int:
    """Current time as Unix milliseconds."""
    return time.time_ns() // 1_000_000


def now_us() -> int:
    """Current time as Unix microseconds."""
    return time.time_ns() // 1_000


def current_interval_start(interval_sec: int = 300) -> int:
    """Return the Unix timestamp (seconds) of the current interval start."""
    now = int(time.time())
    return now - (now % interval_sec)


def next_interval_start(interval_sec: int = 300) -> int:
    """Return the Unix timestamp (seconds) of the next interval start."""
    return current_interval_start(interval_sec) + interval_sec


def seconds_until_interval_end(interval_sec: int = 300) -> float:
    """Seconds remaining in the current interval."""
    now = time.time()
    start = now - (now % interval_sec)
    return start + interval_sec - now


def polymarket_taker_fee(price: float, trade_value: float) -> float:
    """Polymarket taker fee for crypto 5-min markets.

    The effective fee rate peaks at 1.56% at price=0.50 and decreases
    symmetrically toward both extremes (0 and 1).
    """
    if price <= 0.0 or price >= 1.0:
        return 0.0
    effective_rate = 0.25 * (price * (1.0 - price)) ** 2
    return effective_rate * trade_value


def backoff_sleep(backoff: float) -> float:
    """Return jittered sleep duration to prevent thundering herd."""
    return backoff + random.uniform(0, backoff * 0.25)
