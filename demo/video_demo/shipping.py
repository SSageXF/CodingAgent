"""Shipping price rules for the EvidenceCoder video demo."""

FREE_SHIPPING_THRESHOLD = 100.0
STANDARD_SHIPPING_FEE = 8.0


def shipping_fee(order_total: float) -> float:
    """Return zero at or above the free-shipping threshold."""
    if order_total > FREE_SHIPPING_THRESHOLD:
        return 0.0
    return STANDARD_SHIPPING_FEE


def checkout_total(order_total: float) -> float:
    """Return the order total including any shipping fee."""
    return order_total + shipping_fee(order_total)
