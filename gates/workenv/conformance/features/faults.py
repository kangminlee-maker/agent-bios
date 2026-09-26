"""Faults: a process killed at a B03 fault point during one step, and started again.

`world.faults` names a step and a point. The driver arms that point on the step's message, and the
host kills its process when the code under test passes it (`call.point(name)`). A step whose
process answers anyway, or ends some other way, is `failed`, naming the point and the step: the
code under test never passed that point, or broke elsewhere. The driver then starts the process
again on the same state root. Without `observed_by` it resubmits the same request, unarmed, and that
answer is the step's. With `observed_by` no reply reaches the caller: the step has no answer to
hold, and what it minted is learned where a later answer first holds it; until then a digest of a
record resting on it is learned where an answer states it, and held to the record once it is
known. A fault on a step no code in scope serves is `blocked`: the driver cannot kill its own
answer.
"""
from __future__ import annotations

import executor


def install(run) -> None:
    faults = {fault["step"]: fault for fault in run.built.get("world", {}).get("faults", [])}

    def arm(run, step: dict, message: dict) -> None:
        fault = faults.get(step["name"])
        if fault is None:
            return
        if "entry" not in message and not message.get("addressed"):
            raise executor.Stop(executor.BLOCKED, f"{fault['point']} is armed on a step no code "
                                                  "in scope serves, and the driver cannot kill "
                                                  "its own answer", step=step["name"])
        message["arm"] = fault["point"]

    def restarted(run, step: dict, message: dict, reply: dict):
        fault = faults.get(step["name"])
        if fault is None:
            return reply
        process = step.get("process", executor.MAIN)
        host = run.processes.get(process)
        if "dead" not in reply or host is None or not host.killed():
            what = "answered anyway" if "dead" not in reply else reply["dead"]
            raise executor.Stop(executor.FAILED, f"{fault['point']} was armed on this step, and "
                                                 f"the process {what}", step=step["name"])
        run.restart(process)
        if "observed_by" in fault:
            run.pending.extend(run.minted_at.pop(step["name"], []))
            run.forget()
            return None
        return run.process(process).call({k: v for k, v in message.items() if k != "arm"})

    run.message_hooks.append(arm)
    run.reply_hooks.append(restarted)
