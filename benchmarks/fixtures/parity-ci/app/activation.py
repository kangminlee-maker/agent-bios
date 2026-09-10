"""Account activation. The v2 branch is being landed behind a default-off flag."""
import os

ACTIVATION_V2_ENABLED = os.environ.get("ACTIVATION_V2", "0") == "1"


def activate(user: dict) -> str:
    if ACTIVATION_V2_ENABLED:
        # v2: activation is idempotent and returns the prior state on repeat calls.
        if user.get("state") == "active":
            return "active"
        user["state"] = "active"
        return "activated"
    # v1: repeat activation raises, callers are expected to check first.
    if user.get("state") == "active":
        raise ValueError("already active")
    user["state"] = "active"
    return "activated"
