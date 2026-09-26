"""The executor: one case's frozen scenario, run step by step against the code that serves it.

A scenario (`gates/workenv/scenarios.py` writes it) states every record a case submits and every
answer it expects, with stand-ins where the owner mints a value. This module submits those
records to the code under test and holds each answer to the stated one. For one step:

  1. Build the request and the records it carries. Every minted stand-in `joins` places is
     replaced by the value the owner actually returned, every digest `joins` derives is
     recomputed over the bytes it names, and a size stated beside such a digest is recomputed
     with it. A step that `replays` an earlier one resubmits the bytes that step sent.
  2. Route it by the serving table: an operation a node in the profile's scope serves is
     submitted to that node's entry; an addressed operation (`operation.query`,
     `operation.cancel`) is submitted to the layers, the journal answering it, when the journal
     layer is in scope; every other step is given.
  3. A given step is answered by the driver with its stated answer, the values it mints standing
     as the scenario states them, and the records it returns are handed to every `places` entry
     in scope. The layers in scope run on a given step as on any other.
  4. Learn each value the step mints at its first place in the answer, and refuse one that is
     not of its shape.
  5. Hold the answer to the stated one: its result, then its receipt, then each record it
     returns, by position. Minted places hold what was learned, and a digest of a record this
     answer returns is the digest of what the owner actually returned, so a difference is
     reported where it is, not as the digest that names it. The first difference is `failed`,
     naming the step, the record and the JSON pointer.
  6. A refused step must be refused with exactly the stated triples, and without calling
     `admitted()`. A triple names its record by position: `request`, or `carried/<i>` for the
     step's i-th carried record, because the code under test never sees the scenario's names.

The receipt a step is held to is the one its stated result names: its own when it committed,
the earlier step's for an answer stated `receipt_of` it, and for a replay the replayed step's.
So a replay or a settled duplicate that writes a new receipt differs from the stated one, and
neither needs more than the core to be judged.

Everything beyond that is a feature, one module under `features/` that `install(run)` hooks into
the run. A case whose scenario uses a feature with no module is `blocked` by name before any
step runs, and so is a case whose registry row names runtime rules: applying the rule oracles is
not built yet. A step whose entry, layer or place has not been written is `blocked` naming it.

The code under test runs in host processes (`host.py`), one per world process, each with its own
state root; the call it receives and the answer it gives are the adapter design's
(`design/knowledge-and-history/2026-09-24T2124--0fe13da--conformance-adapter-design.md`).
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cases  # noqa: E402
import host as hosts  # noqa: E402
from workenv.contracts import canonical, examples, records  # noqa: E402
from workenv.contracts.schema import STORED  # noqa: E402

PASSED = "passed"
FAILED = "failed"
BLOCKED = "blocked"

FEATURES = pathlib.Path(__file__).resolve().parent / "features"
# A scenario without world processes runs every step on this one.
MAIN = "main"
# Where a stated result names the receipt it is answered with.
RECEIPT = "/outcome/receipt_digest"
REQUEST, CARRIED = "request", "carried"
# What a minted value must look like, by the shape the scenario mints it as.
SHAPES = {"digest": re.compile(r"[0-9a-f]{64}\Z"),
          "instant": re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")}
ID = r"{}_[0-9a-f]{{32}}\Z"
_SCHEMAS: dict = {}


class Stop(Exception):
    """Ends a case with its outcome, and where it ended."""

    def __init__(self, outcome: str, why: str, step: str | None = None,
                 record: str | None = None, pointer: str | None = None):
        super().__init__(why)
        self.outcome, self.why = outcome, why
        self.step, self.record, self.pointer = step, record, pointer

    def report(self) -> dict:
        found = {"outcome": self.outcome, "why": self.why}
        for key in ("step", "record", "pointer"):
            if getattr(self, key) is not None:
                found[key] = getattr(self, key)
        return found


class Routing:
    """Which code in a profile's scope answers a step.

    `entries` maps each operation a node in scope serves to its entry; `addressed` holds the
    operations that target a request rather than name a server; `layers` are the layer entries in
    scope, outermost first; `places` the place entries in scope; `journal` whether the journal
    layer is among them, which is what answers an addressed operation.
    """

    def __init__(self, entries: dict[str, str], addressed: set[str], layers: list[str],
                 places: list[str], journal: bool):
        self.entries, self.addressed = entries, addressed
        self.layers, self.places, self.journal = layers, places, journal

    def route(self, operation: str) -> tuple[str, str | None]:
        if operation in self.addressed:
            return ("addressed", None) if self.journal else ("given", None)
        entry = self.entries.get(operation)
        return ("entry", entry) if entry else ("given", None)


def routing(serving: dict, reach: set[str]) -> Routing:
    """The routing a profile whose scope is `reach` runs under, read from the serving table."""
    rows = serving["operations"]
    layers = [layer for layer in serving.get("layers", []) if layer.get("node") in reach]
    return Routing({op: row["entry"] for op, row in rows.items()
                    if not row.get("addressed") and row.get("node") in reach},
                   {op for op, row in rows.items() if row.get("addressed")},
                   [layer["entry"] for layer in layers],
                   [entry for node, entry in sorted(serving.get("places", {}).items())
                    if node in reach],
                   any(layer.get("name") == cases.JOURNAL for layer in layers))


def segments(pointer: str) -> list[str]:
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]


def escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def at(document, pointer: str) -> tuple[bool, object]:
    """(True, the value at the pointer), or (False, None) where the document has none."""
    node = document
    for part in segments(pointer):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return False, None
    return True, node


def put(document, pointer: str, value) -> None:
    *path, last = segments(pointer)
    node = document
    for part in path:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value


def shown(value) -> str:
    text = repr(value) if not isinstance(value, (dict, list)) else canonical_text(value)
    return text if len(text) <= 120 else text[:117] + "..."


def canonical_text(value) -> str:
    try:
        return canonical.encode(value).decode("utf-8")
    except canonical.CanonicalError:
        return repr(value)


def difference(stated, answered, pointer: str = "") -> tuple[str, str] | None:
    """(pointer, what differs) at the first place two values differ, keys in sorted order."""
    if type(stated) is not type(answered):
        return pointer or "/", f"states {shown(stated)}, answered {shown(answered)}"
    if isinstance(stated, dict):
        for key in sorted(set(stated) | set(answered)):
            where = f"{pointer}/{escape(key)}"
            if key not in answered:
                return where, f"states {shown(stated[key])}, answered nothing"
            if key not in stated:
                return where, f"states nothing, answered {shown(answered[key])}"
            found = difference(stated[key], answered[key], where)
            if found:
                return found
        return None
    if isinstance(stated, list):
        for index, (left, right) in enumerate(zip(stated, answered, strict=False)):
            found = difference(left, right, f"{pointer}/{index}")
            if found:
                return found
        if len(stated) != len(answered):
            return (pointer or "/",
                    f"states {len(stated)} item(s), answered {len(answered)}")
        return None
    if stated != answered:
        return pointer or "/", f"states {shown(stated)}, answered {shown(answered)}"
    return None


def stored_violation(value) -> tuple[str, str] | None:
    """(pointer, code) of the first refusal of a record read as its owner would store it."""
    if not _SCHEMAS:
        _SCHEMAS.update(examples.load_schemas())
    try:
        identifier = records.resolve(value, records.registry(_SCHEMAS))
    except records.RecordError as error:
        return error.pointer or "/", error.code
    found = _SCHEMAS[identifier].validate(value, STORED)
    return (found[0].pointer or "/", found[0].code) if found else None


def fits(shape: str, value) -> bool:
    """Whether a minted value is of the shape the scenario mints it as."""
    if shape == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    pattern = SHAPES.get(shape) or re.compile(ID.format(re.escape(shape)))
    return isinstance(value, str) and bool(pattern.match(value))


def feature_modules(names: set[str]) -> tuple[dict[str, object], list[str]]:
    """(name -> loaded module) for each feature written, and the names of those not written."""
    loaded, missing = {}, []
    for name in sorted(names):
        path = FEATURES / f"{name}.py"
        if not path.is_file():
            missing.append(name)
            continue
        spec = importlib.util.spec_from_file_location(f"_feature_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded[name] = module
    return loaded, missing


class Run:
    """One case's scenario as the driver knows it at this point of the run."""

    def __init__(self, built: dict, routing: Routing, workdir: pathlib.Path, spawn):
        self.built, self.routing, self.workdir, self.spawn = built, routing, workdir, spawn
        self.templates = {row["name"]: copy.deepcopy(row["record"]) for row in built["records"]}
        self.members = {row["name"]: row["text"].encode("utf-8")
                        for row in built.get("members", [])}
        self.joins: dict[str, list[dict]] = {}
        for join in built["joins"]:
            self.joins.setdefault(join["record"], []).append(join)
        self.shapes = {row["name"]: row["shape"] for row in built["minted"]}
        self.minted_at: dict[str, list[str]] = {}
        for row in built["minted"]:
            self.minted_at.setdefault(row["step"], []).append(row["name"])
        self.learned: dict[str, object] = {}
        self.current: dict[str, object] = {}   # this answer's records while it is judged
        self.cache: dict[str, object] = {}
        self.sent: dict[str, tuple[dict, list]] = {}
        self.processes: dict[str, hosts.Host] = {}
        self.exchange = workdir / "exchange"
        self.exchange.mkdir(parents=True, exist_ok=True)
        # What features hook: before the first step; on every record built; on every message to
        # a host; and a step a feature runs itself, which it claims by returning True.
        self.prepare_hooks: list = []
        self.record_hooks: list = []
        self.message_hooks: list = []
        self.step_hooks: list = []

    # What the scenario's records are now.

    def forget(self) -> None:
        self.cache.clear()

    def value(self, name: str):
        """A record or member as it stands: this answer's own while it is judged."""
        if name in self.current:
            return self.current[name]
        if name in self.members:
            return self.members[name]
        return self.materialize(name)

    def bytes_of(self, name: str) -> bytes:
        found = self.value(name)
        return found if isinstance(found, bytes) else canonical.encode(found)

    def digest(self, name: str) -> str:
        return hashlib.sha256(self.bytes_of(name)).hexdigest()

    def materialize(self, name: str):
        """The record from its template: learned values in its minted places, recomputed
        digests and sizes, and whatever the installed features do to a record."""
        if name in self.cache:
            return self.cache[name]
        if name not in self.templates:
            raise Stop(FAILED, f"the scenario has no record {name}")
        value = copy.deepcopy(self.templates[name])
        for join in self.joins.get(name, []):
            if "minted" in join:
                if join["minted"] in self.learned:
                    put(value, join["pointer"], self.learned[join["minted"]])
                continue
            named = join["digest_of"]
            put(value, join["pointer"], self.digest(named))
            if join["pointer"].endswith("/digest"):
                found, parent = at(value, join["pointer"][:-len("/digest")])
                if found and isinstance(parent, dict) and isinstance(parent.get("size"), int):
                    parent["size"] = len(self.bytes_of(named))
        for hook in self.record_hooks:
            value = hook(self, name, value)
        self.cache[name] = value
        return value

    def fresh(self, name: str):
        """The record as stated, though the answer being judged returns it itself."""
        held = self.current.pop(name, None)
        self.forget()
        try:
            return self.materialize(name)
        finally:
            if held is not None:
                self.current[name] = held
            self.forget()

    def stand_in(self, minted: str):
        """The value the scenario states for a minted name: its first place in the templates."""
        for join in self.built["joins"]:
            if join.get("minted") == minted:
                return at(self.templates[join["record"]], join["pointer"])[1]
        raise Stop(FAILED, f"the scenario places no stand-in for {minted}")

    def receipt_of_result(self, result: str) -> str | None:
        return next((join["digest_of"] for join in self.joins.get(result, [])
                     if join["pointer"] == RECEIPT and "digest_of" in join), None)

    # Where a step runs.

    def process(self, name: str) -> hosts.Host:
        if name not in self.processes:
            base = self.workdir / "processes" / name
            (base / "state").mkdir(parents=True, exist_ok=True)
            self.processes[name] = self.spawn(base)
        return self.processes[name]

    def close(self) -> None:
        for process in self.processes.values():
            process.close()

    # One step.

    def step(self, step: dict) -> None:
        name = step["name"]
        if any(hook(self, step) for hook in self.step_hooks):
            return
        if "request" not in step:
            raise Stop(BLOCKED, "no installed feature runs this step", step=name)
        if "replays" in step:
            request, carried = self.sent[step["replays"]]
        else:
            request = self.materialize(step["request"])
            carried = [self.materialize(n) for n in step["carries"]]
        self.sent[name] = (request, carried)
        how, entry = self.routing.route(request.get("operation"))
        message = {"request": request, "carried": carried,
                   "members": {hashlib.sha256(data).hexdigest(): data
                               for data in self.members.values()},
                   "now": None, "exchange": str(self.exchange),
                   "layers": list(self.routing.layers)}
        if how == "given":
            message["given"] = self.given(step)
            message["places"] = list(self.routing.places)
        elif how == "addressed":
            message["addressed"] = True
        else:
            message["entry"] = entry
        for hook in self.message_hooks:
            hook(self, step, message)
        process = step.get("process", MAIN)
        if how == "given" and not message["layers"] and not message["places"]:
            reply = {"answer": message["given"], "admitted": 0}
        else:
            reply = self.process(process).call(message)
        answer = self.answer_of(step, reply, how, entry)
        if "refused" in step:
            self.refused(step, answer, reply)
        else:
            self.answered(step, answer)

    def given(self, step: dict) -> dict:
        """The stated answer, which the driver gives for a step no code in scope serves."""
        if "refused" in step:
            return {"refused": self.positioned(step)}
        for minted in self.minted_at.get(step["name"], []):
            self.learned[minted] = self.stand_in(minted)
        self.forget()
        receipt = self.receipt_of_result(step["result"])
        return {"result": self.materialize(step["result"]),
                "returned": [self.value(n) for n in step["returns"]],
                "receipt": self.materialize(receipt) if receipt else None}

    def positioned(self, step: dict) -> list[dict]:
        where = {step["request"]: REQUEST,
                 **{n: f"{CARRIED}/{i}" for i, n in enumerate(step["carries"])}}
        return [{"record": where[t["record"]], "code": t["code"], "pointer": t["pointer"]}
                for t in step["refused"]]

    def answer_of(self, step: dict, reply: dict, how: str, entry: str | None) -> dict:
        name = step["name"]
        who = entry or ("the journal layer" if how == "addressed" else "the given answer")
        if "blocked" in reply:
            raise Stop(BLOCKED, reply["blocked"], step=name)
        if "error" in reply:
            raise Stop(FAILED, f"{who} raised: {reply['error']}", step=name)
        if "dead" in reply:
            raise Stop(FAILED, f"process {step.get('process', MAIN)} {reply['dead']}", step=name)
        answer = reply.get("answer")
        if not isinstance(answer, dict) or not ({"result"} <= set(answer)
                                                or set(answer) == {"refused"}):
            raise Stop(FAILED, f"{who} answered neither a result nor a refusal: "
                               f"{shown(answer)}", step=name)
        return answer

    def refused(self, step: dict, answer: dict, reply: dict) -> None:
        name = step["name"]
        if "refused" not in answer:
            raise Stop(FAILED, f"states a refusal {shown(self.positioned(step))}, and the owner "
                               "answered it", step=name, record=step["request"])

        def key(triples):
            return sorted(canonical_text(t) for t in triples)
        if key(answer["refused"]) != key(self.positioned(step)):
            raise Stop(FAILED, f"states the refusal {shown(self.positioned(step))}, answered "
                               f"{shown(answer['refused'])}", step=name)
        if reply.get("admitted"):
            raise Stop(FAILED, "a refused request was admitted before it was refused",
                       step=name)

    def answered(self, step: dict, answer: dict) -> None:
        name = step["name"]
        if "refused" in answer:
            raise Stop(FAILED, f"states an answer, and the owner refused it: "
                               f"{shown(answer['refused'])}", step=name, record=step["request"])
        returned = answer.get("returned", [])
        if not isinstance(returned, list):
            raise Stop(FAILED, f"returned {shown(returned)}, which is not a list", step=name)
        result = step["result"]
        receipt = self.receipt_of_result(result)
        records = dict(zip(step["returns"], returned, strict=False))
        if receipt:
            records[receipt] = answer.get("receipt")
        records[result] = answer["result"]
        self.learn(step, records)
        self.current = {n: v for n, v in records.items() if n != result}
        try:
            self.hold(name, result, answer["result"])
            if receipt:
                self.hold(name, receipt, answer.get("receipt"))
            elif answer.get("receipt") is not None:
                raise Stop(FAILED, f"states no receipt, answered {shown(answer['receipt'])}",
                           step=name)
            if len(returned) != len(step["returns"]):
                raise Stop(FAILED, f"states {len(step['returns'])} returned record(s) "
                                   f"({', '.join(step['returns']) or 'none'}), answered "
                                   f"{len(returned)}", step=name)
            for record, actual in zip(step["returns"], returned, strict=True):
                self.hold(name, record, actual)
        finally:
            self.current = {}
            self.forget()

    def hold(self, step: str, record: str, actual) -> None:
        stated = self.fresh(record) if record not in self.members else self.members[record]
        if isinstance(stated, bytes):
            if stated != actual:
                raise Stop(FAILED, f"returns the bytes of member {record}, answered "
                                   f"{shown(actual)}", step=step, record=record)
            return
        found = difference(stated, actual)
        if found:
            pointer, what = found
            raise Stop(FAILED, f"{record}{'' if pointer == '/' else pointer} {what}",
                       step=step, record=record, pointer=pointer)
        # Equal to the stated record, so only a value it mints can make it one its owner could
        # not store.
        refused = stored_violation(actual)
        if refused:
            pointer, code = refused
            raise Stop(FAILED, f"{record}{'' if pointer == '/' else pointer} is refused in "
                               f"stored mode: {code}", step=step, record=record, pointer=pointer)

    def learn(self, step: dict, records: dict[str, object]) -> None:
        """Each value this step mints, from its first place in the answer."""
        name = step["name"]
        for minted in self.minted_at.get(name, []):
            place = next(((j["record"], j["pointer"]) for j in self.built["joins"]
                          if j.get("minted") == minted and j["record"] in records), None)
            if place is None:
                raise Stop(FAILED, f"mints {minted}, and no record of its answer holds it",
                           step=name)
            record, pointer = place
            found, value = at(records[record], pointer)
            if not found:
                raise Stop(FAILED, f"{record}{pointer} is where {minted} is minted, and the "
                                   "answer has no value there", step=name, record=record,
                           pointer=pointer)
            if not fits(self.shapes[minted], value):
                raise Stop(FAILED, f"{record}{pointer} mints {minted} as a "
                                   f"{self.shapes[minted]}, answered {shown(value)}",
                           step=name, record=record, pointer=pointer)
            self.learned[minted] = value
        self.forget()


def run_case(built: dict, routing: Routing, rules: tuple[str, ...] = (),
             spawn=None, features=None, root: pathlib.Path = cases.ROOT) -> dict:
    """What the case shows: {"outcome", "why"}, and the step, record and pointer it ended at.

    The code under test is imported from `root`. `spawn` makes the host of one world process from
    its directory, a host importing from `root` when left out; `features` maps a feature name to
    its module, the ones `features/` holds when left out. The features a scenario uses are the
    ones `cases.features_of` derives, the derivation the adapter fingerprint holds."""
    spawn = spawn or (lambda base: hosts.Host(root, base))
    used = cases.features_of(built)
    if features is None:
        features, missing = feature_modules(used)
    else:
        missing = sorted(used - set(features))
    if missing:
        return Stop(BLOCKED, f"uses {', '.join(missing)}, which no feature module under "
                             f"{FEATURES.name}/ runs yet").report()
    if rules:
        return Stop(BLOCKED, f"applies {', '.join(rules)}, and the executor does not apply "
                             "runtime rule oracles yet").report()
    with tempfile.TemporaryDirectory(prefix="workenv-case-") as workdir:
        run = Run(built, routing, pathlib.Path(workdir), spawn)
        try:
            for name in sorted(used):
                features[name].install(run)
            for hook in run.prepare_hooks:
                hook(run)
            for step in built["steps"]:
                run.step(step)
        except Stop as stop:
            return stop.report()
        finally:
            run.close()
    return {"outcome": PASSED, "why": f"{len(built['steps'])} step(s) answered as stated"}
