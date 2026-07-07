import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core


def test_tax_applied():
    assert core.calculate_total(100.0) == 108.75


def test_discount_applied():
    # 20% off 100 = 80, taxed = 87.00 — fails against the deliberate bug.
    assert core.calculate_total(100.0, discount_percent=20.0) == 87.0
