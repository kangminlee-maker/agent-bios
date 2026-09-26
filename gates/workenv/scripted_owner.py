"""A scripted owner: the executor's test double for the code that serves a case.

It answers each request-bearing step with the stated answer of the scenario `SCRIPTED_SCENARIO`
names, in the order the scenario states them, but mints every value of its own: a fresh id,
digest, instant or count of each stand-in's shape. It takes the public keys and signatures the
driver made from the records it is sent, and it computes every digest over the bytes it received
or wrote, as a real owner does. So a case passes against it only if the executor learned what it
minted, carried it where the scenario joins it, and recomputed what depends on it.

A request it has answered before, by the same bytes, gets the same answer: a replay writes
nothing new. `SCRIPTED_PLANTS` lists deliberate departures, each a negative control's single
difference:

  {"step": s, "path": "result" | "receipt" | "returned/<i>" | "refused/<i>",
   "pointer": p, "value": v}          replace one value of the answer to step s; without
                                     "value", remove it
  {"step": s, "admit": true}         call admitted() before refusing step s
  {"step": s, "answer": true}        answer step s, whose request the script refuses, with a
                                     result naming it

`journal` is a layer that answers addressed operations from the script and passes every other
call inward; `place` takes a given answer. Both append what they saw to `SCRIPTED_LOG`, one JSON
line each, so a test can read who ran on what.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import os
import pathlib
import secrets
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "conformance"))
import executor  # noqa: E402
from workenv.contracts import canonical  # noqa: E402

ADDRESSED = ("operation.query", "operation.cancel")
SUBSTITUTED = ("public_key", "sshsig")
_OWNER = None


def owner(call):
    global _OWNER
    if _OWNER is None:
        _OWNER = Owner(json.loads(pathlib.Path(os.environ["SCRIPTED_SCENARIO"]).read_bytes()),
                       json.loads(os.environ.get("SCRIPTED_PLANTS", "[]")), call.state / "owner")
    return _OWNER


def answer(call):
    return owner(call).answer(call)


def journal(call, inner):
    log({"layer": "journal", "operation": call.request["operation"],
         "request_id": call.request["request_id"], "given": call.given is not None})
    if call.request["operation"] in ADDRESSED:
        return owner(call).answer(call)
    return inner(call)


def place(call):
    log({"place": call.request["request_id"],
         "returned": len(call.given.get("returned", [])) if "result" in call.given else None})


def log(line: dict) -> None:
    path = os.environ.get("SCRIPTED_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as out:
            out.write(json.dumps(line) + "\n")


def fresh(shape: str):
    if shape == "digest":
        return hashlib.sha256(secrets.token_bytes(16)).hexdigest()
    if shape == "instant":
        start = datetime.datetime(2031, 1, 1, tzinfo=datetime.timezone.utc)
        moment = start + datetime.timedelta(seconds=secrets.randbelow(10 ** 8))
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    if shape == "integer":
        return 2 + secrets.randbelow(10 ** 6)
    return f"{shape}_{secrets.token_hex(16)}"


def substitutions(template, actual, found: dict) -> None:
    """What the driver put in place of the scenario's keys and signatures."""
    if isinstance(template, dict) and isinstance(actual, dict):
        for key, item in template.items():
            if key in SUBSTITUTED and isinstance(item, str) and isinstance(actual.get(key), str):
                if item != actual[key]:
                    found[item] = actual[key]
            elif key in actual:
                substitutions(item, actual[key], found)
    elif isinstance(template, list) and isinstance(actual, list):
        for left, right in zip(template, actual, strict=False):
            substitutions(left, right, found)


def substituted(value, found: dict):
    if isinstance(value, dict):
        return {k: (found.get(v, v) if k in SUBSTITUTED and isinstance(v, str)
                    else substituted(v, found)) for k, v in value.items()}
    if isinstance(value, list):
        return [substituted(item, found) for item in value]
    return value


class Owner:
    def __init__(self, built: dict, plants: list[dict], workdir: pathlib.Path):
        self.plants = plants
        self.steps = [step for step in built["steps"] if "request" in step]
        self.next = 0
        self.answered: dict[str, dict] = {}
        self.found: dict[str, str] = {}
        self.run = executor.Run(built, None, workdir, None)
        self.run.record_hooks.append(lambda run, name, value: substituted(value, self.found))

    def step_for(self, request: dict) -> dict:
        """The next step of the script sent under this request id; a step the driver gave
        instead of sending is passed over."""
        for index in range(self.next, len(self.steps)):
            step = self.steps[index]
            if self.run.templates[step["request"]]["request_id"] == request["request_id"]:
                self.next = index + 1
                return step
        raise ValueError(f"the script sends no further request {request['request_id']}")

    def answer(self, call) -> dict:
        step = self.step_for(call.request)
        sent = hashlib.sha256(canonical.encode(call.request)).hexdigest()
        if "replays" in step:
            if sent not in self.answered:
                raise ValueError(f"{step['name']} replays a request this owner never answered")
            try:
                return self.written(step, mint=False)
            finally:
                self.run.current = {}
                self.run.forget()
        run = self.run
        for name, record in zip([step["request"], *step["carries"]],
                                [call.request, *call.carried], strict=True):
            substitutions(run.templates[name], record, self.found)
        run.current = {step["request"]: call.request,
                       **dict(zip(step["carries"], call.carried, strict=True))}
        run.forget()
        try:
            if "refused" in step:
                if any(p["step"] == step["name"] and p.get("answer") for p in self.plants):
                    return {"result": {"kind": "operation_result", "schema": 1,
                                       "request_id": call.request["request_id"]},
                            "returned": [], "receipt": None}
                found = {"refused": run.positioned(step)}
                self.plant(step, found, "refused", call)
                return found
            found = self.written(step)
        finally:
            run.current = {}
            run.forget()
        self.answered[sent] = copy.deepcopy(found)
        return found

    def written(self, step: dict, mint: bool = True) -> dict:
        """The stated answer under values of this owner's own, minted afresh unless the step
        replays one it answered. A planted record is written as planted, and every other record
        of the answer is written over the bytes of the records it names, planted ones included,
        so a planted difference is consistent and shows where it was planted."""
        run = self.run
        if mint:
            for minted in run.minted_at.get(step["name"], []):
                run.learned[minted] = fresh(run.shapes[minted])
        run.forget()
        receipt = run.receipt_of_result(step["result"])
        names = [n for n in [*step["returns"], receipt, step["result"]]
                 if n is not None and n not in run.members]
        found = {"returned": [copy.deepcopy(run.value(n)) for n in step["returns"]],
                 "receipt": copy.deepcopy(run.materialize(receipt)) if receipt else None,
                 "result": copy.deepcopy(run.materialize(step["result"]))}
        planted = set()
        for part in ("returned", "receipt", "result"):
            planted |= self.plant(step, found, part)
        written = {**dict(zip(step["returns"], found["returned"], strict=True)),
                   step["result"]: found["result"]}
        if receipt:
            written[receipt] = found["receipt"]
        run.current.update(written)
        for _ in names:
            for name in names:
                if name not in planted:
                    run.current[name] = copy.deepcopy(run.fresh(name))
        found = {"returned": [run.current.get(n, found["returned"][i])
                              for i, n in enumerate(step["returns"])],
                 "receipt": run.current[receipt] if receipt else None,
                 "result": run.current[step["result"]]}
        return copy.deepcopy(found)

    def plant(self, step: dict, found: dict, part: str, call=None) -> set[str]:
        """Apply the plants aimed at one part of the answer; the names of the records changed."""
        changed = set()
        for plant in self.plants:
            if plant["step"] != step["name"]:
                continue
            if plant.get("admit"):
                if call is not None:
                    call.admitted()
                continue
            if "path" not in plant:
                continue
            head, _, index = plant["path"].partition("/")
            if head != part:
                continue
            if head == "returned":
                changed.add(step["returns"][int(index)])
            elif head in ("receipt", "result"):
                changed.add(self.run.receipt_of_result(step["result"]) if head == "receipt"
                            else step["result"])
            target = found[head] if not index else found[head][int(index)]
            if "value" in plant:
                executor.put(target, plant["pointer"], plant["value"])
            else:
                *path, last = executor.segments(plant["pointer"])
                for key in path:
                    target = target[int(key)] if isinstance(target, list) else target[key]
                del target[int(last) if isinstance(target, list) else last]
        return changed
