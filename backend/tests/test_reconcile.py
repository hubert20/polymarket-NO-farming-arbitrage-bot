from bot.models import LimitOrderIntent, OpenOrder, Side
from bot.reconcile import has_nearby_open_order


def _intent(price: float = 0.50, side: Side = Side.BUY) -> LimitOrderIntent:
    return LimitOrderIntent(token_id="token", side=side, price=price, size=10.0)


def test_has_nearby_open_order_exact_match() -> None:
    intent = _intent(price=0.50, side=Side.BUY)
    open_orders = [
        OpenOrder(order_id="1", token_id="token", side=Side.BUY, price=0.50, status="OPEN")
    ]
    assert has_nearby_open_order(intent, open_orders, tick_size=0.01, tolerance_ticks=0)


def test_has_nearby_open_order_with_tolerance() -> None:
    intent = _intent(price=0.50, side=Side.BUY)
    open_orders = [
        OpenOrder(order_id="1", token_id="token", side=Side.BUY, price=0.51, status="OPEN")
    ]
    assert has_nearby_open_order(intent, open_orders, tick_size=0.01, tolerance_ticks=1)


def test_ignores_non_working_status() -> None:
    intent = _intent(price=0.50, side=Side.BUY)
    open_orders = [
        OpenOrder(order_id="1", token_id="token", side=Side.BUY, price=0.50, status="FILLED")
    ]
    assert not has_nearby_open_order(intent, open_orders, tick_size=0.01, tolerance_ticks=0)


def test_ignores_other_side() -> None:
    intent = _intent(price=0.50, side=Side.BUY)
    open_orders = [
        OpenOrder(order_id="1", token_id="token", side=Side.SELL, price=0.50, status="OPEN")
    ]
    assert not has_nearby_open_order(intent, open_orders, tick_size=0.01, tolerance_ticks=0)

