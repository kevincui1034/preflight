"""Entry point (demo fixture)."""

import core
import notifications
import payments
import reports


def checkout(subtotal: float, discount_percent: float) -> dict:
    receipt = payments.charge(subtotal, discount_percent)
    notifications.notify_total(subtotal)
    return receipt


def summary(orders) -> dict:
    return {"revenue": reports.daily_revenue(orders), "tax_rate": core.TAX_RATE}
