"""Preflight review pipeline — stages designed as pure functions so they
wrap cleanly into RocketRide pipeline nodes.

Stage order: extract → graph upsert → traversals (Q1–Q4) → findings →
(deep only) Nebius judge + Daytona execution → callback to Butterbase.
"""

__version__ = "0.1.0"
