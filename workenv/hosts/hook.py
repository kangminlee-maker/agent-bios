#!/usr/bin/env python3
"""The command a host runs on its events, as its adapter's hook: `python3 hook.py <host name>`.

The command is the same bytes on every run, so a host that asks the person to trust a hook once
(Codex lists a session's hooks as untrusted until the person reviews them) keeps trusting it.
What a run does is named by the job file `AGENT_BIOS_HOOK_JOB` points at, which whoever
configured the hook wrote. The host passes the event on standard input.

A probe's job (`workenv.hosts.probes`) names a recipient and the text it hands that recipient:
where the host's adapter says the event reaches that recipient on a route the hook carries, the
command prints the adapter's output carrying the text, and otherwise nothing. A route another
carrier serves was handed its text when the host started, so the hook hands it nothing.

A session's job (`workenv.hosts.start`) names the state root, the actor, the host, the
preparation request the session was started with, the bodies handed at launch, the tiers, and
the activation the start handed on. The hook records, through the owner, what reached the
session, at the event where the host reports that it did:

  - `new` (the session began): it first asks the start's activation again under its own id, so
    one still unknown activates, and one already settled stays as it was: the session began
    either way. Then it opens the link for the session id the host reported, composes the job's
    request for that link, and only where that composition renders exactly the environment
    handed at launch, byte for byte (the job's digest of it), carrying the same units (the
    job's `carried`, by source, member, revision and body: `start.Handed`), activates the
    session with it and records that the new session received it: the delivery it records names
    a preparation whose text is the text the session holds (F-20). Where they differ, the
    checkout moved between the start and the session, and it records nothing more and says so.
  - `rehydrated` (the session was compacted): it records that the session received again the
    bodies it was activated with, which the host kept.
  - `child` (a child began): for a tier, it records that the child, under a use id of its own,
    received the bodies its definition carried. A child of any other kind received none.
  - `current` (a prompt): where the latest preparation composed for this session's link has not
    reached it, and its carried bodies read otherwise than those the session last received (the
    text a session holds, `start.Handed.body_text`), the hook prints its bodies and records that
    the session received them, once: the host runs this hook more than
    once a turn. Where they are more than the host's hook carries whole, it prints a short
    notice that a new session receives them, once for that preparation, and records nothing;
    where no probe qualified the route, it prints and records nothing. A prompt with nothing new
    prints nothing.

Only the last prints, and what it prints is handed over before it is recorded: the delivery is
recorded, or the notice kept as given, only once the output was written to the host. Output the
host did not take records nothing, so a later prompt hands it again; output taken and then not
recorded is said on standard error. It never fails its host: an event it cannot read, a job it
cannot read or an owner that refuses leaves the session as it was, with the reason on standard
error.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import sys
from typing import Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from workenv import delivery, hosts, journal, storage  # noqa: E402
from workenv.contracts import canonical  # noqa: E402
from workenv.hosts import start  # noqa: E402

JOB = "AGENT_BIOS_HOOK_JOB"
NOTICE = ("agent-bios: this session's work environment changed, and the change is larger than "
          "this host takes from a hook during a session. A new session started through "
          "agent-bios receives it whole.")


class Unrecorded(Exception):
    """Nothing was recorded for the event, and why."""


def answer(host_name: str, event: dict, job: dict) -> str | None:
    """What the command prints for one event of a probe's job: the adapter's output where the
    event reaches the job's recipient on a route the hook carries, or None."""
    adapter = hosts.adapter_for(host_name)
    recipient = adapter.recipient_of(event) if adapter is not None else None
    if recipient is None or recipient != job["recipient"] or \
            adapter.routes[recipient].carrier != "hook":
        return None
    return adapter.output(event, job["text"])


class Session:
    """One host session a start launched, as the owner holds it."""

    def __init__(self, adapter: hosts.Adapter, event: dict, job: dict, environ: dict):
        self.adapter, self.event, self.job = adapter, event, job
        # The launch's own directory, which holds the job.
        self.directory = pathlib.Path(environ[JOB]).parent
        self.state = pathlib.Path(job["state"])
        self.actor, self.host = job["actor"], job["host"]
        self.id = adapter.session_of(event, environ)
        if self.id is None:
            raise Unrecorded("the host reported no session id")
        self.store = storage.of(self.state)
        # What is recorded once the output is handed over (`main`), or nothing.
        self.handed: Callable | None = None

    def asked(self, operation: str, target: str, payload: dict | None = None,
              expected: str = "committed", **fields) -> dict:
        answer = start.submit(self.state, self.actor, operation, target, payload, **fields)
        if start.stage(answer) != expected:
            raise Unrecorded(f"{operation} was {start.reason(answer)}")
        return answer

    def link(self) -> tuple[dict, str]:
        """The link opened for this session: the latest naming its id on its host."""
        destination = hosts.destination_digest(self.id)
        found = [value for value in (self.store.get(digest) for (digest,) in
                                     self.store.read("SELECT digest FROM links"))
                 if value["destination"]["destination_digest"] == destination
                 and value["host"]["name"] == self.host["name"]]
        if not found:
            raise Unrecorded("no link was opened for this session")
        latest = max(found, key=lambda value: value["created_at"])
        return latest, canonical.digest_of(latest)

    def reached(self, link_digest: str) -> list[dict]:
        """The preparations whose bodies reached this session, in the order they did."""
        return [delivery.preparation_by_id(self.store, preparation) for (preparation,) in
                self.store.read("SELECT preparation FROM deliveries WHERE recipient = ? AND "
                                "saw IN (?, ?) ORDER BY position",
                                (link_digest, delivery.ACTIVATED, delivery.DELIVERED))]

    def activated(self, link_digest: str) -> dict:
        reached = self.reached(link_digest)
        if not reached:
            raise Unrecorded("nothing reached this session")
        return reached[0]

    def attempt(self, link: dict, prepared: dict, recipient: str) -> None:
        self.asked("recipient.delivery.attempt", link["link_id"], {
            "kind": "delivery_attempt", "schema": 1, "link_id": link["link_id"],
            "use_id": journal.mint("use"),
            "requested": {"what": "body", "recipient": recipient,
                          "preparation_digest": canonical.digest_of(prepared),
                          "bodies": self.described(prepared).bodies}})

    def described(self, prepared: dict) -> start.Handed:
        return start.handed(self.state, prepared)

    def confirmed(self) -> None:
        """The start's activation, asked again under its own id now the session has begun."""
        asked = self.job["activation"]
        answer = start.answered(self.state, asked["request"], asked["payload"])
        if start.stage(answer) == "refused" or start.stage(answer) in journal.PENDING:
            raise Unrecorded(f"the start's activation was {start.reason(answer)}")

    def began(self) -> None:
        self.confirmed()
        principal = self.actor["principal_id"]
        link = self.asked("recipient.link.open", principal, {
            "kind": "recipient_link", "schema": 1, "principal_id": principal,
            "work_scope": {"layer": "personal", "principal_id": principal}, "host": self.host,
            "destination": {"destination_kind": "conversation",
                            "destination_digest": hosts.destination_digest(self.id)},
            "isolation": "proven_fresh"})["returned"][0]
        prepared = self.asked("preparation.compose", principal, self.job["request"],
                              expected="previewed",
                              recipient_digest=canonical.digest_of(link))["returned"][0]
        mine = self.described(prepared)
        if mine.digest != self.job.get("environment") or \
                mine.carried != self.job.get("carried", mine.carried):
            raise Unrecorded("the checkout moved after the session was started: what composes "
                             "now is not what the session was handed")
        self.asked("session.routing.activate", self.actor["profile_id"], {
            "kind": "session_activation", "schema": 1,
            "preparation_digest": canonical.digest_of(prepared),
            "session": {"host": self.host, "profile_id": self.actor["profile_id"]}})
        self.attempt(link, prepared, "new")

    def compacted(self) -> None:
        link, digest = self.link()
        self.attempt(link, self.activated(digest), "rehydrated")

    def child(self) -> None:
        if self.event.get("agent_type") not in self.job["tiers"]:
            return
        link, digest = self.link()
        self.attempt(link, self.activated(digest), "child")

    def prompted(self) -> str | None:
        link, digest = self.link()
        reached = self.reached(digest)
        composed = [value for value in (self.store.get(row) for (row,) in self.store.read(
            "SELECT digest FROM preparations ORDER BY rowid"))
            if value["recipient"].get("recipient_digest") == digest]
        if not reached or not composed:
            return None
        latest = composed[-1]
        given = self.described(latest)
        # What the session holds is the bodies' text: a preparation that hands the same text
        # brings nothing new, whatever else about it changed.
        if given.body_text == self.described(reached[-1]).body_text or \
                not hosts.supports(self.store, self.host, "current"):
            return None
        text = f"{start.TITLE}, as it changed during this session\n\n" + given.body_text
        if not self.adapter.fits(text):
            return self.noticed(latest)
        self.handed = lambda: self.attempt(link, latest, "current")
        return self.adapter.output(self.event, text)

    def noticed(self, prepared: dict) -> str | None:
        """The notice that a new session receives the preparation, given once for it."""
        kept = self.directory / "noticed"
        if prepared["preparation_id"] in (kept.read_text().split() if kept.is_file() else []):
            return None

        def given() -> None:
            with kept.open("a", encoding="utf-8") as out:
                out.write(prepared["preparation_id"] + "\n")
        self.handed = given
        return self.adapter.output(self.event, NOTICE)


def recorded(host_name: str, event: dict, job: dict,
             environ: dict) -> tuple[str | None, Callable | None]:
    """What the command prints for one event of a session's job, having recorded what reached
    the session by then, and what it records once that is handed over, or None."""
    adapter = hosts.adapter_for(host_name)
    if adapter is None:
        raise Unrecorded(f"no adapter here names {host_name}")
    recipient = adapter.recipient_of(event)
    if recipient is None:
        return None, None
    session = Session(adapter, event, job, environ)
    if recipient == "new":
        session.began()
    elif recipient == "rehydrated":
        session.compacted()
    elif recipient == "child":
        session.child()
    elif recipient == "current":
        return session.prompted(), session.handed
    return None, None


def main(argv: list[str], stdin, environ) -> int:
    try:
        event = json.load(stdin)
        job = json.loads(pathlib.Path(environ[JOB]).read_text(encoding="utf-8"))
        printed, handed = recorded(argv[0], event, job, environ) \
            if job.get("kind") == "session" else (answer(argv[0], event, job), None)
    except (IndexError, KeyError, OSError, ValueError, TypeError) as error:
        print(f"agent-bios hook: nothing handed over ({type(error).__name__})", file=sys.stderr)
        return 0
    except (Unrecorded, start.StartError) as error:
        print(f"agent-bios hook: nothing recorded: {error}", file=sys.stderr)
        return 0
    if printed is None:
        return 0
    try:
        print(printed, flush=True)
    except OSError as error:
        # The host did not take it: nothing is recorded, and a later prompt hands it again. What
        # stays buffered goes nowhere, so the flush at exit does not fail the host's hook.
        with contextlib.suppress(AttributeError, OSError, ValueError, io.UnsupportedOperation):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        print(f"agent-bios hook: nothing handed over ({type(error).__name__})", file=sys.stderr)
        return 0
    if handed is not None:
        try:
            handed()
        except (KeyError, OSError, ValueError, TypeError, Unrecorded, start.StartError) as error:
            print(f"agent-bios hook: handed over and not recorded: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], sys.stdin, os.environ))
