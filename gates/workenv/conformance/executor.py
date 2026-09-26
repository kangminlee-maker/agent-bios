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
     in scope. The layers in scope run on a given step as on any other, and what they return
     is held to the stated answer like any answer.
  4. Learn each value the step mints at its first place in the answer, and refuse one that is
     not of its shape; a value the driver already knows, because the world fixes it or an
     answer the caller never received stated it, is held there instead. A value the answer holds
     only inside a record it names by digest is learned where a later answer first holds it;
     until then a digest or size of a record resting on it is learned where an answer states
     it, and held to that record once the record is known, at the latest when the run ends. A
     request resting on a value no answer has returned is `failed`, and a run that ends with
     such a record never shown is `blocked`: nothing judged what the code wrote there.
  5. Hold the answer to the stated one: its result, then its receipt, then each record it
     returns, by position. Minted places hold what was learned, and a digest of a record this
     answer returns is the digest of what the owner actually returned, so a difference is
     reported where it is, not as the digest that names it. The first difference is `failed`,
     naming the step, the record and the JSON pointer.
  6. A refused step must be refused with exactly the stated triples, and without calling
     `admitted()`. A triple names its record by position: `request`, or `carried/<i>` for the
     step's i-th carried record, because the code under test never sees the scenario's names.
  7. Apply each runtime rule the case's registry row names to every record of the kind its
     oracle judges that code in scope returned, with the context `rules.context` finds for it
     among the run's records. A given answer is the driver's, held to the stated one, so no
     rule judges it.

The receipt a step is held to is the one its stated result names: its own when it committed,
the earlier step's for an answer stated `receipt_of` it, and for a replay the replayed step's.
So a replay or a settled duplicate that writes a new receipt differs from the stated one, and
neither needs more than the core to be judged.

Everything beyond that is a feature, one module under `features/` that `install(run)` hooks into
the run: before the first step, on every record built, before each step, on every message to a
host, on every reply, after an answer is held, or by running a step itself. A case whose scenario
uses a feature with no module is `blocked` by name before any step runs, and so is a case naming a
rule whose context no run finds yet. A step whose entry, layer or place has not been written is
`blocked` naming it.

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
import rules as oracles  # noqa: E402
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


class Unknown:
    """A digest or size of a record that rests on a value no answer has returned yet.

    A step whose reply never reached the caller (a fault observed by a later step) minted values
    the caller first learns later. Until then a digest of a record resting on one of them cannot
    be computed; where an answer states it, it is learned like a minted value, and it is held to
    the record once the record is known."""

    def __init__(self, name: str, what: str):
        self.name, self.what = name, what

    def __repr__(self) -> str:
        return f"<the {self.what} of {self.name}, not yet known>"


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
        # Values a step minted whose reply never reached the caller, learned where they appear.
        self.pending: list[str] = []
        self.later: dict[tuple[str, str], object] = {}   # (record, digest|size) learned early
        self._dark: dict[str, bool] = {}
        self.current: dict[str, object] = {}   # this answer's records while it is judged
        self.cache: dict[str, object] = {}
        self.sent: dict[str, tuple[dict, list]] = {}
        self.processes: dict[str, hosts.Host] = {}
        self.exchange = workdir / "exchange"
        self.exchange.mkdir(parents=True, exist_ok=True)
        # The directory the code under test runs in, and the checkout a feature built.
        self.cwd: pathlib.Path | None = None
        self.checkout: pathlib.Path | None = None
        self.file_digests: dict[str, tuple[str, str]] = {}
        self.written: dict[str, dict[str, str]] = {}
        self.rules: tuple[str, ...] = ()
        self.applied: dict[str, int] = {}
        # What features hook: before the first step; on every record built; before each step;
        # on every message to a host; on every reply, which a hook may replace, or end the step
        # with None when no answer reaches the caller; after an answer is held; and a step a
        # feature runs itself, which it claims by returning True.
        self.prepare_hooks: list = []
        self.record_hooks: list = []
        self.before_hooks: list = []
        self.message_hooks: list = []
        self.reply_hooks: list = []
        self.after_hooks: list = []
        self.step_hooks: list = []

    # What the scenario's records are now.

    def forget(self) -> None:
        self.cache.clear()
        self._dark.clear()

    def value(self, name: str):
        """A record or member as it stands: this answer's own while it is judged."""
        if name in self.current:
            return self.current[name]
        if name in self.members:
            return self.members[name]
        return self.materialize(name)

    def unknowable(self, name: str) -> bool:
        """Whether a record holds a value no answer has returned yet: a pending minted value,
        or the digest or size of such a record that no answer has stated either."""
        if name in self.current or name in self.members:
            return False
        if name not in self._dark:
            self._dark[name] = False    # a digest cycle is refused by the generator
            for join in self.joins.get(name, []):
                if "minted" in join:
                    dark = join["minted"] in self.pending
                else:
                    named, pointer = join["digest_of"], join["pointer"]
                    sized = pointer.endswith("/digest") and isinstance(
                        at(self.templates[name], pointer[:-len("/digest")])[1], dict) and \
                        isinstance(at(self.templates[name], pointer[:-len("/digest")])[1]
                                   .get("size"), int)
                    dark = self.unknowable(named) and (
                        (named, "digest") not in self.later
                        or (sized and (named, "size") not in self.later))
                if dark:
                    self._dark[name] = True
                    break
        return self._dark[name]

    def bytes_of(self, name: str) -> bytes:
        if self.unknowable(name):
            raise Stop(FAILED, f"{name} rests on a value no answer has returned yet")
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
            dark = self.unknowable(named)
            put(value, join["pointer"], self.later.get((named, "digest"), Unknown(named, "digest"))
                if dark else self.digest(named))
            if join["pointer"].endswith("/digest"):
                found, parent = at(value, join["pointer"][:-len("/digest")])
                if found and isinstance(parent, dict) and isinstance(parent.get("size"), int):
                    parent["size"] = (self.later.get((named, "size"), Unknown(named, "size"))
                                      if dark else len(self.bytes_of(named)))
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
            self.processes[name] = self.spawn(base, self.cwd)
        return self.processes[name]

    def restart(self, name: str) -> hosts.Host:
        """The process started again on the state root it had."""
        if name in self.processes:
            self.processes.pop(name).close()
        return self.process(name)

    def close(self) -> None:
        for process in self.processes.values():
            process.close()

    # One step.

    def step(self, step: dict) -> None:
        name = step["name"]
        for hook in self.before_hooks:
            hook(self, step)
        if any(hook(self, step) for hook in self.step_hooks):
            return
        if "request" not in step:
            raise Stop(BLOCKED, "no installed feature runs this step", step=name)
        if "replays" in step:
            request, carried = self.sent[step["replays"]]
        else:
            request = self.materialize(step["request"])
            carried = [self.materialize(n) for n in step["carries"]]
        if any(self.unknowable(n) for n in [step["request"], *step["carries"]]):
            raise Stop(FAILED, "its request rests on a value no answer has returned yet",
                       step=name)
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
        for hook in self.reply_hooks:
            reply = hook(self, step, message, reply)
            if reply is None:
                return
        answer = self.answer_of(step, reply, how, entry)
        if "refused" in step:
            self.refused(step, answer, reply)
            return
        self.answered(step, answer)
        for hook in self.after_hooks:
            hook(self, step, answer, how)
        if how != "given":
            self.judge_rules(step, answer)

    def judge_rules(self, step: dict, answer: dict) -> None:
        """Each rule the case names, applied to every record of the kind it judges that code in
        scope returned at this step, with the context the run holds for it."""
        for rule in self.rules:
            kind, _, oracle = oracles.RULES[rule]
            for index, record in enumerate(answer.get("returned", [])):
                if not isinstance(record, dict) or record.get("kind") != kind:
                    continue
                context = oracles.context(rule, record, self.known)
                if context is None:
                    raise Stop(FAILED, f"{rule} reads what {step['returns'][index]} names, and "
                                       "the run holds no record by that digest",
                               step=step["name"], record=step["returns"][index])
                broken = oracle(record, context)
                if broken:
                    raise Stop(FAILED, f"{step['returns'][index]} breaks {rule} at "
                                       f"{', '.join(broken)}", step=step["name"],
                               record=step["returns"][index], pointer=broken[0])
                self.applied[rule] = self.applied.get(rule, 0) + 1

    def settle(self) -> None:
        """At the end of the run: each digest or size learned before its record is held to the
        record now it is known, and a record still resting on a value no answer returned was
        never shown, so the case cannot pass on it."""
        for (record, what), stated in self.later.items():
            if self.unknowable(record):
                continue
            measured = self.digest(record) if what == "digest" else len(self.bytes_of(record))
            if measured != stated:
                raise Stop(FAILED, f"{record} is not the record an earlier answer named: its "
                                   f"{what} is {measured}, and that answer stated {stated}",
                           record=record)
        unshown = sorted({record for record, _ in self.later if self.unknowable(record)}
                         | set(self.pending))
        if unshown:
            raise Stop(BLOCKED, f"no answer of the scenario shows {', '.join(unshown)}; answers "
                                "name it only by digest, so what the code under test wrote "
                                "there cannot be judged")

    def known(self, digest: str):
        """The record or member the run holds under this digest, or None."""
        for name in [*self.templates, *self.members]:
            if not self.unknowable(name) and self.digest(name) == digest:
                return self.value(name)
        return None

    def given(self, step: dict) -> dict:
        """The stated answer, which the driver gives for a step no code in scope serves."""
        if "refused" in step:
            return {"refused": self.positioned(step)}
        for minted in self.minted_at.get(step["name"], []):
            if minted not in self.learned:
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
        if not isinstance(answer, dict) or not (("result" in answer and "refused" not in answer)
                                                or set(answer) == {"refused"}):
            raise Stop(FAILED, f"{who} answered neither a result nor a refusal alone: "
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
        stated = self.resolve(stated, actual, step, record, "")
        found = difference(stated, actual)
        if found:
            pointer, what = found
            raise Stop(FAILED, f"{record}{'' if pointer == '/' else pointer} {what}",
                       step=step, record=record, pointer=pointer)
        for what, measured in (("digest", lambda: self.digest(record)),
                               ("size", lambda: len(self.bytes_of(record)))):
            earlier = self.later.get((record, what))
            if earlier is not None and not self.unknowable(record) and measured() != earlier:
                raise Stop(FAILED, f"{record} is not the record an earlier answer named: its "
                                   f"{what} is {measured()}, and that answer stated {earlier}",
                           step=step, record=record)
        # Equal to the stated record, so only a value it mints can make it one its owner could
        # not store.
        refused = stored_violation(actual)
        if refused:
            pointer, code = refused
            raise Stop(FAILED, f"{record}{'' if pointer == '/' else pointer} is refused in "
                               f"stored mode: {code}", step=step, record=record, pointer=pointer)

    def resolve(self, stated, actual, step: str, record: str, pointer: str):
        """The stated value with each digest or size not yet known learned from the answer."""
        if isinstance(stated, Unknown):
            found, value = at(actual, pointer) if pointer else (True, actual)
            shape = "digest" if stated.what == "digest" else "integer"
            if not found or not fits(shape, value):
                raise Stop(FAILED, f"{record}{pointer} states {stated!r}, answered "
                                   f"{shown(value)}", step=step, record=record, pointer=pointer)
            self.later[(stated.name, stated.what)] = value
            return value
        if isinstance(stated, dict):
            return {key: self.resolve(item, actual, step, record, f"{pointer}/{escape(key)}")
                    for key, item in stated.items()}
        if isinstance(stated, list):
            return [self.resolve(item, actual, step, record, f"{pointer}/{index}")
                    for index, item in enumerate(stated)]
        return stated

    def learn(self, step: dict, records: dict[str, object]) -> None:
        """Each value this step mints, from its first place in the answer, and each value an
        earlier step minted without its reply reaching the caller, where this answer holds it."""
        name = step["name"]
        # A value already known, from the world or from an answer the caller never received, is
        # held where it is minted rather than learned again.
        due = [m for m in self.minted_at.get(name, []) if m not in self.learned]
        for minted in [*due, *(m for m in self.pending if m not in due)]:
            place = next(((j["record"], j["pointer"]) for j in self.built["joins"]
                          if j.get("minted") == minted and j["record"] in records), None)
            if place is None:
                # Held only inside a record this answer names by digest: learned where a
                # later answer returns it, and a digest resting on it where one states it.
                if minted not in self.pending:
                    self.pending.append(minted)
                continue
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
            if minted in self.pending:
                self.pending.remove(minted)
        self.forget()


def run_case(built: dict, routing: Routing, rules: tuple[str, ...] = (),
             spawn=None, features=None, root: pathlib.Path = cases.ROOT) -> dict:
    """What the case shows: {"outcome", "why"}, and the step, record and pointer it ended at.

    The code under test is imported from `root`. `spawn` makes the host of one world process from
    its directory, a host importing from `root` when left out; `features` maps a feature name to
    its module, the ones `features/` holds when left out. The features a scenario uses are the
    ones `cases.features_of` derives, the derivation the adapter fingerprint holds."""
    spawn = spawn or (lambda base, cwd: hosts.Host(root, base, cwd=cwd))
    used = cases.features_of(built)
    if features is None:
        features, missing = feature_modules(used)
    else:
        missing = sorted(used - set(features))
    if missing:
        return Stop(BLOCKED, f"uses {', '.join(missing)}, which no feature module under "
                             f"{FEATURES.name}/ runs yet").report()
    unread = [rule for rule in rules if not oracles.readable(rule)]
    if unread:
        return Stop(BLOCKED, f"applies {', '.join(unread)}, whose context the executor does not "
                             "find in a run yet").report()
    with tempfile.TemporaryDirectory(prefix="workenv-case-") as workdir:
        run = Run(built, routing, pathlib.Path(workdir), spawn)
        run.rules = tuple(rules)
        try:
            for name in sorted(used):
                features[name].install(run)
            for hook in run.prepare_hooks:
                hook(run)
            for step in built["steps"]:
                run.step(step)
            run.settle()
        except Stop as stop:
            return stop.report()
        finally:
            run.close()
    why = f"{len(built['steps'])} step(s) answered as stated"
    if rules:
        why += "; " + "; ".join(f"{rule} held on {run.applied.get(rule, 0)} record(s)"
                                for rule in rules)
    return {"outcome": PASSED, "why": why}
