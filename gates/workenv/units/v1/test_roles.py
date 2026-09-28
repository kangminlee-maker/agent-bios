"""Activation: what reaches a session activated with one preparation, through the journal."""
from __future__ import annotations

import contextlib
import hashlib
import unittest

import bench
from test_delivery import LATER, NOTE, REVIEW, Delivering
from test_preparation import unit
from test_sources import INSTANT, Checkout, gaps, sha

from workenv import delivery, roles
from workenv.contracts import c01, c02, c03, c04, c07, canonical

ACTIVATE = "session.routing.activate"
RELEASE = b"# Release\n"


class Activating(Delivering):
    def setUp(self):
        super().setUp()
        self.team = {"layer": "team", "team_id": bench.ident("tem")}

    def activate(self, prepared: dict, where=None, target: str | None = None,
                 profile: str | None = None, now: str = INSTANT, host: str = "claude-code",
                 version: str = "1", entry=roles.session_routing_activate) -> dict:
        activation = {"kind": "session_activation", "schema": 1,
                      "preparation_digest": canonical.digest_of(prepared),
                      "session": {"host": {"name": host, "version": version},
                                  "profile_id": profile or self.person.profile}}
        sealed = bench.request(self.person, ACTIVATE, target or self.person.profile, activation)
        with contextlib.chdir(where or self.scratch):
            return self.run_with(entry, sealed, [activation], now=now)

    def activated(self, prepared: dict, **options) -> dict:
        answer = self.activate(prepared, **options)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        return answer


class Routing(Activating):
    def test_a_session_is_activated_with_its_instructions_and_the_usage_contract(self):
        _, digest = self.linked("codex")
        prepared = self.for_link(digest)
        answer = self.activated(prepared, host="codex")
        routing, projection, member = answer["returned"]
        guide = (bench.ROOT / "workenv" / roles.GUIDE).read_bytes()
        self.assertEqual(routing, {
            "kind": "session_routing", "schema": 1,
            "session": {"host": {"name": "codex", "version": "1"},
                        "profile_id": self.person.profile},
            "delivery": {"state": "activated", "projections": [canonical.digest_of(projection)],
                         "memory_usage": {"text": roles.USAGE, "guide": {
                             "path": "guides/memory-use.md",
                             "digest": hashlib.sha256(guide).hexdigest()}}},
            "always_surface": "unchanged", "native_files": "preserved", "routed_at": INSTANT})
        only = prepared["units"][0]
        self.assertEqual(projection["units"], [{
            "unit_id": only["unit_id"], "source_id": only["source_id"],
            "revision_digest": only["revision_digest"], "layer": "personal",
            "standing": "layered", "body_digest": sha(REVIEW), "source_role": "instructions"}])
        self.assertEqual((projection["role"], projection["recipient_view"],
                          projection["material_gaps"], projection["prepared_at"]),
                         ("instructions", "executor", [], INSTANT))
        self.assertTrue(projection["projection_id"].startswith("prj_"))
        self.assertEqual(member, REVIEW)

    def test_the_projection_plan_is_the_preparations_instructions_as_entered_at_start(self):
        _, digest = self.linked()
        prepared = self.for_link(digest)
        projection = self.activated(prepared)["returned"][1]
        only = prepared["units"][0]
        self.assertEqual(projection["plan_digest"], canonical.digest_of({
            "kind": "projection_plan", "schema": 1,
            "source_pins": [{"source_id": only["source_id"],
                             "revision_digest": only["revision_digest"]}],
            "role": "instructions", "recipient_view": "executor",
            "entrance": {"name": "session_start", "root_origin": "owner"},
            "order": prepared["order"]}))

    def test_a_shadowed_unit_is_projected_and_its_body_is_not_delivered(self):
        _, digest = self.linked()
        mine, mine_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        team, team_rev = self.authored(self.team, {"rules/review.md": RELEASE})
        self.placed(self.collection(self.person.scope, "instructions", [self.entry(
            mine, mine_rev, [unit("rules/review.md", "review")])]))
        self.placed(self.collection(self.team, "instructions", [self.entry(
            team, team_rev, [unit("rules/review.md", "review")])]))
        prepared = self.prepared(self.ask([self.person.scope, self.team]),
                                 recipient_digest=digest)
        _, projection, *members = self.activated(prepared)["returned"]
        self.assertEqual([(u["standing"], u.get("shadowed_by") is not None, u["concern"])
                          for u in projection["units"]],
                         [("winning", False, "review"), ("shadowed", True, "review")])
        self.assertEqual(members, [REVIEW])

    def test_a_preparation_with_no_instructions_projects_nothing_and_still_carries_the_contract(
            self):
        _, digest = self.linked()
        source, revision = self.authored(self.person.scope, {"notes.md": NOTE}, role="knowledge")
        prepared = self.prepared(self.ask([self.person.scope], pins=[(source, revision)]),
                                 recipient_digest=digest)
        self.assertEqual([u["role"] for u in prepared["units"]], ["knowledge"])
        (routing,) = self.activated(prepared)["returned"]
        self.assertEqual(routing["delivery"]["projections"], [])
        self.assertEqual(routing["delivery"]["memory_usage"], roles.usage_contract())

    def test_a_projection_leaves_out_the_gaps_of_other_roles_units(self):
        _, digest = self.linked()
        rules, rules_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        notes, notes_rev = self.authored(self.person.scope, {"notes.md": NOTE},
                                         role="knowledge", held=False)
        self.placed(self.collection(self.person.scope, "knowledge", [self.entry(
            notes, notes_rev, [unit("notes.md", "notes")])]))
        answer = self.compose(self.ask([self.person.scope], pins=[(rules, rules_rev)]),
                              recipient_digest=digest)
        units = answer["returned"][0]["units"]
        self.assertEqual([(u["role"], u["standing"]) for u in units],
                         [("instructions", "layered"), ("knowledge", "winning")])
        self.assertEqual(gaps(answer), [{"code": c04.ROLE_BODY_UNAVAILABLE,
                                         "pointer": "/units/1"}])
        projection = self.activated(answer["returned"][0])["returned"][1]
        self.assertEqual(projection["material_gaps"], [])

    def test_a_projection_carries_the_gaps_of_its_own_units_only(self):
        _, digest = self.linked()
        mine, mine_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW},
                                       held=False)
        self.placed(self.collection(self.person.scope, "instructions", [self.entry(
            mine, mine_rev, [unit("rules/review.md", "review")])]))
        prepared = self.compose(self.ask([self.person.scope]),
                                recipient_digest=digest)["returned"][0]
        prepared["material_gaps"].append({"code": c07.WORKING_BYTES_MOVED})
        self.assertEqual(prepared["material_gaps"][0], {"code": c04.ROLE_BODY_UNAVAILABLE,
                                                        "pointer": "/units/0"})
        projection, members = roles.projection(self.bench.call(
            bench.request(self.person, ACTIVATE, self.person.profile), now=INSTANT), prepared)
        self.assertEqual((projection["material_gaps"], members),
                         ([{"code": c04.ROLE_BODY_UNAVAILABLE, "pointer": "/units/0"}], []))


class Refusals(Activating):
    def test_a_session_on_another_profile_is_a_mismatch(self):
        _, digest = self.linked()
        prepared = self.for_link(digest)
        other = bench.ident("prf")
        for answer in (self.activate(prepared, target=other),
                       self.activate(prepared, profile=other),
                       self.activate(prepared, target=other, profile=other)):
            self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH,
                                             "pointer": "/target/resource_id"}])
            self.assertEqual(answer["result"]["supported_recovery"], ["new_governed_request"])

    def test_a_session_on_another_host_than_the_preparations_link_is_a_mismatch(self):
        _, digest = self.linked()
        prepared = self.for_link(digest)
        for host, version in (("codex", "1"), ("claude-code", "2")):
            answer = self.activate(prepared, host=host, version=version)
            self.assertEqual(gaps(answer), [{"code": c02.RECIPIENT_MISMATCH,
                                             "pointer": "/session/host"}])
        self.assertEqual(self.count("deliveries"), 0)
        self.activated(self.for_link(None), host="codex")

    def test_a_preparation_not_composed_here_is_unavailable(self):
        _, digest = self.linked()
        prepared = {**self.for_link(digest), "preparation_id": bench.ident("prp")}
        self.assertEqual(gaps(self.activate(prepared)), [{"code": c01.REF_UNAVAILABLE,
                                                          "pointer": "/preparation_digest"}])


class Handed(Activating):
    """The activation a start hands to a host, and the answers it has before and after."""

    def handed(self, prepared: dict) -> tuple[dict, dict, dict]:
        """The request, its activation and the answer the start is given as it hands it on."""
        activation = {"kind": "session_activation", "schema": 1,
                      "preparation_digest": canonical.digest_of(prepared),
                      "session": {"host": {"name": "claude-code", "version": "1"},
                                  "profile_id": self.person.profile}}
        sealed = bench.request(self.person, ACTIVATE, self.person.profile, activation)
        with contextlib.chdir(self.scratch):
            answer = self.run_with(roles.session_routing_dispatched, sealed, [activation],
                                   now=INSTANT)
        return sealed, activation, answer

    def again(self, sealed: dict, activation: dict, entry) -> dict:
        with contextlib.chdir(self.scratch):
            return self.run_with(entry, sealed, [activation], now=LATER)

    def test_an_activation_handed_on_is_unknown_until_its_session_reports(self):
        prepared = self.for_link(None)
        sealed, activation, answer = self.handed(prepared)
        result = answer["result"]
        self.assertEqual((result["outcome"], result["supported_recovery"], result["local_effect"],
                          result["provider_effect"], result["outputs"], answer["returned"],
                          answer["receipt"]),
                         ({"stage": "unknown", "material_gaps": [{"code": c03.OUTCOME_UNKNOWN}]},
                          ["query_same_request", "retry_same_request"], "private_state_written",
                          "unknown", [], [], None))
        reported = self.again(sealed, activation, roles.session_routing_activate)
        self.assertEqual(reported["result"]["outcome"]["stage"], "committed", gaps(reported))
        self.assertEqual(reported["returned"][-1], REVIEW)

    def test_an_activation_handed_on_is_refused_as_the_activation_is(self):
        _, digest = self.linked()
        prepared = self.for_link(digest)
        for options, gap in (({"target": bench.ident("prf")},
                              {"code": c03.REQUEST_MISMATCH, "pointer": "/target/resource_id"}),
                             ({"host": "codex"},
                              {"code": c02.RECIPIENT_MISMATCH, "pointer": "/session/host"})):
            answer = self.activate(prepared, entry=roles.session_routing_dispatched, **options)
            self.assertEqual(gaps(answer), [gap])
        elsewhere = {**prepared, "preparation_id": bench.ident("prp")}
        self.assertEqual(gaps(self.activate(elsewhere, entry=roles.session_routing_dispatched)),
                         [{"code": c01.REF_UNAVAILABLE, "pointer": "/preparation_digest"}])
        self.assertEqual(self.bench.store().read(
            "SELECT stage FROM requests WHERE operation = ?", (ACTIVATE,)), [("refused",)] * 3)

    def test_an_activation_its_session_never_reported_is_settled_as_not_reported(self):
        prepared = self.for_link(None)
        sealed, activation, _ = self.handed(prepared)
        settled = self.again(sealed, activation, roles.session_routing_unreported)
        result = settled["result"]
        self.assertEqual((result["outcome"], result["supported_recovery"], result["local_effect"],
                          result["provider_effect"], settled["returned"], settled["receipt"]),
                         ({"stage": "expired",
                           "material_gaps": [{"code": c07.DELIVERY_UNOBSERVED}]},
                          ["new_governed_request"], "private_state_written", "dispatched", [],
                          None))
        late = self.again(sealed, activation, roles.session_routing_activate)
        self.assertEqual(late, settled)
        self.activated(prepared, now=LATER)

    def test_an_unknown_activation_holds_back_the_same_one_under_a_new_id(self):
        prepared = self.for_link(None)
        self.handed(prepared)
        self.assertEqual(gaps(self.activate(prepared)),
                         [{"code": c03.RESUBMITTED_WHILE_UNKNOWN, "pointer": "/request_id"}])


class Moved(Activating):
    def authored_in(self, checkout: Checkout) -> dict:
        """A preparation of a repository-authored source admitted from the checkout."""
        _, digest = self.linked()
        checkout.write("rules/review.md", REVIEW)
        checkout.commit()
        self.bind(checkout)
        scope = {"layer": "repository", "repository_id": self.repository}
        with contextlib.chdir(checkout.path):
            source, revision = self.authored(scope, {"rules/review.md": REVIEW},
                                             mode="repository_authored", held=False)
        return self.prepared(self.ask([scope], pins=[(source, revision)]),
                             where=checkout.path, recipient_digest=digest)

    def test_a_repository_authored_document_as_composed_is_activated(self):
        checkout = Checkout(self.scratch)
        prepared = self.authored_in(checkout)
        self.assertEqual(self.activated(prepared, where=checkout.path)["returned"][-1], REVIEW)

    def test_a_repository_authored_document_edited_or_removed_since_is_moved(self):
        checkout = Checkout(self.scratch)
        prepared = self.authored_in(checkout)
        checkout.write("rules/review.md", REVIEW + b"edited\n")
        self.assertEqual(gaps(self.activate(prepared, where=checkout.path)),
                         [{"code": c07.WORKING_BYTES_MOVED}])
        (checkout.path / "rules/review.md").unlink()
        self.assertEqual(gaps(self.activate(prepared, where=checkout.path)),
                         [{"code": c07.WORKING_BYTES_MOVED}])
        self.assertEqual(self.count("deliveries"), 0)

    def test_working_bytes_the_preparation_claimed_that_moved_are_refused(self):
        _, digest = self.linked()
        checkout = Checkout(self.scratch)
        checkout.write("docs/adr/0001.md", b"one\n")
        checkout.commit()
        self.bind(checkout)
        self.observe(self.selection(checkout, ("docs/adr", "required")))
        prepared = self.prepared(self.ask([self.person.scope]), where=checkout.path,
                                 recipient_digest=digest)
        self.assertIn("working_bytes_digest", prepared["observed"])
        checkout.write("docs/adr/0001.md", b"one, edited\n")
        self.assertEqual(gaps(self.activate(prepared, where=checkout.path)),
                         [{"code": c07.WORKING_BYTES_MOVED}])
        checkout.write("docs/adr/0001.md", b"one\n")
        self.activated(prepared, where=checkout.path)


class Recorded(Activating):
    def test_an_activation_is_what_the_links_session_received(self):
        link, digest = self.linked()
        prepared = self.for_link(digest)
        answer = self.activated(prepared)
        (found,) = self.observations(prepared["preparation_id"])["returned"]
        self.assertEqual(found["requested"], {"recipient_kind": delivery.HOST_SESSION,
                                              "recipient_digest": digest})
        self.assertEqual(found["observed"]["saw"], "activated")
        self.assertEqual(found["observed"]["evidence_digest"],
                         canonical.digest_of([answer["result"]["request_digest"]]))
        self.assertEqual([u["body_digest"] for u in found["observed"]["inventory"]],
                         [sha(REVIEW)])

    def test_an_activation_delivers_no_shadowed_body(self):
        _, digest = self.linked()
        mine, mine_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        team, team_rev = self.authored(self.team, {"rules/review.md": RELEASE})
        self.placed(self.collection(self.person.scope, "instructions", [self.entry(
            mine, mine_rev, [unit("rules/review.md", "review")])]))
        self.placed(self.collection(self.team, "instructions", [self.entry(
            team, team_rev, [unit("rules/review.md", "review")])]))
        prepared = self.prepared(self.ask([self.person.scope, self.team]),
                                 recipient_digest=digest)
        self.activated(prepared)
        (found,) = self.observations(prepared["preparation_id"])["returned"]
        self.assertEqual([u["body_digest"] for u in found["observed"]["inventory"]],
                         [sha(REVIEW)])

    def test_a_preparation_composed_for_no_link_is_activated_and_observed_for_nobody(self):
        prepared = self.for_link(None)
        self.assertEqual(self.activated(prepared)["returned"][-1], REVIEW)
        self.assertEqual(self.observations(prepared["preparation_id"])["returned"], [])
        self.assertEqual(self.count("deliveries"), 0)

    def test_a_session_both_delivered_to_and_activated_was_activated(self):
        link, digest = self.linked()
        prepared = self.for_link(digest)
        self.received(link, prepared, "new")
        self.activated(prepared, now=LATER)
        (found,) = self.observations(prepared["preparation_id"])["returned"]
        self.assertEqual((found["observed"]["saw"], found["observed"]["at"],
                          found["recorded_at"]), ("activated", INSTANT, LATER))


if __name__ == "__main__":
    unittest.main()
