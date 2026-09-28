"""The lost reply: a request whose effect the owner hands on to a host or a provider, and whose
reply never comes back.

A `reply_lost` event names an answered step. The owner answers that step as the code in scope
answers the operation while the reply it handed on is outstanding: through the entry the serving
table names for the operation's lost reply (`reply_lost` on its row, `Routing.lost`), in place of
the entry that answers once the reply has come. No reply follows, so that answer stands, and a
later step sees what the owner holds. A step whose operation names no such entry in scope, or
that no code in scope serves, is `blocked` by name: the driver cannot lose the reply of its own
given answer.
"""
from __future__ import annotations

import executor


def install(run) -> None:
    lost = {event["step"] for event in run.built.get("world", {}).get("events", [])
            if event["kind"] == "reply_lost"}

    def handed_on(run, step: dict, message: dict) -> None:
        if step["name"] not in lost:
            return
        operation = message["request"].get("operation")
        entry = run.routing.lost.get(operation)
        if entry is None or "entry" not in message:
            raise executor.Stop(executor.BLOCKED, f"its reply is lost, and no code in scope "
                                                  f"answers {operation} while its reply is "
                                                  "outstanding, so no lost reply of it runs yet",
                                step=step["name"])
        message["entry"] = entry

    run.message_hooks.append(handed_on)
