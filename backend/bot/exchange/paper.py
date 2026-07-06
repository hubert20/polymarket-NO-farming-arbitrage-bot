import time

from bot.models import (
    LimitOrderIntent,
    MarketOrderIntent,
    MarketRules,
    OpenOrder,
    OrderBookLevel,
    OrderBookSnapshot,
    OrderReadiness,
    OrderResult,
    Trade,
)
from bot.time_utils import to_epoch_seconds


class PaperExchangeClient:
    def __init__(
        self,
        initial_mid: float = 0.50,
        tick_size: float = 0.01,
        min_order_size: float = 1.0,
        initial_collateral_balance: float = 100.0,
    ) -> None:
        self.mid = initial_mid
        self._tick_size = tick_size
        self._min_order_size = min_order_size
        self._counter = 0
        self._open_orders: list[OpenOrder] = []
        self._trades: list[Trade] = []
        self._conditional_balances: dict[str, float] = {}
        self._collateral_balance = float(initial_collateral_balance)
        self._orders_by_id: dict[str, OpenOrder] = {}

    def set_mid(self, value: float) -> None:
        self.mid = value

    def bootstrap_live_trading(self, token_id: str | None = None) -> None:
        _ = token_id
        return None

    def get_mid_price(self, token_id: str) -> float:
        _ = token_id
        return self.mid

    def get_market_rules(self, token_id: str) -> MarketRules:
        _ = token_id
        return MarketRules(tick_size=self._tick_size, min_order_size=self._min_order_size)

    def get_order_book(self, token_id: str) -> OrderBookSnapshot:
        _ = token_id
        bid = max(self.mid - self._tick_size, self._tick_size)
        ask = max(self.mid, self._tick_size)
        return OrderBookSnapshot(
            token_id=token_id,
            bids=(OrderBookLevel(price=bid, size=1_000.0),),
            asks=(OrderBookLevel(price=ask, size=1_000.0),),
            tick_size=self._tick_size,
            min_order_size=self._min_order_size,
            timestamp=int(time.time() * 1000),
        )

    def get_open_orders(self, token_id: str) -> list[OpenOrder]:
        return [o for o in self._open_orders if o.token_id == token_id]

    def get_order(self, order_id: str) -> OpenOrder | None:
        return self._orders_by_id.get(order_id)

    def place_limit_order(self, order: LimitOrderIntent) -> OrderResult:
        self._counter += 1
        oid = f"paper-{int(time.time())}-{self._counter}"
        snapshot = OpenOrder(
            order_id=oid,
            token_id=order.token_id,
            side=order.side,
            price=order.price,
            original_size=order.size,
            status="OPEN",
        )
        self._open_orders.append(snapshot)
        self._orders_by_id[oid] = snapshot
        return OrderResult(order_id=oid, status="simulated", raw={"order": order})

    def place_market_order(self, order: MarketOrderIntent) -> OrderResult:
        self._counter += 1
        oid = f"paper-{int(time.time())}-{self._counter}"
        execution_price = max(float(order.reference_price or self.mid), self._tick_size)
        if order.side.value == "SELL":
            size = min(order.amount, self._conditional_balances.get(order.token_id, 0.0))
            received_usd = size * execution_price
            self._conditional_balances[order.token_id] = max(
                0.0, self._conditional_balances.get(order.token_id, 0.0) - size
            )
            self._collateral_balance += received_usd
            raw = {
                "order": order,
                "_market_price": execution_price,
                "_buffered_price": execution_price,
                "_fill_price": execution_price,
                "makingAmount": str(size),
                "takingAmount": str(received_usd),
            }
        else:
            spent_usd = min(float(order.amount), self._collateral_balance)
            size = (spent_usd / execution_price) if execution_price > 0 else 0.0
            self._conditional_balances[order.token_id] = (
                self._conditional_balances.get(order.token_id, 0.0) + size
            )
            self._collateral_balance = max(0.0, self._collateral_balance - spent_usd)
            raw = {
                "order": order,
                "_market_price": execution_price,
                "_buffered_price": execution_price,
                "_fill_price": execution_price,
                "makingAmount": str(spent_usd),
                "takingAmount": str(size),
            }
        self._trades.append(
            Trade(
                trade_id=f"{oid}-fill",
                order_id=oid,
                token_id=order.token_id,
                side=order.side,
                price=execution_price,
                size=size,
                timestamp=int(time.time()),
            )
        )
        self._orders_by_id[oid] = OpenOrder(
            order_id=oid,
            token_id=order.token_id,
            side=order.side,
            price=execution_price,
            size_matched=size,
            original_size=size,
            status="matched",
        )
        return OrderResult(order_id=oid, status="matched", raw=raw)

    def warm_token_cache(self, token_id: str) -> None:
        _ = token_id

    def prepare_sell(self, token_id: str) -> bool:
        _ = token_id
        return True

    def get_conditional_balance(self, token_id: str) -> float:
        return float(self._conditional_balances.get(token_id, 0.0))

    def get_collateral_balance(self) -> float:
        return float(self._collateral_balance)

    def get_trades(self, token_id: str, after_timestamp: int | None = None) -> list[Trade]:
        trades = [t for t in self._trades if t.token_id == token_id]
        if after_timestamp is None:
            return trades

        filtered: list[Trade] = []
        for trade in trades:
            ts = to_epoch_seconds(trade.timestamp)
            if ts is None or ts > after_timestamp:
                filtered.append(trade)
        return filtered

    def check_order_readiness(self, order: LimitOrderIntent | MarketOrderIntent) -> OrderReadiness:
        _ = order
        return OrderReadiness(ready=True, reason="paper_exchange")

    def cancel_order(self, order_id: str) -> bool:
        self._open_orders = [o for o in self._open_orders if o.order_id != order_id]
        return True

    def cancel_all(self) -> bool:
        self._open_orders.clear()
        return True
