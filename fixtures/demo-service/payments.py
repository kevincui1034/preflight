"""Payment capture (demo fixture)."""

import os

import core
import db

# STRIPE_API_KEY is set on every dev laptop but NOT in the prod manifest
# (deploy/prod.env) — the classic it-works-on-my-machine deploy breaker.
STRIPE_API_KEY = os.environ["STRIPE_API_KEY"]


def charge(subtotal: float, discount_percent: float) -> dict:
    total = core.calculate_total(subtotal, discount_percent)
    db.connect()
    return {"amount": total, "key": STRIPE_API_KEY[:8]}
