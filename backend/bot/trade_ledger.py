"""Append-only trade ledger for incident reconstruction.

Every order attempt (BUY/SELL) is recorded with timestamp, market,
side, token, order result, and context. The ledger is NOT used for
trading decisions — it exists purely for post-hoc analysis.

Records are written to:
  1. Postgres (trade_events table) — durable, survives dyno restarts
  2. The Python logger at INFO level — captured by Heroku log drains
  3. A local JSON-lines file (trades.jsonl) — for local dev / dashboard
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import threading
import time

logger = logging.getLogger(__name__)

_LEDGER_PATH = os.getenv("TRADE_LEDGER_PATH", "trades.jsonl")
_ledger_fd = None
_db_engine = None
_QUEUE_MAXSIZE = max(128, int(os.getenv("PM_TRADE_LEDGER_QUEUE_MAXSIZE", "4096")))
_ledger_queue: queue.Queue[dict | None] = queue.Queue(maxsize=_QUEUE_MAXSIZE)
_writer_lock = threading.Lock()
_writer_thread: threading.Thread | None = None
_overflow_warned = False
_NONCRITICAL_ACTIONS = {
    "attempt",
    "recovery",
    "f11_startup_orphan",
}


def init_db(database_url: str) -> None:
    """Initialize Postgres connection for trade event storage."""
    global _db_engine
    try:
        from bot.db import create_engine, create_tables
        _db_engine = create_engine(database_url)
        create_tables(_db_engine)
        logger.info("trade_ledger_db_initialized")
    except Exception as e:
        logger.warning("trade_ledger_db_init_failed: %s", e)
        _db_engine = None


def _open_ledger():
    global _ledger_fd
    if _ledger_fd is None:
        try:
            _ledger_fd = open(_LEDGER_PATH, "a", encoding="utf-8")
        except OSError as e:
            logger.warning("Could not open trade ledger at %s: %s", _LEDGER_PATH, e)


def _write_record(record: dict) -> None:
    # 1. Postgres — durable storage
    if _db_engine is not None:
        try:
            from bot.db import trade_events_table
            row = {k: v for k, v in record.items() if k in _DB_COLUMNS}
            overflow = {k: v for k, v in record.items() if k not in _DB_COLUMNS}
            if overflow:
                row["extra"] = json.dumps(overflow)
            with _db_engine.connect() as conn:
                conn.execute(trade_events_table.insert().values(**row))
                conn.commit()
        except Exception:
            pass  # never let DB issues kill the hot path

    # 2. Logger — captured by Heroku log drains
    try:
        logger.info("trade_ledger", extra=record)
    except Exception:
        pass

    # 3. Local file — for local dev and dashboard tailing
    _open_ledger()
    if _ledger_fd is None:
        return
    try:
        _ledger_fd.write(json.dumps(record) + "\n")
        _ledger_fd.flush()
    except OSError as e:
        logger.warning("Failed to write trade ledger: %s", e)


def _writer_loop() -> None:
    while True:
        try:
            item = _ledger_queue.get(timeout=0.25)
        except queue.Empty:
            continue
        if item is None:
            _ledger_queue.task_done()
            break
        record = dict(item)
        queued_at = record.pop("_queued_perf_ns", None)
        if isinstance(queued_at, int):
            record["ledger_queue_lag_ms"] = round((time.perf_counter_ns() - queued_at) / 1_000_000.0, 3)
        _write_record(record)
        _ledger_queue.task_done()


def _ensure_writer_thread() -> None:
    global _writer_thread
    if _writer_thread is not None and _writer_thread.is_alive():
        return
    with _writer_lock:
        if _writer_thread is not None and _writer_thread.is_alive():
            return
        _writer_thread = threading.Thread(
            target=_writer_loop,
            name="trade-ledger-writer",
            daemon=True,
        )
        _writer_thread.start()


def flush_trade_ledger(timeout_sec: float = 5.0) -> bool:
    """Best-effort wait for queued records to be persisted."""
    deadline = time.time() + max(0.0, timeout_sec)
    while _ledger_queue.unfinished_tasks > 0 and time.time() < deadline:
        time.sleep(0.01)
    return _ledger_queue.unfinished_tasks == 0


def shutdown_trade_ledger(timeout_sec: float = 5.0) -> None:
    global _writer_thread
    deadline = time.time() + max(0.0, timeout_sec)
    flush_trade_ledger(timeout_sec=timeout_sec)
    if _writer_thread is None:
        return
    while True:
        remaining = max(0.0, deadline - time.time())
        try:
            _ledger_queue.put(None, timeout=remaining if remaining > 0.0 else 0.0)
            break
        except queue.Full:
            if remaining <= 0.0:
                break
    _writer_thread.join(timeout=max(0.0, deadline - time.time()))
    if _writer_thread.is_alive():
        return
    _writer_thread = None


atexit.register(shutdown_trade_ledger)


# Known columns in trade_events table
_DB_COLUMNS = {
    "ts", "action", "market_slug", "side", "token_id", "amount",
    "reference_price", "order_id", "order_status", "flip_count",
    "interval_start", "spot_price", "strike", "sigma", "gap", "fair", "error",
}


def record_order(
    *,
    action: str,
    market_slug: str,
    side: str,
    token_id: str,
    amount: float,
    reference_price: float | None = None,
    order_id: str = "",
    order_status: str = "",
    flip_count: int = 0,
    interval_start: int = 0,
    spot_price: float = 0.0,
    strike: float = 0.0,
    sigma: float = 0.0,
    gap: float = 0.0,
    fair: float = 0.0,
    error: str = "",
    **extra,
) -> None:
    """Append a single trade record to the ledger and log it."""
    global _overflow_warned
    record = {
        "ts": time.time(),
        "action": action,
        "market_slug": market_slug,
        "side": side,
        "token_id": token_id,
        "amount": amount,
        "reference_price": reference_price,
        "order_id": order_id,
        "order_status": order_status,
        "flip_count": flip_count,
        "interval_start": interval_start,
        "spot_price": spot_price,
        "strike": strike,
        "sigma": sigma,
        "gap": gap,
        "fair": fair,
    }
    bot_variant = os.getenv("BOT_VARIANT", "").strip()
    if bot_variant and "bot_variant" not in extra:
        record["bot_variant"] = bot_variant
    if error:
        record["error"] = error
    if extra:
        record.update(extra)
    record["_queued_perf_ns"] = time.perf_counter_ns()

    _ensure_writer_thread()
    try:
        _ledger_queue.put_nowait(record)
        return
    except queue.Full:
        pass

    if action in _NONCRITICAL_ACTIONS:
        if not _overflow_warned:
            logger.warning(
                "trade_ledger_queue_full_dropping_noncritical",
                extra={"queue_maxsize": _QUEUE_MAXSIZE, "action": action},
            )
            _overflow_warned = True
        return

    sync_record = dict(record)
    queued_at = sync_record.pop("_queued_perf_ns", None)
    if isinstance(queued_at, int):
        sync_record["ledger_queue_lag_ms"] = round((time.perf_counter_ns() - queued_at) / 1_000_000.0, 3)
    _write_record(sync_record)
