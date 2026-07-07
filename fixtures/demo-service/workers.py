"""Background jobs (demo fixture)."""

import core
import payments


def retry_failed_charges(queue: list[dict]) -> list[dict]:
    return [payments.charge(item["subtotal"], item.get("discount", 0.0)) for item in queue]


def reprice(subtotals: list[float]) -> list[float]:
    return [core.calculate_total(s) for s in subtotals]
