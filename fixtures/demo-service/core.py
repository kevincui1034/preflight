"""Order math — the hub module everything imports (load-bearing)."""

TAX_RATE = 0.0875


def apply_discount(subtotal: float, percent: float) -> float:
    return round(subtotal * (1 - percent / 100), 2)


def calculate_total(subtotal: float, discount_percent: float = 0.0) -> float:
    # BUG (deliberate, for the demo): the discount is never applied, so
    # customers are overcharged. tests/test_core.py catches this.
    taxed = subtotal * (1 + TAX_RATE)
    return round(taxed, 2)
