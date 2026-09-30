"""The start and the hook it configures: a session launched in the person's environment, and what
the owner records at each event its host reports.

The host is `fakehost.py` on a PATH of the test's own, as in `test_probes`; the start, each
adapter, `hook.py` and the owner are the real code. A body carries the probe's instruction, so a
fake session that answers the probe code was handed that body.
"""
from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import io
import json
import pathlib
import tomllib
import unittest
from unittest import mock

import bench
from test_delivery import Delivering
from test_probes import VERSION, Hosts

from workenv import delivery, hosts, journal, roles, storage
from workenv.contracts import c07, canonical
from workenv.hosts import codex, hook, probes, start

CODE = "5eed5eed5eed5eed"
BODY = f"# Review\n\n{probes.handed(CODE)}\n".encode()
OTHER = b"# Release\n\nTag after the review.\n"
ASK = probes.ASK


def child(kind: str) -> str:
    """A prompt asking the session for a child of the kind, as the probe asks."""
    return probes.ASK_CHILD.replace(probes.KIND, kind)


class Starting(Hosts, Delivering):
    def setUp(self):
        Delivering.setUp(self)
        Hosts.setUp(self)
        self.home = pathlib.Path(self.environ["HOME"])
        source, revision = self.authored(self.person.scope, {"rules/review.md": BODY})
        self.request = self.ask([self.person.scope], pins=[(source, revision)])

    def tearDown(self):
        Hosts.tearDown(self)
        Delivering.tearDown(self)

    def roles(self) -> str:
        """Two roles the person defined for Codex: one with instructions of its own, one
        without, as FAKE_HOST_ROLES states them."""
        helper, keeper = self.home / "helper.toml", self.home / "keeper.toml"
        helper.write_text('name = "helper"\ndescription = "Helps."\nmodel = "a-model"\n'
                          'developer_instructions = "  "\n')
        keeper.write_text('name = "keeper"\ndescription = "Keeps."\n'
                          'developer_instructions = "Keep things."\n')
        return json.dumps({"helper": {"description": "Helps.", "config_file": str(helper)},
                           "keeper": {"description": "Keeps.", "config_file": str(keeper)}})

    def launched(self, host: str, recipients=None, sealed: dict | None = None,
                 skip: bool = False, **environ) -> start.Launch:
        """A start on the host, with a real probe of each recipient's route that worked."""
        for recipient in sorted(hosts.adapter_for(host).routes) if recipients is None \
                else recipients:
            self.probed(host, recipient, version=VERSION)
        return start.start(self.bench.state, self.person.actor, host, self.request, self.work,
                           {**self.environ, **environ}, sealed=sealed, skip=skip)

    def sealed(self, payload: dict | None = None, **more) -> dict:
        """The composition request an entry seals for the payload, as the actor's."""
        row, actor = journal.OPERATIONS[start.COMPOSE], self.person.actor
        return {"kind": "operation_request", "schema": 1, "request_id": journal.mint("req"),
                "operation": start.COMPOSE, "effect_class": row["effect"],
                "action": row["action"], "actor": actor, "local_access_generation": 1,
                "owner": self.person.scope, "target": {"resource_id": actor["principal_id"]},
                "policy_digests": [], "control_digests": [], "proof_digests": [],
                "payload_digest": canonical.digest_of(self.request if payload is None
                                                      else payload), **more}

    def composed(self) -> list[tuple[str, str]]:
        return self.bench.store().read("SELECT request_id, request_digest FROM requests "
                                       "WHERE operation = ?", (start.COMPOSE,))

    def given(self, launch: start.Launch, flag: str) -> list[str]:
        return [launch.arguments[i + 1] for i, part in enumerate(launch.arguments)
                if part == flag]

    def settings(self, launch: start.Launch) -> dict:
        """Codex's per-run configuration, by key."""
        return {part.split("=", 1)[0]: tomllib.loads(f"v = {part.split('=', 1)[1]}")["v"]
                for part in self.given(launch, "-c")}

    def fired(self, launch: start.Launch, host: str, recipient: str, session: str = "s-1",
              job: dict | None = None, **more) -> tuple[str, str]:
        """What the hook printed, and said on standard error, for one event of the host."""
        route = hosts.adapter_for(host).routes[recipient]
        event = {"hook_event_name": route.event, **more}
        if session is not None:
            event["session_id"] = session
        if route.source is not None:
            event["source"] = route.source
        path = pathlib.Path(launch.environ[probes.JOB])
        if job is not None:
            path.write_text(json.dumps(job))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.chdir(self.work), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            self.assertEqual(hook.main([host], io.StringIO(json.dumps(event)),
                                       {hook.JOB: str(path)}), 0)
        return out.getvalue(), err.getvalue()

    def recorded(self) -> list[tuple[str, str]]:
        """What the owner recorded as reaching a recipient, in order: what it saw, and whom."""
        store = self.bench.store()
        found = []
        for saw, record in store.read("SELECT saw, record FROM deliveries ORDER BY position"):
            value = store.get(record)
            found.append((saw, value["requested"]["recipient"] if saw != delivery.ACTIVATED
                          else "session"))
        return found

    def job(self, launch: start.Launch) -> dict:
        return json.loads(pathlib.Path(launch.environ[probes.JOB]).read_text())

    def activations(self) -> list[tuple[str, str]]:
        return self.bench.store().read("SELECT request_id, stage FROM requests WHERE "
                                       "operation = ? ORDER BY position", (start.ACTIVATE,))


class Start(Starting):
    def test_a_host_no_probe_qualified_a_new_session_on_is_not_started_with_it(self):
        for host in ("claude-code", "codex"):
            with self.subTest(host=host):
                with self.assertRaisesRegex(start.StartError, "new_delivery"):
                    self.launched(host, recipients=["current", "child", "rehydrated"])
        self.assertFalse((self.bench.state / start.LAUNCHES).exists())
        self.assertEqual(self.bench.store().read("SELECT count(*) FROM preparations"), [(0,)])

    def test_the_session_starts_with_the_environment_and_is_recorded_for_nobody_yet(self):
        for host in ("claude-code", "codex"):
            with self.subTest(host=host):
                launch = self.launched(host, FAKE_HOST_NATIVE="native rules")
                text = launch.text
                self.assertTrue(text.startswith(start.TITLE))
                for part in ("Decision memory is read", "memory-use.md", BODY.decode(),
                             "\n## Personal instructions: ", "\nSource src_", ", body sha256 "):
                    self.assertIn(part, text)
                if host == "claude-code":
                    [path] = self.given(launch, "--append-system-prompt-file")
                    self.assertEqual(pathlib.Path(path).read_text(), text)
                else:
                    # The person's own instructions first: Codex's replace them.
                    self.assertEqual(self.settings(launch)["developer_instructions"],
                                     f"native rules\n\n{text}")
                job = self.job(launch)
                self.assertEqual((job["kind"], job["host"], job["request"], job["tiers"]),
                                 ("session", {"name": host, "version": VERSION}, self.request,
                                  list(start.TIERS)))
                self.assertEqual(len(job["bodies"]), 1)
                self.assertEqual(job["environment"], hashlib.sha256(text.encode()).hexdigest())
                self.assertNotIn("unt_", text)
                self.assertEqual(launch.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.recorded(), [])

    def test_the_start_composes_in_the_checkout_the_session_works_in(self):
        # As the hook's composition at the session's start does, so the two can agree.
        self.launched("codex")
        store = self.bench.store()
        [(digest,)] = store.read("SELECT digest FROM preparations")
        self.assertEqual(store.get(digest)["observed"], {"locator": str(self.work.resolve())})

    def test_each_tier_starts_from_the_definition_the_host_would_load_and_the_environment(self):
        agents = self.home / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "workhorse.md").write_text(
            "---\nname: workhorse\ndescription: The person's own.\nmodel: persons-model\n---\n\n"
            "The person's workhorse.\n")
        (agents / "sweep.md").write_text("---\nname: sweep\nmodel: persons-sweep\n---\nMine.\n")
        (self.work / ".claude" / "agents").mkdir(parents=True)
        (self.work / ".claude" / "agents" / "sweep.md").write_text(
            "---\nname: sweep\ndescription: The project's.\nmodel: projects-sweep\n"
            "tools: [Read, Grep]\n---\nThe project's sweep.\n")
        launch = self.launched("claude-code")
        [path] = self.given(launch, "--agents")
        defined = json.loads(pathlib.Path(path).read_text())
        self.assertEqual(sorted(defined), sorted(start.TIERS))
        # The shipped frontier, its read-only fence carried over.
        self.assertEqual(defined["frontier"]["disallowedTools"], ["Edit", "Write", "NotebookEdit"])
        shipped = (codex.SHIPPED.parents[1] / "claude" / "agents" / "frontier.md").read_text()
        self.assertTrue(defined["frontier"]["prompt"].startswith(shipped.split("---")[2].strip()))
        self.assertEqual((defined["workhorse"]["model"], defined["workhorse"]["description"]),
                         ("persons-model", "The person's own."))
        self.assertEqual((defined["sweep"]["model"], defined["sweep"]["tools"]),
                         ("projects-sweep", ["Read", "Grep"]))
        for tier in start.TIERS:
            self.assertTrue(defined[tier]["prompt"].endswith(launch.text), tier)

    def test_codex_tiers_keep_their_roles_and_a_child_of_no_role_takes_no_environment(self):
        launch = self.launched("codex", FAKE_HOST_NATIVE="native rules")
        given = self.settings(launch)
        roles = {key.split(".")[1] for key in given if key.startswith("agents.")}
        self.assertEqual(roles, {*start.TIERS, "default"})
        sweep = tomllib.loads(pathlib.Path(given["agents.sweep.config_file"]).read_text())
        self.assertEqual(sweep["sandbox_mode"], "read-only")
        self.assertTrue(sweep["developer_instructions"].endswith(launch.text))
        plain = tomllib.loads(pathlib.Path(given["agents.default.config_file"]).read_text())
        self.assertEqual(plain["developer_instructions"], "native rules")

    def test_with_no_instructions_of_the_persons_a_blank_kind_is_given_the_least_that_is_not(
            self):
        # Codex applies no role whose instructions are blank: its child would take the session's.
        launch = self.launched("codex", FAKE_HOST_ROLES=self.roles())
        given = self.settings(launch)
        self.assertEqual({key.split(".")[1] for key in given if key.startswith("agents.")},
                         {*start.TIERS, "default", "helper"})
        for name in ("default", "helper"):
            role = tomllib.loads(pathlib.Path(given[f"agents.{name}.config_file"]).read_text())
            self.assertEqual(role["developer_instructions"], start.PLAIN, name)
        helper = tomllib.loads(pathlib.Path(given["agents.helper.config_file"]).read_text())
        self.assertEqual((helper["model"], helper["description"]), ("a-model", "Helps."))

    def test_where_no_probe_qualified_a_child_every_kind_is_the_hosts_own(self):
        launch = self.launched("claude-code", recipients=["new", "current", "rehydrated"])
        self.assertEqual((self.given(launch, "--agents"), self.job(launch)["tiers"]), ([], []))
        launch = self.launched("codex", recipients=["new", "current", "rehydrated"])
        self.assertEqual({key.split(".")[1] for key in self.settings(launch)
                          if key.startswith("agents.")}, {"default"})

    def test_skipping_the_confirmations_passes_the_host_s_arguments_for_it_last(self):
        for host, flag in (("claude-code", "--dangerously-skip-permissions"),
                           ("codex", "--dangerously-bypass-approvals-and-sandbox")):
            with self.subTest(host=host):
                self.assertNotIn(flag, self.launched(host).arguments)
                launch = self.launched(host, skip=True)
                self.assertEqual((launch.arguments[-1], launch.arguments.count(flag)), (flag, 1))

    def test_a_host_with_no_arguments_to_skip_its_confirmations_is_not_started_skipping_them(
            self):
        adapter = dataclasses.replace(hosts.adapter_for("codex"), skip=())
        self.launched("codex")
        with mock.patch.object(hosts, "adapter_for", return_value=adapter), \
                self.assertRaisesRegex(start.StartError, "confirmations skipped"):
            self.launched("codex", recipients=[], skip=True)
        self.assertEqual(len(self.composed()), 1)

    def test_a_sealed_composition_is_submitted_as_it_was_sealed(self):
        sealed = self.sealed(rationale="다음 단계")
        launch = self.launched("codex", sealed=sealed)
        self.assertEqual(self.composed(), [(sealed["request_id"], canonical.digest_of(sealed))])
        self.assertEqual(self.job(launch)["request"], self.request)

    def test_a_sealed_request_not_this_actor_s_composition_of_this_request_is_refused(self):
        other = {**self.person.actor, "profile_id": journal.mint("prf")}
        for name, sealed in (("payload", self.sealed(payload={**self.request, "schema": 2})),
                             ("actor", self.sealed(actor=other)),
                             ("operation", self.sealed(operation="operation.query"))):
            with self.subTest(name=name), \
                    self.assertRaisesRegex(start.StartError, "sealed request"):
                self.launched("codex", sealed=sealed)
        self.assertEqual(self.composed(), [])
        self.assertFalse((self.bench.state / start.LAUNCHES).exists())

    def test_an_operation_this_installation_does_not_ask_for_is_not_asked(self):
        with self.assertRaisesRegex(start.StartError, "does not ask the owner for team.found"):
            start.answered(self.bench.state, {"operation": "team.found"}, None)

    def test_the_activation_is_handed_on_and_held_unknown_while_the_start_waits(self):
        launch = self.launched("claude-code")
        self.assertEqual(self.activations(), [(launch.activation, "unknown")])
        self.assertEqual(launch.directory, self.bench.state / start.LAUNCHES / launch.activation)
        asked = self.job(launch)["activation"]
        self.assertEqual(asked["request"]["request_id"], launch.activation)
        self.assertEqual(asked["request"]["payload_digest"], canonical.digest_of(asked["payload"]))
        self.assertEqual(asked["payload"]["session"]["host"], {"name": "claude-code",
                                                               "version": VERSION})
        store = self.bench.store()
        [(digest,)] = store.read("SELECT digest FROM preparations")
        self.assertEqual(asked["payload"]["preparation_digest"], digest)
        self.assertTrue(start.waiting(self.bench.state, launch.activation))
        # Only a request id names a launch, never a path that reaches one.
        self.assertFalse(start.waiting(self.bench.state,
                                       f"../{start.LAUNCHES}/{launch.activation}"))
        start.release(launch)
        self.assertFalse(start.waiting(self.bench.state, launch.activation))

    def test_an_activation_refused_as_it_is_handed_on_launches_nothing(self):
        with mock.patch.object(roles, "moved", return_value=True), \
                self.assertRaisesRegex(start.StartError, "refused with working_bytes_moved"):
            self.launched("codex")
        self.assertEqual(list((self.bench.state / start.LAUNCHES).iterdir()), [])
        self.assertEqual([stage for _, stage in self.activations()], ["refused"])

    def test_an_unknown_start_is_settled_as_not_reported_once_nothing_waits_for_it(self):
        state = self.bench.state
        launch = self.launched("codex")
        self.assertIsNone(start.settle(state, launch.activation))
        settled = start.settle(state, launch.activation, waited=True)
        result = settled["result"]
        self.assertEqual((result["outcome"], result["provider_effect"]),
                         ({"stage": "expired",
                           "material_gaps": [{"code": c07.DELIVERY_UNOBSERVED}]}, "dispatched"))
        self.assertIsNone(start.settle(state, launch.activation, waited=True))
        start.release(launch)
        left = self.launched("codex")
        start.release(left)
        self.assertEqual(start.stage(start.settle(state, left.activation)), "expired")
        self.assertEqual([stage for _, stage in self.activations()], ["expired", "expired"])
        for other in (journal.mint("req"), "../" + launch.activation, "req_x"):
            self.assertIsNone(start.settle(state, other), other)
            self.assertFalse(start.waiting(state, other), other)

    def test_an_unknown_activation_no_launch_holds_is_left_for_its_owner(self):
        launch = self.launched("codex")
        start.release(launch)
        (launch.directory / "job.json").unlink()
        self.assertIsNone(start.settle(self.bench.state, launch.activation))
        self.assertEqual([stage for _, stage in self.activations()], ["unknown"])

    def test_a_body_that_is_not_the_one_its_unit_names_is_not_handed_over(self):
        unit = {"unit_id": "u", "source_id": "s", "body_digest": canonical.digest_of({}),
                "layer": "personal", "role": "instructions"}
        with self.assertRaisesRegex(start.StartError, "not the one its unit names"):
            start.bodies_text([unit], [b"other bytes"])

    def test_each_body_is_headed_by_its_layer_its_role_and_the_member_it_is(self):
        rules, notes = b"# Rules\n", b"# Notes\n"
        units = [{"unit_id": "unt_a", "source_id": "src_a", "layer": "repository",
                  "role": "instructions", "member": "AGENTS.md",
                  "body_digest": hashlib.sha256(rules).hexdigest()},
                 {"unit_id": "unt_b", "source_id": "src_b", "layer": "personal",
                  "role": "knowledge", "body_digest": hashlib.sha256(notes).hexdigest()}]
        self.assertEqual(start.bodies_text(units, [rules, notes]),
                         "## Repository instructions: AGENTS.md\n\n"
                         f"Source src_a, body sha256 {units[0]['body_digest']}.\n\n"
                         "# Rules\n\n"
                         "## Personal knowledge\n\n"
                         f"Source src_b, body sha256 {units[1]['body_digest']}.\n\n"
                         "# Notes\n")

    def test_a_selected_source_that_does_not_resolve_still_starts_and_the_session_is_told(self):
        self.placed(self.collection(self.person.scope, "instructions", [
            self.entry(bench.ident("src"), "6" * 64)]))
        launch = self.launched("claude-code")
        self.assertTrue(launch.text.endswith(
            "\n## Missing from this environment\n\nThis environment was asked to hold something "
            "it does not:\n\n- The personal instructions collection: `selection_unresolved`, a "
            "selected source that is unknown, denied or damaged; this is not absence, and no "
            "lower layer silently satisfies it.\n"), launch.text)
        self.assertIn(BODY.decode(), launch.text)
        self.fired(launch, "claude-code", "new")
        self.assertEqual(self.recorded(), [("activated", "session"), ("delivered", "new")])
        store = self.bench.store()
        [(record,)] = store.read("SELECT record FROM deliveries WHERE saw = ?",
                                 (delivery.ACTIVATED,))
        [projection] = store.get(record)["delivery"]["projections"]
        self.assertEqual(store.get(projection)["material_gaps"],
                         [{"code": c07.SELECTION_UNRESOLVED, "pointer": "/collections/0"}])


class Events(Starting):
    def test_the_new_session_is_linked_activated_and_recorded_as_received(self):
        for host in ("claude-code", "codex"):
            with self.subTest(host=host):
                launch = self.launched(host)
                printed, said = self.fired(launch, host, "new", session=f"{host}-1")
                self.assertEqual((printed, said), ("", ""))
        self.assertEqual(self.recorded(), [("activated", "session"), ("delivered", "new")] * 2)
        store = self.bench.store()
        self.assertEqual({store.get(link)["destination"]["destination_digest"]
                          for (link,) in store.read("SELECT digest FROM links")},
                         {hosts.destination_digest(f"{host}-1") for host in ("claude-code",
                                                                             "codex")})

    def test_the_session_s_report_activates_the_start_s_activation_first(self):
        launch = self.launched("claude-code")
        self.fired(launch, "claude-code", "new")
        [first, second] = self.activations()
        self.assertEqual((first, second[1]), ((launch.activation, "committed"), "committed"))

    def test_a_report_after_its_start_was_settled_still_records_the_session(self):
        launch = self.launched("claude-code")
        start.release(launch)
        start.settle(self.bench.state, launch.activation)
        self.assertEqual(self.fired(launch, "claude-code", "new"), ("", ""))
        self.assertEqual(self.recorded(), [("activated", "session"), ("delivered", "new")])
        self.assertEqual(self.activations()[0], (launch.activation, "expired"))

    def test_a_start_s_activation_the_owner_refuses_on_the_report_records_nothing(self):
        launch = self.launched("claude-code")
        with mock.patch.object(roles, "moved", return_value=True):
            printed, said = self.fired(launch, "claude-code", "new")
        self.assertEqual(printed, "")
        self.assertIn("nothing recorded: the start's activation was refused with "
                      "working_bytes_moved", said)
        self.assertEqual((self.recorded(), self.activations()),
                         ([], [(launch.activation, "refused")]))

    def test_the_delivery_recorded_names_a_preparation_that_renders_what_the_session_holds(self):
        launch = self.launched("claude-code")
        self.fired(launch, "claude-code", "new")
        store = self.bench.store()
        [(record,)] = store.read("SELECT record FROM deliveries WHERE saw = ?",
                                 (delivery.DELIVERED,))
        recorded = delivery.preparation_by_digest(
            store, store.get(record)["requested"]["preparation_digest"])
        [(first,), _] = store.read("SELECT digest FROM preparations ORDER BY rowid")
        launched = store.get(first)
        # Two compositions of one request, each with unit ids of its own (C07) ...
        self.assertNotEqual([u["unit_id"] for u in launched["units"]],
                            [u["unit_id"] for u in recorded["units"]])
        # ... render one environment, which is the one the session was handed.
        self.assertEqual(start.environment(self.bench.state, recorded), launch.text)
        self.assertEqual(start.environment(self.bench.state, launched), launch.text)

    def test_a_checkout_that_moved_after_the_start_records_nothing(self):
        launch = self.launched("claude-code")
        job = {**self.job(launch), "environment": hashlib.sha256(b"another").hexdigest()}
        printed, said = self.fired(launch, "claude-code", "new", job=job)
        self.assertEqual(printed, "")
        self.assertIn("nothing recorded: the checkout moved", said)
        self.assertEqual(self.recorded(), [])

    def test_a_compaction_records_the_bodies_the_session_kept(self):
        launch = self.launched("codex")
        self.fired(launch, "codex", "new")
        self.assertEqual(self.fired(launch, "codex", "rehydrated"), ("", ""))
        self.assertEqual(self.recorded()[-1], ("delivered", "rehydrated"))

    def test_a_tier_child_is_recorded_under_its_own_use_and_no_other_child_is(self):
        launch = self.launched("claude-code")
        self.fired(launch, "claude-code", "new")
        for kind in ("reviewer", "general-purpose", "workhorse", "frontier"):
            self.fired(launch, "claude-code", "child", agent_type=kind)
        store = self.bench.store()
        children = store.read("SELECT recipient FROM deliveries WHERE recipient_kind = ?",
                              (delivery.CHILD_SESSION,))
        self.assertEqual(len(children), 2)
        self.assertEqual(len(set(children)), 2)

    def test_a_change_during_the_session_is_printed_once_and_recorded(self):
        launch = self.launched("claude-code")
        self.fired(launch, "claude-code", "new")
        self.assertEqual(self.fired(launch, "claude-code", "current"), ("", ""))
        self.for_link(self.link_digest(), members={"rules/release.md": OTHER})
        printed, _ = self.fired(launch, "claude-code", "current")
        context = json.loads(printed)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(OTHER.decode().strip(), context)
        self.assertEqual(self.recorded()[-1], ("delivered", "current"))
        self.assertEqual(self.fired(launch, "claude-code", "current"), ("", ""))
        self.assertEqual(len(self.recorded()), 3)

    def test_a_recomposition_with_the_bodies_the_session_has_is_neither_printed_nor_recorded(
            self):
        launch = self.launched("claude-code")
        self.fired(launch, "claude-code", "new")
        self.prepared(self.request, recipient_digest=self.link_digest())
        self.assertEqual(self.fired(launch, "claude-code", "current"), ("", ""))
        self.assertEqual(len(self.recorded()), 2)

    def test_a_change_larger_than_the_hook_carries_is_one_notice_and_no_record(self):
        adapter = hosts.adapter_for("codex")
        original = adapter.limit
        object.__setattr__(adapter, "limit", (40, "bytes"))
        self.addCleanup(object.__setattr__, adapter, "limit", original)
        launch = self.launched("codex")
        self.fired(launch, "codex", "new")
        self.for_link(self.link_digest(), members={"rules/release.md": OTHER})
        printed, _ = self.fired(launch, "codex", "current")
        self.assertEqual(json.loads(printed)["hookSpecificOutput"]["additionalContext"],
                         hook.NOTICE)
        self.assertEqual(self.fired(launch, "codex", "current"), ("", ""))
        self.assertEqual(self.recorded(), [("activated", "session"), ("delivered", "new")])

    def test_a_change_on_a_route_no_probe_qualified_is_neither_printed_nor_recorded(self):
        launch = self.launched("claude-code", recipients=["new", "child", "rehydrated"])
        self.fired(launch, "claude-code", "new")
        self.for_link(self.link_digest(), members={"rules/release.md": OTHER})
        self.assertEqual(self.fired(launch, "claude-code", "current"), ("", ""))
        self.assertEqual(len(self.recorded()), 2)

    def test_a_refusal_or_an_unreported_session_leaves_the_host_running(self):
        launch = self.launched("codex")
        job = self.job(launch)
        refused = {**job, "request": {**job["request"], "basis": {
            **job["request"]["basis"], "source_pins": [{"source_id": "src_" + "0" * 32,
                                                        "revision_digest": "0" * 64}]}}}
        printed, said = self.fired(launch, "codex", "new", job=refused)
        self.assertEqual(printed, "")
        self.assertIn("nothing recorded: preparation.compose was refused", said)
        printed, said = self.fired(launch, "codex", "new", session=None, job=job)
        self.assertEqual(printed, "")
        self.assertIn("reported no session id", said)
        self.assertEqual(self.recorded(), [])

    def link_digest(self) -> str:
        [(digest,)] = self.bench.store().read("SELECT digest FROM links")
        return digest


class Hosted(Starting):
    """The start's launch run by the host, whose hooks run `hook.py` as their own processes."""

    def test_a_claude_code_session_answers_from_its_environment_and_is_recorded(self):
        launch = self.launched("claude-code")
        environ = {**self.environ, **launch.environ}
        replies = {}
        for prompt in (ASK, child("workhorse"), child("reviewer")):
            done = probes.ran([launch.executable, *launch.arguments, "-p", "--output-format",
                               "json", prompt], self.work, environ)
            replies[prompt] = json.loads(done.stdout)["result"]
        self.assertEqual(list(replies.values()), [CODE, CODE, "NONE"])
        # Each run is a session of its own; only the tier's child is recorded as reached.
        began = [("activated", "session"), ("delivered", "new")]
        self.assertEqual(self.recorded(), began + began + [("delivered", "child")] + began)
        self.assertEqual(launch.dropped, hosts.adapter_for("claude-code").nested)

    def test_a_codex_session_keeps_its_environment_through_compaction_and_is_recorded(self):
        launch = self.launched("codex", FAKE_HOST_NATIVE="native rules")
        server = codex.Server(launch.executable, launch.arguments, self.work,
                              {**self.environ, **launch.environ}, 20)
        try:
            server.call("initialize", {"clientInfo": {"name": "t", "version": "1"},
                                       "capabilities": {}})
            thread = server.call("thread/start", {"cwd": str(self.work)})["thread"]["id"]
            replies = [server.turn(thread, ASK)]
            server.call("thread/compact/start", {"threadId": thread})
            server.until(lambda message: message.get("method") == "turn/completed")
            replies += [server.turn(thread, prompt) for prompt in
                        (ASK, child("workhorse"), child("default"))]
        finally:
            server.close()
        self.assertEqual(replies, [[CODE], [CODE], [CODE], ["NONE"]])
        self.assertEqual(self.recorded(), [("activated", "session"), ("delivered", "new"),
                                           ("delivered", "rehydrated"), ("delivered", "child")])
        store = storage.of(self.bench.state)
        self.assertEqual(store.read("SELECT count(*) FROM links"), [(1,)])

    def test_no_codex_child_outside_the_tiers_takes_the_environment_whatever_it_was_given(self):
        # The person has no instructions of their own and a role that states none.
        launch = self.launched("codex", FAKE_HOST_ROLES=self.roles())
        server = codex.Server(launch.executable, launch.arguments, self.work,
                              {**self.environ, "FAKE_HOST_ROLES": self.roles(),
                               **launch.environ}, 20)
        try:
            server.call("initialize", {"clientInfo": {"name": "t", "version": "1"},
                                       "capabilities": {}})
            thread = server.call("thread/start", {"cwd": str(self.work)})["thread"]["id"]
            replies = [server.turn(thread, prompt) for prompt in
                       (ASK, child("default"), child("helper"), child("keeper"),
                        child("workhorse"))]
        finally:
            server.close()
        self.assertEqual(replies, [[CODE], ["NONE"], ["NONE"], ["NONE"], [CODE]])


if __name__ == "__main__":
    unittest.main()
