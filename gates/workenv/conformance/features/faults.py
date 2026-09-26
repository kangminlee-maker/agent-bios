"""Faults: a process killed at a B03 fault point during one step, and started again.

`world.faults` names a step and a point. The driver arms that point on the step's message, and the
host kills its process when the code under test passes it (`call.point(name)`), after the process
has said which point it reached. A step whose process answers anyway, dies some other way, or
exits as if killed without reaching the armed point, is `failed`, naming the point and the step.
At `after_commit_before_return` the code under test hands the point the answer it committed
(`call.point(name, answer)`): the caller never receives it, but the driver judges it as the
step's answer, learning what it mints, so what a later step shows must be what was committed.
The driver then starts the process again on the same state root. Without `observed_by` it
resubmits the same request, unarmed, and that answer is held to the step's too: a restart that
lost the commit and answers afresh mints other values, and fails where they differ. With
`observed_by` no reply reaches the caller, and a later step shows what was committed. A fault on a
step no code in scope serves is `blocked`: the driver cannot kill its own answer.
"""
from __future__ import annotations

import executor

# The one point past the commit: the answer exists, and the caller has not received it.
COMMITTED = "after_commit_before_return"


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
        if "dead" not in reply or reply.get("reached") != fault["point"]:
            what = "answered anyway" if "dead" not in reply else reply["dead"]
            raise executor.Stop(executor.FAILED, f"{fault['point']} was armed on this step, and "
                                                 f"the process {what}", step=step["name"])
        if fault["point"] == COMMITTED:
            if reply.get("withheld") is None:
                raise executor.Stop(executor.FAILED, f"the process reached {COMMITTED} without "
                                                     "the answer it committed",
                                    step=step["name"])
            how = "addressed" if message.get("addressed") else "entry"
            answer = run.answer_of(step, {"answer": reply["withheld"]}, how, message.get("entry"))
            if "refused" in step:
                run.refused(step, answer, {})
            else:
                run.answered(step, answer)
                for hook in run.after_hooks:
                    hook(run, step, answer, how)
                run.judge_rules(step, answer)
        run.restart(process)
        if "observed_by" in fault:
            return None
        return run.process(process).call({k: v for k, v in message.items() if k != "arm"})

    run.message_hooks.append(arm)
    run.reply_hooks.append(restarted)
