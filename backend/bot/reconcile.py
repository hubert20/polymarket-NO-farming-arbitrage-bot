from decimal import Decimal, InvalidOperation

from bot.models import LimitOrderIntent, OpenOrder


_NON_WORKING_STATUSES = {"CANCELED", "CANCELLED", "FILLED", "REJECTED", "EXPIRED"}


def has_nearby_open_order(
    intent: LimitOrderIntent,
    open_orders: list[OpenOrder],
    tick_size: float,
    tolerance_ticks: int,
) -> bool:
    tolerance = Decimal(str(max(tolerance_ticks, 0))) * Decimal(str(max(tick_size, 0.0)))
    for order in open_orders:
        if order.side != intent.side:
            continue
        if order.status and order.status.strip().upper() in _NON_WORKING_STATUSES:
            continue
        if _price_distance(order.price, intent.price) <= tolerance:
            return True
    return False


def _price_distance(a: float, b: float) -> Decimal:
    try:
        return abs(Decimal(str(a)) - Decimal(str(b)))
    except (InvalidOperation, ValueError):
        return Decimal("Infinity")
