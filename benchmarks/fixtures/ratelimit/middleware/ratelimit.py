"""Global rate limiting for the public API."""

RATE_LIMIT_ENABLED = True
MAX_REQUESTS_PER_MINUTE = 60


def check_rate_limit(client_ip, counter):
    """Return True if the request is allowed, False if it should be throttled."""
    if not RATE_LIMIT_ENABLED:
        return True
    return counter.get(client_ip, 0) < MAX_REQUESTS_PER_MINUTE
