"""Qualified routes: a delivery route a real run of the installed host qualified.

A delivery is supported on a host only where the latest probe of that recipient's delivery
capability on it ran for real and worked (C12). Only the installed host itself can make that
run, through its adapter, and no driver run has one: that evidence is the real adapter
qualification family's (N23), measured on the machine. A scenario that delivers states the probe
as a `capability.probe` step with its result. Before the first step this has the driver give each
such step, so its stated probe is placed as given state, which the code under test reads as it
reads a probe it kept. A probe of any other capability is not given here.
"""
from __future__ import annotations

import cases


def install(run) -> None:
    run.prepare_hooks.append(build)


def build(run) -> None:
    run.given_steps |= set(cases.delivery_probes(run.built))
