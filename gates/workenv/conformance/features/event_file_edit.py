"""The file edit: a change the person makes in their checkout between two steps.

A `file_edit` event names the step it comes before and a path in the checkout: it writes the
event's bytes there, or with `absent` removes the file or the whole directory. The checkout is the
one the checkout feature built; an edit reaching outside it is `failed` by name, and a scenario
with an edit but no checkout is `blocked`.
"""
from __future__ import annotations

import shutil

import executor


def install(run) -> None:
    edits = [event for event in run.built.get("world", {}).get("events", [])
             if event["kind"] == "file_edit"]

    def edit(run, step: dict) -> None:
        for event in edits:
            if event["before"] != step["name"]:
                continue
            checkout = run.checkout
            if checkout is None:
                raise executor.Stop(executor.BLOCKED, f"a file edit of {event['path']} comes "
                                                      "before this step, and the run has no "
                                                      "checkout", step=step["name"])
            target = (checkout / event["path"]).resolve()
            if target != checkout and checkout not in target.parents:
                raise executor.Stop(executor.FAILED, f"the file edit of {event['path']} reaches "
                                                     "outside the checkout", step=step["name"])
            if event.get("absent"):
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(event["bytes"].encode("utf-8"))

    # The person's edit lands before the step, and before anything the driver reads for it.
    run.before_hooks.insert(0, edit)
