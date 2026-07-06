from datetime import datetime, timezone

from pytest import approx

import sqlalchemy as sa

from bot.db import create_tables, metadata
from bot.models import Side
from bot.store import OrderStore


def _make_store() -> OrderStore:
    engine = sa.create_engine("sqlite:///:memory:")
    create_tables(engine)
    return OrderStore(engine)


def test_record_and_get_order() -> None:
    store = _make_store()
    store.record_order("o1", "token", Side.BUY, 0.5, 10.0, "submitted")
    ids = store.get_open_order_ids("token")
    assert "o1" in ids


def test_update_order_status() -> None:
    store = _make_store()
    store.record_order("o1", "token", Side.BUY, 0.5, 10.0, "submitted")
    store.update_order_status("o1", "filled")
    ids = store.get_open_order_ids("token")
    assert "o1" not in ids


def test_duplicate_order_upserts() -> None:
    store = _make_store()
    store.record_order("o1", "token", Side.BUY, 0.5, 10.0, "submitted")
    store.record_order("o1", "token", Side.BUY, 0.5, 10.0, "open")
    ids = store.get_open_order_ids("token")
    assert "o1" in ids


def test_order_status_normalizes_working_aliases() -> None:
    store = _make_store()
    store.record_order("o1", "token", Side.BUY, 0.5, 10.0, "OPEN")
    assert "o1" in store.get_open_order_ids("token")


def test_record_fill_idempotent() -> None:
    store = _make_store()
    first = store.record_fill("f1", "o1", "token", Side.BUY, 0.5, 10.0)
    second = store.record_fill("f1", "o1", "token", Side.BUY, 0.5, 10.0)
    assert first is True
    assert second is False


def test_position_tracking_buy() -> None:
    store = _make_store()
    store.update_position("token", Side.BUY, 0.50, 10.0)
    pos = store.get_position("token")
    assert pos is not None
    assert pos["net_qty"] == 10.0
    assert pos["avg_entry"] == 0.50


def test_position_tracking_buy_then_sell() -> None:
    store = _make_store()
    store.update_position("token", Side.BUY, 0.50, 10.0)
    store.update_position("token", Side.SELL, 0.60, 5.0)
    pos = store.get_position("token")
    assert pos is not None
    assert pos["net_qty"] == 5.0
    assert pos["avg_entry"] == 0.50
    assert pos["realized_pnl"] == approx(0.5)  # 5 * (0.60 - 0.50)


def test_position_tracking_full_close() -> None:
    store = _make_store()
    store.update_position("token", Side.BUY, 0.40, 10.0)
    store.update_position("token", Side.SELL, 0.50, 10.0)
    pos = store.get_position("token")
    assert pos["net_qty"] == 0.0
    assert pos["realized_pnl"] == approx(1.0)  # 10 * (0.50 - 0.40)


def test_position_tracking_applies_fees_to_realized_pnl_and_daily_loss() -> None:
    store = _make_store()
    fill_time = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)
    store.update_position("token", Side.BUY, 0.40, 10.0, fee=0.10, filled_at=fill_time)
    store.update_position("token", Side.SELL, 0.50, 10.0, fee=0.20, filled_at=fill_time)
    pos = store.get_position("token")
    assert pos["net_qty"] == 0.0
    assert pos["realized_pnl"] == approx(0.70)  # 1.0 gross - 0.30 fees
    assert store.get_daily_realized_pnl(fill_time.date()) == approx(0.70)


def test_sync_order_fill_status_tracks_partial_and_complete_fills() -> None:
    store = _make_store()
    store.record_order("o1", "token", Side.BUY, 0.5, 10.0, "submitted")
    store.record_fill("f1", "o1", "token", Side.BUY, 0.5, 4.0)
    assert store.sync_order_fill_status("o1") == "partially_filled"
    assert "o1" in store.get_open_order_ids("token")

    store.record_fill("f2", "o1", "token", Side.BUY, 0.5, 6.0)
    assert store.sync_order_fill_status("o1") == "filled"
    assert "o1" not in store.get_open_order_ids("token")


def test_fill_time_queries_return_expected_timestamps() -> None:
    store = _make_store()
    first = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)
    second = datetime(2026, 3, 7, 12, 1, tzinfo=timezone.utc)

    store.record_fill("f1", "o1", "token", Side.BUY, 0.5, 1.0, filled_at=first)
    store.record_fill("f2", "o1", "token", Side.BUY, 0.5, 1.0, filled_at=second)

    assert store.get_first_fill_time("o1") == first
    assert store.get_latest_fill_time("token", Side.BUY) == second


def test_bot_state() -> None:
    store = _make_store()
    assert store.get_state("counter") is None
    store.set_state("counter", "5")
    assert store.get_state("counter") == "5"
    store.set_state("counter", "10")
    assert store.get_state("counter") == "10"


def test_no_position_returns_none() -> None:
    store = _make_store()
    assert store.get_position("nonexistent") is None


def test_stale_order_detection() -> None:
    import time
    store = _make_store()
    store.record_order("o1", "token", Side.BUY, 0.5, 10.0, "submitted")
    # With max_age_seconds=0, any order is immediately stale
    # But we need a tiny delay to ensure created_at < cutoff
    time.sleep(0.05)
    stale = store.get_stale_order_ids("token", max_age_seconds=0)
    assert "o1" in stale


def test_fresh_order_not_stale() -> None:
    store = _make_store()
    store.record_order("o1", "token", Side.BUY, 0.5, 10.0, "submitted")
    stale = store.get_stale_order_ids("token", max_age_seconds=3600)
    assert "o1" not in stale
