"""Webhook notifications (demo fixture)."""

import hashlib
import hmac

import core

# Hardcoded signing secret — should come from the environment.
WEBHOOK_SIGNING_SECRET = "whsec_9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c"


def sign(payload: bytes) -> str:
    return hmac.new(WEBHOOK_SIGNING_SECRET.encode(), payload, hashlib.sha256).hexdigest()


def notify_total(subtotal: float) -> str:
    total = core.calculate_total(subtotal)
    return sign(str(total).encode())
