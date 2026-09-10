"""Password rules for account signup."""

MIN_PASSWORD_LENGTH = 8


def is_valid_password(pw: str) -> bool:
    return len(pw) >= MIN_PASSWORD_LENGTH
