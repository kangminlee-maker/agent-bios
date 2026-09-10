"""Login session handling for the customer-facing web app."""
from datetime import datetime, timedelta

# How long a login session stays valid before the user must re-authenticate.
SESSION_TIMEOUT_MINUTES = 30


def is_session_expired(issued_at: datetime, now: datetime) -> bool:
    return now - issued_at > timedelta(minutes=SESSION_TIMEOUT_MINUTES)


def remaining_seconds(issued_at: datetime, now: datetime) -> int:
    delta = timedelta(minutes=SESSION_TIMEOUT_MINUTES) - (now - issued_at)
    return max(0, int(delta.total_seconds()))
