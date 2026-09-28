"""Host adapters: every adapter answers one suite, so what differs between hosts is data.

The suite runs once per adapter this installation carries. A host added later is held to it by
listing its module, with no test of its own to write, and the owner's rules are tested once, in
`test_delivery`, because no adapter can change them.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile
import unittest

import bench  # noqa: F401 -- puts the repository root on the import path
from test_shipped import ROOT, ships, shipped

from workenv import hosts

HOSTS = ROOT / "workenv" / "hosts"


def event(route: hosts.Route, **more) -> dict:
    value = {"hook_event_name": route.event, **more}
    if route.source is not None:
        value["source"] = route.source
    return value


class Registry(unittest.TestCase):
    def test_every_adapter_module_is_listed_and_every_listed_one_ships(self):
        on_disk = sorted(path.stem for path in HOSTS.glob("*.py")
                         if "\nADAPTER = Adapter(" in path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(hosts.MODULES), on_disk)
        files = shipped()
        self.assertEqual([name for name in hosts.MODULES
                          if not ships(f"workenv/hosts/{name}.py", files)], [])

    def test_no_two_adapters_claim_one_host_name(self):
        names = [name for adapter in {id(a): a for a in hosts.adapters().values()}.values()
                 for name in adapter.names]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(sorted(names), sorted(hosts.adapters()))

    def test_a_host_no_adapter_names_is_reached_on_no_route(self):
        self.assertIsNone(hosts.adapter_for("a-host-nobody-wrote"))
        self.assertEqual([r for r in hosts.RECIPIENTS if hosts.declares("a-host-nobody-wrote", r)],
                         [])

    def test_a_destination_is_the_digest_of_the_session_id_the_host_reported(self):
        self.assertEqual(hosts.destination_digest("1f0e-세션"),
                         hashlib.sha256("1f0e-세션".encode("utf-8")).hexdigest())

    def test_every_host_hands_each_recipient_through_the_same_carrier(self):
        # One method on both hosts (D-20260928-7c45ce): only the arguments differ.
        carriers = {name: {recipient: route.carrier for recipient, route in adapter.routes.items()}
                    for name, adapter in hosts.adapters().items()}
        self.assertEqual(carriers["claude-code"], {"new": "launch", "rehydrated": "launch",
                                                   "child": "definition", "current": "hook"})
        self.assertEqual([name for name, found in carriers.items()
                          if found != carriers["claude-code"]], [])

    def test_an_adapter_declares_a_child_route_where_its_host_shows_one(self):
        # Claude Code's reference and the subagent-start output schema in Codex 0.157.1's binary
        # both show SubagentStart taking context. A declared route is still delivered on only
        # where a probe qualified it (test_delivery).
        self.assertEqual((hosts.declares("claude-code", "child"), hosts.declares("codex", "child")),
                         (True, True))


class Suite:
    """What every adapter answers. A subclass names the adapter by `host`."""
    host: str

    def setUp(self):
        self.adapter = hosts.adapter_for(self.host)
        self.assertIsNotNone(self.adapter)

    def test_it_declares_routes_only_to_recipients_the_contract_names(self):
        self.assertTrue(self.adapter.routes)
        self.assertLessEqual(set(self.adapter.routes), set(hosts.RECIPIENTS))
        for recipient in hosts.RECIPIENTS:
            self.assertEqual(hosts.declares(self.host, recipient),
                             recipient in self.adapter.routes, recipient)

    def test_each_declared_route_reaches_its_recipient(self):
        for recipient, route in self.adapter.routes.items():
            self.assertEqual(self.adapter.recipient_of(event(route, session_id="s")), recipient)

    def test_no_two_routes_take_one_event(self):
        taken = [(route.event, route.source) for route in self.adapter.routes.values()]
        self.assertEqual(len(taken), len(set(taken)))

    def test_an_event_no_route_declares_reaches_nothing(self):
        for route in self.adapter.routes.values():
            if route.source is not None:
                self.assertIsNone(self.adapter.recipient_of(
                    {"hook_event_name": route.event, "source": "not-" + route.source}))
                self.assertIsNone(self.adapter.recipient_of({"hook_event_name": route.event}))
        self.assertIsNone(self.adapter.recipient_of({"hook_event_name": "Stop"}))
        self.assertIsNone(self.adapter.recipient_of({}))

    def test_the_session_is_the_events_own_id_else_the_commands_environment(self):
        environ = {self.adapter.session_env: "from-env"}
        field = self.adapter.session_field
        self.assertEqual(self.adapter.session_of({field: "from-event"}, environ), "from-event")
        self.assertEqual(self.adapter.session_of({}, environ), "from-env")
        self.assertEqual(self.adapter.session_of(None, environ), "from-env")
        for missing in ({field: ""}, {field: 7}, {}):
            self.assertIsNone(self.adapter.session_of(missing, {}), missing)
        self.assertIsNone(self.adapter.session_of())

    def test_its_hooks_give_every_route_a_place_of_its_own_in_declaration_order(self):
        # Codex trusts a hook by its place, so two routes on one event keep two places.
        groups = self.adapter.groups("run it")
        routes = list(self.adapter.routes.values())
        expected = [(event, route.source) for event in dict.fromkeys(r.event for r in routes)
                    for route in routes if route.event == event]
        self.assertEqual([(event, group.get("matcher")) for event, listed in groups.items()
                          for group in listed], expected)
        for listed in groups.values():
            for group in listed:
                self.assertEqual(group["hooks"], [{"type": "command", "command": "run it"}])
                self.assertNotIn(None, group.values())

    def test_every_route_names_a_carrier_with_its_own_wire(self):
        for recipient, route in self.adapter.routes.items():
            self.assertEqual(route.wire, hosts.WIRES[route.carrier], recipient)
        self.assertEqual(len({json.dumps(wire, sort_keys=True)
                              for wire in hosts.WIRES.values()}), len(hosts.WIRES))

    def test_its_launch_hands_over_the_text_and_each_kind_and_nothing_else(self):
        if all(route.carrier == "hook" for route in self.adapter.routes.values()):
            return
        self.assertTrue(callable(self.adapter.launch))
        with tempfile.TemporaryDirectory() as directory:
            where = pathlib.Path(directory)
            self.assertEqual((self.adapter.launch(where, None, {}), list(where.iterdir())),
                             ([], []))

            def reached(arguments: list[str]) -> str:
                """Every argument, and every file an argument names, as one text."""
                return "\n".join(arguments + [path.read_text(encoding="utf-8")
                                              for path in sorted(where.iterdir())
                                              if any(str(path) in part for part in arguments)])
            text = "규칙 하나: \"인용\" 그리고 \\ 백슬래시.\n"
            given = self.adapter.launch(where, text, {})
            self.assertTrue(given and all(isinstance(part, str) for part in given))
            self.assertIn("규칙 하나", reached(given))
        with tempfile.TemporaryDirectory() as directory:
            where = pathlib.Path(directory)
            kind = hosts.Kind(description="A seat.", instructions="자식 규칙.", model="m",
                              effort="high")
            given = self.adapter.launch(where, None, {"seat": kind})
            self.assertIn("seat", reached(given))
            self.assertIn("자식 규칙.", reached(given))
            self.assertNotIn("규칙 하나", reached(given))

    def test_it_can_drive_its_host_as_a_session_of_its_own(self):
        # A probe started from inside one of the host's sessions must not run as part of it.
        self.assertTrue(self.adapter.binary)
        self.assertTrue(callable(self.adapter.drive))
        self.assertIn(self.adapter.session_env, self.adapter.nested)

    def test_the_output_is_the_text_as_context_for_the_event_that_asked(self):
        for route in self.adapter.routes.values():
            printed = self.adapter.output(event(route), "규칙 하나.\n")
            self.assertEqual(json.loads(printed), {"hookSpecificOutput": {
                "hookEventName": route.event, "additionalContext": "규칙 하나.\n"}})
            self.assertIn("규칙", printed)


def suites() -> dict[str, type]:
    """One test class per host name an adapter carries."""
    found = {}
    for name in sorted(hosts.adapters()):
        title = "".join(part.title() for part in name.replace("-", "_").split("_"))
        found[title] = type(title, (Suite, unittest.TestCase), {"host": name})
    return found


globals().update(suites())

if __name__ == "__main__":
    unittest.main()
