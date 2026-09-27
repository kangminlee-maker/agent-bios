"""Host adapters: how each host's own events reach one of its sessions, stated as data, and
whether a route has been shown to work on the host installed here.

The delivery owner (`workenv.delivery`, `workenv.roles`) knows links, preparations and what was
delivered to whom, and nothing about any host. An adapter knows one host and nothing about the
delivery rules: which of its events reaches which recipient C11 names (`new`, `current`, `child`,
`rehydrated`), where a session's own id is found, and how the host takes text into a session's
context. A host is added by writing its module and listing it in `MODULES`; nothing in the owner
changes.

What an adapter declares is how it would reach a recipient, never that it does. A route is
supported on a host only where the adapter declares it and the latest probe of that recipient's
delivery capability (C12) on that host, by name and version, ran for real and worked; a probe
run against a fixture, one that did not work, or none at all leaves the route unsupported, and a
host's documentation cannot stand in for the probe. A route without that is not delivered on: no
other route stands in for it. A host no adapter names has no route at all, so its sessions can
take what the owner composes only by hand, and nothing records a delivery the runtime did not
observe.

The destination a link names is the digest of the session id the adapter reported, the host's
own bytes and never an id the runtime makes up.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json

from workenv import storage

RECIPIENTS = ("new", "current", "child", "rehydrated")
# The C12 capability that qualifies delivery to each recipient.
CAPABILITY = {recipient: f"{recipient}_delivery" for recipient in RECIPIENTS}
PROBE = "capability_probe"
# The adapters this installation carries, by module under this package.
MODULES = ("claude_code", "codex")


@dataclasses.dataclass(frozen=True)
class Route:
    """One host event, and the value of its `source` field where the event has one."""
    event: str
    source: str | None = None


@dataclasses.dataclass(frozen=True)
class Adapter:
    names: tuple[str, ...]
    # The recipient each declared route reaches.
    routes: dict[str, Route]
    # The environment variable a command the session runs finds its session id in.
    session_env: str
    # The field of an event's input that holds the session id.
    session_field: str = "session_id"

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
    """Whether the latest probe of this recipient's delivery on the host ran for real and worked;
    probes of one instant that disagree qualify nothing."""
    probes = latest_probes(store, host, CAPABILITY[recipient])
    return bool(probes) and all(probe["mode"] == {"runs": "real"} and probe["outcome"] == "worked"
                                for probe in probes)


def supports(store: storage.Store, host: dict, recipient: str) -> bool:
    """Whether a route reaches this recipient on the host installed here."""
    return declares(host["name"], recipient) and qualified(store, host, recipient)


def destination_digest(session_id: str) -> str:
    """The digest a link's destination names: of the session id as its host reported it."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()
