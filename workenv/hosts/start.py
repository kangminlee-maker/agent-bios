"""The start: what a session of an installed host is launched with, so that it begins in the
person's work environment, and what the owner is asked on the host's behalf.

An entrance calls `start` with the state root, the actor, the host's name, a preparation
request and the working directory the session will run in, which is the checkout the owner
composes in, as the hook's composition later is. An entry that sealed the composition request
itself hands it over too, and the person's choice to skip the host's confirmations. In order:

  1. It composes the request's preparation for no link, through the owner. A sealed
     composition request is submitted unchanged, so the request the person's screen dispatched
     is the one composed.
  2. It renders the environment from the preparation: the memory usage contract and its guide,
     then each delivered body, read from its revision's bundle, under a header naming its unit,
     its source and its digest.
  3. It writes the launch's files in a private directory of its own under the state root, named
     by the activation's request: the environment; each tier's definition for the session, the
     one the host would have loaded with the environment after its own instructions; where a
     child started with no kind takes the session's instructions, that kind, defined with the
     person's own instructions alone; and the job the hook reads, which carries the activation.
     Its process locks the directory's `waiting` file (`WAITING`) for as long as it waits on the
     host.
  4. It hands the activation on (`roles.session_routing_dispatched`). A host session's id exists
     only once the host reports it, and the session reports only once it has begun, so the
     activation is unknown until then: the hook asks the same request again when the session
     begins, and it activates. Nothing that can fail runs after this step.
  5. It returns what the entrance runs: the host's executable, the arguments that give it the
     launch instructions (the person's own first, where the host's replace them), the
     definitions and the hooks, then, where the person chose it, the host's arguments that skip
     its confirmations; and the environment that names the job.

An activation whose session never reported is settled (`settle`) once nothing waits for the
report any more: by the start's own process when its host exits, or by whoever finds the lock
free. It is asked again under its own id as not reported (`roles.session_routing_unreported`), so
the next start is not held behind it.

Nothing is launched on a route no probe qualified: a host whose `new` route no probe qualified on
its installed version is not started with the environment, and the start says so; where its
`child` route is not qualified, every kind is left as the host would load it.

The tiers (`TIERS`) are the kinds the tier rule dispatches, and they start from the environment
the main session does. A child of any other kind, a review above all, starts from its own
definition alone (`D-20260928-4a1cc3`). On a host whose children take the session's launch
instructions unless their kind states instructions of its own (Codex), every kind the person
defined with none, and the kind a child started with no kind is, are defined for the session
with the person's own instructions, or with `PLAIN` where the person has none: that host does
not apply a kind whose instructions are blank, so an empty definition would hand its child the
environment.

`submit` is how this process asks the owner: a request sealed for the actor (`seal`), answered
by the journal around the operation's entry, or around the answer a caller gives in its place
(`answered`). The hook and the commands a person runs
(`workenv.commands`) ask the same way; `ENTRIES` is every operation they ask for, and one the
journal answers itself (a query) needs no entry.
"""
from __future__ import annotations

import contextlib
import dataclasses
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil

from workenv import access, cli, delivery, hosts, journal, preparation, roles, storage
from workenv.contracts import canonical
from workenv.hosts import probes

# The kinds the tier rule dispatches, which start from the main session's environment.
TIERS = ("frontier", "workhorse", "sweep")
COMPOSE, ACTIVATE = "preparation.compose", "session.routing.activate"
ENTRIES = {COMPOSE: preparation.preparation_compose,
           ACTIVATE: roles.session_routing_activate,
           "recipient.link.open": delivery.recipient_link_open,
           "recipient.delivery.attempt": delivery.recipient_delivery_attempt,
           "delivery.observe": delivery.delivery_observe,
           "capability.probe": hosts.capability_probe,
           "route.offer": cli.route_offer, "route.select": cli.route_select,
           "operation.history.read": journal.operation_history_read,
           "access.profile.read": access.access_profile_read}
# The operations the journal answers from what it holds, handing them to no entry.
ADDRESSED = (journal.QUERY, journal.CANCEL)
# Where each launch's files are kept, under the state root.
LAUNCHES = "launches"
# The file in a launch's directory that the start's process locks while it waits on the host.
WAITING = "waiting"
REQUEST_ID = re.compile(r"req_[0-9a-f]{32}\Z")
TITLE = "# agent-bios work environment"
# The instructions of a kind that must replace the session's where the person has none of their
# own: the least that is not blank.
PLAIN = "Carry out the task you are given."


class StartError(Exception):
    """A start this module refuses, named."""


class Call:
    """A call this process makes on the owner."""

    def __init__(self, request: dict, carried: list, state: pathlib.Path):
        self.request, self.carried, self.state = request, list(carried), pathlib.Path(state)
        self.members: dict = {}
        self.now = self.given = None
        self.exchange = self.state.parent / "exchange"

    def point(self, name: str, answer=None) -> None:
        pass

    def admitted(self) -> None:
        pass


def seal(actor: dict, operation: str, target: str, payload: dict | None = None,
         **fields) -> dict:
    """A request of the actor's, sealed as a client seals one."""
    row = journal.OPERATIONS[operation]
    request = {"kind": "operation_request", "schema": 1, "request_id": journal.mint("req"),
               "operation": operation, "effect_class": row["effect"], "action": row["action"],
               "actor": actor, "local_access_generation": 1,
               "owner": {"layer": "personal", "principal_id": actor["principal_id"]},
               "target": {"resource_id": target}, "policy_digests": [], "control_digests": [],
               "proof_digests": [], **fields}
    if payload is not None:
        request["payload_digest"] = canonical.digest_of(payload)
    return request


def submit(state: pathlib.Path, actor: dict, operation: str, target: str,
           payload: dict | None = None, **fields) -> dict:
    """The owner's answer to one request of the actor's."""
    return answered(state, seal(actor, operation, target, payload, **fields), payload)


def answered(state: pathlib.Path, request: dict, payload: dict | None, entry=None) -> dict:
    """The owner's answer to a request already sealed, carrying its payload: around the
    operation's entry, or around `entry` in its place."""
    operation = request["operation"]
    if operation not in ENTRIES and operation not in ADDRESSED:
        raise StartError(f"this installation does not ask the owner for {operation}")
    return journal.layer_journal(Call(request, [] if payload is None else [payload], state),
                                 entry or ENTRIES.get(operation))


def stage(answer: dict) -> str:
    return "refused" if "refused" in answer else answer["result"]["outcome"]["stage"]


def reason(answer: dict) -> str:
    """What the owner answered instead of what was asked, for a person to read."""
    if "refused" in answer:
        return "the request was refused as unreadable: " + json.dumps(answer["refused"])
    gaps = [gap["code"] for gap in answer["result"]["outcome"]["material_gaps"]]
    return f"{answer['result']['outcome']['stage']} with {', '.join(gaps) or 'no gap named'}"


def delivered(prepared: dict) -> list[dict]:
    """The preparation's units whose bodies reach a session: its winning and layered
    Instructions units that name a body."""
    return [unit for unit in prepared["units"]
            if unit["role"] == roles.INSTRUCTIONS and "body_digest" in unit
            and unit["standing"] in delivery.DELIVERED_STANDINGS]


def body(state: pathlib.Path, unit: dict) -> bytes:
    """A delivered unit's body, from the revision's bundle."""
    return (storage.bundle(state, unit["revision_digest"]) / storage.MEMBERS /
            unit["member"]).read_bytes()


def bodies_text(units: list[dict], data: list[bytes]) -> str:
    """Each body under a header naming its layer, its role and the member it is, then a line
    naming its unit, its source and its digest. A unit id names the unit in its preparation only;
    the source, the member and the digest follow it across preparations (C07)."""
    parts = []
    for unit, held in zip(units, data, strict=True):
        if hashlib.sha256(held).hexdigest() != unit["body_digest"]:
            raise StartError(f"the body of {unit['unit_id']} is not the one its unit names")
        try:
            text = held.decode("utf-8")
        except UnicodeDecodeError as error:
            raise StartError(f"the body of {unit['unit_id']} is not text") from error
        what = f"{unit['layer'].capitalize()} {unit['role']}"
        if unit.get("member"):
            what += f": {unit['member']}"
        parts.append(f"## {what}\n\nUnit {unit['unit_id']}, source {unit['source_id']}, body "
                     f"sha256 {unit['body_digest']}.\n\n{text.rstrip()}\n")
    return "\n".join(parts)


def rendered(usage: dict, units: list[dict], data: list[bytes]) -> str:
    """The environment a session starts in: the usage contract, its guide, then the bodies."""
    guide = roles.GUIDES / pathlib.Path(usage["guide"]["path"]).name
    head = (f"{TITLE}\n\n{usage['text']}\n\nThe guide: {guide} (sha256 "
            f"{usage['guide']['digest']}).\n")
    return head + ("\n" + bodies_text(units, data) if units else "")


@dataclasses.dataclass(frozen=True)
class Launch:
    """What an entrance runs: the executable, its arguments, the environment it adds and the
    variables it drops (those that would mark the session as running inside another), the
    directory the launch's files are in, the environment the session starts in, the activation's
    request id, and the descriptor holding the lock this process keeps while it waits."""
    executable: str
    arguments: list[str]
    environ: dict
    dropped: tuple[str, ...]
    directory: pathlib.Path
    text: str
    activation: str | None = None
    waiting: int | None = None


def hold(directory: pathlib.Path) -> int:
    """The lock on a launch that its start's process keeps while it waits on the host."""
    held = os.open(directory / WAITING, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return held


def release(launch: Launch) -> None:
    if launch.waiting is not None:
        os.close(launch.waiting)


def launched(state: pathlib.Path, request_id: str) -> pathlib.Path | None:
    """The directory of the launch that dispatched this activation, or None."""
    if not REQUEST_ID.match(request_id):
        return None
    directory = pathlib.Path(state) / LAUNCHES / request_id
    return directory if directory.is_dir() else None


def waiting(state: pathlib.Path, request_id: str) -> bool:
    """Whether a start's process still waits on the host it launched with this activation."""
    directory = launched(state, request_id)
    try:
        held = os.open(directory / WAITING, os.O_RDONLY) if directory else None
    except FileNotFoundError:
        return False
    if held is None:
        return False
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    finally:
        os.close(held)
    return False


def settle(state: pathlib.Path, request_id: str, *, waited: bool = False) -> dict | None:
    """The activation a launch dispatched, asked again under its own id as not reported, where
    the journal still holds it unknown; None where it does not, or where no launch here holds it.
    The start's own process settles it once its host has exited (`waited`); anyone else, only
    where no process waits on the launch any more."""
    directory = launched(state, request_id)
    held = journal.held(storage.of(state), request_id)
    if directory is None or held is None or held["stage"] != journal.UNKNOWN or \
            (not waited and waiting(state, request_id)):
        return None
    try:
        asked = json.loads((directory / "job.json").read_text(encoding="utf-8"))["activation"]
    except (OSError, ValueError, KeyError):
        return None
    answer = answered(state, asked["request"], asked["payload"], roles.session_routing_unreported)
    return answer if stage(answer) == "expired" else None


def start(state: pathlib.Path, actor: dict, host_name: str, request: dict,
          workdir: pathlib.Path, environ: dict, *, sealed: dict | None = None,
          skip: bool = False) -> Launch:
    state, workdir = pathlib.Path(state), pathlib.Path(workdir)
    adapter = hosts.adapter_for(host_name)
    if adapter is None or adapter.launch is None or adapter.hooked is None or \
            adapter.configured is None:
        raise StartError(f"no adapter here can start {host_name}")
    if sealed is not None and (sealed.get("operation") != COMPOSE or
                               sealed.get("actor") != actor or
                               sealed.get("payload_digest") != canonical.digest_of(request)):
        raise StartError("the sealed request is not this actor's composition of this request")
    if skip and not adapter.skip:
        raise StartError(f"no arguments here start {host_name} with its confirmations skipped")
    found = probes.installed(adapter, environ, workdir)
    if found is None:
        raise StartError(f"no {host_name} is installed on this machine's path")
    executable, version = found
    host = {"name": host_name, "version": version}
    store = storage.of(state)
    if not hosts.supports(store, host, "new"):
        raise StartError(f"no probe qualified delivery to a new session on {host_name} "
                         f"{version}; probe new_delivery first")
    with contextlib.chdir(workdir):
        composed = answered(state, sealed, request) if sealed is not None else \
            submit(state, actor, COMPOSE, actor["principal_id"], request)
    if stage(composed) != "previewed":
        raise StartError(f"composing the environment was {reason(composed)}")
    prepared = composed["returned"][0]
    units = delivered(prepared)
    text = rendered(roles.usage_contract(), units, [body(state, unit) for unit in units])
    quiet = {name: value for name, value in environ.items() if name not in adapter.nested}
    configured = adapter.configured(executable, workdir, quiet)
    tiers = [tier for tier in TIERS if tier in configured.kinds] \
        if hosts.supports(store, host, "child") else []
    kinds = {tier: configured.kinds[tier].adding(text) for tier in tiers}
    if adapter.plain is not None:
        own = configured.native if (configured.native or "").strip() else PLAIN
        defined = {name: kind for name, kind in configured.kinds.items() if name not in kinds}
        defined.setdefault(adapter.plain, hosts.Kind(
            description="A child started with no kind of its own.", instructions=""))
        kinds.update({name: dataclasses.replace(kind, instructions=own)
                      for name, kind in defined.items() if not kind.instructions.strip()})
    activation = {"kind": "session_activation", "schema": 1,
                  "preparation_digest": canonical.digest_of(prepared),
                  "session": {"host": host, "profile_id": actor["profile_id"]}}
    asked = seal(actor, ACTIVATE, actor["profile_id"], activation)
    directory = state / LAUNCHES / asked["request_id"]
    directory.mkdir(parents=True, mode=0o700)
    held = hold(directory)
    try:
        (directory / "environment.md").write_text(text, encoding="utf-8")
        job = directory / "job.json"
        job.write_text(json.dumps({
            "kind": "session", "state": str(state), "actor": actor, "host": host,
            "request": request, "bodies": [unit["body_digest"] for unit in units],
            "tiers": tiers, "activation": {"request": asked, "payload": activation}},
            ensure_ascii=False), encoding="utf-8")
        instructions = "\n\n".join(part for part in (configured.native, text) if part)
        arguments = [*adapter.hooked(probes.command(host_name), directory),
                     *adapter.launch(directory, instructions, kinds),
                     *(adapter.skip if skip else ())]
        with contextlib.chdir(workdir):
            dispatched = answered(state, asked, activation, roles.session_routing_dispatched)
        if stage(dispatched) != journal.UNKNOWN:
            raise StartError(f"activating the environment was {reason(dispatched)}")
    except BaseException:
        os.close(held)
        found = journal.held(store, asked["request_id"])
        if found is None or found["stage"] != journal.UNKNOWN:
            shutil.rmtree(directory)
        raise
    return Launch(executable, arguments, {probes.JOB: str(job)}, adapter.nested, directory,
                  text, asked["request_id"], held)
