"""An entrance's routes and a scope's history, through the journal: what the owner keeps when an
entrance offers routes and a person selects one (`workenv.cli`), and what it answers when a
scope's recent history is read (`workenv.journal`)."""
from __future__ import annotations

import unittest

import bench
from test_delivery import LATER, Delivering
from test_sources import INSTANT, gaps, sha

from workenv import cli, hosts, journal
from workenv.contracts import c01, c03, c12, canonical

OFFER, SELECT, HISTORY = "route.offer", "route.select", "operation.history.read"
RENAME, ACTIVATE = "access.profile.rename", "session.routing.activate"
# Five seconds after LATER.
LATEST = LATER.replace(":00:05Z", ":00:10Z")


def unknown(call) -> dict:
    """An entry whose host never answered: the outcome is unknown."""
    return journal.answered(call, "unknown", gaps=[{"code": c03.OUTCOME_UNKNOWN}],
                            recovery=["query_same_request", "retry_same_request"],
                            local_effect="private_state_written", provider_effect="unknown")


def commits(call) -> dict:
    return journal.committed(call, [journal.payload(call)])


class Routing(Delivering):
    def setUp(self):
        super().setUp()
        self.repository = {"layer": "repository", "repository_id": bench.ident("rep")}

    def probe(self, host: str = "claude-code", capability: str = "new_delivery",
              outcome: str = "worked", runs: str = "real", carrier: str = "launch",
              at: str = INSTANT) -> str:
        """A probe kept as capability.probe keeps one, and its digest."""
        mode = {"runs": "real"} if runs == "real" else {"runs": "fixture",
                                                          "fixture_digest": sha(b"fixture")}
        probe = {"kind": "capability_probe", "schema": 1, "probe_id": bench.ident("prb"),
                 "client": {"name": host, "version": "1"}, "wire": hosts.WIRES[carrier],
                 "capability": capability, "offered": True, "outcome": outcome,
                 "observed": "what the host did", "mode": mode, "at": at}
        store = self.bench.store()
        with store.unit(self.bench.call(bench.request(self.person, "access.profile.read",
                                                      self.person.profile))):
            return store.put(probe)

    def route(self, action: str = "use", probe: str | None = None,
              scope: dict | None = None) -> dict:
        support = ({"qualified": "yes", "probe_digest": probe} if probe is not None else
                   {"qualified": "no", "because": "offered_but_unproven"})
        return {"route_id": bench.ident("rte"), "scope": scope or self.repository,
                "supported_action": action, "support": support,
                "recovery": ["retry_same_request", "query_same_request"]}

    def offer(self, *routes: dict) -> dict:
        offered = {"kind": "route_offer", "schema": 1,
                   "entrance": {"name": "host_launcher", "root_origin": "owner"},
                   "offered": list(routes)}
        return self.run_with(cli.route_offer,
                             bench.request(self.person, OFFER, self.person.profile, offered),
                             [offered], now=INSTANT)

    def offered(self, *routes: dict) -> dict:
        answer = self.offer(*routes)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        return answer["returned"][0]

    def select(self, offer: dict | str, route: dict, request_id: str, **more) -> dict:
        selection = {"kind": "route_selection", "schema": 1,
                     "offer_digest": offer if isinstance(offer, str) else
                     canonical.digest_of(offer),
                     "selected": route["route_id"],
                     "expected": {"stage": "prepared", "material_gaps": [], "recovery": []},
                     "request_id": request_id, **more}
        answer = self.run_with(cli.route_select,
                               bench.request(self.person, SELECT, self.person.profile, selection),
                               [selection], now=LATER)
        return answer, selection

    def start(self, scopes: list[dict] | None = None, **changes) -> dict:
        """The answer to a start composed for the scopes."""
        return self.compose(self.ask(scopes or [self.repository, self.person.scope]), **changes)

    def activate(self, prepared: dict, entry=unknown) -> dict:
        activation = {"kind": "session_activation", "schema": 1,
                      "preparation_digest": canonical.digest_of(prepared),
                      "session": {"host": {"name": "claude-code", "version": "1"},
                                  "profile_id": self.person.profile}}
        return self.run_with(entry, bench.request(self.person, ACTIVATE, self.person.profile,
                                                  activation), [activation], now=LATER)

    def history(self, scope: dict, limit: int = 10) -> dict:
        query = {"kind": "history_query", "schema": 1, "scope": scope, "limit": limit}
        answer = self.run_with(journal.operation_history_read,
                               bench.request(self.person, HISTORY, self.person.profile, query),
                               [query], now=LATEST)
        self.assertEqual(answer["result"]["outcome"]["stage"], "previewed", gaps(answer))
        return answer["returned"][0]

    def held(self) -> int:
        return self.bench.store().read("SELECT COUNT(*) FROM requests")[0][0]


class Offers(Routing):
    def test_an_offer_is_kept_with_the_instant_it_was_made(self):
        use, decide = self.route(probe=self.probe()), self.route("decide", scope=self.person.scope)
        answer = self.offer(use, decide)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        self.assertIsNotNone(answer["receipt"])
        self.assertEqual(answer["returned"][0]["offered"], [use, decide])
        self.assertEqual(answer["returned"][0]["offered_at"], INSTANT)

    def test_an_unqualified_route_is_kept_as_stated(self):
        self.assertEqual(self.offered(self.route("decide"))["offered"][0]["support"],
                         {"qualified": "no", "because": "offered_but_unproven"})

    def test_a_qualified_route_names_a_probe_held_here(self):
        answer = self.offer(self.route("decide"), self.route(probe=sha(b"no probe")))
        self.assertEqual(gaps(answer), [{"code": c12.CAPABILITY_NOT_QUALIFIED,
                                         "pointer": "/offered/1/support"}])
        self.assertEqual(answer["returned"], [])

    def test_the_probe_is_of_the_capability_the_route_s_action_needs(self):
        self.assertEqual(self.offer(self.route(probe=self.probe()))["result"]["outcome"]["stage"],
                         "committed")
        for action, capability in (("use", "child_delivery"), ("decide", "new_delivery"),
                                   ("decide", "question"), ("read", "new_delivery")):
            with self.subTest(action=action, capability=capability):
                answer = self.offer(self.route(action, self.probe(capability=capability)))
                self.assertEqual(gaps(answer), [{"code": c12.CAPABILITY_NOT_QUALIFIED,
                                                 "pointer": "/offered/0/support"}])

    def test_the_probe_is_the_latest_and_it_ran_for_real_through_the_route_s_wire_and_worked(self):
        for name, options in (("a fixture", {"runs": "fixture"}),
                              ("one that failed", {"outcome": "failed"}),
                              ("through the hook", {"carrier": "hook"}),
                              ("on a host no adapter names", {"host": "another-host"})):
            with self.subTest(probe=name):
                answer = self.offer(self.route(probe=self.probe(**options)))
                self.assertEqual(gaps(answer)[0]["code"], c12.CAPABILITY_NOT_QUALIFIED)
        older = self.probe(host="codex")
        self.assertEqual(self.offer(self.route(probe=older))["result"]["outcome"]["stage"],
                         "committed")
        newer = self.probe(host="codex", at=LATER)
        self.assertEqual(gaps(self.offer(self.route(probe=older)))[0]["code"],
                         c12.CAPABILITY_NOT_QUALIFIED)
        self.assertEqual(self.offer(self.route(probe=newer))["result"]["outcome"]["stage"],
                         "committed")
        self.probe(host="codex", outcome="failed", at=LATEST)
        self.assertEqual(gaps(self.offer(self.route(probe=newer)))[0]["code"],
                         c12.CAPABILITY_NOT_QUALIFIED)


class Selections(Routing):
    def test_a_selection_answers_for_the_start_it_names_with_the_record_it_produced(self):
        use = self.route(probe=self.probe())
        offer = self.offered(use, self.route("decide"))
        started = self.start()
        answer, selection = self.select(offer, use, started["result"]["request_id"],
                                        focused=use["route_id"])
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        self.assertIsNotNone(answer["receipt"])
        self.assertEqual(answer["returned"], [{
            "kind": "route_outcome", "schema": 1,
            "for_request_id": started["result"]["request_id"],
            "client": {"name": "claude-code", "version": "1"}, "capability": "new_delivery",
            "mode": {"runs": "real"},
            "result": {"got": "result",
                       "output_digest": canonical.digest_of(started["returned"][0])},
            "material_gaps": [], "at": LATER}])
        kept = self.bench.store().get(canonical.digest_of({**selection, "selected_at": LATER}))
        self.assertEqual(kept["selected"], use["route_id"])

    def test_the_offer_is_one_the_owner_holds(self):
        use = self.route(probe=self.probe())
        self.offered(use)
        submitted = {"kind": "route_offer", "schema": 1,
                     "entrance": {"name": "host_launcher", "root_origin": "owner"},
                     "offered": [use]}
        for named in (canonical.digest_of(submitted), use["support"]["probe_digest"]):
            answer, _ = self.select(named, use, self.start()["result"]["request_id"])
            self.assertEqual(gaps(answer), [{"code": c01.REF_UNAVAILABLE,
                                             "pointer": "/offer_digest"}])

    def test_the_selected_route_is_one_the_offer_made(self):
        offer = self.offered(self.route(probe=self.probe()))
        answer, _ = self.select(offer, self.route(probe=self.probe()),
                                self.start()["result"]["request_id"])
        self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH, "pointer": "/selected"}])

    def test_an_unqualified_route_is_refused_as_unsupported_and_never_run(self):
        decide = self.route("decide", scope=self.person.scope)
        offer = self.offered(self.route(probe=self.probe(host="codex")), decide)
        before = self.held()
        answer, _ = self.select(offer, decide, bench.ident("req"))
        gap = {"code": c12.CAPABILITY_NOT_QUALIFIED}
        self.assertEqual(answer["result"]["outcome"]["stage"], "refused")
        self.assertEqual((gaps(answer), answer["result"]["local_effect"]), ([gap], "none"))
        self.assertEqual(answer["returned"], [{
            "kind": "route_outcome", "schema": 1,
            "for_request_id": answer["returned"][0]["for_request_id"],
            "client": {"name": "codex", "version": "1"}, "capability": "question",
            "mode": {"runs": "real"},
            "result": {"got": "unsupported", "because": "capability_absent"},
            "material_gaps": [gap], "at": LATER}])
        self.assertEqual(self.held(), before + 1)

    def test_an_offer_whose_qualified_routes_name_no_one_client_returns_no_outcome(self):
        for routes in ((), (self.route(probe=self.probe()),
                            self.route(probe=self.probe(host="codex")))):
            with self.subTest(qualified=len(routes)):
                decide = self.route("decide")
                answer, _ = self.select(self.offered(*routes, decide), decide, bench.ident("req"))
                self.assertEqual(gaps(answer), [{"code": c12.CAPABILITY_NOT_QUALIFIED}])
                self.assertEqual(answer["returned"], [])

    def test_a_route_of_an_action_no_capability_is_needed_for_names_none(self):
        read = self.route("read")
        answer, _ = self.select(self.offered(self.route(probe=self.probe()), read), read,
                                bench.ident("req"))
        self.assertEqual((gaps(answer), answer["returned"]),
                         ([{"code": c12.CAPABILITY_NOT_QUALIFIED}], []))

    def test_a_route_no_longer_qualified_is_refused_as_unsupported_on_its_probe_s_client(self):
        use = self.route(probe=self.probe())
        offer = self.offered(use, self.route(probe=self.probe(host="codex")))
        started = self.start()
        self.probe(outcome="failed", at=LATER)
        answer, _ = self.select(offer, use, started["result"]["request_id"])
        self.assertEqual(gaps(answer), [{"code": c12.CAPABILITY_NOT_QUALIFIED}])
        self.assertEqual([(o["client"]["name"], o["capability"], o["result"])
                          for o in answer["returned"]],
                         [("claude-code", "new_delivery",
                           {"got": "unsupported", "because": "capability_absent"})])

    def test_the_outcome_names_the_first_record_the_start_returned(self):
        use = self.route(probe=self.probe())
        offer = self.offered(use)
        prepared = self.start()["returned"][0]
        started = self.activate(prepared, lambda call: journal.committed(
            call, [prepared, journal.payload(call)]))
        answer, _ = self.select(offer, use, started["result"]["request_id"])
        self.assertEqual(answer["returned"][0]["result"]["output_digest"],
                         canonical.digest_of(prepared))

    def test_the_start_is_held_here_and_of_the_route_s_action(self):
        use = self.route(probe=self.probe())
        offer = self.offered(use)
        answer, _ = self.select(offer, use, bench.ident("req"))
        self.assertEqual(gaps(answer), [{"code": c01.REF_UNAVAILABLE, "pointer": "/request_id"}])
        label = {"kind": "profile_label", "schema": 1, "display_name": "Laptop"}
        renamed = self.run_with(commits, bench.request(self.person, RENAME, self.person.profile,
                                                       label), [label])
        answer, _ = self.select(offer, use, renamed["result"]["request_id"])
        self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH, "pointer": "/request_id"}])

    def test_a_start_still_pending_is_settled_by_querying_it(self):
        use = self.route(probe=self.probe())
        offer = self.offered(use)
        pending = self.activate(self.start()["returned"][0])
        answer, _ = self.select(offer, use, pending["result"]["request_id"])
        self.assertEqual(gaps(answer), [{"code": c03.OUTCOME_UNKNOWN, "pointer": "/request_id"}])
        self.assertEqual(answer["result"]["supported_recovery"], ["query_same_request"])

    def test_a_start_that_returned_no_record_is_nothing_to_answer_with(self):
        use = self.route(probe=self.probe())
        offer = self.offered(use)
        started = self.compose(self.ask([self.person.scope], pins=[(bench.ident("src"),
                                                                    sha(b"not held"))]))
        self.assertEqual(started["result"]["outcome"]["stage"], "refused")
        answer, _ = self.select(offer, use, started["result"]["request_id"])
        self.assertEqual(gaps(answer), [{"code": c01.REF_UNAVAILABLE, "pointer": "/request_id"}])


class History(Routing):
    def test_a_scope_s_history_is_its_starts_oldest_first_with_their_stage_and_when(self):
        started = self.start()
        label = {"kind": "profile_label", "schema": 1, "display_name": "Laptop"}
        self.run_with(commits, bench.request(self.person, RENAME, self.person.profile, label,
                                             work_scope=self.repository), [label])
        pending = self.activate(started["returned"][0])
        found = self.history(self.repository)
        self.assertEqual(found["entries"], [
            {"request_id": started["result"]["request_id"],
             "request_digest": started["result"]["request_digest"],
             "operation": "preparation.compose", "confirmed_stage": "previewed",
             "confirmed_at": INSTANT, "coverage": "local_only", "recovery": []},
            {"request_id": pending["result"]["request_id"],
             "request_digest": pending["result"]["request_digest"],
             "operation": ACTIVATE, "confirmed_stage": "unknown", "confirmed_at": LATER,
             "coverage": "local_only", "recovery": ["query_same_request"]}])
        self.assertEqual((found["scope"], found["observed_at"], found["checkpoints"]),
                         (self.repository, LATEST, []))

    def test_a_request_acts_in_its_owner_its_target_and_the_scopes_its_work_names(self):
        other = {"layer": "repository", "repository_id": bench.ident("rep")}
        started = self.start([self.repository])
        pending = self.activate(started["returned"][0])
        label = {"kind": "profile_label", "schema": 1, "display_name": "Laptop"}
        noted = self.run_with(commits, bench.request(self.person, RENAME, self.person.profile,
                                                     label, work_scope=self.repository,
                                                     rationale="Next: the retry policy."),
                              [label])
        binding = {"kind": "repository_binding", "schema": 1,
                   "repository_id": other["repository_id"], "relation": {"how": "clone"}}
        bound = self.run_with(commits, bench.request(self.person, "repository.bind",
                                                     other["repository_id"], binding,
                                                     rationale="Next: read the README."),
                              [binding], now=LATER)
        mine = self.history(self.repository)
        self.assertEqual([e["request_id"] for e in mine["entries"]],
                         [started["result"]["request_id"], pending["result"]["request_id"]])
        self.assertEqual([c["digest"] for c in mine["checkpoints"]],
                         [noted["result"]["outputs"][0]["digest"]])
        theirs = self.history(other)
        self.assertEqual((theirs["entries"], [(c["kind"], c["note"], c["recorded_at"])
                                              for c in theirs["checkpoints"]]),
                         ([], [("repository_binding", "Next: read the README.", LATER)]))
        personal = self.history(self.person.scope)
        self.assertEqual([e["request_id"] for e in personal["entries"]],
                         [started["result"]["request_id"], pending["result"]["request_id"]])
        self.assertEqual(len(personal["checkpoints"]), 2)
        self.assertEqual(bound["result"]["outcome"]["stage"], "committed")

    def test_a_checkpoint_is_the_first_record_a_noted_request_returned(self):
        started = self.start(rationale="Next: run the payment retry tests.")
        self.start()
        refused = self.compose(self.ask([self.repository], pins=[(bench.ident("src"),
                                                                  sha(b"not held"))]),
                               rationale="Never composed.")
        self.assertEqual(refused["result"]["outcome"]["stage"], "refused")
        self.assertEqual(self.history(self.repository)["checkpoints"], [
            {"digest": canonical.digest_of(started["returned"][0]), "kind": "preparation",
             "recorded_at": INSTANT, "note": "Next: run the payment retry tests."}])

    def test_a_note_longer_than_a_checkpoint_holds_is_cut_and_says_so(self):
        for length, note in ((500, "가" * 500), (501, "가" * 499 + "…")):
            with self.subTest(length=length):
                started = self.start([{"layer": "repository",
                                       "repository_id": bench.ident("rep")}],
                                     rationale="가" * length)
                scope = started["returned"][0]["order"][0]
                self.assertEqual([c["note"] for c in self.history(scope)["checkpoints"]], [note])

    def test_each_list_holds_the_latest_limit_oldest_first(self):
        ids = [self.start(rationale=f"Note {n}.")["result"]["request_id"] for n in range(3)]
        found = self.history(self.repository, limit=2)
        self.assertEqual([e["request_id"] for e in found["entries"]], ids[1:])
        self.assertEqual([c["note"] for c in found["checkpoints"]], ["Note 1.", "Note 2."])

    def test_a_payload_naming_a_record_that_is_no_preparation_names_no_scope(self):
        offer = self.offered(self.route("decide"))
        refused = self.activate(offer, lambda call: journal.answered(
            call, "refused", gaps=[{"code": c01.REF_UNAVAILABLE}]))
        self.assertEqual(refused["result"]["outcome"]["stage"], "refused")
        self.assertEqual(self.history(self.repository)["entries"], [])

    def test_a_basis_that_is_no_preparation_s_names_no_scope(self):
        choice = canonical.load((bench.ROOT / "workenv/contracts/examples/c05/"
                                 "choice_as_submitted.json").read_bytes())
        target = {"resource_id": bench.ident("src"), "base": {"expects": "absent"}}
        refused = self.run_with(lambda call: journal.answered(
            call, "refused", gaps=[{"code": c01.REF_UNAVAILABLE}]),
            bench.request(self.person, "memory.record.publish", target, choice), [choice])
        self.assertEqual(refused["result"]["outcome"]["stage"], "refused")
        self.assertEqual(self.history(self.repository)["entries"], [])

    def test_a_checkpoint_names_the_first_record_of_several(self):
        prepared = self.start()["returned"][0]
        label = {"kind": "profile_label", "schema": 1, "display_name": "Laptop"}
        twice = self.run_with(lambda call: journal.committed(call, [label, prepared]),
                              bench.request(self.person, RENAME, self.person.profile, label,
                                            rationale="Two records."), [label])
        self.assertEqual([(c["digest"], c["kind"])
                          for c in self.history(self.person.scope)["checkpoints"]],
                         [(twice["result"]["outputs"][0]["digest"], "profile_label")])

    def test_reading_history_is_not_history(self):
        self.history(self.person.scope)
        found = self.history(self.person.scope)
        self.assertEqual((found["entries"], found["checkpoints"]), ([], []))

    def test_a_request_held_before_the_journal_kept_notes_is_read_without_one(self):
        started = self.start([self.repository], rationale="Kept before.")
        store = self.bench.store()
        with store.unit(self.bench.call(bench.request(self.person, "access.profile.read",
                                                      self.person.profile))):
            store.write("UPDATE requests SET rationale = NULL, works_in = NULL")
        found = self.history(self.repository)
        self.assertEqual((found["entries"], found["checkpoints"]), ([], []))
        self.assertEqual([e["request_id"] for e in self.history(self.person.scope)["entries"]],
                         [started["result"]["request_id"]])


if __name__ == "__main__":
    unittest.main()
