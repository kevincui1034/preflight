"""Database connection (demo fixture)."""

import os

DATABASE_URL = os.environ["DATABASE_URL"]


def connect():
    return {"dsn": DATABASE_URL}
