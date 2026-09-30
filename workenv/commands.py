#!/usr/bin/env python3
"""The commands a person runs on the work environment: `python3 workenv/commands.py <verb>`.

`install.sh` dispatches `start`, `profile`, `sources`, `prepare` and `received` here, and the host
launcher routes a bare interactive launch to `start`. Every request is submitted through the
journal as the actor's (`workenv.local`), from the directory the command runs in. The scope is
the repository bound from the checkout the command runs in, where one is bound, and otherwise the
person's.

  - `profile` reads the profile (`access.profile.read`); the first request writes it.
  - `sources` prints each position of the scope's basis in the order they compose: the
    collection or the sources held there, with their accepted revisions and member paths.
  - `prepare <host>` composes the start the entry would suggest and prints the preparation's
    units in order, with their standing and body digests, and its material gaps. It activates
    and launches nothing.
  - `start <host>`: the host probe, if needed; `route.offer` of a start route per host installed
    here that a probe qualified, the named host's first; `operation.history.read` of the scope;
    then the entry, drawn in the terminal (`workenv.terminal`). On a dispatched start, the entry's
    sealed composition request goes unchanged to `workenv.hosts.start` with the permissions the
    person chose. The start composes and hands the activation on; `route.select` records the
    route for that request; and the program runs the host as its child and waits for it, exiting
    with its status. A start the owner refuses is drawn as its answer, and nothing is launched.
  - `received` answers `delivery.observe` for the latest session this installation activated.

Leaving the entry (Ctrl-C, Ctrl-D) sends nothing, and `start` exits with 130.

A session reports that it began through its hook, which activates the start. A start whose
session has not reported by the time its host exits is settled as not reported, and `start` says
so: the next start is not held behind it (`D-20260929-703c89`). A start whose program was itself
ended, by a closed terminal for one, stays unknown, and the entry shows it with its check. Where
no program waits on that start's host any more, the check first settles it as not reported; the
check's query then answers the stage the start stands at, and a start no longer pending is drawn
settled on the same screen, where the next start can run at once.

The host probe: a host whose installed version no probe qualified for delivery to a new session is
probed before anything else, which launches it once and makes one model call; the command says so
first. A host a probe did not qualify is not started. `prepare` probes the same way, because the
suggestion rests on a start route.

`start` and `prepare` offer routes as the entrance they are (`setup`, or `host_launcher` where the
launcher routed here). A root the caller chose (`AGENT_BIOS_STATE_DIR`) makes the offer's
`root_origin` the caller's.
"""
from __future__ import annotations

import argparse
import contextlib
import os
import pathlib
import signal
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from workenv import access, cli, delivery, hosts, journal, local, preparation, storage  # noqa: E402
from workenv import terminal, tui  # noqa: E402
from workenv.contracts import canonical  # noqa: E402
from workenv.hosts import probes, start  # noqa: E402
from workenv.sources import checkouts  # noqa: E402

HOSTS = tuple(hosts.adapters())
ENTRANCES = ("setup", "host_launcher")
NEW = "new"
RECOVERY = ["retry_same_request", "query_same_request"]
HISTORY_LIMIT = 10
SKIP = "skip_confirmations"
# What `start` exits with when the person leaves the entry, as a shell reports an interrupt.
LEFT = 130
# Where a person the launcher routed here goes when the entry cannot start.
PRESETS = "agent-launch --presets HOST opens the preset menu instead."
# What each state of a position means, for a person to read.
STATES = {"installed": "installed", "not_checked": "held; its bodies are read for a task",
          "checked_empty": "none", "configured": "registered, with no accepted revision",
          "partial": "some selected sources do not resolve",
          "missing": "no selected source resolves"}


class CommandError(Exception):
    """What a command could not do, and why, for a person to read."""


class Owner:
    """This installation's state and actor, and the requests made as the actor from the directory
    the command runs in."""

    def __init__(self, environ: dict, workdir: pathlib.Path, actor: dict):
        self.environ, self.workdir, self.actor = environ, pathlib.Path(workdir), actor
        self.state = local.state_root(environ)
        self.person = {"layer": "personal", "principal_id": actor["principal_id"]}

    @property
    def store(self) -> storage.Store:
        return storage.of(self.state)

    def ask(self, operation: str, target: str, payload: dict | None = None,
            expected: str = "committed", **fields) -> dict:
        with contextlib.chdir(self.workdir):
            answer = start.submit(self.state, self.actor, operation, target, payload, **fields)
        if start.stage(answer) != expected:
            raise CommandError(f"{operation} was {start.reason(answer)}")
        return answer

    def scope(self) -> dict:
        checkout = checkouts.top(self.workdir.resolve())
        bound = checkouts.bound_at(self.store, checkout) if checkout is not None else None
        return {"layer": "repository", "repository_id": bound[0]} if bound else self.person

    def layers(self) -> list[dict]:
        scope = self.scope()
        return [scope] + ([self.person] if scope != self.person else [])


def held(environ: dict, workdir: pathlib.Path) -> Owner | None:
    """The owner of an installation that has had its first use, or None."""
    actor = local.held_actor(environ)
    return Owner(environ, workdir, actor) if actor is not None else None


# The host and its routes.

def tool(host_name: str) -> str:
    return tui.TOOLS.get(host_name, host_name)


def installed(owner: Owner, host_name: str) -> dict | None:
    found = probes.installed(hosts.adapter_for(host_name), owner.environ, owner.workdir)
    return {"name": host_name, "version": found[1]} if found else None


def qualifying(store: storage.Store, host: dict) -> dict | None:
    """A latest probe that qualifies delivery to a new session on the host now, or None."""
    capability = hosts.CAPABILITY[NEW]
    return next((probe for probe in hosts.latest_probes(store, host, capability)
                 if cli.qualifies(store, probe, capability)), None)


def qualify(owner: Owner, host_name: str, say) -> tuple[dict, dict]:
    """The installed host and the probe that qualifies its new sessions, probing it if needed."""
    host = installed(owner, host_name)
    if host is None:
        raise CommandError(f"no {tool(host_name)} is installed on this machine's path")
    probe = qualifying(owner.store, host)
    if probe is None:
        say(f"Checking that {tool(host_name)} {host['version']} hands a new session its work "
            f"environment. This runs {tool(host_name)} once and makes one model call.")
        asked = {"kind": "capability_probe", "schema": 1, "client": host,
                 "wire": hosts.adapter_for(host_name).routes[NEW].wire,
                 "capability": hosts.CAPABILITY[NEW]}
        probed = owner.ask("capability.probe", owner.actor["profile_id"], asked)["returned"][0]
        say(f"  {probed['outcome']}: {probed['observed']}")
        probe = qualifying(owner.store, host)
        if probe is None:
            raise CommandError(f"{tool(host_name)} {host['version']} was not shown to hand a new "
                               f"session its work environment, so nothing is started with it")
    return host, probe


def offer(owner: Owner, scope: dict, host_name: str, probe: dict, entrance: str) -> dict:
    """The offer of a start route per host installed here that a probe qualified, the named
    host's first."""
    probes_by_host = {host_name: probe}
    for other in HOSTS:
        if other != host_name:
            host = installed(owner, other)
            found = qualifying(owner.store, host) if host is not None else None
            if found is not None:
                probes_by_host[other] = found
    offered = {"kind": "route_offer", "schema": 1,
               "entrance": {"name": entrance, "root_origin": local.root_origin(owner.environ)},
               "offered": [{"route_id": journal.mint("rte"), "scope": scope,
                            "supported_action": "use",
                            "support": {"qualified": "yes",
                                        "probe_digest": canonical.digest_of(found)},
                            "recovery": list(RECOVERY)} for found in probes_by_host.values()]}
    return owner.ask("route.offer", owner.actor["profile_id"], offered)["returned"][0]


def entry(owner: Owner, host_name: str, entrance: str, locale: str, size: tuple[int, int],
          say, dispatch) -> tuple[tui.Entry, dict]:
    """The entry at this entrance, over what the owner holds once the host is qualified, the
    routes offered and the scope's history read; and the offer."""
    _, probe = qualify(owner, host_name, say)
    scope = owner.scope()
    offered = offer(owner, scope, host_name, probe, entrance)
    owner.ask("operation.history.read", owner.actor["profile_id"],
              {"kind": "history_query", "schema": 1, "scope": scope, "limit": HISTORY_LIMIT},
              expected="previewed")
    _, state = access.profile_of(owner.store, owner.actor["profile_id"])
    script = {"kind": "surface_script", "schema": 1, "entrance": offered["entrance"],
              "terminal": {"columns": size[0], "rows": size[1]}, "locale": locale,
              "inputs": []}
    request = {"actor": owner.actor, "local_access_generation": state["access_generation"]}
    return tui.Entry(owner.store, request, script, dispatch), offered


def checked(answer: dict) -> tuple[str, str | None]:
    """How the entry draws the answer to its check, a query of the unknown start: an outcome the
    journal still holds pending stays unknown, one it no longer holds pending is settled at its
    stage, and a query not answered is unavailable, with why."""
    if start.stage(answer) != "previewed":
        return "unavailable", start.reason(answer)
    found = answer["returned"][0]
    if found.get("kind") == "request_not_held":
        return "unavailable", "this installation holds no such request"
    stage = found["outcome"]["stage"]
    if stage in journal.PENDING:
        return "unknown", None
    return "settled", stage


# The commands.

def profile(owner: Owner, out) -> int:
    found, state = owner.ask("access.profile.read", owner.actor["profile_id"],
                             expected="previewed")["returned"]
    out(f"Profile {found['profile_id']}")
    out(f"  principal {found['principal_id']}")
    out(f"  written at first use, {found['created_at']}")
    out(f"  access {state['state']['is']} ({state['state']['because']}), generation "
        f"{state['access_generation']}")
    out(f"  kept in {owner.state}")
    return 0


def held_at(store: storage.Store, scope: dict, role: str) -> tuple[str | None, list[tuple]]:
    """The collection held at a position, and its sources switched on; or, with none, the
    sources held there: each with its revision, its member paths, and the gap codes it states
    where it does not resolve, read as composition reads it (`preparation.resolved`)."""
    collection_id = preparation.held_collection(store, scope, role)
    if collection_id is not None:
        collection = store.get(journal.head_of(store, collection_id))
        entries = [entry for entry in collection["entries"] if entry["switch"] == "on"] \
            if collection["switch"] == "on" else []
        found = [(entry["source_id"], entry.get("pin", {}).get("revision_digest"),
                  preparation.resolved(store, entry, role)[0]) for entry in entries]
    else:
        found = [(source, revision, []) for source, revision in store.read(
            "SELECT source_id, revision_digest FROM sources WHERE scope = ? AND role = ? "
            "ORDER BY rowid", (journal.scope_key(scope), role))]
    return collection_id, [(source, revision, tui.revision_names(store, revision), codes)
                           for source, revision, codes in found]


def sources(owner: Owner | None, out) -> int:
    if owner is None:
        out("Nothing is held on this installation yet.")
        return 0
    out("Each position, in the order it composes:")
    for scope in owner.layers():
        for role in tui.ROLES:
            position = tui.position_of(owner.store, scope, role)
            collection_id, found = held_at(owner.store, scope, role)
            where = f" (collection {collection_id})" if collection_id else ""
            out(f"  {scope['layer']} {role}{where}: {STATES[position.state]}")
            for source, revision, names, codes in found:
                accepted = f"revision {revision[:12]}" if revision else "no accepted revision"
                line = f"    {source} {accepted}" + (f": {', '.join(names)}" if names else "")
                if codes:
                    line += ("; " if names else ": ") + \
                        f"does not resolve here ({', '.join(dict.fromkeys(codes))})"
                out(line)
    return 0


def prepare(owner: Owner, host_name: str, out) -> int:
    captured: list = []
    held_entry, _ = entry(owner, host_name, "setup", "en", (80, 24), out,
                          lambda sealed, carried: captured.append((sealed, carried[0])))
    held_entry.begin()
    if not captured:
        raise CommandError(f"the last start's result is unknown ({held_entry.draft['request_id']}"
                           f"); agent-bios start {host_name} opens it to check")
    sealed, asked = captured[0]
    with contextlib.chdir(owner.workdir):
        answer = start.answered(owner.state, sealed, asked)
    if start.stage(answer) != "previewed":
        raise CommandError(f"composing was {start.reason(answer)}")
    prepared = answer["returned"][0]
    out(f"Preparation {prepared['preparation_id']}, composed in the order "
        f"{', '.join(scope['layer'] for scope in prepared['order'])}:")
    for unit in prepared["units"]:
        body = unit.get("body_digest", "no body")[:12]
        out(f"  {unit['layer']} {unit['role']} {unit['standing']}: {unit['member']} "
            f"(source {unit['source_id']}, body {body})")
    if not prepared["units"]:
        out("  no unit")
    for gap in prepared["material_gaps"]:
        out(f"  gap {gap['code']}" + (f" at {gap['pointer']}" if "pointer" in gap else ""))
    out("Nothing was activated or launched.")
    return 0


def begin(owner: Owner, host_name: str, entrance: str, locale: str, screen, say, execute) -> int:
    """`start`: the entry, drawn in the terminal, and the host it starts."""
    captured: list = []
    answers: list = []

    def dispatch(sealed: dict, carried: list) -> None:
        if sealed["operation"] == tui.COMPOSE:
            captured.append((sealed, carried[0]))
            return
        with contextlib.chdir(owner.workdir):
            # A start nothing waits for any more is settled first, so the query answers it.
            start.settle(owner.state, carried[0]["request_id"])
            answers.append((sealed["request_id"],
                            checked(start.answered(owner.state, sealed, carried[0]))))

    held_entry, offered = entry(owner, host_name, entrance, locale, screen.size(), say,
                                dispatch)
    launch, after = None, 0
    with screen:
        screen.draw(held_entry.frame(after))
        for given in screen.inputs():
            if given == terminal.QUIT:
                return LEFT
            held_entry.press(given)
            while answers:
                request_id, (state, reason) = answers.pop(0)
                held_entry.answered(request_id, state, reason)
            after += 1
            screen.draw(held_entry.frame(after))
            if not captured:
                continue
            sealed, asked = captured.pop()
            try:
                launch = start.start(owner.state, owner.actor,
                                     held_entry.start.probe["client"]["name"], asked,
                                     owner.workdir, owner.environ, sealed=sealed,
                                     skip=held_entry.permissions == SKIP)
            except start.StartError as error:
                held_entry.answered(sealed["request_id"], "unavailable", str(error))
                after += 1
                screen.draw(held_entry.frame(after))
                continue
            break
    if launch is None:
        return LEFT
    selection = {"kind": "route_selection", "schema": 1,
                 "offer_digest": canonical.digest_of(offered),
                 "selected": held_entry.start.route["route_id"],
                 "expected": {"stage": "prepared", "material_gaps": [], "recovery": []},
                 "request_id": sealed["request_id"]}
    try:
        try:
            owner.ask("route.select", owner.actor["profile_id"], selection)
        except CommandError as error:
            say(f"agent-bios start: the start is not recorded as the route's: {error}")
        return execute(launch, owner.environ)
    finally:
        with contextlib.chdir(owner.workdir):
            settled = start.settle(owner.state, launch.activation, waited=True)
        start.release(launch)
        if settled is not None:
            say(f"agent-bios start: the session never reported that it began, so its start is "
                f"recorded as not reported ({launch.activation}).")


def received(owner: Owner | None, out) -> int:
    found = owner.store.read("SELECT preparation FROM deliveries WHERE saw = ? ORDER BY "
                             "position DESC LIMIT 1", (delivery.ACTIVATED,)) if owner else []
    if not found:
        out("No session started here has reported that it began.")
        return 0
    preparation_id = found[0][0]
    answer = owner.ask("delivery.observe", preparation_id, expected="previewed")
    out(f"What reached the session started with preparation {preparation_id}:")
    for observation in answer["returned"]:
        requested, observed = observation["requested"], observation["observed"]
        who = requested["recipient_kind"].replace("_", " ")
        if "recipient_digest" in requested:
            who += f" {requested['recipient_digest'][:12]}"
        if observed["saw"] == "not_observed":
            gaps = ", ".join(gap["code"] for gap in observation["material_gaps"])
            out(f"  {who}: nothing observed ({gaps})")
            continue
        out(f"  {who}: {observed['saw']} at {observed['at']}")
        for unit in observed["inventory"]:
            out(f"    {unit['unit_id']} from {unit['source_id']}, body "
                f"{unit['body_digest'][:12]}")
        if not observed["inventory"]:
            out("    no body")
    return 0


def waited(number, frame) -> None:
    """An interrupt or quit typed at the terminal while the host runs: it is the host's."""


def execute(launch: start.Launch, environ: dict) -> int:
    """Run the host as this process's child, as the start said to run it, and wait for it; its
    exit status, as a shell reports it. While it runs, this process catches the interrupt and
    quit the terminal sends both, and does nothing with them. A caught signal is the default
    again after `exec`, so the host handles its own."""
    kept = {name: value for name, value in environ.items() if name not in launch.dropped}
    previous = {number: signal.signal(number, waited)
                for number in (signal.SIGINT, signal.SIGQUIT)}
    try:
        done = subprocess.run([launch.executable, *launch.arguments],
                              env={**kept, **launch.environ}, check=False)
    except OSError as error:
        raise CommandError(f"{launch.executable} could not be run: {error}") from error
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    return done.returncode if done.returncode >= 0 else 128 - done.returncode


def parser() -> argparse.ArgumentParser:
    found = argparse.ArgumentParser(prog="agent-bios",
                                    description="The work environment on this installation.")
    verbs = found.add_subparsers(dest="verb", required=True)
    verbs.add_parser("profile", help="show this installation's profile and its access")
    verbs.add_parser("sources", help="show what each position holds, in the order it composes")
    prepared = verbs.add_parser("prepare", help="compose a start and show it; start nothing")
    prepared.add_argument("host", choices=HOSTS)
    started = verbs.add_parser("start", help="open the entry and start a host session")
    started.add_argument("host", choices=HOSTS)
    started.add_argument("--entrance", choices=ENTRANCES, default="setup")
    started.add_argument("--locale", choices=tuple(tui.CATALOG))
    verbs.add_parser("received", help="show what reached the latest session started here")
    return found


def main(argv: list[str] | None = None, environ: dict | None = None,
         workdir: pathlib.Path | None = None, out=print, screen=None, run=execute) -> int:
    args = parser().parse_args(argv)
    environ = dict(os.environ if environ is None else environ)
    workdir = pathlib.Path.cwd() if workdir is None else pathlib.Path(workdir)
    try:
        if args.verb in ("sources", "received"):
            return {"sources": sources, "received": received}[args.verb](held(environ, workdir),
                                                                          out)
        owner = Owner(environ, workdir, local.actor(environ))
        if args.verb == "profile":
            return profile(owner, out)
        if args.verb == "prepare":
            return prepare(owner, args.host, out)
        if screen is None:
            if not (os.isatty(0) and os.isatty(1)):
                raise CommandError("the entry needs a terminal")
            screen = terminal.Terminal()
        return begin(owner, args.host, args.entrance, args.locale or local.locale(environ),
                     screen, out, run)
    except (CommandError, local.LocalError, start.StartError, storage.StorageError) as error:
        print(f"agent-bios {args.verb}: {error}", file=sys.stderr)
        if args.verb == "start" and args.entrance == "host_launcher":
            print(PRESETS, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
