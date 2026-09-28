"""The start: what a session of an installed host is launched with, so that it begins in the
person's work environment, and what the owner is asked on the host's behalf.

An entrance calls `start` with the state root, the actor, the host's name, a preparation
request and the working directory the session will run in, which is the checkout the owner
composes in, as the hook's composition later is. An entry that sealed the composition request
itself hands it over too, and the person's choice to skip the host's confirmations. In order:

  1. It composes the request's preparation for no link and activates the session with it,
     through the owner. A sealed composition request is submitted unchanged, so the request the
     person's screen dispatched is the one composed. A host session's id exists only once the
     host reports it, so nothing names the session yet: the activation is recorded for nobody,
     and it returns every delivered body.
  2. It renders the environment: the memory usage contract and its guide, then each delivered
     body under a header naming its unit, its source and its digest.
  3. It writes the launch's files in a private directory of its own under the state root: the
     environment; each tier's definition for the session, the one the host would have loaded
     with the environment after its own instructions; where a child started with no kind takes
     the session's instructions, that kind, defined with the person's own instructions alone;
     and the job the hook reads.
  4. It returns what the entrance runs: the host's executable, the arguments that give it the
     launch instructions (the person's own first, where the host's replace them), the
     definitions and the hooks, then, where the person chose it, the host's arguments that skip
     its confirmations; and the environment that names the job.

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

`submit` is how this process asks the owner: a request sealed for the actor, answered by the
journal around the operation's entry (`answered`). The hook asks the same way.
"""
from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import pathlib
import secrets

from workenv import delivery, hosts, journal, preparation, roles, storage
from workenv.contracts import canonical
from workenv.hosts import probes

# The kinds the tier rule dispatches, which start from the main session's environment.
TIERS = ("frontier", "workhorse", "sweep")
COMPOSE = "preparation.compose"
ENTRIES = {COMPOSE: preparation.preparation_compose,
           "session.routing.activate": roles.session_routing_activate,
           "recipient.link.open": delivery.recipient_link_open,
           "recipient.delivery.attempt": delivery.recipient_delivery_attempt}
# Where each launch's files are kept, under the state root.
LAUNCHES = "launches"
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


def submit(state: pathlib.Path, actor: dict, operation: str, target: str,
           payload: dict | None = None, **fields) -> dict:
    """The owner's answer to one request of the actor's, sealed as a client seals one."""
    row = journal.OPERATIONS[operation]
    request = {"kind": "operation_request", "schema": 1, "request_id": journal.mint("req"),
               "operation": operation, "effect_class": row["effect"], "action": row["action"],
               "actor": actor, "local_access_generation": 1,
               "owner": {"layer": "personal", "principal_id": actor["principal_id"]},
               "target": {"resource_id": target}, "policy_digests": [], "control_digests": [],
               "proof_digests": [], **fields}
    if payload is not None:
        request["payload_digest"] = canonical.digest_of(payload)
    return answered(state, request, payload)


def answered(state: pathlib.Path, request: dict, payload: dict | None) -> dict:
    """The owner's answer to a request already sealed, carrying its payload."""
    return journal.layer_journal(Call(request, [] if payload is None else [payload], state),
                                 ENTRIES[request["operation"]])


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
    """Each body under a header naming its unit, its source and its digest."""
    parts = []
    for unit, held in zip(units, data, strict=True):
        if hashlib.sha256(held).hexdigest() != unit["body_digest"]:
            raise StartError(f"the body of {unit['unit_id']} is not the one its unit names")
        try:
            text = held.decode("utf-8")
        except UnicodeDecodeError as error:
            raise StartError(f"the body of {unit['unit_id']} is not text") from error
        parts.append(f"## {unit['unit_id']}\n\nSource {unit['source_id']}, body sha256 "
                     f"{unit['body_digest']}.\n\n{text.rstrip()}\n")
    return "\n".join(parts)


def rendered(routing: dict, units: list[dict], data: list[bytes]) -> str:
    """The environment a session starts in: the usage contract, its guide, then the bodies."""
    usage = routing["delivery"]["memory_usage"]
    guide = roles.GUIDES / pathlib.Path(usage["guide"]["path"]).name
    head = (f"{TITLE}\n\n{usage['text']}\n\nThe guide: {guide} (sha256 "
            f"{usage['guide']['digest']}).\n")
    return head + ("\n" + bodies_text(units, data) if units else "")


@dataclasses.dataclass(frozen=True)
class Launch:
    """What an entrance runs: the executable, its arguments, the environment it adds and the
    variables it drops (those that would mark the session as running inside another), the
    directory the launch's files are in, and the environment the session starts in."""
    executable: str
    arguments: list[str]
    environ: dict
    dropped: tuple[str, ...]
    directory: pathlib.Path
    text: str


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
        activated = submit(state, actor, "session.routing.activate", actor["profile_id"], {
            "kind": "session_activation", "schema": 1,
            "preparation_digest": canonical.digest_of(prepared),
            "session": {"host": host, "profile_id": actor["profile_id"]}})
    if stage(activated) != "committed":
        raise StartError(f"activating the environment was {reason(activated)}")
    routing = activated["returned"][0]
    data = [value for value in activated["returned"] if isinstance(value, bytes)]
    units = delivered(prepared)
    if len(units) != len(data):
        raise StartError("the activation returned other bodies than the preparation delivers")
    text = rendered(routing, units, data)
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
    directory = state / LAUNCHES / secrets.token_hex(8)
    directory.mkdir(parents=True, mode=0o700)
    (directory / "environment.md").write_text(text, encoding="utf-8")
    job = directory / "job.json"
    job.write_text(json.dumps({
        "kind": "session", "state": str(state), "actor": actor, "host": host,
        "request": request, "bodies": [unit["body_digest"] for unit in units],
        "tiers": tiers}, ensure_ascii=False), encoding="utf-8")
    launched = "\n\n".join(part for part in (configured.native, text) if part)
    arguments = [*adapter.hooked(probes.command(host_name), directory),
                 *adapter.launch(directory, launched, kinds), *(adapter.skip if skip else ())]
    return Launch(executable, arguments, {probes.JOB: str(job)}, adapter.nested, directory,
                  text)
