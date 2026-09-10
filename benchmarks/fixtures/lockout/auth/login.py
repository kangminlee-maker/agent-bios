"""Login attempt handling."""

MAX_FAILED_ATTEMPTS = 5


def is_locked(failed_count: int) -> bool:
    return failed_count >= MAX_FAILED_ATTEMPTS
