"""Preparation: the nine positions and the environment composed from them, through the journal."""
from __future__ import annotations

import contextlib
import unittest

import bench
from test_sources import INSTANT, ORIGIN, Base, Checkout, gaps, home, manifest, sha

from workenv import journal, preparation, sources, storage
from workenv.contracts import c01, c03, c04, c07, c11, canonical

CHANGE, READ, COMPOSE = "collection.change", "collection.read", "preparation.compose"
ADMIT = "source.revision.admit"
REVIEW, RELEASE, NOTE = b"# Review\n\nOne approval.\n", b"# Release\n", b"A note.\n"


def team_scope() -> dict:
    return {"layer": "team", "team_id": bench.ident("tem")}


def unit(member: str, concern: str | None = None, startup: str = "required", **more) -> dict:
    value = {"member": member, "startup": startup, **more}
    if concern is not None:
        value["concern"] = concern
    return value


class Composing(Base):
    def setUp(self):
        super().setUp()
        self.repository_scope = {"layer": "repository", "repository_id": self.repository}
        self.team = team_scope()

    # Sources and positions.

    def authored(self, scope: dict, members: dict[str, bytes], role: str = "instructions",
                 mode: str = "managed", held: bool = True, source: str | None = None,
                 base: dict | None = None) -> tuple[str, str]:
        """A source admitted here in the scope: its id and the revision it committed."""
        source = source or bench.ident("src")
        submitted = manifest(source, members)
        asked = {"kind": "source_request", "schema": 1, "role": role,
                 "destination": {"scope": scope, "home_mode": mode},
                 "route": {"route": "author_here",
                           "manifest_digest": canonical.digest_of(submitted)}}
        answer = self.run_with(sources.source_revision_admit,
                               bench.request(self.person, ADMIT, {
                                   "resource_id": source, "base": base or {"expects": "absent"}},
                                   asked), [asked, submitted],
                               members={sha(data): data for data in members.values()} if held
                               else {}, now=INSTANT)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        return source, answer["receipt"]["head_digest"]

    def collection(self, scope: dict, role: str, entries: list[dict], switch: str = "on",
                   collection_id: str | None = None, drafts=()) -> dict:
        return {"kind": "collection", "schema": 1,
                "collection_id": collection_id or bench.ident("col"),
                "position": {"scope": scope, "role": role}, "switch": switch,
                "entries": entries, "drafts": list(drafts)}

    def entry(self, source: str, revision: str | None, units=None, switch: str = "on",
              precedence: int | None = None) -> dict:
        value = {"source_id": source, "switch": switch,
                 "pin": {"pinned": "revision", "revision_digest": revision}
                 if revision else {"pinned": "observed_frontier"}}
        if units is not None:
            value["units"] = units
        if precedence is not None:
            value["precedence"] = precedence
        return value

    def change(self, collection: dict, base: dict | None = None, carried=(), members=None,
               **changes) -> dict:
        target = {"resource_id": collection["collection_id"],
                  "base": base or {"expects": "absent"}}
        sealed = bench.request(self.person, CHANGE, target, collection,
                               owner=collection["position"]["scope"])
        sealed.update(changes)
        return self.run_with(preparation.collection_change, sealed, [collection, *carried],
                             members=members, now=INSTANT)

    def placed(self, collection: dict) -> str:
        answer = self.change(collection)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        return answer["receipt"]["head_digest"]

    def ask(self, scopes: list[dict], pins=(), operation: str = "session.routing.activate",
            **more) -> dict:
        return {"kind": "preparation_request", "schema": 1,
                "basis": {"from": "ad_hoc", "scopes": scopes,
                          "source_pins": [{"source_id": s, "revision_digest": r}
                                          for s, r in pins]},
                "declared_operation": {"name": operation, "action": "use"}, **more}

    def compose(self, asked: dict, where=None, **changes) -> dict:
        sealed = bench.request(self.person, COMPOSE, self.person.principal, asked)
        sealed.update(changes)
        with contextlib.chdir(where or self.scratch):
            return self.run_with(preparation.preparation_compose, sealed, [asked], now=INSTANT)

    def prepared(self, asked: dict, **options) -> dict:
        answer = self.compose(asked, **options)
        self.assertEqual(answer["result"]["outcome"]["stage"], "previewed", gaps(answer))
        return answer["returned"][0]

    def standing(self, prepared: dict) -> list[tuple]:
        return [(u["source_id"], u["member"], u["layer"], u["standing"])
                for u in prepared["units"]]


class Collections(Composing):
    def test_a_change_stores_the_collection_with_its_time_and_its_digest_is_the_head(self):
        value = self.collection(self.person.scope, "instructions", [])
        answer = self.change(value)
        stored = {**value, "changed_at": INSTANT}
        self.assertEqual((answer["returned"], answer["receipt"]["head_digest"]),
                         ([stored], canonical.digest_of(stored)))

    def test_a_later_change_names_the_head_it_expects(self):
        value = self.collection(self.person.scope, "instructions", [])
        head = self.placed(value)
        moved = self.change({**value, "switch": "off"}, {"expects": "head", "head_digest": head})
        self.assertEqual(moved["result"]["outcome"]["stage"], "committed")
        stale = self.change(value, {"expects": "head", "head_digest": head})
        self.assertEqual(gaps(stale), [{"code": c03.STALE_BASE}])
        again = self.change(value)
        self.assertEqual(gaps(again), [{"code": c03.STALE_BASE}])

    def test_a_collection_of_another_id_than_the_target_is_a_mismatch(self):
        value = self.collection(self.person.scope, "instructions", [])
        sealed_target = {"resource_id": bench.ident("col"), "base": {"expects": "absent"}}
        answer = self.run_with(preparation.collection_change,
                               bench.request(self.person, CHANGE, sealed_target, value),
                               [value], now=INSTANT)
        self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH,
                                         "pointer": "/target/resource_id"}])

    def test_a_collection_keeps_its_position_and_a_position_keeps_its_collection(self):
        value = self.collection(self.person.scope, "instructions", [])
        head = self.placed(value)
        moved = {**value, "position": {"scope": self.person.scope, "role": "knowledge"}}
        self.assertEqual(gaps(self.change(moved, {"expects": "head", "head_digest": head})),
                         [{"code": c03.REQUEST_MISMATCH, "pointer": "/position"}])
        second = self.collection(self.person.scope, "instructions", [])
        self.assertEqual(gaps(self.change(second)),
                         [{"code": c03.REQUEST_MISMATCH, "pointer": "/position"}])
        other_role = self.collection(self.person.scope, "knowledge", [])
        self.assertEqual(self.change(other_role)["result"]["outcome"]["stage"], "committed")

    def test_a_change_whose_owner_is_not_the_positions_scope_is_a_mismatch(self):
        value = self.collection(self.team, "instructions", [])
        answer = self.change(value, owner=self.person.scope)
        self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH, "pointer": "/owner"}])

    def test_a_draft_is_staged_as_carried_and_nothing_accepts_it(self):
        source, revision = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        draft = manifest(source, {"rules/review.md": REVIEW + b"more\n"})
        value = self.collection(self.person.scope, "instructions",
                                [self.entry(source, revision)],
                                drafts=[{"source_id": source,
                                         "manifest_digest": canonical.digest_of(draft)}])
        answer = self.change(value, carried=[draft],
                             members={sha(REVIEW + b"more\n"): REVIEW + b"more\n"})
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        store = self.bench.store()
        self.assertEqual(store.get(canonical.digest_of(draft)), draft)
        self.assertEqual(store.get(sha(REVIEW + b"more\n")), REVIEW + b"more\n")
        self.assertEqual(journal.head_of(store, source), revision)
        self.assertEqual(self.count("revisions"), 1)

    def test_a_draft_the_change_does_not_carry_or_of_another_source_is_refused(self):
        source, revision = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        draft = manifest(source, {"rules/review.md": REVIEW})
        named = [{"source_id": source, "manifest_digest": canonical.digest_of(draft)}]
        value = self.collection(self.person.scope, "instructions", [], drafts=named)
        self.assertEqual(gaps(self.change(value)), [{"code": c01.REF_UNAVAILABLE,
                                                     "pointer": "/drafts/0/manifest_digest"}])
        other = manifest(bench.ident("src"), {"rules/review.md": REVIEW})
        value["drafts"] = [{"source_id": source, "manifest_digest": canonical.digest_of(other)}]
        self.assertEqual(gaps(self.change(value, carried=[other])),
                         [{"code": c03.REQUEST_MISMATCH, "pointer": "/drafts/0/source_id"}])
        not_a_manifest = self.collection(self.team, "knowledge", [])
        value["drafts"] = [{"source_id": source,
                            "manifest_digest": canonical.digest_of(not_a_manifest)}]
        self.assertEqual(gaps(self.change(value, carried=[not_a_manifest])),
                         [{"code": c01.REF_UNAVAILABLE, "pointer": "/drafts/0/manifest_digest"}])
        self.assertEqual(self.count("collections"), 0)

    def test_a_read_answers_the_collection_at_the_head_the_position_holds(self):
        value = self.collection(self.person.scope, "instructions", [])
        head = self.placed(value)
        target = {"resource_id": value["collection_id"],
                  "base": {"expects": "head", "head_digest": head}}
        read = self.run_with(preparation.collection_read,
                             bench.request(self.person, READ, target))
        self.assertEqual((read["result"]["outcome"]["stage"], read["returned"], read["receipt"]),
                         ("previewed", [{**value, "changed_at": INSTANT}], None))
        unknown = self.run_with(preparation.collection_read,
                                bench.request(self.person, READ, {
                                    "resource_id": bench.ident("col"),
                                    "base": {"expects": "absent"}}))
        self.assertEqual(gaps(unknown), [{"code": c01.REF_UNAVAILABLE}])
        target["base"]["head_digest"] = "0" * 64
        stale = self.run_with(preparation.collection_read,
                              bench.request(self.person, READ, target))
        self.assertEqual(gaps(stale), [{"code": c03.STALE_BASE}])


class Order(Composing):
    def test_scopes_apply_repository_then_personal_then_team_unless_an_order_is_stated(self):
        scopes = [self.team, self.person.scope, self.repository_scope]
        self.assertEqual(self.prepared(self.ask(scopes))["order"],
                         [self.repository_scope, self.person.scope, self.team])
        stated = [self.person.scope, self.team, self.repository_scope]
        self.assertEqual(self.prepared(self.ask(scopes, order=stated))["order"], stated)

    def test_an_order_naming_other_scopes_than_the_basis_is_a_mismatch(self):
        for order in ([self.person.scope, self.team], [self.team]):
            answer = self.compose(self.ask([self.person.scope], order=order))
            self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH, "pointer": "/order"}])

    def test_a_preparation_is_the_requesters_own(self):
        asked = self.ask([self.person.scope])
        sealed = bench.request(self.person, COMPOSE, bench.ident("prn"), asked)
        answer = self.run_with(preparation.preparation_compose, sealed, [asked], now=INSTANT)
        self.assertEqual(gaps(answer), [{"code": c03.REQUEST_MISMATCH,
                                         "pointer": "/target/resource_id"}])

    def test_an_adopted_basis_and_a_task_request_are_not_served_yet(self):
        adopted = self.ask([self.person.scope])
        adopted["basis"] = {"from": "environment", "environment_id": bench.ident("env"),
                            "adoption_evidence_digest": "0" * 64}
        with self.assertRaisesRegex(journal.JournalError, "adopted environment"):
            self.compose(adopted)
        tasked = self.ask([self.person.scope], work_request={"concern": {"question": "Why?"}})
        with self.assertRaisesRegex(journal.JournalError, "task"):
            self.compose(tasked)


class Positions(Composing):
    def test_each_position_is_named_at_its_head_role_by_role_in_the_order(self):
        source, revision = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        mine = self.collection(self.person.scope, "instructions",
                               [self.entry(source, revision, [unit("rules/review.md", "review")])])
        empty = self.collection(self.repository_scope, "instructions", [])
        off = self.collection(self.team, "knowledge", [self.entry(source, revision)], "off")
        known = self.collection(self.repository_scope, "knowledge", [])
        heads = {c["collection_id"]: self.placed(c) for c in (off, mine, known, empty)}
        prepared = self.prepared(self.ask([self.person.scope, self.team,
                                           self.repository_scope]))
        self.assertEqual(prepared["collections"], [
            {"collection_id": c["collection_id"], "head_digest": heads[c["collection_id"]],
             "state": state}
            for c, state in ((empty, "empty"), (mine, "applied"), (known, "empty"),
                             (off, "switched_off"))])
        self.assertEqual(self.standing(prepared),
                         [(source, "rules/review.md", "personal", "winning")])

    def test_composing_writes_no_position_and_is_kept_whole_without_a_receipt(self):
        value = self.collection(self.person.scope, "instructions", [])
        head = self.placed(value)
        answer = self.compose(self.ask([self.person.scope]))
        prepared = answer["returned"][0]
        self.assertEqual((answer["result"]["local_effect"], answer["receipt"],
                          answer["result"]["outcome"]["stage"]),
                         ("private_state_written", None, "previewed"))
        store = self.bench.store()
        self.assertEqual(journal.head_of(store, value["collection_id"]), head)
        self.assertIsNone(journal.head_of(store, self.person.principal))
        self.assertEqual(store.read("SELECT digest FROM preparations WHERE preparation_id = ?",
                                    (prepared["preparation_id"],)),
                         [(canonical.digest_of(prepared),)])
        self.assertEqual(store.get(canonical.digest_of(prepared)), prepared)
        self.assertEqual((prepared["request_digest"], prepared["prepared_at"],
                          prepared["work_support"], prepared["omissions"],
                          prepared["adapter"]),
                         (canonical.digest_of(self.ask([self.person.scope])), INSTANT,
                          {"assessed": "not_requested"}, [], preparation.ADAPTER))


class Competition(Composing):
    def three_layers(self):
        repo, repo_rev = self.authored(self.repository_scope, {"rules/review.md": REVIEW})
        mine, mine_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW + b"p\n"})
        team, team_rev = self.authored(self.team, {"rules/review.md": REVIEW + b"t\n",
                                                   "rules/release.md": RELEASE})
        return repo, repo_rev, mine, mine_rev, team, team_rev

    def test_the_first_layer_wins_a_concern_and_lower_units_are_shadowed_by_it(self):
        repo, repo_rev, mine, mine_rev, team, team_rev = self.three_layers()
        self.placed(self.collection(self.team, "instructions", [self.entry(
            team, team_rev, [unit("rules/review.md", "review"),
                             unit("rules/release.md", "release")])]))
        self.placed(self.collection(self.person.scope, "instructions", [self.entry(
            mine, mine_rev, [unit("rules/review.md", "review")])]))
        self.placed(self.collection(self.repository_scope, "instructions", [self.entry(
            repo, repo_rev, [unit("rules/review.md", "review")])]))
        prepared = self.prepared(self.ask([self.team, self.person.scope, self.repository_scope]))
        units = prepared["units"]
        self.assertEqual(self.standing(prepared), [
            (repo, "rules/review.md", "repository", "winning"),
            (mine, "rules/review.md", "personal", "shadowed"),
            (team, "rules/review.md", "team", "shadowed"),
            (team, "rules/release.md", "team", "winning")])
        self.assertEqual([u.get("shadowed_by") for u in units],
                         [None, units[0]["unit_id"], units[0]["unit_id"], None])
        self.assertEqual(prepared["material_gaps"], [])
        reversed_order = [self.team, self.person.scope, self.repository_scope]
        flipped = self.prepared(self.ask(reversed_order, order=reversed_order))
        self.assertEqual([u["standing"] for u in flipped["units"]],
                         ["winning", "winning", "shadowed", "shadowed"])

    def test_precedence_orders_one_layer_and_without_it_the_concern_stays_unresolved(self):
        one, one_rev = self.authored(self.team, {"tables/rates.csv": b"a\n"}, "knowledge")
        two, two_rev = self.authored(self.team, {"tables/rates.csv": b"b\n"}, "knowledge")
        low, low_rev = self.authored(self.person.scope, {"tables/rates.csv": b"c\n"}, "knowledge")
        rates = [unit("tables/rates.csv", "tax.rate", "not_required")]
        value = self.collection(self.team, "knowledge", [self.entry(one, one_rev, rates),
                                                         self.entry(two, two_rev, rates)])
        head = self.placed(value)
        self.placed(self.collection(self.person.scope, "knowledge",
                                    [self.entry(low, low_rev, rates)]))
        both = [self.team, self.person.scope]
        prepared = self.prepared(self.ask(both, order=both))
        self.assertEqual([u["standing"] for u in prepared["units"]],
                         ["unresolved", "unresolved", "unresolved"])
        self.assertEqual(prepared["material_gaps"],
                         [{"code": c07.SAME_LAYER_UNORDERED, "pointer": "/units/0"},
                          {"code": c07.SAME_LAYER_UNORDERED, "pointer": "/units/1"}])
        value["entries"][0]["precedence"], value["entries"][1]["precedence"] = 2, 1
        self.change(value, {"expects": "head", "head_digest": head})
        prepared = self.prepared(self.ask(both, order=both))
        units = prepared["units"]
        self.assertEqual([(u["source_id"], u["standing"], u.get("shadowed_by")) for u in units],
                         [(one, "shadowed", units[1]["unit_id"]), (two, "winning", None),
                          (low, "shadowed", units[1]["unit_id"])])
        self.assertEqual(prepared["material_gaps"], [])

    def test_one_unit_with_precedence_against_one_without_leaves_the_concern_unresolved(self):
        one, one_rev = self.authored(self.team, {"tables/rates.csv": b"a\n"}, "knowledge")
        two, two_rev = self.authored(self.team, {"tables/rates.csv": b"b\n"}, "knowledge")
        rates = [unit("tables/rates.csv", "tax.rate", "not_required")]
        self.placed(self.collection(self.team, "knowledge", [
            self.entry(one, one_rev, rates, precedence=1), self.entry(two, two_rev, rates)]))
        self.assertEqual([u["standing"] for u in self.prepared(self.ask([self.team]))["units"]],
                         ["unresolved", "unresolved"])

    def test_a_switched_off_entry_is_disabled_and_the_next_layer_answers_its_concern(self):
        repo, repo_rev, mine, mine_rev, team, team_rev = self.three_layers()
        self.placed(self.collection(self.repository_scope, "instructions", [self.entry(
            repo, repo_rev, [unit("rules/review.md", "review")], "off")]))
        self.placed(self.collection(self.team, "instructions", [self.entry(
            team, team_rev, [unit("rules/review.md", "review")])]))
        prepared = self.prepared(self.ask([self.repository_scope, self.team]))
        self.assertEqual(prepared["units"][0], {
            "unit_id": prepared["units"][0]["unit_id"], "source_id": repo,
            "revision_digest": repo_rev, "role": "instructions", "layer": "repository",
            "member": "rules/review.md", "concern": "review", "startup": "required",
            "standing": "disabled"})
        self.assertEqual(self.standing(prepared)[1:],
                         [(team, "rules/review.md", "team", "winning")])

    def test_a_switched_off_position_contributes_nothing_and_hides_no_other_layer(self):
        repo, repo_rev, mine, mine_rev, team, team_rev = self.three_layers()
        self.placed(self.collection(self.repository_scope, "instructions", [self.entry(
            repo, repo_rev, [unit("rules/review.md", "review")])], "off"))
        self.placed(self.collection(self.team, "instructions", [self.entry(
            team, team_rev, [unit("rules/review.md", "review")])]))
        prepared = self.prepared(self.ask([self.repository_scope, self.team]))
        self.assertEqual(self.standing(prepared), [(team, "rules/review.md", "team", "winning")])

    def test_unkeyed_prose_is_layered_and_an_entry_declaring_no_unit_brings_every_member(self):
        team, team_rev = self.authored(self.team, {"rules/review.md": REVIEW, "notes.md": NOTE})
        self.placed(self.collection(self.team, "instructions", [self.entry(
            team, team_rev, [unit("notes.md", startup="not_required")])]))
        prepared = self.prepared(self.ask([self.team]))
        self.assertEqual(prepared["units"][0]["standing"], "layered")
        self.assertEqual(prepared["units"][0]["startup"], "not_required")
        self.assertNotIn("concern", prepared["units"][0])
        mine, mine_rev = self.authored(self.person.scope, {"a.md": NOTE, "b.md": REVIEW})
        self.placed(self.collection(self.person.scope, "instructions",
                                    [self.entry(mine, mine_rev)]))
        prepared = self.prepared(self.ask([self.person.scope]))
        self.assertEqual([(u["member"], u["standing"], "startup" in u)
                          for u in prepared["units"]],
                         [("a.md", "layered", False), ("b.md", "layered", False)])

    def test_units_are_listed_role_by_role_then_layer_by_layer_then_as_stated(self):
        rules, rules_rev = self.authored(self.team, {"z.md": NOTE, "a.md": REVIEW})
        known, known_rev = self.authored(self.person.scope, {"k.md": NOTE}, "knowledge")
        mine, mine_rev = self.authored(self.person.scope, {"m.md": NOTE})
        self.placed(self.collection(self.person.scope, "knowledge",
                                    [self.entry(known, known_rev)]))
        self.placed(self.collection(self.team, "instructions", [self.entry(
            rules, rules_rev, [unit("z.md"), unit("a.md")])]))
        prepared = self.prepared(self.ask([self.team, self.person.scope],
                                          pins=[(mine, mine_rev)]))
        self.assertEqual([(u["role"], u["layer"], u["member"]) for u in prepared["units"]], [
            ("instructions", "personal", "m.md"), ("instructions", "team", "z.md"),
            ("instructions", "team", "a.md"), ("knowledge", "personal", "k.md")])

    def test_a_winning_units_needs_name_it_on_the_units_it_relies_on(self):
        team, team_rev = self.authored(self.team, {"rules/review.md": REVIEW,
                                                   "rules/base.md": NOTE})
        needs = [{"source_id": team, "member": "rules/base.md"}]
        self.placed(self.collection(self.team, "instructions", [self.entry(
            team, team_rev, [unit("rules/review.md", "review", needs=needs),
                             unit("rules/base.md", "base")])]))
        units = self.prepared(self.ask([self.team]))["units"]
        self.assertEqual((units[1].get("needed_by"), "needed_by" in units[0]),
                         ([units[0]["unit_id"]], False))
        mine, mine_rev = self.authored(self.person.scope, {"rules/review.md": RELEASE})
        self.placed(self.collection(self.person.scope, "instructions", [self.entry(
            mine, mine_rev, [unit("rules/review.md", "review")])]))
        units = self.prepared(self.ask([self.person.scope, self.team]))["units"]
        self.assertEqual([(u["source_id"], u["standing"], u.get("needed_by")) for u in units],
                         [(mine, "winning", None), (team, "shadowed", None),
                          (team, "winning", None)])


class Selections(Composing):
    def test_a_selected_source_revision_or_member_not_held_is_unresolved_at_its_position(self):
        held, held_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        other, other_rev = self.authored(self.person.scope, {"rules/other.md": NOTE})
        self.placed(self.collection(self.team, "instructions", [
            self.entry(bench.ident("src"), "1" * 64), self.entry(held, "2" * 64),
            self.entry(other, held_rev)]))
        self.placed(self.collection(self.repository_scope, "instructions", [
            self.entry(held, held_rev, [unit("rules/absent.md", "absent")]),
            self.entry(other, other_rev, [unit("rules/other.md", "other")])]))
        prepared = self.prepared(self.ask([self.repository_scope, self.team]))
        self.assertEqual(prepared["material_gaps"], [
            {"code": c07.SELECTION_UNRESOLVED, "pointer": "/collections/0"},
            {"code": c07.SELECTION_UNRESOLVED, "pointer": "/collections/1"},
            {"code": c07.SELECTION_UNRESOLVED, "pointer": "/collections/1"},
            {"code": c07.SELECTION_UNRESOLVED, "pointer": "/collections/1"}])
        self.assertEqual(self.standing(prepared),
                         [(other, "rules/other.md", "repository", "winning")])

    def test_an_entry_applies_in_its_positions_layer_whoever_owns_its_source(self):
        team, team_rev = self.authored(self.team, {"rules/review.md": REVIEW})
        self.placed(self.collection(self.repository_scope, "instructions", [self.entry(
            team, team_rev, [unit("rules/review.md", "review")])]))
        prepared = self.prepared(self.ask([self.repository_scope]))
        self.assertEqual(self.standing(prepared),
                         [(team, "rules/review.md", "repository", "winning")])
        self.assertEqual(sources.homes.source_of(self.bench.store(), team)["scope"], self.team)

    def test_a_source_of_another_role_than_its_position_is_not_composed_there(self):
        known, known_rev = self.authored(self.person.scope, {"k.md": NOTE}, "knowledge")
        rules, rules_rev = self.authored(self.person.scope, {"r.md": NOTE})
        self.placed(self.collection(self.person.scope, "instructions",
                                    [self.entry(known, known_rev)]))
        self.placed(self.collection(self.person.scope, "memory", [self.entry(rules, None)]))
        prepared = self.prepared(self.ask([self.person.scope]))
        self.assertEqual((prepared["units"], prepared["frontiers"], prepared["material_gaps"]),
                         ([], [], [{"code": c04.ROLE_PROMOTION_REFUSED,
                                    "pointer": "/collections/0"},
                                   {"code": c07.SELECTION_UNRESOLVED,
                                    "pointer": "/collections/1"}]))

    def test_a_pinned_source_brings_each_member_as_prose_in_its_own_layer(self):
        team, team_rev = self.authored(self.team, {"a.md": NOTE, "b.md": REVIEW})
        prepared = self.prepared(self.ask([self.person.scope], pins=[(team, team_rev)]))
        self.assertEqual(self.standing(prepared), [(team, "a.md", "team", "layered"),
                                                   (team, "b.md", "team", "layered")])

    def test_a_pin_naming_a_revision_not_held_for_its_source_is_unavailable(self):
        team, team_rev = self.authored(self.team, {"a.md": NOTE})
        answer = self.compose(self.ask([self.person.scope], pins=[(team, "3" * 64)]))
        self.assertEqual(gaps(answer), [{"code": c01.REF_UNAVAILABLE,
                                         "pointer": "/basis/source_pins/0"}])
        mine, mine_rev = self.authored(self.person.scope, {"a.md": NOTE})
        for pin in ((bench.ident("src"), team_rev), (team, mine_rev)):
            other = self.compose(self.ask([self.person.scope], pins=[pin]))
            self.assertEqual(gaps(other), [{"code": c01.REF_UNAVAILABLE,
                                            "pointer": "/basis/source_pins/0"}])

    def test_memory_fixes_its_sources_frontier_at_its_head_and_brings_no_unit(self):
        notes, notes_rev = self.authored(self.person.scope, {"notes.jsonl": NOTE}, "memory")
        pinned, pinned_rev = self.authored(self.person.scope, {"more.jsonl": NOTE}, "memory")
        self.placed(self.collection(self.person.scope, "memory", [self.entry(notes, None)]))
        prepared = self.prepared(self.ask([self.person.scope], pins=[(pinned, pinned_rev)]))
        self.assertEqual((prepared["units"], prepared["frontiers"]),
                         ([], [{"source_id": notes, "checkpoint_digest": notes_rev},
                               {"source_id": pinned, "checkpoint_digest": pinned_rev}]))
        twice = self.prepared(self.ask([self.person.scope], pins=[(notes, notes_rev)]))
        self.assertEqual(twice["frontiers"], [{"source_id": notes, "checkpoint_digest": notes_rev}])
        off = self.collection(self.team, "memory", [self.entry(notes, None, switch="off"),
                                                    self.entry(bench.ident("src"), None)])
        self.placed(off)
        prepared = self.prepared(self.ask([self.team]))
        self.assertEqual((prepared["frontiers"], prepared["material_gaps"]),
                         ([], [{"code": c07.SELECTION_UNRESOLVED, "pointer": "/collections/0"}]))


class Bodies(Composing):
    def winner(self, prepared: dict) -> dict:
        return next(u for u in prepared["units"] if u["standing"] == "winning")

    def test_a_body_this_installation_holds_is_named_by_its_digest(self):
        team, team_rev = self.authored(self.team, {"rules/review.md": REVIEW})
        self.placed(self.collection(self.team, "instructions", [self.entry(
            team, team_rev, [unit("rules/review.md", "review")])]))
        prepared = self.prepared(self.ask([self.team]))
        self.assertEqual((self.winner(prepared)["body_digest"], prepared["material_gaps"]),
                         (sha(REVIEW), []))

    def test_a_winning_unit_whose_body_is_not_held_is_unavailable_and_nothing_lower_serves(self):
        mine, mine_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW},
                                       held=False)
        team, team_rev = self.authored(self.team, {"rules/review.md": RELEASE})
        self.placed(self.collection(self.person.scope, "instructions", [self.entry(
            mine, mine_rev, [unit("rules/review.md", "review")])]))
        self.placed(self.collection(self.team, "instructions", [self.entry(
            team, team_rev, [unit("rules/review.md", "review")])]))
        answer = self.compose(self.ask([self.person.scope, self.team]))
        prepared = answer["returned"][0]
        self.assertEqual([u["standing"] for u in prepared["units"]], ["winning", "shadowed"])
        self.assertNotIn("body_digest", prepared["units"][0])
        self.assertEqual(prepared["units"][1]["body_digest"], sha(RELEASE))
        self.assertEqual(gaps(answer), [{"code": c04.ROLE_BODY_UNAVAILABLE,
                                         "pointer": "/units/0"}])
        self.assertEqual(prepared["material_gaps"], gaps(answer))

    def test_a_shadowed_or_disabled_unit_whose_body_is_not_held_gates_nothing(self):
        mine, mine_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        team, team_rev = self.authored(self.team, {"rules/review.md": RELEASE}, held=False)
        self.placed(self.collection(self.person.scope, "instructions", [self.entry(
            mine, mine_rev, [unit("rules/review.md", "review")])]))
        self.placed(self.collection(self.team, "instructions", [self.entry(
            team, team_rev, [unit("rules/review.md", "review")])]))
        prepared = self.prepared(self.ask([self.person.scope, self.team]))
        self.assertEqual((prepared["material_gaps"], "body_digest" in prepared["units"][1]),
                         ([], False))

    def test_a_layered_unit_whose_body_is_not_held_states_none_and_gates_nothing(self):
        mine, mine_rev = self.authored(self.person.scope, {"notes.md": NOTE}, held=False)
        answer = self.compose(self.ask([self.person.scope], pins=[(mine, mine_rev)]))
        self.assertEqual((gaps(answer), "body_digest" in answer["returned"][0]["units"][0]),
                         ([], False))

    def test_a_unit_a_winner_needs_whose_body_is_not_held_is_unavailable(self):
        base, base_rev = self.authored(self.team, {"rules/base.md": NOTE}, held=False)
        team, team_rev = self.authored(self.team, {"rules/review.md": REVIEW})
        needs = [{"source_id": base, "member": "rules/base.md"}]
        self.placed(self.collection(self.team, "instructions", [
            self.entry(team, team_rev, [unit("rules/review.md", "review", needs=needs)]),
            self.entry(base, base_rev, [unit("rules/base.md")])]))
        answer = self.compose(self.ask([self.team]))
        units = answer["returned"][0]["units"]
        self.assertEqual([(u["standing"], "needed_by" in u) for u in units],
                         [("winning", False), ("layered", True)])
        self.assertEqual(gaps(answer), [{"code": c04.ROLE_BODY_UNAVAILABLE,
                                         "pointer": "/units/1"}])

    def test_bundle_bytes_that_are_not_the_members_are_a_mismatch_and_not_named(self):
        mine, mine_rev = self.authored(self.person.scope, {"rules/review.md": REVIEW})
        path = storage.bundle(self.bench.state, mine_rev) / storage.MEMBERS / "rules/review.md"
        path.write_bytes(REVIEW.replace(b"One", b"Two"))   # the same size, other bytes
        self.placed(self.collection(self.person.scope, "instructions", [self.entry(
            mine, mine_rev, [unit("rules/review.md", "review")])]))
        answer = self.compose(self.ask([self.person.scope]))
        self.assertEqual(gaps(answer), [{"code": c03.OBJECT_DIGEST_MISMATCH,
                                         "pointer": "/units/0"}])
        self.assertNotIn("body_digest", answer["returned"][0]["units"][0])

    def test_a_repository_authored_body_is_its_revisions_snapshot_not_the_working_tree(self):
        checkout = Checkout(self.scratch)
        checkout.write("rules/review.md", REVIEW)
        checkout.write("rules/deploy.md", RELEASE)
        checkout.commit()
        self.bind(checkout)
        with contextlib.chdir(checkout.path):
            source, revision = self.authored(self.repository_scope,
                                             {"rules/review.md": REVIEW,
                                              "rules/deploy.md": RELEASE},
                                             mode="repository_authored", held=False)
        pins = [(source, revision)]
        (checkout.path / "rules/review.md").unlink()
        checkout.write("rules/deploy.md", RELEASE + b"edited\n")
        answer = self.compose(self.ask([self.repository_scope], pins=pins), checkout.path)
        self.assertEqual(([u.get("body_digest") for u in answer["returned"][0]["units"]],
                          gaps(answer)), ([sha(REVIEW), sha(RELEASE)], []))

    def test_a_unit_names_the_home_its_source_is_registered_with(self):
        checkout = Checkout(self.scratch)
        checkout.write("docs/rules.md", REVIEW)
        checkout.commit()
        binding = self.bind(checkout)["returned"][0]
        registered = self.register(home(
            self.person, self.source, role="instructions",
            home={"mode": "repository_authored", "repository_id": self.repository,
                  "document_root": "docs",
                  "binding_evidence_digest": canonical.digest_of(binding)}))
        head = registered["receipt"]["head_digest"]
        revision = self.commit(manifest(self.source, {"docs/rules.md": REVIEW}),
                               head)["receipt"]["head_digest"]
        prepared = self.prepared(self.ask([self.person.scope], pins=[(self.source, revision)]))
        self.assertEqual([(u["layer"], u["home_digest"], u.get("body_digest"))
                          for u in prepared["units"]], [("personal", head, sha(REVIEW))])


class Observed(Composing):
    def test_a_directory_no_repository_is_bound_from_is_recorded_by_itself(self):
        elsewhere = Checkout(self.scratch, "elsewhere")
        elsewhere.commit()
        self.bind(elsewhere)
        checkout = Checkout(self.scratch)
        checkout.git("remote", "add", "origin", ORIGIN)
        prepared = self.prepared(self.ask([self.person.scope]), where=checkout.path)
        self.assertEqual(prepared["observed"], {"locator": str(checkout.path)})
        plain = self.scratch / "plain"
        plain.mkdir()
        self.assertEqual(self.prepared(self.ask([self.person.scope]), where=plain)["observed"],
                         {"locator": str(plain.resolve())})

    def test_a_bound_checkout_is_recorded_as_it_is_with_the_working_bytes_observed(self):
        checkout = Checkout(self.scratch)
        checkout.write("docs/adr/0001.md", b"one\n")
        checkout.commit()
        checkout.git("remote", "add", "origin", ORIGIN)
        self.bind(checkout)
        head = checkout.git("rev-parse", "HEAD")
        prepared = self.prepared(self.ask([self.person.scope]), where=checkout.path)
        self.assertEqual(prepared["observed"], {"locator": ORIGIN, "branch": "main",
                                                "commit": head})
        observation = self.observe(self.selection(checkout, ("docs/adr", "required")))
        prepared = self.prepared(self.ask([self.person.scope]), where=checkout.path)
        self.assertEqual(prepared["observed"]["working_bytes_digest"],
                         canonical.digest_of(observation["returned"][0]))
        self.assertEqual(prepared["material_gaps"], [])

    def test_working_bytes_the_binding_claimed_that_moved_are_named(self):
        checkout = Checkout(self.scratch)
        checkout.write("docs/adr/0001.md", b"one\n")
        checkout.commit()
        self.observe(self.selection(checkout, ("docs/adr", "required")))
        self.bind(checkout)
        checkout.write("docs/adr/0001.md", b"one, edited\n")
        answer = self.compose(self.ask([self.person.scope]), checkout.path)
        self.assertEqual(gaps(answer), [{"code": c07.WORKING_BYTES_MOVED}])
        self.assertNotIn("working_bytes_digest", answer["returned"][0]["observed"])
        again = self.observe(self.selection(checkout, ("docs/adr", "required")))
        answer = self.compose(self.ask([self.person.scope]), checkout.path)
        self.assertEqual((gaps(answer), answer["returned"][0]["observed"]["working_bytes_digest"]),
                         ([{"code": c07.WORKING_BYTES_MOVED}],
                          canonical.digest_of(again["returned"][0])))

    def test_the_last_repository_bound_from_the_checkout_is_the_one_recorded(self):
        checkout = Checkout(self.scratch)
        checkout.commit()
        self.observe(self.selection(checkout, ("README.md", "optional")))
        self.bind(checkout)
        later = bench.ident("rep")
        payload = {"kind": "repository_binding", "schema": 1, "repository_id": later,
                   "relation": {"how": "clone"}}
        with contextlib.chdir(checkout.path):
            self.run_with(sources.repository_bind,
                          bench.request(self.person, "repository.bind", later, payload),
                          [payload], now=INSTANT)
        self.assertEqual(sources.checkouts.bound_at(self.bench.store(), checkout.path)[0], later)


class Recipients(Composing):
    def link(self, isolation: str = "proven_fresh") -> str:
        value = {"kind": "recipient_link", "schema": 1, "link_id": bench.ident("lnk"),
                 "principal_id": self.person.principal, "work_scope": self.person.scope,
                 "host": {"name": "claude-code", "version": "2.1.278"},
                 "destination": {"destination_kind": "conversation",
                                 "destination_digest": "4" * 64},
                 "isolation": isolation, "created_at": INSTANT}
        store = self.bench.store()
        with store.unit(self.bench.call(bench.request(self.person, "access.profile.read",
                                                      self.person.profile))):
            return store.put(value)

    def test_the_recipient_works_in_the_first_scope_named_unless_the_request_says(self):
        prepared = self.prepared(self.ask([self.team, self.person.scope]))
        self.assertEqual(prepared["recipient"], {"work_scope": self.team,
                                                 "isolation": "proven_fresh"})
        prepared = self.prepared(self.ask([self.team, self.person.scope]),
                                 work_scope=self.person.scope)
        self.assertEqual(prepared["recipient"]["work_scope"], self.person.scope)

    def test_a_named_link_is_the_recipient_and_a_session_start_on_it_is_selected_only(self):
        digest = self.link("evidenced_isolated")
        answer = self.compose(self.ask([self.person.scope]), recipient_digest=digest)
        prepared, routing = answer["returned"]
        self.assertEqual(prepared["recipient"], {"work_scope": self.person.scope,
                                                 "recipient_digest": digest,
                                                 "isolation": "evidenced_isolated"})
        self.assertEqual(routing, {
            "kind": "session_routing", "schema": 1,
            "session": {"host": {"name": "claude-code", "version": "2.1.278"},
                        "profile_id": self.person.profile},
            "delivery": {"state": "selected_only"}, "always_surface": "unchanged",
            "native_files": "preserved", "routed_at": INSTANT})
        delivery = self.compose(self.ask([self.person.scope],
                                         operation="recipient.delivery.attempt"),
                                recipient_digest=digest)
        self.assertEqual([v["kind"] for v in delivery["returned"]], ["preparation"])

    def test_a_link_this_installation_does_not_hold_is_unknown(self):
        held = self.placed(self.collection(self.person.scope, "instructions", []))
        for digest in ("5" * 64, held):
            answer = self.compose(self.ask([self.person.scope]), recipient_digest=digest)
            self.assertEqual(gaps(answer), [{"code": c11.RECIPIENT_LINK_UNKNOWN,
                                             "pointer": "/recipient_digest"}])
        self.assertEqual(self.count("preparations"), 0)


if __name__ == "__main__":
    unittest.main()
