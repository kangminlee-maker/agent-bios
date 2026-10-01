"""Paths that reach the next step: a start followed from its composition through activation, the
environment it renders, what an observation lists and what the entry shows before it, across the
states that tell them apart (design record `2026-10-01T2134--3551ccb--v1-restructure-design.md`).

Each case states what it expects from the rule it holds, never by reading back the code that
applies it: which unit is required, which bodies a session is handed, which units an observation
lists. The interleavings the journal decides on are held in `test_journal` (`Held`, `Ruled`,
`Decided`), and a compaction the host accepted and did not do in `test_probes`.
"""
from __future__ import annotations

import contextlib
import itertools
import unittest

import bench
from test_delivery import NOTE, REVIEW
from test_preparation import unit
from test_roles import RELEASE, Activating
from test_routes import commits
from test_tui import DRIVE, Entering
from test_sources import INSTANT, Checkout, gaps

from workenv import commands, journal, terminal, tui
from workenv.contracts import c04, c07
from workenv.hosts import start

BASE, RULES, NOTES = "rules/base.md", "rules/review.md", "notes.md"


def labels(positions: list[tui.Position]) -> str:
    """The positions as the entry words them, in Korean."""
    drawer = tui.Entry.__new__(tui.Entry)
    drawer.locale = "ko"
    return "\n".join(drawer.position_label(position) for position in positions)

# Where the unit the winner needs stands: selected and on, switched off, in no selection, or
# shadowed by another unit of its concern in a layer above.
NEEDED = ("on", "off", "omitted", "shadowed")
ACTIVATE = "session.routing.activate"


class Crossed(Activating):
    """A required or optional personal winner that needs a Team member, the needed unit in one of
    the states above, its body held or not, and its bytes the winner's own or other bytes. A
    knowledge source holds the winner's bytes in every case, so equal bytes in another role are
    always there."""

    def composed(self, needed: str, required: bool, held: bool, same: bool):
        link, digest = self.linked()
        companion, companion_rev = self.authored(self.team, {BASE: REVIEW if same else NOTE},
                                                 held=held)
        mine, mine_rev = self.authored(self.person.scope, {RULES: REVIEW})
        entries = [self.entry(mine, mine_rev, [unit(
            RULES, "review", "required" if required else "not_required",
            needs=[{"source_id": companion, "member": BASE}])])]
        # What a session is handed: the winners whose bodies are held.
        carried = [(mine, RULES)]
        if needed == "shadowed":
            other, other_rev = self.authored(self.person.scope, {BASE: RELEASE})
            entries.append(self.entry(other, other_rev, [unit(BASE, "base", "not_required")]))
            carried.append((other, BASE))
        self.placed(self.collection(self.person.scope, "instructions", entries))
        if needed != "omitted":
            self.placed(self.collection(self.team, "instructions", [self.entry(
                companion, companion_rev, [unit(BASE, "base", "not_required")],
                switch="off" if needed == "off" else "on")]))
        if needed == "on" and held:
            carried.append((companion, BASE))
        self.authored(self.person.scope, {NOTES: REVIEW}, role="knowledge")
        # The start the entry would send: the person includes the knowledge position, and leaves
        # the Team's Instructions out where the needed unit is in no selection.
        scopes = [self.person.scope, self.team]
        chosen = {"positions.personal.knowledge": True}
        if needed == "omitted":
            chosen["positions.team.instructions"] = False
        positions = tui.positions_of(self.bench.store(), scopes, chosen)
        asked = self.ask(scopes)
        asked["basis"]["source_pins"] = [pin for position in positions if position.included
                                         for pin in position.pins]
        prepared = self.prepared(asked, recipient_digest=digest)
        # A unit the winner needs stays required while the winner is, however it stands, so the
        # start is refused where the winner is required and that unit is missing or bodiless.
        refused = required and (needed == "omitted" or not held)
        return link, prepared, positions, carried, refused

    def check(self, needed: str, required: bool, held: bool, same: bool) -> None:
        link, prepared, positions, carried, refused = self.composed(needed, required, held,
                                                                     same)
        identity = {held_unit["unit_id"]: (held_unit["source_id"], held_unit["member"])
                    for held_unit in prepared["units"]}

        # The entry before the start shows every cause the start refuses for.
        if refused:
            shown = [member for position in positions
                     for member in position.needs + position.unheld]
            self.assertIn(BASE, shown, "the entry hides why the start is refused")
            words = tui.CATALOG["ko"]["needs" if needed == "omitted" else "unheld"]
            self.assertIn(words.format(member=BASE), labels(positions))

        # The start is refused exactly where a required unit has no usable body.
        answer = self.activate(prepared)
        if refused:
            codes = {gap["code"] for gap in answer["result"]["outcome"]["material_gaps"]}
            self.assertNotEqual(answer["result"]["outcome"]["stage"], "committed")
            self.assertTrue(codes & tui.UNMET, codes)
            self.assertEqual(self.count("deliveries"), 0)
        else:
            self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))

        # The environment holds exactly the carried bodies, each once.
        handed = start.handed(self.bench.state, prepared)
        self.assertEqual(sorted((u["source_id"], u["member"]) for u in handed.units),
                         sorted(carried))
        for source_id, member in identity.values():
            self.assertEqual(handed.text.count(f"Source {source_id}, body sha256 "),
                             1 if (source_id, member) in carried else 0, member)
        if refused:
            return

        # The observation lists exactly the carried units handed over, by identity: equal bytes
        # in another role or standing are not listed.
        self.received(link, prepared, recipient="new", bodies=handed.bodies)
        observed = self.observations(prepared["preparation_id"])["returned"]
        inventory = [identity[u["unit_id"]] for u in observed[0]["observed"]["inventory"]]
        self.assertEqual(sorted(inventory), sorted(carried))


def crossed(needed: str, required: bool, held: bool, same: bool):
    def test(self) -> None:
        self.check(needed, required, held, same)
    test.__doc__ = (f"needed {needed}, winner {'required' if required else 'optional'}, body "
                    f"{'held' if held else 'missing'}, bytes {'the same' if same else 'other'}")
    return test


for _needed, _required, _held, _same in itertools.product(NEEDED, (True, False), (True, False),
                                                            (True, False)):
    setattr(Crossed, f"test_{_needed}_{'required' if _required else 'optional'}_"
                     f"{'held' if _held else 'missing'}_{'same' if _same else 'other'}",
            crossed(_needed, _required, _held, _same))


class OtherRole(Activating):
    """A required or optional personal Instructions winner that needs a Team knowledge member,
    its position included or left out, its body held or not. Knowledge reaches no session at its
    start, but a unit a winner needs is read there whatever its role and wherever it is."""

    def check(self, included: bool, required: bool, held: bool) -> None:
        link, digest = self.linked()
        notes, _ = self.authored(self.team, {NOTES: NOTE}, role="knowledge", held=held)
        mine, mine_rev = self.authored(self.person.scope, {RULES: REVIEW})
        self.placed(self.collection(self.person.scope, "instructions", [self.entry(
            mine, mine_rev, [unit(RULES, "review", "required" if required else "not_required",
                                  needs=[{"source_id": notes, "member": NOTES}])])]))
        scopes = [self.person.scope, self.team]
        positions = tui.positions_of(self.bench.store(), scopes,
                                     {"positions.team.knowledge": included})
        asked = self.ask(scopes)
        asked["basis"]["source_pins"] = [pin for position in positions if position.included
                                         for pin in position.pins]
        prepared = self.prepared(asked, recipient_digest=digest)
        refused = required and (not included or not held)
        if refused:
            words = tui.CATALOG["ko"]["unheld" if included else "needs"]
            self.assertIn(words.format(member=NOTES), labels(positions))
        answer = self.activate(prepared)
        self.assertEqual(answer["result"]["outcome"]["stage"] == "committed", not refused,
                         gaps(answer))
        handed = start.handed(self.bench.state, prepared)
        self.assertEqual([u["source_id"] for u in handed.units], [mine])


def other_role(included: bool, required: bool, held: bool):
    def test(self) -> None:
        self.check(included, required, held)
    return test


for _included, _required, _held in itertools.product((True, False), (True, False), (True, False)):
    setattr(OtherRole, f"test_{'included' if _included else 'left_out'}_"
                       f"{'required' if _required else 'optional'}_"
                       f"{'held' if _held else 'missing'}", other_role(_included, _required, _held))


class Changed(Activating):
    """A repository document a start may rest on, changed in the checkout after it was admitted
    or not, winning, shadowed or switched off, needed by the winner or not."""

    def check(self, standing: str, needed: bool, changed: bool) -> None:
        _, digest = self.linked()
        checkout = Checkout(self.scratch)
        checkout.write(RULES, REVIEW)
        checkout.commit()
        self.bind(checkout)
        scope = {"layer": "repository", "repository_id": self.repository}
        with contextlib.chdir(checkout.path):
            theirs, theirs_rev = self.authored(scope, {RULES: REVIEW},
                                               mode="repository_authored", held=False)
        mine, mine_rev = self.authored(scope, {"rules/mine.md": NOTE})
        needs = {"needs": [{"source_id": theirs, "member": RULES}]} if needed else {}
        concern = "review" if standing == "shadowed" else "mine"
        self.placed(self.collection(scope, "instructions", [
            self.entry(mine, mine_rev, [unit("rules/mine.md", concern, **needs)], precedence=1),
            self.entry(theirs, theirs_rev, [unit(RULES, "review", "not_required")],
                       switch="off" if standing == "off" else "on", precedence=2)]))
        prepared = self.prepared(self.ask([scope]), where=checkout.path,
                                 recipient_digest=digest)
        if changed:
            checkout.write(RULES, REVIEW + b"edited\n")
        # A start rests on a document it carries, or on one a unit it carries needs.
        moved = changed and (standing == "winning" or needed)
        position = next(p for p in tui.positions_of(self.bench.store(), [scope])
                        if p.role == "instructions")
        self.assertEqual(position.changed, [RULES] if moved else [])
        self.assertEqual(tui.CATALOG["ko"]["changed"].format(member=RULES) in
                         labels([position]), moved)
        answer = self.activate(prepared, where=checkout.path)
        if moved:
            self.assertEqual(gaps(answer), [{"code": c07.WORKING_BYTES_MOVED}])
        else:
            self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))


def changed_case(standing: str, needed: bool, changed: bool):
    def test(self) -> None:
        self.check(standing, needed, changed)
    return test


for _standing, _needed_by, _changed in itertools.product(("winning", "shadowed", "off"),
                                                         (True, False), (True, False)):
    setattr(Changed, f"test_{_standing}_{'needed' if _needed_by else 'unneeded'}_"
                     f"{'changed' if _changed else 'unchanged'}",
            changed_case(_standing, _needed_by, _changed))


class Recovering(Entering):
    """The entry's recovery against what the owner holds: each check is a real query, drawn as the
    terminal draws it."""

    def setUp(self):
        super().setUp()
        self.answers: list = []
        self.dispatched: list = []

    def unknown_start(self) -> tuple[dict, str]:
        """A start the owner holds with an unknown outcome: its preparation and its request id."""
        self.launcher()
        prepared = self.prepared(self.ask([self.repository, self.person.scope]))
        answer = self.activate(prepared)
        self.assertEqual(answer["result"]["outcome"]["stage"], "unknown")
        return prepared, answer["result"]["request_id"]

    def dispatch(self, sealed: dict, carried: list) -> None:
        """The terminal's dispatcher, as `commands.begin` has it: a check is a real query."""
        self.dispatched.append(sealed)
        if sealed["operation"] == tui.QUERY:
            answer = journal.layer_journal(self.bench.call(sealed, carried, now=INSTANT), None)
            self.answers.append((sealed["request_id"], commands.checked(answer)))

    def opened(self) -> tui.Entry:
        script = {"kind": "surface_script", "schema": 1,
                  "entrance": {"name": "host_launcher", "root_origin": "owner"},
                  "terminal": {"columns": 100, "rows": 24}, "locale": "ko", "inputs": []}
        return tui.Entry(self.bench.store(),
                         bench.request(self.person, DRIVE, self.person.profile, script), script,
                         self.dispatch)

    def press(self, entry: tui.Entry, *keys: str) -> list[str]:
        """The keys, each answer handed over as the terminal hands it, and the lines drawn."""
        for key in keys:
            entry.press({"input": "key", "key": key})
            while self.answers:
                request_id, (state, reason) = self.answers.pop(0)
                entry.answered(request_id, state, reason)
        return terminal.lines(entry.frame(len(keys)))

    def test_check_unknown_check_again_settled_then_the_start_runs(self):
        prepared, draft = self.unknown_start()
        entry = self.opened()
        self.assertEqual((entry.check_state(), entry.here["focus"]),
                         ("not_checked", "action.check"))
        lines = self.press(entry, "enter")
        self.assertEqual(entry.check_state(), "still_unknown")
        self.assertIn(tui.CATALOG["ko"]["draft"].format(
            coverage=tui.CATALOG["ko"]["coverage.local_only"]), "\n".join(lines))
        # Asked again under its own id, the owner settles the start.
        settled = self.activate(prepared, entry=commits, request_id=draft)
        self.assertEqual(settled["result"]["outcome"]["stage"], "committed")
        lines = self.press(entry, "enter")
        self.assertEqual(entry.check_state(), "settled")
        self.assertIn(tui.CATALOG["ko"]["settled.committed"], "\n".join(lines))
        self.press(entry, "enter")
        self.assertEqual([sealed["operation"] for sealed in self.dispatched],
                         [tui.QUERY, tui.QUERY], "a settled check is not asked again")
        self.assertFalse(entry.holds_back())
        self.press(entry, "tab", "tab", "tab", "enter")
        self.assertEqual(self.dispatched[-1]["operation"], tui.COMPOSE)
        # Reopened, the entry finds nothing unknown.
        self.assertEqual(self.opened().check_state(), "none")

    def test_a_check_of_a_request_this_installation_does_not_hold_could_not_check(self):
        self.launcher()
        entry = self.opened()
        entry.draft = {"request_id": bench.ident("req"), "confirmed_stage": "unknown",
                       "coverage": "local_only"}
        entry.here["focus"] = "action.check"
        lines = self.press(entry, "enter")
        self.assertEqual(entry.check_state(), "could_not_check")
        self.assertTrue(entry.holds_back() and entry.may_check())
        self.assertIn(tui.CATALOG["ko"]["not_checked"].format(
            reason=entry.answers[entry.checking][1]), "\n".join(lines))

    def test_the_unknown_start_is_found_around_more_starts_than_a_history_lists(self):
        self.launcher()
        basis = self.ask([self.repository, self.person.scope])
        for _ in range(12):
            self.activate(self.prepared(basis), entry=commits)
        _, draft = self.unknown_start()
        for _ in range(12):
            self.activate(self.prepared(basis), entry=commits)
        listed = self.history(self.repository, limit=3)["entries"]
        self.assertEqual(len(listed), 3)
        self.assertEqual([entry["request_id"] for entry in listed
                          if entry["confirmed_stage"] == "unknown"], [draft])
        entry = self.opened()
        self.assertEqual((entry.draft["request_id"], entry.check_state()), (draft, "not_checked"))

    def test_a_refused_start_is_drawn_in_its_words_and_reopens_the_choices(self):
        self.launcher()
        entry = self.opened()
        self.press(entry, "tab", "tab", "enter")
        self.assertEqual(entry.start_state(), "sent")
        self.assertFalse(entry.choosing())
        entry.answered(entry.started, "unavailable", "refused",
                       codes=[c04.ROLE_BODY_UNAVAILABLE])
        lines = terminal.lines(entry.frame(4))
        self.assertIn(tui.CATALOG["ko"]["not_started.required"], "\n".join(lines))
        self.assertEqual(entry.start_state(), "refused")
        self.assertTrue(entry.choosing())


if __name__ == "__main__":
    unittest.main()
