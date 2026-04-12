import sqlalchemy as sa

metadata = sa.MetaData()

orders_table = sa.Table(
    "orders",
    metadata,
    sa.Column("order_id", sa.String, primary_key=True),
    sa.Column("token_id", sa.String, nullable=False),
    sa.Column("side", sa.String(4), nullable=False),
    sa.Column("price", sa.Float, nullable=False),
    sa.Column("size", sa.Float, nullable=False),
    sa.Column("status", sa.String(20), nullable=False, server_default="submitted"),
    sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
)

fills_table = sa.Table(
    "fills",
    metadata,
    sa.Column("fill_id", sa.String, primary_key=True),
    sa.Column("order_id", sa.String, nullable=True),
    sa.Column("token_id", sa.String, nullable=False),
    sa.Column("side", sa.String(4), nullable=False),
    sa.Column("price", sa.Float, nullable=False),
    sa.Column("size", sa.Float, nullable=False),
    sa.Column("fee", sa.Float, nullable=False, server_default="0"),
    sa.Column("filled_at", sa.DateTime, server_default=sa.func.now()),
)

positions_table = sa.Table(
    "positions",
    metadata,
    sa.Column("token_id", sa.String, primary_key=True),
    sa.Column("net_qty", sa.Float, nullable=False, server_default="0"),
    sa.Column("avg_entry", sa.Float, nullable=False, server_default="0"),
    sa.Column("realized_pnl", sa.Float, nullable=False, server_default="0"),
    sa.Column("last_updated", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
)

bot_state_table = sa.Table(
    "bot_state",
    metadata,
    sa.Column("key", sa.String, primary_key=True),
    sa.Column("value", sa.String, nullable=False),
    sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
)


trade_events_table = sa.Table(
    "trade_events",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ts", sa.Float, nullable=False),
    sa.Column("action", sa.String(30), nullable=False, index=True),
    sa.Column("market_slug", sa.String, nullable=False, index=True),
    sa.Column("side", sa.String(10), nullable=False),
    sa.Column("token_id", sa.String, nullable=False),
    sa.Column("amount", sa.Float, nullable=False),
    sa.Column("reference_price", sa.Float, nullable=True),
    sa.Column("order_id", sa.String, nullable=True),
    sa.Column("order_status", sa.String(20), nullable=True),
    sa.Column("flip_count", sa.Integer, nullable=True),
    sa.Column("interval_start", sa.Integer, nullable=True, index=True),
    sa.Column("spot_price", sa.Float, nullable=True),
    sa.Column("strike", sa.Float, nullable=True),
    sa.Column("sigma", sa.Float, nullable=True),
    sa.Column("gap", sa.Float, nullable=True),
    sa.Column("fair", sa.Float, nullable=True),
    sa.Column("error", sa.String, nullable=True),
    sa.Column("extra", sa.String, nullable=True),  # JSON for overflow fields
    sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
)


pending_settlements_table = sa.Table(
    "pending_settlements",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("market_slug", sa.String, nullable=False, index=True),
    sa.Column("interval_start", sa.Integer, nullable=False, index=True),
    sa.Column("open_side", sa.String(10), nullable=False),
    sa.Column("token_id", sa.String, nullable=False),
    sa.Column("entry_spent_usd", sa.Float, nullable=False),
    sa.Column("entry_shares", sa.Float, nullable=False),
    sa.Column("open_notional_usd", sa.Float, nullable=False),
    sa.Column("strike", sa.Float, nullable=False),
    sa.Column("strike_source", sa.String, nullable=False, server_default=""),
    sa.Column("flip_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("trade_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("state", sa.String(30), nullable=False, index=True, server_default="pending"),
    sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("ready_at_ts", sa.Float, nullable=False),
    sa.Column("next_retry_at_ts", sa.Float, nullable=False),
    sa.Column("last_error", sa.String, nullable=True),
    sa.Column("settle_status", sa.String(40), nullable=True),
    sa.Column("pnl_usd", sa.Float, nullable=True),
    sa.Column("bot_variant", sa.String, nullable=True),
    sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
)


ambiguous_orders_table = sa.Table(
    "ambiguous_orders",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("market_slug", sa.String, nullable=False, index=True),
    sa.Column("interval_start", sa.Integer, nullable=False, index=True),
    sa.Column("phase", sa.String(20), nullable=False, index=True),
    sa.Column("side", sa.String(10), nullable=False),
    sa.Column("token_id", sa.String, nullable=False),
    sa.Column("up_token_id", sa.String, nullable=True),
    sa.Column("down_token_id", sa.String, nullable=True),
    sa.Column("requested_amount", sa.Float, nullable=False),
    sa.Column("reference_price", sa.Float, nullable=True),
    sa.Column("order_id", sa.String, nullable=True),
    sa.Column("state", sa.String(30), nullable=False, index=True, server_default="pending"),
    sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("fast_retries_done", sa.Integer, nullable=False, server_default="0"),
    sa.Column("next_retry_at_ts", sa.Float, nullable=False),
    sa.Column("last_error", sa.String, nullable=True),
    sa.Column("resolved_filled_shares", sa.Float, nullable=True),
    sa.Column("resolved_spent_usd", sa.Float, nullable=True),
    sa.Column("resolved_received_usd", sa.Float, nullable=True),
    sa.Column("resolved_fill_price", sa.Float, nullable=True),
    sa.Column("bot_variant", sa.String, nullable=True),
    sa.Column("created_at_ts", sa.Float, nullable=False),
    sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
)


def create_engine(database_url: str) -> sa.Engine:
    # Heroku uses postgres:// but SQLAlchemy requires postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return sa.create_engine(database_url, pool_pre_ping=True)


def create_tables(engine: sa.Engine) -> None:
    metadata.create_all(engine)
