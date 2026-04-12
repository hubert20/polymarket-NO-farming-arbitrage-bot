"""Structured latency logging helpers for the live bot."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def monotonic_us() -> int:
    """Monotonic clock for duration measurement."""
    return time.perf_counter_ns() // 1_000


def log_latency_event(marker: str, **extra: Any) -> None:
    """Emit a structured latency marker."""
    payload = {"marker": marker}
    bot_variant = os.getenv("BOT_VARIANT", "").strip()
    if bot_variant and "bot_variant" not in extra:
        payload["bot_variant"] = bot_variant
    payload.update(extra)
    logger.info("latency_event", extra=payload)


def log_latency_span(marker: str, start_us: int, end_us: int | None = None, **extra: Any) -> int:
    """Emit a duration-bearing latency marker and return the elapsed time."""
    finish_us = monotonic_us() if end_us is None else int(end_us)
    elapsed_us = max(0, finish_us - int(start_us))
    payload = {
        "marker": marker,
        "elapsed_us": elapsed_us,
        "elapsed_ms": round(elapsed_us / 1_000.0, 3),
    }
    bot_variant = os.getenv("BOT_VARIANT", "").strip()
    if bot_variant and "bot_variant" not in extra:
        payload["bot_variant"] = bot_variant
    payload.update(extra)
    logger.info("latency_event", extra=payload)
    return elapsed_us
