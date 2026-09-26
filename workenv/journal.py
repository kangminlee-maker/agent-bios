"""The request journal: every request is read, held and answered once, here (C03).

`layer_journal` wraps whatever answers a request — an operation's entry, or an answer given by
someone else — and does, in order:

  1. Read the sealed request. The request and its payload are read in submit mode and every
     other record it carries in stored mode, as their schemas state them. A record that fails is
     refused by triples, `request` or `carried/<i>` with the code and pointer, and nothing is
     written: a query for that id later finds nothing held. Another carried record that fails
     in stored mode is let through when it reads as a submission, because only the operation
     that reads it knows whether it submits it; the operation refuses it if it does not.
  2. A request id the journal already holds with other bytes is `request_id_conflict`, and the
     original stays what the id answers. The same bytes get the original result, the records it
     returned and its receipt, and nothing runs again — unless the request is still pending: one
     held in review, approved, executing, unknown or partial is handed on again, because asking
     again under the same id is how such a request moves or is settled, and its new answer
     replaces the held one.
  3. What the operation's row fixes: the payload must be a kind it takes (`payload_not_taken`),
     and the request must state its effect class (`effect_class_mismatch`).
  4. A request that repeats the operation, target and payload of one held with an unknown
     outcome, under a new id, is `resubmitted_while_unknown`: the first is settled by asking
     again under its own id.
  5. An addressed operation is answered here: `operation.query` with the original result and
     its receipt, or `request_not_held`, from what the journal holds: a query does not settle a
     pending outcome yet. `operation.cancel` of a request the journal holds is `cancel_too_late`,
     because every request it holds has been answered; a request runs in flight nowhere yet, so
     a cancel of one the journal does not hold is not served.
  6. Otherwise the request is handed on. An entry that publishes bytes before its commit
     carries a `prepare` step, which runs first, outside the unit, and hands the entry what it
     staged as `call.prepared`, or answers the request itself. Then the entry runs in one unit of
     work, and the answer is kept in the same unit, so a crash leaves the request either held
     with its answer or not held at all. The first request from a profile writes that profile
     (`workenv.access`), in the same unit.

After the unit commits and before the answer returns, the journal passes the fault point
`after_commit_before_return` the answer it committed. A refusal by triples from anything it
wraps rolls the unit back. A refusal that answers in place of a held request — a conflicting id,
a resubmission, a late cancel — reached no provider: its provider effect is `not_applicable`
where the held request had no provider to reach, and `none` where it had.

`committed` and `answered` build the answers an entry returns: the result, and for a commit its
receipt with the owner's next sequence and the head the target moved to. `stale` is the answer to
a request on a head-keeping target whose expected base is not the head the journal holds.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import secrets

from workenv import storage
from workenv.contracts import c03, canonical, errors, records
from workenv.contracts.schema import STORED, SUBMIT, load_schema

# Every operation a request may name, with its row: what it takes, returns and states.
OPERATIONS = {operation: row for module in errors.OWNERS
              for operation, row in getattr(module, "OPERATIONS", {}).items()}
QUERY, CANCEL = "operation.query", "operation.cancel"
COMMITTED = "after_commit_before_return"
REQUEST, CARRIED = "request", "carried"
UNKNOWN = "unknown"
# The contract schemas, which ship beside the contract modules.
SCHEMAS = pathlib.Path(canonical.__file__).with_name("schemas")
SCHEMA_SUFFIX = ".schema.json"
# The stages a request can still leave when it is asked again under its own id.
PENDING = ("in_review", "approved", "executing", UNKNOWN, "partial")

_READER: dict = {}


class JournalError(Exception):
    """A defect of what the journal wraps, or a request it does not serve yet."""


class _Refused(Exception):
    def __init__(self, answer: dict):
        super().__init__("refused")
        self.answer = answer


def reader() -> tuple[dict, dict]:
    """Every contract schema by id, and the (kind, version) table read from them."""
    if not _READER:
        schemas = {path.name[:-len(SCHEMA_SUFFIX)]: load_schema(canonical.parse(path.read_bytes()))
                   for path in sorted(SCHEMAS.glob(f"*{SCHEMA_SUFFIX}"))}
        _READER.update(schemas=schemas, kinds=records.registry(schemas))
    return _READER["schemas"], _READER["kinds"]


def refusals(value, mode: str, where: str) -> list[dict]:
    """The refusals of one value read as a contract record, as triples naming `where`."""
    schemas, kinds = reader()
    try:
        identifier = records.resolve(value, kinds)
    except records.RecordError as error:
        return [{"record": where, "code": error.code, "pointer": error.pointer}]
    return [{"record": where, "code": found.code, "pointer": found.pointer}
            for found in schemas[identifier].validate(value, mode)]


def digest_of(value) -> str | None:
    try:
        return canonical.digest_of(value)
    except canonical.CanonicalError:
        return None


def read(request, carried: list) -> list[dict]:
    """The triples that refuse a sealed request before anything is written, or none."""
    found = refusals(request, SUBMIT, REQUEST)
    if not found and digest_of(request) is None:
        found.append({"record": REQUEST, "code": records.NOT_A_RECORD, "pointer": ""})
    named = request.get("payload_digest") if isinstance(request, dict) else None
    for index, value in enumerate(carried):
        where = f"{CARRIED}/{index}"
        if named is not None and digest_of(value) == named:
            found += refusals(value, SUBMIT, where)
            continue
        stored = refusals(value, STORED, where)
        if stored and refusals(value, SUBMIT, where):
            found += stored
    return found


def payload(call):
    """The carried record the request names as its payload, or None."""
    named = call.request.get("payload_digest")
    return next((value for value in call.carried
                 if named is not None and digest_of(value) == named), None)


def now(call) -> str:
    """The instant a request is answered at: the world's clock when it has one."""
    if call.now:
        return call.now
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mint(prefix: str) -> str:
    """A new opaque id this installation makes."""
    return f"{prefix}_{secrets.token_hex(16)}"


def scope_key(scope: dict) -> str:
    return canonical.encode(scope).decode("ascii")


# Answers.

def outputs_of(values) -> list[dict]:
    return [{"kind": storage.MEMBER, "digest": hashlib.sha256(value).hexdigest()}
            if isinstance(value, bytes) else
            {"kind": value["kind"], "digest": canonical.digest_of(value)} for value in values]


def _result(call, outcome: dict, values, recovery, local_effect: str,
            provider_effect: str) -> dict:
    return {"kind": "operation_result", "schema": 1,
            "request_id": call.request["request_id"],
            "request_digest": canonical.digest_of(call.request),
            "local_effect": local_effect, "provider_effect": provider_effect,
            "outcome": outcome, "outputs": outputs_of(values),
            "supported_recovery": list(recovery)}


def answered(call, stage: str, values=(), gaps=(), recovery=(), local_effect: str = "none",
             provider_effect: str = "not_applicable") -> dict:
    """An answer that commits nothing: its result and the records it returns."""
    outcome = {"stage": stage, "material_gaps": list(gaps)}
    return {"result": _result(call, outcome, values, recovery, local_effect, provider_effect),
            "returned": list(values), "receipt": None}


def committed(call, values=(), head: str | None = None, gaps=(),
              provider_effect: str = "not_applicable") -> dict:
    """An answer that commits: its result, the records it returns and its receipt, with the
    owner's next sequence and the head the target moved to. Without a head of its own, the
    target's head is the one this request made."""
    store = storage.of(call.state)
    request = call.request
    digest = canonical.digest_of(request)
    owner = request["owner"]
    last = store.read("SELECT MAX(sequence) FROM receipts WHERE owner = ?",
                      (scope_key(owner),))[0][0]
    receipt = {"kind": "operation_receipt", "schema": 1, "request_id": request["request_id"],
               "request_digest": digest, "owner": owner, "target": request["target"],
               "head_digest": head or canonical.digest_of(
                   {"resource_id": request["target"]["resource_id"], "request_digest": digest}),
               "sequence": (last or 0) + 1, "committed_at": now(call)}
    outcome = {"stage": "committed", "receipt_digest": canonical.digest_of(receipt),
               "material_gaps": list(gaps)}
    return {"result": _result(call, outcome, values, (), "committed", provider_effect),
            "returned": list(values), "receipt": receipt}


# What the journal holds.

def held(store: storage.Store, request_id: str) -> dict | None:
    """The request held under this id: its digest, stage and provider effect, and the answer
    it was given, or None."""
    found = store.read("SELECT request_digest, stage, provider_effect, result_digest, returned, "
                       "receipt_digest FROM requests WHERE request_id = ?", (request_id,))
    if not found:
        return None
    digest, stage, provider, result, returned, receipt = found[0]
    return {"request_digest": digest, "stage": stage, "provider_effect": provider,
            "answer": {"result": store.get(result),
                       "returned": [store.get(item) for item in json.loads(returned)],
                       "receipt": store.get(receipt) if receipt else None}}


def keep(store: storage.Store, request: dict, digest: str, answer: dict, at: str) -> None:
    """Hold a request with the answer it was given, in place of a pending one it had."""
    result = answer["result"]
    if result.get("request_id") != request["request_id"] or \
            result.get("request_digest") != digest:
        raise JournalError(f"an answer to {request['request_id']} names another request")
    receipt = answer.get("receipt")
    receipt_digest = store.put(receipt) if receipt is not None else None
    if receipt is not None and receipt.get("request_id") == request["request_id"]:
        store.write("INSERT INTO receipts (owner, sequence, request_id, digest) "
                    "VALUES (?, ?, ?, ?)",
                    (scope_key(receipt["owner"]), receipt["sequence"], request["request_id"],
                     receipt_digest))
        store.write("INSERT OR REPLACE INTO heads (resource_id, head_digest) VALUES (?, ?)",
                    (receipt["target"]["resource_id"], receipt["head_digest"]))
    returned = [store.put(value) for value in answer.get("returned", [])]
    found = store.read("SELECT position FROM requests WHERE request_id = ?",
                       (request["request_id"],))
    position = found[0][0] if found else store.read("SELECT COUNT(*) FROM requests")[0][0] + 1
    store.write(
        "INSERT OR REPLACE INTO requests (request_id, request_digest, operation, owner, target, "
        "payload_digest, stage, provider_effect, result_digest, returned, receipt_digest, "
        "answered_at, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (request["request_id"], digest, request["operation"], scope_key(request["owner"]),
         scope_key(request["target"]), request.get("payload_digest"),
         result["outcome"]["stage"], result["provider_effect"], store.put(result),
         json.dumps(returned), receipt_digest, at, position))


def head_of(store: storage.Store, resource_id: str) -> str | None:
    """The head the last receipt on this target moved it to, or None."""
    found = store.read("SELECT head_digest FROM heads WHERE resource_id = ?", (resource_id,))
    return found[0][0] if found else None


def stale(call, store: storage.Store) -> dict | None:
    """`stale_base` when the request expects a head the target is not at, or expects no head
    where one is; else None."""
    target = call.request["target"]
    base = target.get("base")
    if base is None:
        return None
    current = head_of(store, target["resource_id"])
    expected = base["head_digest"] if base["expects"] == "head" else None
    if current == expected:
        return None
    return answered(call, "stale", gaps=[{"code": c03.STALE_BASE}],
                    recovery=["reseal_on_current_head"])


def provider_after(earlier: dict) -> str:
    """The provider effect of a refusal that answers in place of a held request: no provider
    was reached, where the held one had any provider to reach."""
    return "not_applicable" if earlier["provider_effect"] == "not_applicable" else "none"


def ruled(call, store: storage.Store) -> dict | None:
    """The answer the operation's row or an unknown outcome gives before anything runs."""
    request = call.request
    row = OPERATIONS[request["operation"]]
    found = payload(call)
    named = request.get("payload_digest")
    if (named is None) != (not row["takes"]) or (named is not None and (
            found is None or found.get("kind") not in row["takes"])):
        return answered(call, "refused", gaps=[{"code": c03.PAYLOAD_NOT_TAKEN,
                                                "pointer": "/payload_digest"}],
                        recovery=["new_governed_request"])
    if request["effect_class"] != row["effect"]:
        return answered(call, "refused", gaps=[{"code": c03.EFFECT_CLASS_MISMATCH}])
    if request["effect_class"] != "pure_preview":
        waiting = store.read(
            "SELECT request_id, provider_effect FROM requests WHERE stage = ? AND operation = ? "
            "AND target = ? AND payload_digest IS ? AND request_id != ?",
            (UNKNOWN, request["operation"], scope_key(request["target"]), named,
             request["request_id"]))
        if waiting:
            return answered(call, "refused", gaps=[{"code": c03.RESUBMITTED_WHILE_UNKNOWN,
                                                    "pointer": "/request_id"}],
                            provider_effect=provider_after({"provider_effect": waiting[0][1]}))
    return None


def addressed(call, store: storage.Store) -> dict:
    """What the journal answers a query or a cancel with."""
    asked = payload(call)["request_id"]
    earlier = held(store, asked)
    if call.request["operation"] == QUERY:
        if earlier is None:
            return answered(call, "previewed", [{"kind": "request_not_held", "schema": 1,
                                                  "request_id": asked}])
        original = earlier["answer"]
        return answered(call, "previewed", [original["result"]] + (
            [original["receipt"]] if original["receipt"] is not None else []))
    if earlier is None:
        raise JournalError(f"a cancel of {asked}, which this owner does not hold, would race "
                           "an operation in flight; no operation runs in flight here yet")
    return answered(call, "refused", gaps=[{"code": c03.CANCEL_TOO_LATE}],
                    recovery=["new_governed_request"], provider_effect=provider_after(earlier))


def layer_journal(call, inner):
    from workenv import access

    request = call.request
    refused = read(request, call.carried)
    if refused:
        return {"refused": refused}
    store = storage.of(call.state)
    digest = canonical.digest_of(request)
    earlier = held(store, request["request_id"])
    if earlier is not None and earlier["request_digest"] != digest:
        return answered(call, "refused", gaps=[{"code": c03.REQUEST_ID_CONFLICT}],
                        recovery=["query_same_request"],
                        provider_effect=provider_after(earlier))
    if earlier is not None and earlier["stage"] not in PENDING:
        return earlier["answer"]
    answer = ruled(call, store)
    prepare = getattr(inner, "prepare", None)
    if answer is None and prepare is not None and request["operation"] not in (QUERY, CANCEL):
        call.prepared = prepare(call)
        answer = call.prepared.get("answer")
    try:
        with store.unit(call):
            access.first_use(store, request["actor"], now(call))
            if answer is None:
                answer = (addressed(call, store) if request["operation"] in (QUERY, CANCEL)
                          else inner(call))
            if "refused" in answer:
                raise _Refused(answer)
            keep(store, request, digest, answer, now(call))
    except _Refused as refusal:
        return refusal.answer
    call.point(COMMITTED, answer)
    return answer
