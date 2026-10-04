"""A scripted owner: the executor's test double for the code that serves a case.

It answers each request-bearing step with the stated answer of the scenario `SCRIPTED_SCENARIO`
names, in the order the scenario states them, but mints every value of its own: a fresh id,
digest, instant or count of each stand-in's shape. It takes the public keys and signatures the
driver made from the records it is sent, and it computes every digest over the bytes it received
or wrote, as a real owner does. So a case passes against it only if the executor learned what it
minted, carried it where the scenario joins it, and recomputed what depends on it: it holds each
request and record it is sent to the values it minted and the digests it can compute wherever the
scenario joins one, and raises on another.

It reads the world it runs in as a real owner does: where it runs in a git checkout, a file digest
the scenario states is the digest of the file at that path, the checkout path is the directory it
runs in and a stated commit is HEAD. A scenario with several checkouts is read one checkout at a
time, where the first step working in it runs (the checkout feature says which records and steps
speak of which), and a binding's commit is that checkout's HEAD when the step returning it runs.
The guide a routing's usage contract points at is the one its `workenv` package ships at that
path, wherever it runs. It keeps what it has written under
the call's state root and passes every B03 fault point, committing before
`after_commit_before_return` and handing that point the answer it committed, so a process killed
at a point and started again answers as a restarted owner does: with what it committed, or
afresh when it was killed before committing.

A request it has answered before, by the same bytes, gets the same answer: a replay writes
nothing new. `SCRIPTED_PLANTS` lists deliberate departures, each a negative control's single
difference:

  {"step": s, "path": "result" | "receipt" | "returned/<i>" | "refused/<i>",
   "pointer": p, "value": v}          replace one value of the answer to step s; without
                                     "value", remove it
  {"step": s, "admit": true}         call admitted() before refusing step s
  {"step": s, "answer": true}        answer step s, whose request the script refuses, with a
                                     result naming it
  {"step": s, "forget": true}        commit nothing durable for step s, so a restart loses it

`journal` is a layer that answers addressed operations from the script and passes every other
call inward; `place` takes a given answer. They and the owner append what they saw to
`SCRIPTED_LOG`, one JSON line each, so a test can read who ran on what.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import os
import pathlib
import secrets
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "conformance"))
import executor  # noqa: E402
import host as hosts  # noqa: E402
import cases  # noqa: E402
from features import checkout, revision_bytes, shipped_guide  # noqa: E402
import workenv  # noqa: E402
from workenv.contracts import b03, canonical  # noqa: E402

ADDRESSED = ("operation.query", "operation.cancel")
SUBSTITUTED = ("public_key", "sshsig")
COMMIT_POINT = "after_commit_before_return"
_OWNER = None


def owner(call):
    global _OWNER
    if _OWNER is None:
        _OWNER = Owner(json.loads(pathlib.Path(os.environ["SCRIPTED_SCENARIO"]).read_bytes()),
                       json.loads(os.environ.get("SCRIPTED_PLANTS", "[]")), call.state)
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
        return {k: substituted(v, found) for k, v in value.items()}
    if isinstance(value, list):
        return [substituted(item, found) for item in value]
    return found.get(value, value) if isinstance(value, str) else value


def world(run) -> dict[str, str]:
    """The digest of the bytes the person holds for each member of a revision they commit that
    the scenario states by digest alone, and of the guide its package ships where a routing's
    usage contract points."""
    found = stated_bytes(run)
    for name in cases.guide_pointers(run.built):
        guide = run.templates[name]["delivery"]["memory_usage"]["guide"]
        digest = shipped_guide.shipped(pathlib.Path(workenv.__file__).parent.parent, guide["path"])
        if digest is not None:
            found.setdefault(guide["digest"], digest)
    return found


def checkout_facts(run, plan, key, here: pathlib.Path) -> dict[str, str]:
    """What the stated facts of one checkout are where this owner runs in it: the digests of the
    files the records speaking of it state at their paths, its directory, and its HEAD for each
    commit a binding made in it states."""
    joined = {(j["record"], j["pointer"]) for j in run.built["joins"]}
    edited = {event.get("digest") for event in run.built.get("world", {}).get("events", [])
              if event["kind"] == "file_edit"}
    found = {}
    for name, record in run.templates.items():
        stated = checkout.places(run, name, record)
        if stated and checkout.place_key(run, plan, name, record) == key:
            for pointer, entry in stated:
                target = here / entry["path"]
                if (name, pointer + "/digest") not in joined and target.is_file() \
                        and entry["digest"] not in edited:
                    found.setdefault(entry["digest"],
                                     hashlib.sha256(target.read_bytes()).hexdigest())
        commit = stated_commit(run, name)
        if commit and plan.record_key(name, "the binding") == key:
            found[commit] = head(here)
    if key in plan.paths:
        found[key] = str(here)
    for place in checkout.worked_in(run.templates):
        if place == key or (place not in plan.paths and key == plan.default()):
            found[place] = str(here)
    return found


def stated_commit(run, name: str) -> str | None:
    """The commit a binding states it observed, where the scenario joins it to nothing."""
    record = run.templates.get(name, {})
    seen = record.get("observed") if record.get("kind") == "repository_binding" else None
    if isinstance(seen, dict) and seen.get("commit") and not any(
            join["pointer"] == "/observed/commit" for join in run.joins.get(name, [])):
        return seen["commit"]
    return None


def head(here: pathlib.Path) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=here, env=env, capture_output=True,
                          text=True).stdout.strip()


def stated_bytes(run) -> dict[str, str]:
    found = {}
    for name, pointer in cases.stated_revision_members(run.built):
        member = executor.at(run.templates[name], pointer)[1]
        data = revision_bytes.made(member["digest"], member["size"])
        found[member["digest"]] = hashlib.sha256(data).hexdigest()
    return found


class Owner:
    def __init__(self, built: dict, plants: list[dict], state: pathlib.Path):
        self.plants = plants
        self.steps = [step for step in built["steps"] if "request" in step]
        self.saved = state / "owner.json"
        self.run = executor.Run(built, None, state / "owner", None)
        self.run.record_hooks.append(lambda run, name, value: substituted(value, self.found))
        # The digests it mints for files it reads are those of the files in the checkout they
        # are in, and a file a record it returns says it wrote is written there.
        here = (pathlib.Path.cwd() / ".git").exists()
        self.plan = checkout.Plan(self.run) if here else None
        self.files, self.writes, self.dirs = {}, {}, {}
        if here:
            written = checkout.written(self.run, self.plan)
            self.files = checkout.file_digests(self.run, self.plan, written)
            minted = {(j["record"], j["pointer"]): j["minted"] for j in built["joins"]
                      if "minted" in j}
            for record, members in written.items():
                for pointer, (key, path) in members.items():
                    self.writes[minted[(record, pointer + "/digest")]] = (
                        key, path, minted[(record, pointer + "/size")])
        # Started again on a state root it wrote: the first request may be the one it was
        # answering when it was killed.
        self.restarted = self.saved.exists()
        if self.restarted:
            kept = hosts.decode(json.loads(self.saved.read_text()))
            self.next, self.answered, self.found = kept["next"], kept["answered"], kept["found"]
            self.run.learned, self.dirs = kept["learned"], kept["dirs"]
        else:
            self.next, self.answered, self.found = 0, {}, world(self.run)

    def save(self) -> None:
        """What this owner has committed, durably, under its state root."""
        kept = {"next": self.next, "answered": self.answered, "found": self.found,
                "learned": self.run.learned, "dirs": self.dirs}
        self.saved.write_text(json.dumps(hosts.encode(kept)))

    def step_for(self, request: dict) -> dict:
        """The next step of the script sent under this request id; a step the driver gave
        instead of sending is passed over. A request id the entry mints is the one this owner
        minted where it answered first."""
        for index in range(self.next, len(self.steps)):
            step = self.steps[index]
            if self.run.materialize(step["request"])["request_id"] == request["request_id"]:
                self.next = index + 1
                return step
        raise ValueError(f"the script sends no further request {request['request_id']}")

    def answer(self, call) -> dict:
        log({"answer": call.request["request_id"]})
        sent = hashlib.sha256(canonical.encode(call.request)).hexdigest()
        restarted, self.restarted = self.restarted, False
        if restarted and sent in self.answered:
            # The request it was killed answering, sent again: what it committed is the answer.
            return copy.deepcopy(self.answered[sent])
        step = self.step_for(call.request)
        self.entered(step)
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
        self.carried_as_joined(step, [call.request, *call.carried])
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
        for point in b03.FAULT_POINTS[:b03.FAULT_POINTS.index(COMMIT_POINT)]:
            call.point(point)
        self.answered[sent] = copy.deepcopy(found)
        if not any(p["step"] == step["name"] and p.get("forget") for p in self.plants):
            self.save()
        call.point(COMMIT_POINT, copy.deepcopy(found))
        for point in b03.FAULT_POINTS[b03.FAULT_POINTS.index(COMMIT_POINT) + 1:]:
            call.point(point)
        return found

    def known(self, name: str, seen: set | None = None) -> bool:
        """Whether this owner holds every value a record rests on: each value minted into it was
        minted here, and each record it names by digest is known in turn."""
        seen = set() if seen is None else seen
        if name in seen or name in self.run.members:
            return True
        seen.add(name)
        for join in self.run.joins.get(name, []):
            if "minted" in join:
                if join["minted"] not in self.run.learned:
                    return False
            elif not self.known(join["digest_of"], seen):
                return False
        return True

    def carried_as_joined(self, step: dict, received: list) -> None:
        """What the driver sent holds, wherever the scenario joins one, each value this owner
        minted and the digest of each record whose values it all holds; another value there is
        the driver carrying the wrong one, which an owner answering as stated would not see."""
        run = self.run
        run.forget()
        for name, value in zip([step["request"], *step["carries"]], received, strict=True):
            for join in run.joins.get(name, []):
                if "minted" in join:
                    if join["minted"] not in run.learned:
                        continue
                    expected = run.learned[join["minted"]]
                elif self.known(join["digest_of"]):
                    expected = run.digest(join["digest_of"])
                else:
                    continue
                held = executor.at(value, join["pointer"])[1]
                if held != expected:
                    raise ValueError(f"{name}{join['pointer']} arrived as {held!r}, where this "
                                     f"owner holds {expected!r}")

    def entered(self, step: dict) -> None:
        """The checkout the step works in, read where this owner runs now the first time a step
        works in it; and its HEAD read again for each binding the step returns."""
        if self.plan is None:
            return
        here = pathlib.Path.cwd()
        key = self.plan.step_key(step)
        key = self.plan.default() if key is None else key
        if key not in self.dirs:
            self.dirs[key] = str(here)
            for stated, value in checkout_facts(self.run, self.plan, key, here).items():
                self.found.setdefault(stated, value)
        for name in step.get("returns", []):
            commit = stated_commit(self.run, name)
            if commit:
                self.found[commit] = head(here)

    def place(self, key) -> pathlib.Path:
        """The directory of a checkout this owner has worked in, else the one it runs in now."""
        return pathlib.Path(self.dirs.get(key, pathlib.Path.cwd()))

    def written(self, step: dict, mint: bool = True) -> dict:
        """The stated answer under values of this owner's own, minted afresh unless the step
        replays one it answered. A planted record is written as planted, and every other record
        of the answer is written over the bytes of the records it names, planted ones included,
        so a planted difference is consistent and shows where it was planted."""
        run = self.run
        if mint:
            for minted in run.minted_at.get(step["name"], []):
                read = self.files.get(minted)
                target = None if read is None else self.place(read[1]) / read[2]
                if target is not None and target.is_file():
                    run.learned[minted] = hashlib.sha256(target.read_bytes()).hexdigest()
                else:
                    run.learned[minted] = fresh(run.shapes[minted])
            for minted in run.minted_at.get(step["name"], []):
                if minted in self.writes:
                    key, path, size = self.writes[minted]
                    data = f"{step['name']} {secrets.token_hex(8)}\n".encode()
                    target = self.place(key) / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    run.learned[minted] = hashlib.sha256(data).hexdigest()
                    run.learned[size] = len(data)
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
