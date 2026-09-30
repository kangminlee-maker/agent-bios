"""Delivery: links, the attempts that record what an adapter handed a host, and what each of a
preparation's recipients received, through the journal.

The owner knows no host, so every rule here holds on every host an adapter carries; the tests
that say so run once per adapter.
"""
from __future__ import annotations

import unittest

import bench
from test_preparation import Composing
from test_sources import INSTANT, gaps, sha

from workenv import delivery, hosts, journal
from workenv.contracts import c01, c02, c03, c06, c07, c11, c12, canonical

OPEN, ATTEMPT, OBSERVE = "recipient.link.open", "recipient.delivery.attempt", "delivery.observe"
REVIEW, NOTE = b"# Review\n\nOne approval.\n", b"A note.\n"
# Five seconds after INSTANT.
LATER = INSTANT.replace(":00:00Z", ":00:05Z")


class Delivering(Composing):
    # Links.

    def open(self, host: str = "claude-code", session: str = "session-1", **changes) -> dict:
        link = {"kind": "recipient_link", "schema": 1, "principal_id": self.person.principal,
                "work_scope": self.person.scope, "host": {"name": host, "version": "1"},
                "destination": {"destination_kind": "conversation",
                                "destination_digest": hosts.destination_digest(session)},
                "isolation": "proven_fresh", **changes.pop("link", {})}
        sealed = bench.request(self.person, OPEN, changes.pop("target", self.person.principal),
                               link)
        return self.run_with(delivery.recipient_link_open, sealed, [link], now=INSTANT)

    def linked(self, host: str = "claude-code", session: str = "session-1",
               qualify: bool = True) -> tuple[dict, str]:
        """A link opened here: the link and its digest. Every route the host's adapter declares
        is qualified on it unless `qualify` is false."""
        answer = self.open(host, session)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        adapter = hosts.adapter_for(host)
        for recipient in sorted(adapter.routes) if adapter and qualify else ():
            self.probed(host, recipient)
        return answer["returned"][0], canonical.digest_of(answer["returned"][0])

    def without(self, host: str, recipient: str) -> None:
        """The host's adapter declaring no route to the recipient, for the length of a test."""
        adapter = hosts.adapter_for(host)
        routes = adapter.routes
        object.__setattr__(adapter, "routes", {r: v for r, v in routes.items() if r != recipient})
        self.addCleanup(object.__setattr__, adapter, "routes", routes)

    def probed(self, host: str, recipient: str, outcome: str = "worked", runs: str = "real",
               version: str = "1", at: str = INSTANT, carrier: str | None = None) -> None:
        """A probe of a recipient's delivery on the host, kept as capability.probe keeps one:
        through the carrier the host's route to it takes, unless another is named."""
        mode = {"runs": "real"} if runs == "real" else {"runs": "fixture",
                                                          "fixture_digest": sha(b"fixture")}
        adapter = hosts.adapter_for(host)
        route = adapter.routes.get(recipient) if adapter is not None else None
        carrier = carrier or (route.carrier if route is not None else "hook")
        probe = {"kind": "capability_probe", "schema": 1, "probe_id": bench.ident("prb"),
                 "client": {"name": host, "version": version}, "wire": hosts.WIRES[carrier],
                 "capability": hosts.CAPABILITY[recipient], "offered": True, "outcome": outcome,
                 "observed": "what the host did", "mode": mode, "at": at}
        store = self.bench.store()
        with store.unit(self.bench.call(bench.request(self.person, "access.profile.read",
                                                      self.person.profile))):
            store.put(probe)

    # Preparations.

    def for_link(self, link_digest: str | None, members=None) -> dict:
        """A preparation of one Instructions source of the person's, composed for the link."""
        source, revision = self.authored(self.person.scope, members or {"rules/review.md": REVIEW})
        options = {} if link_digest is None else {"recipient_digest": link_digest}
        return self.prepared(self.ask([self.person.scope], pins=[(source, revision)]), **options)

    # Attempts and observations.

    def attempt(self, link: dict, prepared: dict, recipient: str = "current", bodies=None,
                use_id: str | None = None, target: str | None = None, now: str = INSTANT,
                requested: dict | None = None) -> dict:
        value = {"kind": "delivery_attempt", "schema": 1, "link_id": link["link_id"],
                 "use_id": use_id or bench.ident("use"),
                 "requested": requested or {
                     "what": "body", "recipient": recipient,
                     "preparation_digest": canonical.digest_of(prepared),
                     "bodies": bodies if bodies is not None else
                     [u["body_digest"] for u in prepared["units"] if "body_digest" in u]}}
        sealed = bench.request(self.person, ATTEMPT, target or link["link_id"], value)
        return self.run_with(delivery.recipient_delivery_attempt, sealed, [value], now=now)

    def received(self, *args, **options) -> dict:
        answer = self.attempt(*args, **options)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        return answer

    def observations(self, preparation_id: str, now: str = INSTANT) -> dict:
        sealed = bench.request(self.person, OBSERVE, preparation_id)
        return self.run_with(delivery.delivery_observe, sealed, now=now)


class Links(Delivering):
    def test_a_link_is_stored_as_stated_with_the_id_and_time_the_runtime_owns(self):
        answer = self.open()
        link = answer["returned"][0]
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed")
        self.assertTrue(link["link_id"].startswith("lnk_"))
        self.assertEqual(link["created_at"], INSTANT)
        self.assertEqual(delivery.link_of(self.bench.store(), link["link_id"]),
                         (canonical.digest_of(link), link))
        self.assertIsNone(delivery.link_of(self.bench.store(), bench.ident("lnk")))

    def test_a_link_for_another_principal_is_a_mismatch(self):
        other = bench.ident("prn")
        for answer in (self.open(target=other), self.open(link={"principal_id": other}),
                       self.open(target=other, link={"principal_id": other})):
            self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH,
                                             "pointer": "/target/resource_id"}])
        self.assertEqual(self.count("links"), 0)


class Attempts(Delivering):
    def test_a_delivery_is_received_for_exactly_the_bodies_it_names_on_every_host(self):
        for host, adapter in sorted(hosts.adapters().items()):
            for recipient in sorted(adapter.routes):
                with self.subTest(host=host, recipient=recipient):
                    link, digest = self.linked(host, f"{host}-{recipient}")
                    prepared = self.for_link(digest)
                    answer = self.received(link, prepared, recipient)
                    attempt = answer["returned"][0]
                    self.assertEqual((attempt["supported"], attempt["observed"],
                                      attempt["material_gaps"], attempt["at"]),
                                     (True, {"saw": "received", "received": [sha(REVIEW)],
                                             "evidence_digest": answer["result"][
                                                 "request_digest"]}, [], INSTANT))

    def test_an_attempt_on_a_link_other_than_its_target_is_a_mismatch(self):
        link, digest = self.linked()
        answer = self.attempt(link, self.for_link(digest), target=bench.ident("lnk"))
        self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH,
                                         "pointer": "/target/resource_id"}])

    def test_delivering_a_question_or_a_resume_is_not_served(self):
        link, digest = self.linked()
        prepared = self.for_link(digest)
        question = {"what": "question", "question_id": bench.ident("qst"), "question_version": 1}
        resume = {**question, "what": "resume", "answer_evidence_digest": sha(NOTE),
                  "bodies": [sha(REVIEW)]}
        for requested in (question, resume):
            with self.assertRaisesRegex(journal.JournalError, "not served"):
                self.attempt(link, prepared, requested=requested)

    def test_a_link_not_opened_here_has_no_channel_and_delivers_nothing(self):
        link, digest = self.linked()
        prepared = self.for_link(digest)
        stranger = {**link, "link_id": bench.ident("lnk")}
        answer = self.attempt(stranger, prepared)
        self.assertEqual(gaps(answer), [{"code": c11.RECIPIENT_LINK_UNKNOWN}])
        self.assertEqual({k: answer["returned"][0][k] for k in ("supported", "observed")},
                         {"supported": True, "observed": {"saw": "no_channel"}})
        self.assertEqual((answer["result"]["supported_recovery"],
                          answer["result"]["local_effect"]), ([], "private_state_written"))
        self.assertEqual(self.count("deliveries"), 0)

    def test_a_preparation_not_composed_here_is_unavailable(self):
        link, digest = self.linked()
        prepared = self.for_link(digest)
        answer = self.attempt(link, {**prepared, "preparation_id": bench.ident("prp")})
        self.assertEqual(gaps(answer), [{"code": c01.REF_UNAVAILABLE,
                                         "pointer": "/requested/preparation_digest"}])

    def test_a_preparation_composed_for_another_recipient_goes_to_no_other(self):
        link, _ = self.linked()
        _, elsewhere = self.linked(session="session-2")
        for prepared in (self.for_link(elsewhere), self.for_link(None)):
            answer = self.attempt(link, prepared)
            self.assertEqual((gaps(answer), answer["returned"]),
                             ([{"code": c02.RECIPIENT_MISMATCH}], []))
        self.assertEqual(self.count("deliveries"), 0)

    def test_a_rehydrated_recipient_offered_a_body_not_composed_has_lost_it(self):
        link, digest = self.linked()
        prepared = self.for_link(digest)
        answer = self.attempt(link, prepared, "rehydrated", bodies=[sha(REVIEW), sha(NOTE)])
        self.assertEqual(gaps(answer), [{"code": c11.REHYDRATION_NEEDS_BODIES}])
        self.assertEqual(answer["returned"][0]["observed"], {"saw": "lost"})
        self.assertEqual((answer["returned"][0]["supported"], answer["result"]["local_effect"]),
                         (True, "private_state_written"))

    def test_any_other_recipient_naming_a_body_not_composed_is_a_mismatch(self):
        link, digest = self.linked()
        prepared = self.for_link(digest)
        for recipient in ("new", "current", "child"):
            answer = self.attempt(link, prepared, recipient, bodies=[sha(NOTE)])
            self.assertEqual((gaps(answer), answer["returned"], answer["result"]["local_effect"]),
                             ([{"code": c03.REQUEST_MISMATCH, "pointer": "/requested/bodies"}],
                              [], "none"), recipient)
        self.assertEqual(self.count("deliveries"), 0)

    def test_a_body_whose_bytes_are_not_held_was_not_composed_and_cannot_be_delivered(self):
        link, digest = self.linked()
        source, revision = self.authored(self.person.scope, {"rules/review.md": REVIEW},
                                         held=False)
        prepared = self.prepared(self.ask([self.person.scope], pins=[(source, revision)]),
                                 recipient_digest=digest)
        self.assertNotIn("body_digest", prepared["units"][0])
        answer = self.attempt(link, prepared, "rehydrated", bodies=[sha(REVIEW)])
        self.assertEqual(gaps(answer), [{"code": c11.REHYDRATION_NEEDS_BODIES}])

    def test_a_route_the_hosts_adapter_does_not_declare_is_not_delivered_on(self):
        self.without("codex", "child")
        link, digest = self.linked("codex")
        answer = self.attempt(link, self.for_link(digest), "child")
        self.assertEqual(gaps(answer), [{"code": c06.CHILD_ROUTE_UNSUPPORTED}])
        self.assertEqual({k: answer["returned"][0][k] for k in ("supported", "observed")},
                         {"supported": False, "observed": {"saw": "no_channel"}})
        self.assertEqual(answer["result"]["local_effect"], "private_state_written")
        link, digest = self.linked("a-host-nobody-wrote", "session-3")
        for recipient in hosts.RECIPIENTS:
            answer = self.attempt(link, self.for_link(digest), recipient)
            code = c06.CHILD_ROUTE_UNSUPPORTED if recipient == "child" else \
                c12.ROUTE_UNSUPPORTED
            self.assertEqual((gaps(answer), answer["returned"][0]["supported"]),
                             ([{"code": code}], False), recipient)


class Qualification(Delivering):
    def unsupported(self, answer: dict, recipient: str = "current") -> None:
        code = c06.CHILD_ROUTE_UNSUPPORTED if recipient == "child" else c12.ROUTE_UNSUPPORTED
        self.assertEqual((gaps(answer), answer["returned"][0]["supported"]),
                         ([{"code": code}], False))

    def test_a_declared_route_no_probe_qualified_is_not_delivered_on(self):
        link, digest = self.linked(qualify=False)
        prepared = self.for_link(digest)
        for recipient in hosts.RECIPIENTS:
            self.unsupported(self.attempt(link, prepared, recipient), recipient)

    def test_a_probe_of_a_fixture_or_one_that_did_not_work_qualifies_nothing(self):
        link, digest = self.linked(qualify=False)
        prepared = self.for_link(digest)
        self.probed("claude-code", "current", runs="fixture")
        self.probed("claude-code", "child", outcome="refused")
        self.unsupported(self.attempt(link, prepared, "current"))
        self.unsupported(self.attempt(link, prepared, "child"), "child")

    def test_a_probe_qualifies_one_recipient_on_one_host_version(self):
        link, digest = self.linked(qualify=False)
        prepared = self.for_link(digest)
        self.probed("claude-code", "current", version="2")
        self.probed("codex", "current", version="1")
        self.probed("claude-code", "new")
        self.unsupported(self.attempt(link, prepared, "current"))
        self.received(link, prepared, "new")

    def test_the_latest_probe_decides_and_probes_of_one_instant_that_disagree_qualify_nothing(self):
        link, digest = self.linked(qualify=False)
        prepared = self.for_link(digest)
        self.probed("claude-code", "current")
        self.probed("claude-code", "current", outcome="no_response", at=LATER)
        self.unsupported(self.attempt(link, prepared, "current"))
        self.probed("claude-code", "rehydrated", outcome="refused")
        self.probed("claude-code", "rehydrated", at=LATER)
        self.received(link, prepared, "rehydrated")
        self.probed("claude-code", "new", at=LATER)
        self.probed("claude-code", "new", outcome="refused", at=LATER)
        self.unsupported(self.attempt(link, prepared, "new"))

    def test_a_probe_through_a_carrier_the_route_no_longer_takes_qualifies_nothing(self):
        # A route that moved to launch instructions is not qualified by a probe of its hook.
        link, digest = self.linked(qualify=False)
        prepared = self.for_link(digest)
        for recipient in ("new", "rehydrated", "child"):
            with self.subTest(recipient=recipient):
                self.probed("claude-code", recipient, carrier="hook")
                self.unsupported(self.attempt(link, prepared, recipient), recipient)
        self.probed("claude-code", "new", at=LATER)
        self.received(link, prepared, "new")
        self.probed("claude-code", "current", carrier="launch")
        self.unsupported(self.attempt(link, prepared, "current"))

    def test_a_probe_does_not_qualify_a_route_the_adapter_does_not_declare(self):
        self.without("codex", "child")
        link, digest = self.linked("codex", qualify=False)
        self.probed("codex", "child")
        self.unsupported(self.attempt(link, self.for_link(digest), "child"), "child")


class Observations(Delivering):
    def test_a_preparation_not_composed_here_is_unavailable(self):
        answer = self.observations(bench.ident("prp"))
        self.assertEqual(gaps(answer), [{"code": c01.REF_UNAVAILABLE,
                                         "pointer": "/target/resource_id"}])

    def test_a_preparation_nothing_reached_answers_none_and_writes_nothing(self):
        _, digest = self.linked()
        answer = self.observations(self.for_link(digest)["preparation_id"])
        self.assertEqual((answer["returned"], answer["result"]["local_effect"]), ([], "none"))

    def test_each_recipient_is_observed_once_in_the_order_it_first_received(self):
        link, digest = self.linked()
        prepared = self.for_link(digest)
        child = self.received(link, prepared, "child")
        current = self.received(link, prepared, "current", now=LATER)
        again = self.received(link, prepared, "child", use_id=child["returned"][0]["use_id"],
                              now=LATER)
        unit_ = prepared["units"][0]
        inventory = [{"unit_id": unit_["unit_id"], "source_id": unit_["source_id"],
                      "revision_digest": unit_["revision_digest"], "body_digest": sha(REVIEW)}]
        found = self.observations(prepared["preparation_id"])["returned"]

        def evidence(*answers):
            return canonical.digest_of([a["result"]["request_digest"] for a in answers])
        self.assertEqual(found, [
            {"kind": "delivery_observation", "schema": 1,
             "preparation_id": prepared["preparation_id"],
             "requested": {"recipient_kind": delivery.CHILD_SESSION,
                           "recipient_digest": canonical.digest_of({
                               "link": digest, "use_id": child["returned"][0]["use_id"]})},
             "observed": {"saw": "delivered", "at": INSTANT,
                          "evidence_digest": evidence(child, again), "inventory": inventory},
             "material_gaps": [], "recorded_at": LATER},
            {"kind": "delivery_observation", "schema": 1,
             "preparation_id": prepared["preparation_id"],
             "requested": {"recipient_kind": delivery.HOST_SESSION, "recipient_digest": digest},
             "observed": {"saw": "delivered", "at": LATER,
                          "evidence_digest": evidence(current), "inventory": inventory},
             "material_gaps": [], "recorded_at": LATER}])

    def test_a_child_is_its_own_recipient_and_the_host_sessions_recipients_are_one(self):
        link, digest = self.linked()
        prepared = self.for_link(digest)
        for recipient in ("child", "child", "new", "current", "rehydrated"):
            self.received(link, prepared, recipient)
        found = self.observations(prepared["preparation_id"])["returned"]
        self.assertEqual([o["requested"]["recipient_kind"] for o in found],
                         [delivery.CHILD_SESSION, delivery.CHILD_SESSION, delivery.HOST_SESSION])

    def test_the_inventory_names_only_the_units_whose_bodies_arrived(self):
        link, digest = self.linked()
        prepared = self.for_link(digest, {"rules/review.md": REVIEW, "rules/note.md": NOTE})
        self.received(link, prepared, bodies=[sha(NOTE)])
        found = self.observations(prepared["preparation_id"])["returned"]
        self.assertEqual([u["body_digest"] for u in found[0]["observed"]["inventory"]],
                         [sha(NOTE)])

    def test_the_inventory_names_no_unit_a_delivery_does_not_carry(self):
        link, digest = self.linked()
        rules, rules_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        notes, notes_rev = self.authored(self.person.scope, {"notes/review.md": REVIEW},
                                         role="knowledge")
        prepared = self.prepared(self.ask([self.person.scope],
                                          pins=[(rules, rules_rev), (notes, notes_rev)]),
                                 recipient_digest=digest)
        self.received(link, prepared, bodies=[sha(REVIEW)])
        found = self.observations(prepared["preparation_id"])["returned"]
        self.assertEqual([u["source_id"] for u in found[0]["observed"]["inventory"]], [rules])

    def test_a_recipient_a_delivery_was_requested_of_and_nothing_reached_is_not_observed(self):
        self.without("codex", "child")
        link, digest = self.linked("codex")
        prepared = self.for_link(digest)
        self.received(link, prepared, "current")
        self.attempt(link, prepared, "child")
        self.attempt(link, prepared, "child", now=LATER)
        found = self.observations(prepared["preparation_id"])["returned"]
        unseen = {"kind": "delivery_observation", "schema": 1,
                  "preparation_id": prepared["preparation_id"],
                  "requested": {"recipient_kind": delivery.CHILD_SESSION},
                  "observed": {"saw": "not_observed"},
                  "material_gaps": [{"code": c07.DELIVERY_UNOBSERVED}]}
        self.assertEqual([o["observed"]["saw"] for o in found],
                         ["delivered", "not_observed", "not_observed"])
        self.assertEqual(found[1:], [{**unseen, "recorded_at": INSTANT},
                                     {**unseen, "recorded_at": LATER}])
        other, elsewhere = self.linked("a-host-nobody-wrote", "session-2")
        alone = self.for_link(elsewhere)
        self.attempt(other, alone, "rehydrated")
        self.assertEqual(self.observations(alone["preparation_id"])["returned"], [
            {**unseen, "preparation_id": alone["preparation_id"],
             "requested": {"recipient_kind": delivery.HOST_SESSION,
                           "recipient_digest": elsewhere}, "recorded_at": INSTANT}])

    def test_a_recipient_only_lost_or_unsupported_attempts_reached_is_not_observed(self):
        link, digest = self.linked(qualify=False)
        prepared = self.for_link(digest)
        self.attempt(link, prepared, "rehydrated", bodies=[sha(NOTE)])
        (found,) = self.observations(prepared["preparation_id"])["returned"]
        self.assertEqual((found["requested"], found["observed"], found["recorded_at"]),
                         ({"recipient_kind": delivery.HOST_SESSION, "recipient_digest": digest},
                          {"saw": "not_observed"}, INSTANT))
        self.attempt(link, prepared, "current", now=LATER)
        (found,) = self.observations(prepared["preparation_id"], now=LATER)["returned"]
        self.assertEqual((found["observed"], found["recorded_at"]),
                         ({"saw": "not_observed"}, LATER))

    def test_a_delivery_lost_after_one_arrived_changes_nothing_observed(self):
        link, digest = self.linked()
        prepared = self.for_link(digest)
        self.received(link, prepared, "current")
        before = self.observations(prepared["preparation_id"])["returned"]
        self.attempt(link, prepared, "rehydrated", bodies=[sha(NOTE)], now=LATER)
        again = self.observations(prepared["preparation_id"], now=LATER)
        self.assertEqual((again["returned"], again["result"]["local_effect"]), (before, "none"))

    def test_observing_keeps_the_observation_privately_once(self):
        link, digest = self.linked()
        prepared = self.for_link(digest)
        self.received(link, prepared)
        first = self.observations(prepared["preparation_id"])
        self.assertEqual(first["result"]["local_effect"], "private_state_written")
        self.assertEqual(self.bench.store().get(canonical.digest_of(first["returned"][0])),
                         first["returned"][0])
        again = self.observations(prepared["preparation_id"], now=LATER)
        self.assertEqual((again["returned"], again["result"]["local_effect"]),
                         (first["returned"], "none"))

    def test_a_refused_attempt_and_a_later_preparation_change_no_observation(self):
        link, digest = self.linked()
        prepared = self.for_link(digest)
        self.received(link, prepared)
        before = self.observations(prepared["preparation_id"])["returned"]
        self.attempt(link, prepared, bodies=[sha(NOTE)])
        later = self.for_link(digest)
        self.received(link, later, now=LATER)
        self.assertEqual(self.observations(prepared["preparation_id"])["returned"], before)
        self.assertEqual(len(self.observations(later["preparation_id"])["returned"]), 1)


if __name__ == "__main__":
    unittest.main()
