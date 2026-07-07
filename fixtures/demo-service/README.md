# demo-service (fixture)

A small order service with deliberate deploy-breakers, so every Preflight
finding fires deterministically on stage:

- `payments.py` reads `STRIPE_API_KEY`, which `deploy/prod.env` does not
  set → **prod env gap** (graph Q3).
- `notifications.py` hardcodes a webhook signing secret → **secret scan**.
- `core.py` has a discount bug; `tests/test_core.py` fails → surfaced by
  the **Daytona deep-review run**.
- `core.py` is imported by app, payments, notifications, reports, and
  workers → **load-bearing hub** (graph Q2), and the changed files
  (`.preflight-changed`: payments.py, core.py) have a wide **blast
  radius** (graph Q1).
