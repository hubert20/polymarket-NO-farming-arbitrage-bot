import json
import logging
from datetime import date, datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from bot.db import bot_state_table, fills_table, orders_table, positions_table
from bot.models import OpenOrder, Side
from bot.order_status import normalize_order_status

logger = logging.getLogger(__name__)


_WORKING_ORDER_STATUSES = {"submitted", "open", "live", "partially_filled"}


class OrderStore:
    def __init__(self, engine: sa.Engine) -> None:
        self.engine = engine

    # --- Orders ---

    def record_order(
        self, order_id: str, token_id: str, side: Side, price: float, size: float, status: str = "submitted"
    ) -> None:
        now = datetime.now(timezone.utc)
        normalized_status = normalize_order_status(status)
        with self.engine.begin() as conn:
            try:
                conn.execute(
                    orders_table.insert().values(
                        order_id=order_id,
                        token_id=token_id,
                        side=side.value,
                        price=price,
                        size=size,
                        status=normalized_status,
                        created_at=now,
                        updated_at=now,
                    )
                )
            except IntegrityError:
                conn.execute(
                    orders_table.update()
                    .where(orders_table.c.order_id == order_id)
                    .values(status=normalized_status, updated_at=now)
                )

    def update_order_status(self, order_id: str, status: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                orders_table.update()
                .where(orders_table.c.order_id == order_id)
                .values(status=normalize_order_status(status), updated_at=datetime.now(timezone.utc))
            )

    def get_stale_order_ids(self, token_id: str, max_age_seconds: int) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        with self.engine.connect() as conn:
            rows = conn.execute(
                sa.select(orders_table.c.order_id).where(
                    orders_table.c.token_id == token_id,
                    orders_table.c.status.in_(sorted(_WORKING_ORDER_STATUSES)),
                    orders_table.c.created_at < cutoff,
                )
            ).fetchall()
            return [r[0] for r in rows]

    def get_open_order_ids(self, token_id: str) -> list[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                sa.select(orders_table.c.order_id).where(
                    orders_table.c.token_id == token_id,
                    orders_table.c.status.in_(sorted(_WORKING_ORDER_STATUSES)),
                )
            ).fetchall()
            return [r[0] for r in rows]

    def get_open_orders(self, token_id: str) -> list[OpenOrder]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                sa.select(
                    orders_table.c.order_id,
                    orders_table.c.token_id,
                    orders_table.c.side,
                    orders_table.c.price,
                    orders_table.c.size,
                    orders_table.c.status,
                ).where(
                    orders_table.c.token_id == token_id,
                    orders_table.c.status.in_(sorted(_WORKING_ORDER_STATUSES)),
                )
            ).fetchall()
            return [
                OpenOrder(
                    order_id=row[0],
                    token_id=row[1],
                    side=Side(row[2]),
                    price=row[3],
                    original_size=row[4],
                    status=row[5],
                )
                for row in rows
            ]

    def get_order(self, order_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.select(
                    orders_table.c.order_id,
                    orders_table.c.token_id,
                    orders_table.c.side,
                    orders_table.c.price,
                    orders_table.c.size,
                    orders_table.c.status,
                ).where(orders_table.c.order_id == order_id)
            ).first()
            if row is None:
                return None
            return {
                "order_id": row[0],
                "token_id": row[1],
                "side": row[2],
                "price": row[3],
                "size": row[4],
                "status": row[5],
            }

    def get_filled_size(self, order_id: str) -> float:
        with self.engine.connect() as conn:
            total = conn.execute(
                sa.select(sa.func.coalesce(sa.func.sum(fills_table.c.size), 0.0)).where(
                    fills_table.c.order_id == order_id
                )
            ).scalar_one()
            return float(total or 0.0)

    def get_first_fill_time(self, order_id: str) -> datetime | None:
        with self.engine.connect() as conn:
            value = conn.execute(
                sa.select(sa.func.min(fills_table.c.filled_at)).where(
                    fills_table.c.order_id == order_id
                )
            ).scalar_one_or_none()
            return _normalize_db_timestamp(value)

    def get_latest_fill_time(self, token_id: str, side: Side) -> datetime | None:
        with self.engine.connect() as conn:
            value = conn.execute(
                sa.select(sa.func.max(fills_table.c.filled_at)).where(
                    fills_table.c.token_id == token_id,
                    fills_table.c.side == side.value,
                )
            ).scalar_one_or_none()
            return _normalize_db_timestamp(value)

    def sync_order_fill_status(self, order_id: str) -> str | None:
        order = self.get_order(order_id)
        if order is None:
            return None

        filled_size = self.get_filled_size(order_id)
        if filled_size <= 0:
            return order["status"]

        if filled_size + 1e-9 >= float(order["size"]):
            status = "filled"
        else:
            status = "partially_filled"

        self.update_order_status(order_id, status)
        return status

    # --- Fills ---

    def record_fill(
        self,
        fill_id: str,
        order_id: str | None,
        token_id: str,
        side: Side,
        price: float,
        size: float,
        fee: float = 0.0,
        filled_at: datetime | None = None,
    ) -> bool:
        ts = filled_at or datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            try:
                conn.execute(
                    fills_table.insert().values(
                        fill_id=fill_id,
                        order_id=order_id,
                        token_id=token_id,
                        side=side.value,
                        price=price,
                        size=size,
                        fee=fee,
                        filled_at=ts,
                    )
                )
                return True
            except IntegrityError:
                return False

    # --- Positions ---

    def update_position(
        self,
        token_id: str,
        side: Side,
        fill_price: float,
        fill_size: float,
        fee: float = 0.0,
        filled_at: datetime | None = None,
    ) -> dict[str, float]:
        ts = filled_at or datetime.now(timezone.utc)
        signed_qty = fill_size if side == Side.BUY else -fill_size
        with self.engine.begin() as conn:
            row = conn.execute(
                sa.select(positions_table.c.net_qty, positions_table.c.avg_entry, positions_table.c.realized_pnl)
                .where(positions_table.c.token_id == token_id)
            ).first()

            if row is None:
                realized_delta = -fee
                conn.execute(
                    positions_table.insert().values(
                        token_id=token_id,
                        net_qty=signed_qty,
                        avg_entry=fill_price if signed_qty != 0 else 0.0,
                        realized_pnl=realized_delta,
                        last_updated=ts,
                    )
                )
                self._increment_state_value(
                    conn,
                    _daily_realized_pnl_key(ts.date()),
                    realized_delta,
                    ts,
                )
                return {"net_qty": signed_qty, "avg_entry": fill_price if signed_qty != 0 else 0.0, "realized_pnl": realized_delta}

            old_qty, old_avg, old_pnl = row[0], row[1], row[2]
            new_qty = old_qty + signed_qty

            # Realized PnL when reducing position
            realized = 0.0
            if old_qty != 0 and (old_qty > 0) != (signed_qty > 0):
                closed_qty = min(abs(signed_qty), abs(old_qty))
                if old_qty > 0:
                    realized = closed_qty * (fill_price - old_avg)
                else:
                    realized = closed_qty * (old_avg - fill_price)

            # Update average entry
            if new_qty == 0:
                new_avg = 0.0
            elif (old_qty > 0) == (signed_qty > 0):
                new_avg = (old_avg * abs(old_qty) + fill_price * abs(signed_qty)) / abs(new_qty)
            elif abs(signed_qty) > abs(old_qty):
                new_avg = fill_price
            else:
                new_avg = old_avg

            realized_delta = realized - fee
            new_realized_pnl = old_pnl + realized_delta

            conn.execute(
                positions_table.update()
                .where(positions_table.c.token_id == token_id)
                .values(
                    net_qty=new_qty,
                    avg_entry=new_avg,
                    realized_pnl=new_realized_pnl,
                    last_updated=ts,
                )
            )
            self._increment_state_value(
                conn,
                _daily_realized_pnl_key(ts.date()),
                realized_delta,
                ts,
            )
            return {"net_qty": new_qty, "avg_entry": new_avg, "realized_pnl": new_realized_pnl}

    def get_position(self, token_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.select(
                    positions_table.c.net_qty,
                    positions_table.c.avg_entry,
                    positions_table.c.realized_pnl,
                ).where(positions_table.c.token_id == token_id)
            ).first()
            if row is None:
                return None
            return {"net_qty": row[0], "avg_entry": row[1], "realized_pnl": row[2]}

    def get_daily_realized_pnl(self, day: date | None = None) -> float:
        pnl_day = day or datetime.now(timezone.utc).date()
        raw = self.get_state(_daily_realized_pnl_key(pnl_day))
        if raw is None:
            return 0.0
        return float(raw)

    def get_orders_sent(self, token_id: str) -> int:
        raw = self.get_state(_risk_orders_sent_key(token_id))
        return int(float(raw)) if raw is not None else 0

    def get_session_notional(self, token_id: str) -> float:
        raw = self.get_state(_risk_session_notional_key(token_id))
        return float(raw) if raw is not None else 0.0

    def increment_risk_counters(
        self,
        token_id: str,
        order_count_delta: int = 0,
        session_notional_delta: float = 0.0,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            if order_count_delta:
                self._increment_state_value(conn, _risk_orders_sent_key(token_id), float(order_count_delta), now)
            if session_notional_delta:
                self._increment_state_value(conn, _risk_session_notional_key(token_id), session_notional_delta, now)

    def get_json_state(self, key: str) -> dict | None:
        raw = self.get_state(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_json_state(self, key: str, value: dict) -> None:
        self.set_state(key, json.dumps(value, separators=(",", ":")))

    def set_submission_lock(
        self,
        token_id: str,
        side: Side,
        price: float,
        size: float,
        error: str,
    ) -> None:
        payload = {
            "token_id": token_id,
            "side": side.value,
            "price": price,
            "size": size,
            "error": error,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.set_json_state(_submission_lock_key(token_id), payload)

    def get_submission_lock(self, token_id: str) -> dict | None:
        raw = self.get_state(_submission_lock_key(token_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"token_id": token_id, "error": raw}

    def clear_submission_lock(self, token_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                bot_state_table.delete().where(bot_state_table.c.key == _submission_lock_key(token_id))
            )

    def has_fill_since(self, token_id: str, side: Side, since: datetime) -> bool:
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.select(fills_table.c.fill_id).where(
                    fills_table.c.token_id == token_id,
                    fills_table.c.side == side.value,
                    fills_table.c.filled_at >= since,
                ).limit(1)
            ).first()
            return row is not None

    # --- Bot state ---

    def set_state(self, key: str, value: str) -> None:
        now = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            existing = conn.execute(
                sa.select(bot_state_table.c.key).where(bot_state_table.c.key == key)
            ).first()
            if existing:
                conn.execute(
                    bot_state_table.update()
                    .where(bot_state_table.c.key == key)
                    .values(value=value, updated_at=now)
                )
            else:
                conn.execute(
                    bot_state_table.insert().values(key=key, value=value, updated_at=now)
                )

    def get_state(self, key: str) -> str | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.select(bot_state_table.c.value).where(bot_state_table.c.key == key)
            ).first()
            return row[0] if row else None

    def _increment_state_value(
        self,
        conn: sa.Connection,
        key: str,
        delta: float,
        now: datetime,
    ) -> None:
        if delta == 0:
            return

        existing = conn.execute(
            sa.select(bot_state_table.c.value).where(bot_state_table.c.key == key)
        ).first()
        current = float(existing[0]) if existing else 0.0
        new_value = current + delta
        if existing:
            conn.execute(
                bot_state_table.update()
                .where(bot_state_table.c.key == key)
                .values(value=str(new_value), updated_at=now)
            )
        else:
            conn.execute(
                bot_state_table.insert().values(key=key, value=str(new_value), updated_at=now)
            )


def _daily_realized_pnl_key(day: date) -> str:
    return f"daily_realized_pnl:{day.isoformat()}"


def _submission_lock_key(token_id: str) -> str:
    return f"submission_lock:{token_id}"


def _normalize_db_timestamp(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return None


def _risk_orders_sent_key(token_id: str) -> str:
    return f"risk:orders_sent:{token_id}"


def _risk_session_notional_key(token_id: str) -> str:
    return f"risk:session_notional:{token_id}"
