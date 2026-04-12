from typing import Protocol

from bot.models import LimitOrderIntent, MarketOrderIntent, MarketRules, OpenOrder, OrderReadiness, OrderResult, Trade


class ExchangeClient(Protocol):
    def bootstrap_live_trading(self, token_id: str) -> None:
        ...

    def get_mid_price(self, token_id: str) -> float:
        ...

    def get_market_rules(self, token_id: str) -> MarketRules | None:
        ...

    def get_open_orders(self, token_id: str) -> list[OpenOrder]:
        ...

    def get_order(self, order_id: str) -> OpenOrder | None:
        ...

    def place_limit_order(self, order: LimitOrderIntent) -> OrderResult:
        ...

    def place_market_order(self, order: MarketOrderIntent) -> OrderResult:
        ...

    def get_trades(self, token_id: str, after_timestamp: int | None = None) -> list[Trade]:
        ...

    def check_order_readiness(self, order: LimitOrderIntent | MarketOrderIntent) -> OrderReadiness:
        ...

    def cancel_order(self, order_id: str) -> bool:
        ...

    def cancel_all(self) -> bool:
        ...
