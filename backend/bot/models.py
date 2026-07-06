from dataclasses import dataclass
from enum import Enum
from typing import Any


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class LimitOrderIntent:
    token_id: str
    side: Side
    price: float
    size: float

    @property
    def notional(self) -> float:
        return self.price * self.size


@dataclass(frozen=True)
class MarketOrderIntent:
    token_id: str
    side: Side
    amount: float
    reference_price: float | None = None
    allowed_slippage: float | None = None
    price_cap: float | None = None

    @property
    def price(self) -> float:
        return float(self.reference_price or 0.0)

    @property
    def size(self) -> float:
        if self.side == Side.BUY:
            if self.reference_price is None or self.reference_price <= 0:
                return 0.0
            return self.amount / self.reference_price
        return self.amount

    @property
    def notional(self) -> float:
        if self.side == Side.BUY:
            return self.amount
        if self.reference_price is None or self.reference_price <= 0:
            return 0.0
        return self.amount * self.reference_price


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    status: str
    raw: Any


@dataclass(frozen=True)
class MarketRules:
    tick_size: float
    min_order_size: float


@dataclass(frozen=True)
class OpenOrder:
    order_id: str
    token_id: str
    side: Side
    price: float
    size_matched: float | None = None
    original_size: float | None = None
    status: str | None = None


@dataclass(frozen=True)
class Trade:
    trade_id: str
    order_id: str
    token_id: str
    side: Side
    price: float
    size: float
    fee: float = 0.0
    timestamp: str | int | float | None = None


@dataclass(frozen=True)
class OrderReadiness:
    ready: bool
    reason: str
    balance: float | None = None
    allowance: float | None = None


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class OrderBookSnapshot:
    token_id: str
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    tick_size: float
    min_order_size: float
    timestamp: int = 0


@dataclass(frozen=True)
class StrategyContext:
    token_id: str
    mid_price: float
    open_orders: list[OpenOrder]
    position: dict | None
    market_rules: MarketRules | None


@dataclass(frozen=True)
class PlaceOrder:
    intent: LimitOrderIntent | MarketOrderIntent


@dataclass(frozen=True)
class CancelOrder:
    order_id: str
    reason: str = ""


StrategyAction = PlaceOrder | CancelOrder
