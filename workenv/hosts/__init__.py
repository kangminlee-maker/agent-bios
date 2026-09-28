"""Host adapters: how each host's own events reach one of its sessions, stated as data, and
whether a route has been shown to work on the host installed here.

The delivery owner (`workenv.delivery`, `workenv.roles`) knows links, preparations and what was
delivered to whom, and nothing about any host. An adapter knows one host and nothing about the
delivery rules: which of its events reaches which recipient C11 names (`new`, `current`, `child`,
`rehydrated`), where a session's own id is found, and how the host takes text into a session's
context. A host is added by writing its module and listing it in `MODULES`; nothing in the owner
changes.

Each route names the carrier that hands its recipient the text, the same on every host:

  - `launch`: the instructions the host is started with, which it keeps for the session's life,
    compaction included; a `new` and a `rehydrated` session take their text this way;
  - `definition`: a kind of child the session is started with, defined for that session alone;
    a child of that kind starts from its definition's instructions;
  - `hook`: a command the host runs on the route's event, whose output it adds to the session.

The event of a launch or definition route is where the host reports that the recipient began,
not how the text reaches it. An adapter states its host's arguments for the first two carriers
(`launch`), and its hook output for the third (`output`), with the most a hook's output carries
whole (`limit`).

An adapter also says what the host would give a session it started on its own (`configured`),
because launch arguments stand in for some of it: the person's own instructions, where the
host's launch instructions replace them rather than add to them, and each kind of child the
host would load, the person's own definition over the one this installation ships. A kind
defined for the session keeps every field of the definition it stands in for (its model, its
effort, the tools it may not use), so defining one changes only its instructions.

What an adapter declares is how it would reach a recipient, never that it does. A route is
supported on a host only where the adapter declares it and the latest probe of that recipient's
delivery capability (C12) on that host, by name and version, ran for real through the wire the
route takes now and worked; a probe run against a fixture, one that did not work, one through
another carrier, or none at all leaves the route unsupported, and a host's documentation cannot
stand in for the probe. A route without that is not delivered on: no
other route stands in for it. A host no adapter names has no route at all, so its sessions can
take what the owner composes only by hand, and nothing records a delivery the runtime did not
observe.

The destination a link names is the digest of the session id the adapter reported, the host's
own bytes and never an id the runtime makes up.

An adapter also says how its host is driven for a probe: the executable that runs it, the
environment that marks a process as running inside one of its sessions, and a run that starts
the host with the arguments a probe gives it and its hooks, and asks one recipient
(`workenv.hosts.probes`). A host is always given every declared route's hook, whatever the
route's carrier, one group per route in the order the routes are declared, so a route keeps its
place across runs: Codex trusts a hook by its place, and two routes on one event would otherwise
take the same place in turn.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
from typing import Callable

from workenv import storage

RECIPIENTS = ("new", "current", "child", "rehydrated")
# The C12 capability that qualifies delivery to each recipient.
CAPABILITY = {recipient: f"{recipient}_delivery" for recipient in RECIPIENTS}
PROBE = "capability_probe"
# The adapters this installation carries, by module under this package.
MODULES = ("claude_code", "codex")
# The wire a probe of a route states (C12), by the route's carrier.
WIRES = {"launch": {"protocol": "launch_instructions", "version": "1"},
         "definition": {"protocol": "session_definition", "version": "1"},
         "hook": {"protocol": "command_hook", "version": "1"}}


class HostError(Exception):
    """The host could not tell an adapter what it needs, named."""


@dataclasses.dataclass(frozen=True)
class Route:
    """One host event, the value of its `source` field where the event has one, and the carrier
    that hands the recipient its text."""
    event: str
    source: str | None = None
    carrier: str = dataclasses.field(kw_only=True)

    @property
    def wire(self) -> dict:
        return WIRES[self.carrier]


@dataclasses.dataclass(frozen=True)
class Kind:
    """A kind of child defined for one session: what it is for, the instructions it starts with,
    and every other field of its definition in the host's own terms, carried as they are."""
    description: str
    instructions: str
    settings: dict = dataclasses.field(default_factory=dict)

    def adding(self, text: str) -> Kind:
        """The same kind, starting from its own instructions and then `text`."""
        return dataclasses.replace(self, instructions=f"{self.instructions.rstrip()}\n\n{text}")


@dataclasses.dataclass(frozen=True)
class Configured:
    """What the host would give a session it starts on its own: the person's instructions where
    launch instructions replace them (None where they add to them), and each kind of child it
    would load, by name."""
    native: str | None
    kinds: dict[str, Kind]


@dataclasses.dataclass(frozen=True)
class Adapter:
    names: tuple[str, ...]
    # The recipient each declared route reaches.
    routes: dict[str, Route]
    # The environment variable a command the session runs finds its session id in.
    session_env: str
    # The field of an event's input that holds the session id.
    session_field: str = "session_id"
    # The executable that runs the host.
    binary: str = ""
    # The environment variables that mark a process as running inside one of its sessions,
    # dropped before a probe starts a session of its own.
    nested: tuple[str, ...] = ()
    # The arguments that start the host with its confirmations skipped: it asks the person
    # before no action, and a host that sandboxes its commands runs them outside the sandbox.
    skip: tuple[str, ...] = ()
    # The arguments that start the host with the text as its session's launch instructions and
    # the kinds defined for that session alone, writing any file they name in the directory:
    # (directory, text or None, {name: Kind}) -> arguments.
    launch: Callable | None = None
    # The arguments that give the host its hooks, one group per declared route, each running the
    # command, writing any file they name in the directory: (command, directory) -> arguments.
    hooked: Callable | None = None
    # What the host would give a session it started on its own:
    # (executable, working directory, environment) -> Configured.
    configured: Callable | None = None
    # The kind a child started with no kind is, where such a child takes the session's launch
    # instructions; a start defines it with the person's own instructions alone.
    plain: str | None = None
    # The most a hook's output carries whole, and what that is counted in: `characters`, or
    # `bytes` of UTF-8 where the host counts tokens, since no token is shorter than a byte.
    limit: tuple[int, str] = (0, "characters")
    # Starts the host with the given arguments and its hooks and asks one recipient for what it
    # was handed: (recipient, executable, hook command, arguments, working directory,
    # environment) -> probes.Run.
    drive: Callable | None = None

    def recipient_of(self, event: dict) -> str | None:
        """The recipient one event of this host reaches, or None where it reaches none."""
        for recipient, route in self.routes.items():
            if event.get("hook_event_name") == route.event and (
                    route.source is None or event.get("source") == route.source):
                return recipient
        return None

    def session_of(self, event: dict | None = None, environ: dict | None = None) -> str | None:
        """The session id the host reported: in the event's input, else in the environment."""
        found = (event or {}).get(self.session_field) or (environ or {}).get(self.session_env)
        return found if isinstance(found, str) and found else None

    def groups(self, command: str) -> dict[str, list[dict]]:
        """The hooks a host is given: one group per declared route, running `command`, grouped
        by event in the order the routes are declared."""
        found: dict[str, list[dict]] = {}
        for route in self.routes.values():
            group = {"hooks": [{"type": "command", "command": command}]}
            if route.source is not None:
                group = {"matcher": route.source, **group}
            found.setdefault(route.event, []).append(group)
        return found

    def fits(self, text: str) -> bool:
        """Whether a hook's output carries the text whole on this host."""
        most, unit = self.limit
        return (len(text.encode("utf-8")) if unit == "bytes" else len(text)) <= most

    def output(self, event: dict, text: str) -> str:
        """What the command answering this event prints, for its host to add to the session."""
        return json.dumps({"hookSpecificOutput": {"hookEventName": event["hook_event_name"],
                                                  "additionalContext": text}},
                          ensure_ascii=False)


def adapters() -> dict[str, Adapter]:
    found = {}
    for name in MODULES:
        adapter = importlib.import_module(f"{__name__}.{name}").ADAPTER
        for host in adapter.names:
            found[host] = adapter
    return found


def adapter_for(host_name: str) -> Adapter | None:
    return adapters().get(host_name)


def declares(host_name: str, recipient: str) -> bool:
    """Whether an adapter names the host and declares a route to this recipient."""
    adapter = adapter_for(host_name)
    return adapter is not None and recipient in adapter.routes


def latest_probes(store: storage.Store, host: dict, capability: str) -> list[dict]:
    """The probes of one capability on the host, by name and version, made at the latest instant
    any was."""
    client = {"name": host["name"], "version": host["version"]}
    found = [store.get(digest) for (digest,) in
             store.read("SELECT digest FROM objects WHERE kind = ?", (PROBE,))]
    found = [probe for probe in found
             if probe["client"] == client and probe["capability"] == capability]
    latest = max((probe["at"] for probe in found), default=None)
    return [probe for probe in found if probe["at"] == latest]


def qualified(store: storage.Store, host: dict, recipient: str) -> bool:
    """Whether the latest probe of this recipient's delivery on the host ran for real, through
    the wire the host's route to it takes now, and worked; probes of one instant that disagree
    qualify nothing, and neither does a probe of a carrier the route no longer takes."""
    adapter = adapter_for(host["name"])
    route = adapter.routes.get(recipient) if adapter is not None else None
    probes = latest_probes(store, host, CAPABILITY[recipient])
    return route is not None and bool(probes) and all(
        probe["mode"] == {"runs": "real"} and probe["outcome"] == "worked"
        and probe["wire"] == route.wire for probe in probes)


def supports(store: storage.Store, host: dict, recipient: str) -> bool:
    """Whether a route reaches this recipient on the host installed here."""
    return declares(host["name"], recipient) and qualified(store, host, recipient)


def capability_probe(call) -> dict:
    """C12 `capability.probe`, served by `workenv.hosts.probes`, which drives the adapters."""
    from workenv.hosts import probes
    return probes.capability_probe(call)


def _prepare_probe(call) -> dict:
    from workenv.hosts import probes
    return probes.prepare(call)


capability_probe.prepare = _prepare_probe


def destination_digest(session_id: str) -> str:
    """The digest a link's destination names: of the session id as its host reported it."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()
