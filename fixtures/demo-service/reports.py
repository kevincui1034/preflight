"""Daily revenue report (demo fixture)."""

import core


def daily_revenue(orders: list[tuple[float, float]]) -> float:
    return round(sum(core.calculate_total(s, d) for s, d in orders), 2)
