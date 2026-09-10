"""The v2 contract, written ahead of the cutover so CI shows the gap."""
import app.activation as activation


def test_activate_fresh_user():
    assert activation.activate({"state": "new"}) == "activated"


def test_activation_branch_would_fail_today():
    # v2 semantics: repeat activation is idempotent. Red until ACTIVATION_V2 ships
    # as the default; the cutover decision owns flipping it.
    user = {"state": "active"}
    assert activation.activate(user) == "active"
