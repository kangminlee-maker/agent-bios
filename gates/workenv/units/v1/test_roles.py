"""Activation: what reaches a session activated with one preparation, through the journal."""
from __future__ import annotations

import contextlib
import hashlib
import unittest

import bench
from test_delivery import LATER, NOTE, REVIEW, Delivering
from test_preparation import unit
from test_sources import INSTANT, Checkout, gaps, sha

from workenv import delivery, roles, storage
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
        call = self.bench.call(bench.request(self.person, ACTIVATE, self.person.profile),
                               now=INSTANT)
        held, why = roles.bodies(call.state, prepared)
        projection, members = roles.projection(call, prepared, held)
        self.assertEqual((projection["material_gaps"], members, why),
                         ([{"code": c04.ROLE_BODY_UNAVAILABLE, "pointer": "/units/0"}], [], None))

    def test_a_selected_instructions_source_that_does_not_resolve_is_carried_with_no_unit(self):
        _, digest = self.linked()
        self.placed(self.collection(self.person.scope, "instructions", [
            self.entry(bench.ident("src"), "6" * 64)]))
        prepared = self.prepared(self.ask([self.person.scope]), recipient_digest=digest)
        unresolved = [{"code": c07.SELECTION_UNRESOLVED, "pointer": "/collections/0"}]
        self.assertEqual((prepared["units"], prepared["material_gaps"]), ([], unresolved))
        routing, projection = self.activated(prepared)["returned"]
        self.assertEqual(routing["delivery"]["projections"], [canonical.digest_of(projection)])
        self.assertEqual((projection["units"], projection["material_gaps"]), ([], unresolved))

    def test_an_unresolved_selection_of_another_role_is_not_carried(self):
        _, digest = self.linked()
        self.placed(self.collection(self.person.scope, "knowledge", [
            self.entry(bench.ident("src"), "6" * 64)]))
        prepared = self.prepared(self.ask([self.person.scope]), recipient_digest=digest)
        self.assertEqual(prepared["material_gaps"],
                         [{"code": c07.SELECTION_UNRESOLVED, "pointer": "/collections/0"}])
        (routing,) = self.activated(prepared)["returned"]
        self.assertEqual(routing["delivery"]["projections"], [])


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

    def test_a_body_no_longer_held_as_its_unit_names_refuses_and_records_nothing(self):
        # The bundle a carried body was composed from holds other bytes, or none, by the time the
        # activation reads it: the activation and the answer as it is handed on are refused, and
        # no session is recorded as having received anything (r11-0).
        for changed, code in ((b"Do not require review.\n", c03.OBJECT_DIGEST_MISMATCH),
                              (None, c04.ROLE_BODY_UNAVAILABLE)):
            with self.subTest(code=code):
                _, digest = self.linked("codex")
                prepared = self.for_link(digest)
                only = prepared["units"][0]
                held = storage.bundle(self.bench.state, only["revision_digest"]) / \
                    storage.MEMBERS / only["member"]
                original, before = held.read_bytes(), self.count("deliveries")
                held.chmod(0o644)
                if changed is None:
                    held.unlink()
                else:
                    held.write_bytes(changed)
                try:
                    for entry in (roles.session_routing_dispatched,
                                  roles.session_routing_activate):
                        answer = self.activate(prepared, host="codex", entry=entry)
                        self.assertEqual((answer["result"]["outcome"]["stage"], gaps(answer),
                                          answer["returned"]),
                                         ("refused", [{"code": code,
                                                       "pointer": "/preparation_digest"}], []))
                    self.assertEqual(self.count("deliveries"), before)
                finally:
                    held.write_bytes(original)
                answer = self.activated(prepared, host="codex")
                self.assertEqual(answer["returned"][-1], original)


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


class Required(Activating):
    def winner(self, startup: str = "required", needs=None, held: bool = False) -> dict:
        """A preparation whose winning Instructions unit declares `startup` and `needs`, its
        body held or not."""
        _, digest = self.linked()
        mine, mine_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW}, held=held)
        declared = unit("rules/review.md", "review", startup, **({"needs": needs} if needs else {}))
        self.placed(self.collection(self.person.scope, "instructions", [
            self.entry(mine, mine_rev, [declared])]))
        return self.prepared(self.ask([self.person.scope]), recipient_digest=digest)

    def test_a_required_winner_whose_body_is_not_held_is_refused(self):
        prepared = self.winner()
        unavailable = [{"code": c04.ROLE_BODY_UNAVAILABLE, "pointer": "/units/0"}]
        self.assertEqual(prepared["material_gaps"], unavailable)
        for entry in (roles.session_routing_activate, roles.session_routing_dispatched):
            with self.subTest(entry=entry.__name__):
                answer = self.activate(prepared, entry=entry)
                self.assertEqual(gaps(answer), unavailable)
                self.assertEqual(answer["result"]["supported_recovery"], ["new_governed_request"])
        self.assertEqual(self.count("deliveries"), 0)

    def test_a_winner_not_required_at_startup_whose_body_is_not_held_starts(self):
        prepared = self.winner("not_required")
        projection = self.activated(prepared)["returned"][1]
        self.assertEqual(projection["material_gaps"],
                         [{"code": c04.ROLE_BODY_UNAVAILABLE, "pointer": "/units/0"}])

    def test_a_unit_a_required_winner_needs_whose_body_is_not_held_is_refused(self):
        # Not required by itself, and the only unit of its concern: only the need gates it.
        needed, needed_rev = self.authored(self.team, {"rules/base.md": NOTE}, held=False)
        self.placed(self.collection(self.team, "instructions", [
            self.entry(needed, needed_rev, [unit("rules/base.md", "base", "not_required")])]))
        _, digest = self.linked()
        mine, mine_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        self.placed(self.collection(self.person.scope, "instructions", [self.entry(
            mine, mine_rev, [unit("rules/review.md", "review", needs=[
                {"source_id": needed, "member": "rules/base.md"}])])]))
        prepared = self.prepared(self.ask([self.person.scope, self.team]),
                                 recipient_digest=digest)
        [base] = [u for u in prepared["units"] if u["source_id"] == needed]
        self.assertIn("needed_by", base)
        self.assertEqual([gap["code"] for gap in gaps(self.activate(prepared))],
                         [c04.ROLE_BODY_UNAVAILABLE])


    def needing_off(self, held: bool) -> tuple[dict, dict]:
        """A preparation whose required winner needs a unit its collection switches off, that
        unit's bytes held or not: the preparation and the needed unit."""
        needed, needed_rev = self.authored(self.team, {"rules/base.md": NOTE}, held=held)
        self.placed(self.collection(self.team, "instructions", [self.entry(
            needed, needed_rev, [unit("rules/base.md", "base")], switch="off")]))
        _, digest = self.linked()
        mine, mine_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        self.placed(self.collection(self.person.scope, "instructions", [self.entry(
            mine, mine_rev, [unit("rules/review.md", "review", needs=[
                {"source_id": needed, "member": "rules/base.md"}])])]))
        prepared = self.prepared(self.ask([self.person.scope, self.team]),
                                 recipient_digest=digest)
        [base] = [u for u in prepared["units"] if u["source_id"] == needed]
        self.assertEqual((base["standing"], "needed_by" in base), ("disabled", True))
        return prepared, base

    def test_a_switched_off_unit_a_required_winner_needs_gates_the_start(self):
        prepared, base = self.needing_off(held=False)
        self.assertNotIn("body_digest", base)
        self.assertEqual(gaps(self.activate(prepared)), [{"code": c04.ROLE_BODY_UNAVAILABLE,
                                                          "pointer": "/units/1"}])

    def test_a_switched_off_unit_a_required_winner_needs_is_read_and_not_delivered(self):
        prepared, base = self.needing_off(held=True)
        self.assertEqual(base["body_digest"], sha(NOTE))
        answer = self.activated(prepared)
        self.assertEqual(answer["returned"][2:], [REVIEW])


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

    def test_a_switched_off_repository_authored_unit_claims_nothing_and_activates(self):
        _, digest = self.linked()
        checkout = Checkout(self.scratch)
        checkout.write("rules/review.md", REVIEW)
        checkout.commit()
        self.bind(checkout)
        scope = {"layer": "repository", "repository_id": self.repository}
        with contextlib.chdir(checkout.path):
            source, revision = self.authored(scope, {"rules/review.md": REVIEW},
                                             mode="repository_authored", held=False)
        self.placed(self.collection(scope, "instructions",
                                    [self.entry(source, revision, switch="off")]))
        prepared = self.prepared(self.ask([scope]), where=checkout.path, recipient_digest=digest)
        self.assertEqual([(u["standing"], "body_digest" in u) for u in prepared["units"]],
                         [("disabled", False)])
        self.activated(prepared, where=checkout.path)

    def test_a_shadowed_document_no_winner_needs_blocks_nothing_and_a_needed_one_does(self):
        checkout = Checkout(self.scratch)
        checkout.write("rules/review.md", REVIEW)
        checkout.commit()
        self.bind(checkout)
        scope = {"layer": "repository", "repository_id": self.repository}
        with contextlib.chdir(checkout.path):
            theirs, theirs_rev = self.authored(scope, {"rules/review.md": REVIEW},
                                               mode="repository_authored", held=False)
        mine, mine_rev = self.authored(scope, {"rules/mine.md": NOTE})
        held, head = None, None
        for needs in (None, [{"source_id": theirs, "member": "rules/review.md"}]):
            with self.subTest(needs=needs):
                _, digest = self.linked(session=f"session-{bool(needs)}")
                declared = unit("rules/mine.md", "review",
                                **({"needs": needs} if needs else {}))
                held = {**(held or self.collection(scope, "instructions", [])), "entries": [
                    self.entry(mine, mine_rev, [declared], precedence=1),
                    self.entry(theirs, theirs_rev, [unit("rules/review.md", "review")],
                               precedence=2)]}
                answer = self.change(held, head and {"expects": "head", "head_digest": head})
                head = answer["receipt"]["head_digest"]
                checkout.write("rules/review.md", REVIEW)
                prepared = self.prepared(self.ask([scope]), where=checkout.path,
                                         recipient_digest=digest)
                self.assertEqual([(u["source_id"], u["standing"]) for u in prepared["units"]],
                                 [(mine, "winning"), (theirs, "shadowed")])
                checkout.write("rules/review.md", REVIEW + b"edited\n")
                answer = self.activate(prepared, where=checkout.path)
                if needs:
                    self.assertEqual(gaps(answer), [{"code": c07.WORKING_BYTES_MOVED}])
                else:
                    self.assertEqual(answer["result"]["outcome"]["stage"], "committed")

    def test_a_document_is_drifted_only_where_its_authored_checkout_no_longer_reads_as_it(self):
        checkout = Checkout(self.scratch)
        prepared = self.authored_in(checkout)
        [authored] = prepared["units"]
        store = self.bench.store()
        drifted = lambda: roles.drifted(store, authored["source_id"], "rules/review.md",  # noqa
                                        authored["body_digest"])
        self.assertFalse(drifted())
        mine, revision = self.authored(self.person.scope, {"rules/review.md": NOTE})
        self.assertFalse(roles.drifted(store, mine, "rules/review.md", sha(REVIEW)))
        checkout.write("rules/review.md", REVIEW + b"edited\n")
        self.assertTrue(drifted())
        (checkout.path / "rules/review.md").unlink()
        self.assertTrue(drifted())

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

    def test_a_unit_no_delivery_carries_is_not_received_although_its_body_is_the_same(self):
        _, digest = self.linked()
        rules, rules_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        notes, notes_rev = self.authored(self.person.scope, {"notes/review.md": REVIEW},
                                         role="knowledge")
        prepared = self.prepared(self.ask([self.person.scope],
                                          pins=[(rules, rules_rev), (notes, notes_rev)]),
                                 recipient_digest=digest)
        self.assertEqual(sorted(u["role"] for u in prepared["units"]
                                if u.get("body_digest") == sha(REVIEW)),
                         ["instructions", "knowledge"])
        self.activated(prepared)
        (found,) = self.observations(prepared["preparation_id"])["returned"]
        self.assertEqual([u["source_id"] for u in found["observed"]["inventory"]], [rules])

    def test_a_shadowed_unit_is_not_received_although_its_body_is_the_winner_s(self):
        _, digest = self.linked()
        mine, mine_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        team, team_rev = self.authored(self.team, {"rules/review.md": REVIEW})
        self.placed(self.collection(self.person.scope, "instructions", [self.entry(
            mine, mine_rev, [unit("rules/review.md", "review")])]))
        self.placed(self.collection(self.team, "instructions", [self.entry(
            team, team_rev, [unit("rules/review.md", "review")])]))
        prepared = self.prepared(self.ask([self.person.scope, self.team]),
                                 recipient_digest=digest)
        shadowed = [u for u in prepared["units"] if u["source_id"] == team]
        self.assertEqual([(u["standing"], u.get("body_digest")) for u in shadowed],
                         [("shadowed", sha(REVIEW))])
        self.activated(prepared)
        (found,) = self.observations(prepared["preparation_id"])["returned"]
        self.assertEqual([u["source_id"] for u in found["observed"]["inventory"]], [mine])

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
