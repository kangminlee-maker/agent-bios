"""The clock: the scenario's time, which each step states.

With `world.clock` the generator states on every step the instant it runs at (`at`): the clock
starts at `start`, and a step moves it by `advance_seconds` before it runs. The call's `now` is that
instant, so code under test that asks the call for the time gets the scenario's.
"""
from __future__ import annotations


def install(run) -> None:
    run.message_hooks.append(stamp)


def stamp(run, step: dict, message: dict) -> None:
    message["now"] = step.get("at")
