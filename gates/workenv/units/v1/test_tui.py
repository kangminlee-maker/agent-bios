"""The entry model (`workenv.tui`): what an entrance draws from what the owner holds, one frame per
input, and the one request an input dispatches. The conformance runner holds a trace without its
labels (D-20260928-380689), so the wording is held here, against the catalog."""
from __future__ import annotations

import contextlib
import shutil
import string
import unittest

import bench
from test_preparation import unit
from test_routes import HISTORY, LATER, Routing, commits
from test_sources import INSTANT, ORIGIN, Checkout, gaps, home

from workenv import cli, journal, sources, tui
from workenv.contracts import canonical

DRIVE, OFFER, COMPOSE = "surface.drive", "route.offer", "preparation.compose"
RULES, NOTES = {"AGENTS.md": b"# Rules\n"}, {"notes.md": b"# Notes\n"}


def fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def longest(table: dict, prefix: str) -> str:
    return max((text for key, text in table.items() if key.startswith(prefix)), key=tui.cells)


class Catalog(unittest.TestCase):
    def test_every_locale_names_the_same_keys_with_the_same_placeholders(self):
        ko = tui.CATALOG["ko"]
        for locale, table in tui.CATALOG.items():
            with self.subTest(locale=locale):
                self.assertEqual(set(table), set(ko))
                for key, text in table.items():
                    self.assertEqual(fields(text), fields(ko[key]), key)

    def test_no_label_asks_a_question_or_restates_the_suggestion_mark(self):
        for locale, table in tui.CATALOG.items():
            word = table["suggested"].strip("()")
            for key, text in table.items():
                with self.subTest(locale=locale, key=key):
                    self.assertNotRegex(text, "[?？]")
                    if key != "suggested":
                        self.assertNotIn(word, text)

    def test_a_label_that_carries_no_held_name_fits_one_line_of_80_columns(self):
        room = 80 - tui.GUTTER
        named = {"location.repository", "location.team", "checkpoint", "position",
                 "position.more", "position.unresolved", "unresolved", "unresolved.more",
                 "unheld", "unheld.more", "changed", "changed.more",
                 "detail", "not_started", "not_checked"}
        for locale, table in tui.CATALOG.items():
            fill = {"layer": longest(table, "layer."), "role": longest(table, "role."),
                    "action": longest(table, "action."),
                    "coverage": longest(table, "coverage."),
                    "state": longest(table, "state."), "more": "99",
                    "tool": max(tui.TOOLS.values(), key=tui.cells),
                    "choice": longest(table, "permissions."), "stage": "changes_requested"}
            marks = {"position.empty": ["›", "[-]", table["unavailable"]],
                     "position.configured": ["›", "[-]", table["unavailable"]],
                     "tool": ["›", table["suggested"]],
                     "permissions": ["›", table["suggested"]]}
            for key, text in table.items():
                if key in named or key.startswith("key."):
                    continue
                line = " ".join([*marks.get(key, ["›"]),
                                 text.format(**{name: fill[name] for name in fields(text)})])
                with self.subTest(locale=locale, key=key):
                    self.assertLessEqual(tui.cells(line), room, line)
            # A detail names only its own Enter and Esc; every other view, the rest.
            keys = " · ".join(text for key, text in table.items()
                              if key.startswith("key.") and key != "key.start")
            self.assertLessEqual(tui.cells(keys), room, keys)
            detail = " · ".join((table["key.start"], table["key.escape"]))
            self.assertLessEqual(tui.cells(detail), room, detail)


class Cells(unittest.TestCase):
    def test_wide_characters_take_two_cells_and_marks_and_medial_jamo_none(self):
        self.assertEqual(tui.cells("ab"), 2)
        self.assertEqual(tui.cells("한글"), 4)
        self.assertEqual(tui.cells("한"), 2)
        self.assertEqual(tui.cells("é"), 1)
        self.assertEqual(tui.cells("Ａ"), 2)

    def test_a_control_character_takes_two_cells(self):
        self.assertEqual(tui.cells("\x1b[0m\n"), 2 + 3 + 2)
        self.assertEqual(tui.cells("\x7f"), 2)


class Entering(Routing):
    def offer_at(self, entrance: str, *routes: dict) -> dict:
        offered = {"kind": "route_offer", "schema": 1,
                   "entrance": {"name": entrance, "root_origin": "owner"},
                   "offered": list(routes)}
        answer = self.run_with(cli.route_offer,
                               bench.request(self.person, OFFER, self.person.profile, offered),
                               [offered], now=INSTANT)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        return answer["returned"][0]

    def launcher(self, *more: dict, scope: dict | None = None, hosts=("claude-code",),
                 entrance: str = "host_launcher") -> list[dict]:
        """An offer of one qualified start route per host in the scope, then the routes given."""
        starts = [self.route(probe=self.probe(host), scope=scope) for host in hosts]
        self.offer_at(entrance, *starts, *more)
        return starts

    def drive(self, *inputs, entrance: str = "host_launcher", terminal=(80, 24),
              locale: str = "ko", link: dict | None = None) -> list[dict]:
        script = {"kind": "surface_script", "schema": 1,
                  "entrance": {"name": entrance, "root_origin": "owner"},
                  "terminal": {"columns": terminal[0], "rows": terminal[1]}, "locale": locale,
                  "inputs": [{"input": "key", "key": given} if isinstance(given, str) else given
                             for given in inputs]}
        if link is not None:
            script["link"] = link
        self.drive_request = bench.request(self.person, DRIVE, self.person.profile, script,
                                           local_access_generation=7)
        self.sent: list[tuple[dict, list]] = []
        trace = tui.drive(self.bench.store(), self.drive_request, script, LATER,
                          dispatch=lambda sealed, carried: self.sent.append((sealed, carried)))
        return trace["frames"]

    def holding(self, *inputs) -> tui.Entry:
        """An entry the terminal holds, after the inputs, whose dispatcher records."""
        script = {"kind": "surface_script", "schema": 1,
                  "entrance": {"name": "host_launcher", "root_origin": "owner"},
                  "terminal": {"columns": 80, "rows": 24}, "locale": "ko", "inputs": []}
        self.sent = []
        entry = tui.Entry(self.bench.store(),
                          bench.request(self.person, DRIVE, self.person.profile, script),
                          script, dispatch=lambda sealed, carried: self.sent.append(
                              (sealed, carried)))
        for given in inputs:
            entry.press({"input": "key", "key": given} if isinstance(given, str) else given)
        return entry

    @staticmethod
    def ids(frame: dict) -> list[str]:
        return [element["element_id"] for element in frame["elements"]]

    @staticmethod
    def element(frame: dict, element_id: str) -> dict:
        return next(e for e in frame["elements"] if e["element_id"] == element_id)

    @staticmethod
    def focus(frame: dict) -> str | None:
        return next((e["element_id"] for e in frame["elements"] if e["focused"]), None)

    def marks(self, frame: dict, element_id: str) -> tuple:
        found = self.element(frame, element_id)
        return found["state"], found["selection"], found["marks"]

    def bound(self, branch: str) -> Checkout:
        """The repository bound from a checkout of ORIGIN on the branch: the checkout."""
        checkout = Checkout(self.scratch)
        checkout.git("remote", "add", "origin", ORIGIN)
        checkout.git("checkout", "-q", "-b", branch)
        checkout.commit()
        payload = {"kind": "repository_binding", "schema": 1,
                   "repository_id": self.repository["repository_id"],
                   "relation": {"how": "clone"}}
        with contextlib.chdir(checkout.path):
            answer = self.run_with(sources.repository_bind,
                                   bench.request(self.person, "repository.bind",
                                                 self.repository["repository_id"], payload),
                                   [payload], now=INSTANT)
        self.assertEqual(answer["result"]["outcome"]["stage"], "committed", gaps(answer))
        return checkout

    @staticmethod
    def positions(*layers: str) -> list[str]:
        return [f"positions.{layer}.{role}" for layer in layers for role in tui.ROLES]


class Drawing(Entering):
    def test_w01_draws_the_basis_the_note_the_tool_the_permissions_the_blockers_and_the_start(self):
        decide = self.route("decide", scope=self.person.scope)
        start = self.launcher(decide)[0]
        frame = self.drive()[0]
        self.assertEqual(self.ids(frame), ["context.location",
                                           *self.positions("repository", "personal"),
                                           "field.note", "execution.tool",
                                           "execution.permissions",
                                           "blocker.personal.decide", "action.start",
                                           "help.keys"])
        self.assertEqual(frame["view"], {"view": "w01", "selected_scope": self.repository,
                                         "origin": {"name": "host_launcher",
                                                    "root_origin": "owner"},
                                         "missing_bodies": []})
        self.assertEqual(self.element(frame, "context.location")["refers_to"],
                         {"ref": "scope", "scope": self.repository})
        blocker = self.element(frame, "blocker.personal.decide")
        self.assertEqual((blocker["role"], blocker["state"], blocker["refers_to"]),
                         ("blocker", "blocked", {"ref": "route", "route_id": decide["route_id"]}))
        begin = self.element(frame, "action.start")
        self.assertEqual((begin["refers_to"], begin["effects"], begin["executing"]),
                         ({"ref": "route", "route_id": start["route_id"]},
                          ["file_changes", "model_calls"], False))
        tool = self.element(frame, "execution.tool")
        self.assertEqual((tool["value"], tool["selection"], tool["marks"], tool["effects"]),
                         ("Claude Code", "suggested", ["(제안)"], ["model_calls"]))
        permissions = self.element(frame, "execution.permissions")
        self.assertEqual((permissions["role"], permissions["value"], permissions["selection"],
                          permissions["marks"], permissions["effects"], permissions["label"]),
                         ("setting", "host_settings", "suggested", ["(제안)"],
                          ["permission_request"], "권한 · 호스트 설정대로 확인"))
        self.assertEqual(self.element(frame, "field.note")["value"], "")

    def test_a_start_in_the_person_s_scope_draws_their_positions_alone(self):
        self.launcher(scope=self.person.scope)
        frame = self.drive()[0]
        self.assertEqual(frame["view"]["selected_scope"], self.person.scope)
        self.assertEqual([i for i in self.ids(frame) if i.startswith("positions.")],
                         self.positions("personal"))

    def test_with_no_qualified_start_the_person_s_scope_is_shown_and_nothing_starts(self):
        self.offer_at("host_launcher", self.route("use"))
        frames = self.drive("tab")
        frame = frames[1]
        self.assertEqual(frame["elements"], frames[0]["elements"])
        self.assertEqual(frame["view"]["selected_scope"], self.person.scope)
        self.assertNotIn("action.start", self.ids(frame))
        self.assertNotIn("field.note", self.ids(frame))
        self.assertIn("blocker.repository.use", self.ids(frame))
        self.assertEqual(self.sent, [])

    def test_the_latest_offer_from_the_script_s_own_entrance_is_the_one_read(self):
        self.launcher(hosts=("claude-code",))
        self.launcher(hosts=("codex",))
        self.launcher(hosts=("claude-code", "codex"), entrance="setup")
        frame = self.drive()[0]
        self.assertEqual(self.element(frame, "execution.tool")["value"], "Codex CLI")
        self.assertEqual(frame["view"]["origin"]["name"], "host_launcher")

    def test_the_location_names_the_bound_checkout_s_remote_and_branch(self):
        self.launcher()
        self.bound("feature/retry")
        frames = self.drive({"input": "locale", "locale": "en"})
        self.assertEqual(self.element(frames[0], "context.location")["label"],
                         "work · 로컬 레포 · feature/retry")
        self.assertEqual(self.element(frames[1], "context.location")["label"],
                         "work · local repository · feature/retry")

    def test_the_location_names_the_branch_the_checkout_is_on_as_the_entry_opens(self):
        self.launcher()
        checkout = self.bound("main")
        checkout.git("checkout", "-q", "-b", "feature/retry")
        label = lambda: self.element(self.drive()[0], "context.location")["label"]  # noqa: E731
        self.assertEqual(label(), "work · 로컬 레포 · feature/retry")
        checkout.git("checkout", "-q", "--detach")
        self.assertEqual(label(), "work · 로컬 레포 · ")
        # Where git does not read the checkout, the branch it was bound on.
        shutil.rmtree(checkout.path)
        self.assertEqual(label(), "work · 로컬 레포 · main")

    def test_a_route_is_qualified_by_its_host_s_latest_probe_now_not_by_the_offer(self):
        claude = self.route(probe=self.probe())
        codex = self.route(probe=self.probe("codex"))
        self.offer_at("host_launcher", claude, codex)
        self.probe("codex", outcome="failed", at=LATER)
        frames = self.drive("tab", "tab")
        self.assertEqual(self.element(frames[0], "blocker.repository.use")["refers_to"],
                         {"ref": "route", "route_id": codex["route_id"]})
        self.assertEqual(self.element(frames[0], "blocker.repository.use")["label"],
                         tui.CATALOG["ko"]["blocker"].format(layer="레포", action="새 세션",
                                                             tool="Codex CLI"))
        self.assertEqual(self.element(frames[0], "execution.tool")["value"], "Claude Code")
        self.assertEqual(self.focus(frames[2]), "action.start")

    def test_one_start_is_offered_per_host(self):
        self.launcher(hosts=("claude-code", "claude-code"))
        frames = self.drive("tab", "tab")
        self.assertEqual(self.focus(frames[2]), "action.start")
        self.assertFalse([i for i in self.ids(frames[0]) if i.startswith("blocker.")])

    def test_two_blockers_of_one_layer_and_action_are_told_apart(self):
        self.launcher(self.route("decide", scope=self.person.scope),
                      self.route("decide", scope=self.person.scope))
        self.assertEqual([i for i in self.ids(self.drive()[0]) if i.startswith("blocker.")],
                         ["blocker.personal.decide", "blocker.personal.decide.2"])

    def test_a_blocker_names_the_host_its_probe_names_or_the_start_s(self):
        self.launcher(self.route("decide", scope=self.person.scope),
                      self.route("read", scope=self.person.scope))
        frame = self.drive()[0]
        self.assertEqual(self.element(frame, "blocker.personal.decide")["label"],
                         tui.CATALOG["ko"]["blocker"].format(layer="개인", action="결정",
                                                             tool="Claude Code"))
        self.assertEqual(self.element(frame, "blocker.personal.read")["label"],
                         tui.CATALOG["ko"]["blocker"].format(layer="개인", action="read",
                                                             tool="Claude Code"))


class Selecting(Entering):
    def test_a_position_shows_what_the_owner_holds_there(self):
        me = self.person.scope
        self.launcher(scope=me)
        self.authored(me, RULES)
        self.authored(me, NOTES, role="knowledge")
        frame = self.drive()[0]
        self.assertEqual(self.marks(frame, "positions.personal.instructions"),
                         ("installed", "suggested", ["›", "[x]", "(제안)"]))
        self.assertEqual(self.marks(frame, "positions.personal.knowledge"),
                         ("not_checked", "none", ["[ ]"]))
        self.assertEqual(self.marks(frame, "positions.personal.memory"),
                         ("checked_empty", "none", ["[-]", "(선택 불가)"]))
        self.assertEqual(self.element(frame, "positions.personal.knowledge")["refers_to"],
                         {"ref": "position", "view": "original",
                          "position": {"scope": me, "role": "knowledge"}})
        self.assertEqual(self.element(frame, "positions.personal.instructions")["label"],
                         "개인 지침 · AGENTS.md")

    def test_a_held_collection_is_the_recorded_choice_and_space_leaves_it(self):
        me = self.person.scope
        self.launcher(scope=me)
        source, revision = self.authored(me, RULES)
        self.placed(self.collection(me, "instructions", [self.entry(source, revision)]))
        notes, noted = self.authored(me, NOTES, role="knowledge")
        self.placed(self.collection(me, "knowledge", [self.entry(notes, noted)], switch="off"))
        frames = self.drive("space", "down", "space")
        for frame in frames:
            state, selection, marks = self.marks(frame, "positions.personal.instructions")
            self.assertEqual((state, selection, marks[-1:]), ("installed", "selected", ["[x]"]))
            self.assertEqual(self.marks(frame, "positions.personal.knowledge"),
                             ("checked_empty", "none", ["[-]", "(선택 불가)"]))
            self.assertEqual(self.focus(frame), "positions.personal.instructions")
        self.assertEqual(self.element(frames[0], "positions.personal.instructions")["marks"],
                         ["›", "[x]"])

    def test_a_collection_names_what_it_selects_that_does_not_resolve(self):
        me = self.person.scope
        self.launcher(scope=me)
        source, revision = self.authored(me, RULES)
        lost = bench.ident("src")
        self.placed(self.collection(me, "instructions", [self.entry(source, revision),
                                                          self.entry(lost, "6" * 64)]))
        frames = self.drive("enter")
        state, selection, marks = self.marks(frames[0], "positions.personal.instructions")
        self.assertEqual((state, selection, marks), ("partial", "selected", ["›", "[x]"]))
        self.assertEqual(self.element(frames[0], "positions.personal.instructions")["label"],
                         f"개인 지침 · AGENTS.md · 쓸 수 없는 원본 {lost[:12]}")
        self.assertEqual(self.element(frames[1], "detail.personal.instructions")["label"],
                         f"개인 지침 · AGENTS.md · 쓸 수 없는 원본 {lost[:12]} · 원본 · "
                         "일부 원본을 쓸 수 없음")
        english = self.drive(locale="en")[0]
        self.assertEqual(self.element(english, "positions.personal.instructions")["label"],
                         f"Personal Instructions · AGENTS.md · unresolved source {lost[:12]}")

    def test_a_selected_member_whose_body_is_not_held_is_named_and_is_not_installed(self):
        me = self.person.scope
        self.launcher(scope=me)
        source, revision = self.authored(me, RULES)
        bare, bare_rev = self.authored(me, {"notes/bare.md": b"bare\n"}, held=False)
        self.placed(self.collection(me, "instructions", [self.entry(source, revision),
                                                          self.entry(bare, bare_rev)]))
        frames = self.drive("enter")
        self.assertEqual(self.marks(frames[0], "positions.personal.instructions")[:2],
                         ("partial", "selected"))
        self.assertEqual(self.element(frames[0], "positions.personal.instructions")["label"],
                         "개인 지침 · AGENTS.md · 본문 없음 notes/bare.md")
        self.assertEqual(self.element(frames[1], "detail.personal.instructions")["label"],
                         "개인 지침 · AGENTS.md · 본문 없음 notes/bare.md · 원본 · "
                         "일부 원본을 쓸 수 없음")

    def test_a_position_names_only_the_members_its_collection_selects(self):
        me = self.person.scope
        self.launcher(scope=me)
        source, revision = self.authored(me, {"rules/not-selected.md": b"no\n",
                                              "rules/selected.md": b"yes\n"})
        self.placed(self.collection(me, "instructions", [self.entry(
            source, revision, [unit("rules/selected.md")])]))
        frame = self.drive()[0]
        self.assertEqual(self.marks(frame, "positions.personal.instructions")[:2],
                         ("installed", "selected"))
        self.assertEqual(self.element(frame, "positions.personal.instructions")["label"],
                         "개인 지침 · rules/selected.md")

    def test_a_knowledge_position_names_only_the_members_its_collection_selects(self):
        me = self.person.scope
        self.launcher(scope=me)
        source, revision = self.authored(me, {"notes/not-selected.md": b"no\n",
                                              "notes/selected.md": b"yes\n"}, role="knowledge")
        self.placed(self.collection(me, "knowledge", [self.entry(
            source, revision, [unit("notes/selected.md")])]))
        frame = self.drive()[0]
        self.assertEqual(self.element(frame, "positions.personal.knowledge")["label"],
                         "개인 지식 · notes/selected.md")

    def test_a_collection_none_of_whose_selected_bodies_is_held_is_missing(self):
        me = self.person.scope
        self.launcher(scope=me)
        source, revision = self.authored(me, {"rules/not-selected.md": b"no\n",
                                              "rules/selected.md": b"yes\n"}, held=False)
        self.placed(self.collection(me, "instructions", [self.entry(
            source, revision, [unit("rules/selected.md")])]))
        frame = self.drive()[0]
        self.assertEqual(self.marks(frame, "positions.personal.instructions")[:2],
                         ("missing", "selected"))
        self.assertEqual(self.element(frame, "positions.personal.instructions")["label"],
                         "개인 지침 · 본문 없음 rules/selected.md")

    def test_a_suggested_source_none_of_whose_bodies_is_held_is_missing(self):
        me = self.person.scope
        self.launcher(scope=me)
        self.authored(me, RULES, held=False)
        frame = self.drive()[0]
        self.assertEqual(self.marks(frame, "positions.personal.instructions")[:2],
                         ("missing", "suggested"))
        self.assertEqual(self.element(frame, "positions.personal.instructions")["label"],
                         "개인 지침 · 본문 없음 AGENTS.md")

    def test_each_effect_is_drawn_on_the_line_of_what_has_it(self):
        self.launcher()
        frame = self.drive()[0]
        drawn = {element["element_id"]: tui.drawn(element, "ko") for element in frame["elements"]}
        self.assertTrue(drawn["execution.tool"].endswith(" · 모델 호출"), drawn)
        self.assertTrue(drawn["execution.permissions"].endswith(" · 권한 요청"), drawn)
        self.assertTrue(drawn["action.start"].endswith(" · 파일 변경 · 모델 호출"), drawn)

    def test_a_collection_nothing_of_which_resolves_is_missing_and_names_it(self):
        # Read as composition reads an entry: a source or revision not held, a declared member
        # its revision lacks, and a source of another role all fail to resolve.
        me = self.person.scope
        self.launcher(scope=me)
        source, revision = self.authored(me, RULES)
        notes, noted = self.authored(me, NOTES, role="knowledge")
        lost = bench.ident("src")
        self.placed(self.collection(me, "instructions", [
            self.entry(lost, "6" * 64), self.entry(source, revision, [unit("absent.md")]),
            self.entry(notes, noted)]))
        frame = self.drive()[0]
        self.assertEqual(self.marks(frame, "positions.personal.instructions"),
                         ("missing", "selected", ["›", "[x]"]))
        self.assertEqual(self.element(frame, "positions.personal.instructions")["label"],
                         f"개인 지침 · 쓸 수 없는 원본 {lost[:12]} 외 2개")

    def test_a_source_registered_with_no_accepted_revision_is_configured(self):
        me = self.person.scope
        self.launcher(scope=me)
        registered = self.register(home(self.person, bench.ident("src")))
        self.assertEqual(registered["result"]["outcome"]["stage"], "committed", gaps(registered))
        frame = self.drive()[0]
        self.assertEqual(self.marks(frame, "positions.personal.knowledge"),
                         ("configured", "none", ["[-]", "(선택 불가)"]))
        self.assertEqual(self.element(frame, "positions.personal.knowledge")["label"],
                         "개인 지식 · 확정된 판 없음")
        self.assertEqual(self.focus(frame), "field.note")

    def test_space_makes_an_uncollected_position_the_person_s_choice(self):
        me = self.person.scope
        self.launcher(scope=me)
        self.authored(me, RULES)
        self.authored(me, NOTES, role="knowledge")
        frames = self.drive("space", "space", "down", "space", "down", "space")
        instructions = "positions.personal.instructions"
        self.assertEqual(self.marks(frames[1], instructions)[1:], ("none", ["›", "[ ]"]))
        self.assertEqual(self.marks(frames[2], instructions)[1:], ("selected", ["›", "[x]"]))
        self.assertEqual(self.marks(frames[4], "positions.personal.knowledge")[1:],
                         ("selected", ["›", "[x]"]))
        # Down from the last position with something to choose stays on it.
        self.assertEqual(self.marks(frames[6], "positions.personal.knowledge")[1:],
                         ("none", ["›", "[ ]"]))
        self.assertEqual(self.marks(frames[6], "positions.personal.memory")[1:],
                         ("none", ["[-]", "(선택 불가)"]))
        for frame in frames:
            self.assertEqual(self.element(frame, "execution.tool")["selection"], "suggested")
        self.assertEqual(self.element(frames[1], "help.keys")["label"],
                         "Tab 이동 · ↑↓ 자료 · Space 선택 · ←→ 변경 · Enter 열기·시작 · Esc 뒤로")

    def test_the_keys_name_space_only_where_a_position_can_change(self):
        me = self.person.scope
        self.launcher(scope=me)
        self.assertEqual(self.element(self.drive()[0], "help.keys")["label"],
                         "Tab 이동 · ←→ 변경 · Enter 열기·시작 · Esc 뒤로")
        source, revision = self.authored(me, RULES)
        self.placed(self.collection(me, "instructions", [self.entry(source, revision)]))
        self.assertEqual(self.element(self.drive()[0], "help.keys")["label"],
                         "Tab 이동 · ↑↓ 자료 · ←→ 변경 · Enter 열기·시작 · Esc 뒤로")

    def test_the_keys_name_the_arrows_changing_a_setting_only_with_a_start(self):
        self.offer_at("host_launcher", self.route("use"))
        self.assertEqual(self.element(self.drive()[0], "help.keys")["label"],
                         "Enter 열기·시작 · Esc 뒤로")

    def test_the_tool_changes_only_on_the_tool_and_leaves_the_positions(self):
        me = self.person.scope
        claude, codex = self.launcher(scope=me, hosts=("claude-code", "codex"))
        self.authored(me, NOTES, role="knowledge")
        frames = self.drive("right", "down", "space", "tab", "tab", "right", "right", "left")
        self.assertEqual(self.element(frames[1], "execution.tool")["value"], "Claude Code")
        tool = self.element(frames[6], "execution.tool")
        self.assertEqual((tool["value"], tool["selection"], tool["marks"]),
                         ("Codex CLI", "selected", ["›"]))
        self.assertEqual(self.element(frames[6], "action.start")["refers_to"]["route_id"],
                         codex["route_id"])
        self.assertEqual(self.element(frames[7], "execution.tool")["value"], "Claude Code")
        self.assertEqual(self.element(frames[8], "execution.tool")["value"], "Codex CLI")
        for frame in frames[3:]:
            self.assertEqual(self.marks(frame, "positions.personal.knowledge")[1], "selected")
        self.assertEqual(self.element(frames[0], "help.keys")["label"],
                         "Tab 이동 · ↑↓ 자료 · Space 선택 · ←→ 변경 · Enter 열기·시작 · Esc 뒤로")
        for frame in frames:
            self.assertEqual(self.element(frame, "execution.permissions")["value"],
                             "host_settings")
        self.assertEqual(claude["route_id"],
                         self.element(frames[0], "action.start")["refers_to"]["route_id"])


class Moving(Entering):
    def test_focus_starts_on_the_first_position_there_is_something_to_choose_at(self):
        me = self.person.scope
        self.launcher()
        self.assertEqual(self.focus(self.drive()[0]), "field.note")
        self.authored(me, NOTES, role="knowledge")
        self.assertEqual(self.focus(self.drive()[0]), "positions.personal.knowledge")

    def test_tab_moves_through_the_stops_and_wraps(self):
        self.launcher()
        frames = self.drive("tab", "tab", "tab", "tab", "back_tab", "back_tab")
        self.assertEqual([self.focus(f) for f in frames],
                         ["field.note", "execution.permissions", "action.start", "field.note",
                          "execution.permissions", "field.note", "action.start"])

    def test_the_tool_is_a_stop_only_when_it_has_an_alternative(self):
        self.launcher(hosts=("claude-code", "codex"))
        frames = self.drive("tab", "tab", "tab", "tab")
        self.assertEqual([self.focus(f) for f in frames[1:]],
                         ["execution.tool", "execution.permissions", "action.start",
                          "field.note"])

    def test_back_tab_from_a_position_goes_to_the_stop_before_it(self):
        me = self.person.scope
        self.launcher(scope=me)
        self.authored(me, RULES)
        frames = self.drive("back_tab")
        self.assertEqual(self.focus(frames[0]), "positions.personal.instructions")
        self.assertEqual(self.focus(frames[1]), "action.start")

    def test_the_arrows_move_through_the_positions_with_something_to_choose_from_either_end(self):
        me = self.person.scope
        self.launcher()
        self.authored(me, RULES)
        self.authored(me, NOTES, role="memory")
        frames = self.drive("up", "down", "down", "tab", "down", "tab", "up")
        self.assertEqual([self.focus(f) for f in frames],
                         ["positions.personal.instructions", "positions.personal.instructions",
                          "positions.personal.memory", "positions.personal.memory",
                          "field.note", "positions.personal.instructions", "field.note",
                          "positions.personal.memory"])

    def test_with_nothing_to_choose_the_arrows_move_nothing_and_are_not_named(self):
        self.launcher()
        frames = self.drive("down", "up")
        self.assertEqual([self.focus(f) for f in frames], ["field.note"] * 3)
        self.assertNotIn("↑↓", self.element(frames[0], "help.keys")["label"])

    def test_keys_with_nothing_to_do_change_nothing(self):
        self.launcher()
        frames = self.drive("home", "page_up", "page_down", "backspace", "left", "enter")
        for frame in frames[1:]:
            self.assertEqual(frame["elements"], frames[0]["elements"])
        self.assertEqual(self.sent, [])


class Views(Entering):
    def test_enter_opens_a_position_s_detail_and_escape_returns_to_it_as_it_was(self):
        me = self.person.scope
        self.launcher(scope=me)
        self.authored(me, RULES)
        self.authored(me, NOTES, role="knowledge")
        frames = self.drive("down", "enter", "tab", "down", "escape")
        detail = frames[2]
        target = {"ref": "position", "view": "original",
                  "position": {"scope": me, "role": "knowledge"}}
        self.assertEqual((detail["view"]["view"], detail["view"]["target"],
                          detail["view"]["return_view"]), ("w02", target, "w01"))
        self.assertEqual(self.ids(detail), ["context.location", "detail.personal.knowledge",
                                            "help.keys"])
        self.assertEqual(self.focus(detail), "detail.personal.knowledge")
        self.assertEqual(self.element(detail, "detail.personal.knowledge")["state"],
                         "not_checked")
        self.assertEqual(self.element(detail, "help.keys")["label"], "Enter 시작 · Esc 뒤로")
        # Neither Tab nor the arrows move anything on a detail.
        for after in (3, 4):
            self.assertEqual(frames[after], {**detail, "after": after})
        self.assertEqual(frames[5]["view"], frames[1]["view"])
        self.assertEqual(frames[5]["elements"], frames[1]["elements"])

    def test_enter_on_a_detail_starts_from_the_w01_under_it(self):
        me = self.person.scope
        self.launcher(scope=me)
        rules, revision = self.authored(me, RULES)
        frames = self.drive({"input": "text", "text": "메모"}, "enter", "enter")
        self.assertEqual(frames[2]["view"]["view"], "w02")
        started = frames[3]
        self.assertEqual(started["view"]["view"], "w01")
        self.assertNotIn("target", started["view"])
        self.assertNotIn("return_view", started["view"])
        self.assertEqual(self.focus(started), "action.start")
        self.assertEqual(len(self.sent), 1)
        sealed, carried = self.sent[0]
        self.assertEqual(started["dispatched"], [sealed["request_id"]])
        self.assertEqual(carried[0]["basis"]["source_pins"],
                         [{"source_id": rules, "revision_digest": revision}])
        self.assertEqual(self.element(started, "action.start")["state"], "pending")

    def test_a_detail_with_nothing_to_start_names_no_enter_and_enter_does_nothing(self):
        me = self.person.scope
        self.offer_at("host_launcher", self.route("use"))
        self.authored(me, RULES)
        frames = self.drive("enter", "enter")
        self.assertEqual(frames[1]["view"]["view"], "w02")
        self.assertEqual(self.element(frames[1], "help.keys")["label"], "Esc 뒤로")
        self.assertEqual(frames[2], {**frames[1], "after": 2})
        self.assertEqual(self.sent, [])

    def test_escape_on_the_base_w01_opens_the_hub_over_it_and_its_job_returns(self):
        self.launcher()
        frames = self.drive("tab", "escape", "enter")
        hub = frames[2]
        self.assertEqual((hub["view"]["view"], hub["view"]["return_view"]), ("hub", "w01"))
        self.assertEqual(self.ids(hub), ["context.location", "job.prepare", "help.keys"])
        self.assertEqual(self.focus(hub), "job.prepare")
        self.assertEqual(frames[3]["view"], frames[1]["view"])
        self.assertEqual(frames[3]["elements"], frames[1]["elements"])

    def test_the_studio_hub_opens_the_hub_and_its_job_opens_w01_over_it(self):
        team = {"layer": "team", "team_id": bench.ident("tem")}
        self.launcher(scope=team, entrance="studio_hub")
        frames = self.drive("down", "enter", "escape", "enter", entrance="studio_hub")
        self.assertEqual(frames[0]["view"], {"view": "hub", "selected_scope": team,
                                             "origin": {"name": "studio_hub",
                                                        "root_origin": "owner"},
                                             "missing_bodies": []})
        self.assertEqual(self.element(frames[0], "help.keys")["label"], "Enter 열기·시작")
        self.assertEqual(self.focus(frames[1]), "job.prepare")
        opened = frames[2]
        self.assertEqual((opened["view"]["view"], opened["view"]["return_view"]), ("w01", "hub"))
        self.assertEqual(self.focus(opened), "field.note")
        self.assertEqual(frames[3]["view"], frames[0]["view"])
        self.assertEqual(self.focus(frames[4]), "field.note")

    def test_a_link_opens_w01_at_its_target_and_escape_clears_it(self):
        start = self.launcher(entrance="work_link")[0]
        target = {"ref": "route", "route_id": start["route_id"]}
        frames = self.drive("escape", entrance="work_link",
                            link={"target": target, "return_view": "w01"})
        self.assertEqual((frames[0]["view"]["target"], frames[0]["view"]["return_view"]),
                         (target, "w01"))
        self.assertEqual(self.focus(frames[0]), "action.start")
        self.assertNotIn("target", frames[1]["view"])
        self.assertNotIn("return_view", frames[1]["view"])
        self.assertEqual(self.focus(frames[1]), "action.start")
        self.assertEqual(frames[1]["view"]["view"], "w01")

    def test_a_link_to_a_route_not_offered_focuses_the_first_position_to_choose_at(self):
        self.launcher(entrance="work_link")
        self.authored(self.person.scope, RULES)
        frames = self.drive(entrance="work_link", link={
            "target": {"ref": "route", "route_id": bench.ident("rte")}, "return_view": "hub"})
        self.assertEqual(self.focus(frames[0]), "positions.personal.instructions")

    def test_escape_from_a_link_returning_to_the_hub_opens_the_hub(self):
        start = self.launcher(entrance="work_link")[0]
        frames = self.drive("escape", entrance="work_link", link={
            "target": {"ref": "route", "route_id": start["route_id"]}, "return_view": "hub"})
        self.assertEqual(frames[1]["view"]["view"], "hub")
        self.assertEqual(self.focus(frames[1]), "job.prepare")


class Starting(Entering):
    def test_enter_on_the_start_dispatches_one_compose_for_the_basis_with_the_note(self):
        start = self.launcher()[0]
        me = self.person.scope
        rules, revision = self.authored(me, RULES)
        self.authored(me, NOTES, role="knowledge")
        frames = self.drive("tab", {"input": "text", "text": "다음 단계"}, "tab", "tab", "enter",
                            "enter", "up", "up", "space")
        self.assertEqual(len(self.sent), 1)
        sealed, carried = self.sent[0]
        asked = {"kind": "preparation_request", "schema": 1,
                 "basis": {"from": "ad_hoc", "scopes": [self.repository, me],
                           "source_pins": [{"source_id": rules, "revision_digest": revision}]},
                 "declared_operation": {"action": "use", "name": "session.routing.activate"}}
        self.assertEqual(carried, [asked])
        row = journal.OPERATIONS[COMPOSE]
        self.assertEqual({key: value for key, value in sealed.items() if key != "request_id"},
                         {"kind": "operation_request", "schema": 1, "operation": COMPOSE,
                          "effect_class": row["effect"], "action": row["action"],
                          "actor": self.person.actor,
                          "local_access_generation":
                              self.drive_request["local_access_generation"],
                          "owner": me, "target": {"resource_id": self.person.principal},
                          "policy_digests": [], "control_digests": [], "proof_digests": [],
                          "payload_digest": canonical.digest_of(asked), "rationale": "다음 단계"})
        self.assertRegex(sealed["request_id"], r"\Areq_[0-9a-f]{32}\Z")
        sent = frames[5]
        self.assertEqual(sent["dispatched"], [sealed["request_id"]])
        self.assertEqual(sent["calls"], [{"operation": COMPOSE, "reads": "bodies",
                                          "request_digest": canonical.digest_of(sealed)}])
        begin = self.element(sent, "action.start")
        self.assertEqual((begin["executing"], begin["state"]), (True, "pending"))
        result = self.element(sent, "result.start")
        self.assertEqual((result["role"], result["state"], result["refers_to"]),
                         ("result", "pending",
                          {"ref": "request", "request_id": sealed["request_id"]}))
        self.assertEqual(self.ids(sent)[-2:], ["help.keys", "result.start"])
        for frame in frames[6:]:
            self.assertEqual((frame["dispatched"], frame["calls"]), ([], []))
            self.assertEqual(self.element(frame, "action.start")["state"], "pending")
        # Space once a start is sent changes nothing.
        self.assertEqual(self.marks(frames[9], "positions.personal.instructions")[1:],
                         ("suggested", ["›", "[x]", "(제안)"]))
        self.assertEqual(start["route_id"], begin["refers_to"]["route_id"])

    def test_the_tool_and_the_permissions_stay_once_the_start_is_sent(self):
        self.launcher(hosts=("claude-code", "codex"))
        frames = self.drive("tab", "tab", "tab", "enter", "back_tab", "right", "back_tab",
                            "right")
        self.assertEqual(self.focus(frames[6]), "execution.permissions")
        self.assertEqual(self.element(frames[6], "execution.permissions")["value"],
                         "host_settings")
        self.assertEqual(self.element(frames[6], "execution.permissions")["selection"],
                         "suggested")
        self.assertEqual(self.focus(frames[8]), "execution.tool")
        self.assertEqual(self.element(frames[8], "execution.tool")["value"], "Claude Code")
        self.assertEqual(self.element(frames[8], "execution.tool")["selection"], "suggested")

    def test_the_arrows_change_the_permissions_only_while_they_are_focused(self):
        self.launcher(hosts=("claude-code", "codex"))
        frames = self.drive("right", "tab", "tab", "right", "right", "left", locale="en")
        for frame in frames[:4]:
            self.assertEqual(self.element(frame, "execution.permissions")["value"],
                             "host_settings")
        self.assertEqual(self.element(frames[2], "execution.tool")["value"], "Claude Code")
        skipped = self.element(frames[4], "execution.permissions")
        self.assertEqual((skipped["value"], skipped["selection"], skipped["marks"],
                          skipped["label"]),
                         ("skip_confirmations", "selected", ["›"],
                          "Permissions · run without confirmations"))
        self.assertNotIn("effects", skipped)
        again = self.element(frames[5], "execution.permissions")
        self.assertEqual((again["value"], again["selection"], again["marks"], again["effects"]),
                         ("host_settings", "selected", ["›"], ["permission_request"]))
        self.assertEqual(self.element(frames[6], "execution.permissions")["value"],
                         "skip_confirmations")
        self.assertEqual(self.element(frames[6], "execution.tool")["value"], "Claude Code")

    def test_a_start_that_includes_nothing_reads_nothing_and_carries_no_note(self):
        self.launcher()
        frames = self.drive("tab", "tab", "enter")
        sealed, carried = self.sent[0]
        self.assertEqual(carried[0]["basis"]["source_pins"], [])
        self.assertNotIn("rationale", sealed)
        self.assertEqual(frames[3]["calls"][0]["reads"], "nothing")

    def test_a_position_the_person_excluded_is_not_pinned(self):
        me = self.person.scope
        self.launcher(scope=me)
        self.authored(me, RULES)
        self.drive("space", "tab", "tab", "tab", "enter")
        self.assertEqual(self.sent[0][1][0]["basis"]["source_pins"], [])

    def test_a_collection_the_composition_applies_is_not_pinned_again(self):
        me = self.person.scope
        self.launcher(scope=me)
        source, revision = self.authored(me, RULES)
        self.placed(self.collection(me, "instructions", [self.entry(source, revision)]))
        frames = self.drive("tab", "tab", "tab", "enter")
        self.assertEqual(self.sent[0][1][0]["basis"]["source_pins"], [])
        self.assertEqual(frames[4]["calls"][0]["reads"], "bodies")

    def test_a_note_longer_than_a_rationale_holds_is_not_sent(self):
        self.launcher()
        long = [{"input": "text", "text": "a" * 1000}] * 2
        frames = self.drive(*long, {"input": "text", "text": "b"}, "tab", "tab", "enter",
                            "back_tab", "back_tab", "backspace", "tab", "tab", "enter")
        self.assertEqual(self.element(frames[6], "action.start")["state"], "blocked")
        self.assertEqual(self.element(frames[6], "action.start")["executing"], False)
        self.assertEqual(self.focus(frames[6]), "action.start")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][0]["rationale"], "a" * 2000)

    def test_space_in_the_note_is_a_space_and_selects_nothing(self):
        me = self.person.scope
        self.launcher(scope=me)
        self.authored(me, RULES)
        frames = self.drive("tab", {"input": "text", "text": "a"}, "space",
                            {"input": "text", "text": "b"})
        self.assertEqual(self.element(frames[4], "field.note")["value"], "a b")
        for frame in frames:
            self.assertEqual(self.marks(frame, "positions.personal.instructions")[1],
                             "suggested")

    def authored_in_checkout(self) -> tuple[Checkout, str, str]:
        """The repository bound from a checkout whose AGENTS.md is admitted as its
        repository-authored Instructions: the checkout, the source and its revision."""
        checkout = Checkout(self.scratch)
        checkout.write("AGENTS.md", b"# Rules\n")
        checkout.commit()
        where = self.repository["repository_id"]
        payload = {"kind": "repository_binding", "schema": 1, "repository_id": where,
                   "relation": {"how": "clone"}}
        with contextlib.chdir(checkout.path):
            self.run_with(sources.repository_bind, bench.request(
                self.person, "repository.bind", where, payload), [payload], now=INSTANT)
            source, revision = self.authored(self.repository, {"AGENTS.md": b"# Rules\n"},
                                             mode="repository_authored", held=False)
        return checkout, source, revision

    def test_a_repository_document_changed_since_admitted_is_named_before_the_start(self):
        checkout, _, _ = self.authored_in_checkout()
        self.launcher()
        self.assertEqual(self.element(self.drive()[0], "positions.repository.instructions")
                         ["label"], "레포 지침 · AGENTS.md")
        checkout.write("AGENTS.md", b"# Rules\nedited\n")
        frame = self.drive()[0]
        self.assertEqual(self.marks(frame, "positions.repository.instructions")[:2],
                         ("missing", "suggested"))
        self.assertEqual(self.element(frame, "positions.repository.instructions")["label"],
                         "레포 지침 · 등록 뒤 바뀜 AGENTS.md")

    def test_a_start_refused_because_a_repository_document_moved_is_drawn_with_next_steps(self):
        self.launcher()
        for codes, label in ((["working_bytes_moved"],
                              "시작하지 못함 · 레포 문서가 등록 뒤 바뀜 · 다시 등록"),
                             ([], "시작하지 못함 · activating was refused")):
            with self.subTest(codes=codes):
                entry = self.holding("tab", "tab", "enter")
                entry.answered(entry.started, "unavailable", "activating was refused", codes)
                self.assertEqual(self.element(entry.frame(5), "result.start")["label"], label)
        entry = self.holding("tab", "tab", "enter")
        with self.assertRaises(ValueError):
            entry.answered(entry.started, "unknown", codes=["working_bytes_moved"])

    def test_the_refusal_names_space_only_where_the_changed_position_can_be_left_out(self):
        checkout, source, revision = self.authored_in_checkout()
        self.launcher()
        checkout.write("AGENTS.md", b"# Rules\nedited\n")
        refused = self.refused_now()
        self.assertEqual(refused, tui.CATALOG["ko"]["not_started.moved"])
        self.assertEqual(refused,
                         "시작하지 못함 · 레포 문서가 등록 뒤 바뀜 · Space로 빼거나 다시 등록")
        # A collection's position is its recorded choice, which Space does not change.
        self.placed(self.collection(self.repository, "instructions",
                                    [self.entry(source, revision)]))
        frames = self.drive("space")
        for frame in frames:
            self.assertEqual(self.element(frame, "positions.repository.instructions")["label"],
                             "레포 지침 · 등록 뒤 바뀜 AGENTS.md")
            self.assertEqual(self.marks(frame, "positions.repository.instructions")[1],
                             "selected")
        self.assertEqual(self.refused_now(), "시작하지 못함 · 레포 문서가 등록 뒤 바뀜 · 다시 등록")

    def refused_now(self) -> str:
        """The start's result on an entry opened now, after the owner refused its start
        `working_bytes_moved`."""
        entry = self.holding()
        entry.begin()
        entry.answered(entry.started, "unavailable", "activating was refused",
                       ["working_bytes_moved"])
        return self.element(entry.frame(1), "result.start")["label"]

    def test_a_refused_start_opens_the_choices_and_the_start_again(self):
        me = self.person.scope
        self.launcher(scope=me, hosts=("claude-code", "codex"))
        rules, revision = self.authored(me, RULES)
        entry = self.holding("tab", "tab", "tab", "tab", "enter")
        first = entry.started
        self.assertEqual(self.sent[0][1][0]["basis"]["source_pins"],
                         [{"source_id": rules, "revision_digest": revision}])
        entry.answered(first, "unavailable", "activating was refused", ["working_bytes_moved"])
        for given in ("up", "space", "tab", "tab", "right", "tab", "tab"):
            entry.press({"input": "key", "key": given})
        frame = entry.frame(12)
        self.assertEqual(self.marks(frame, "positions.personal.instructions")[1], "none")
        self.assertEqual(self.element(frame, "execution.tool")["value"], "Codex CLI")
        # The refused start stays the result drawn until another is sent.
        self.assertEqual(self.element(frame, "result.start")["state"], "unavailable")
        entry.press({"input": "key", "key": "enter"})
        self.assertEqual(len(self.sent), 2)
        self.assertNotEqual(entry.started, first)
        self.assertEqual(self.sent[1][0]["request_id"], entry.started)
        self.assertEqual(self.sent[1][1][0]["basis"]["source_pins"], [])
        result = self.element(entry.frame(13), "result.start")
        self.assertEqual((result["state"], result["refers_to"]["request_id"]),
                         ("pending", entry.started))

    def test_a_start_pending_or_unknown_holds_the_choices_and_sends_nothing_again(self):
        me = self.person.scope
        self.launcher(scope=me, hosts=("claude-code", "codex"))
        self.authored(me, RULES)
        for answer in (None, "unknown"):
            with self.subTest(answer=answer):
                entry = self.holding("tab", "tab", "tab", "tab", "enter")
                first = entry.started
                if answer:
                    entry.answered(first, answer)
                for given in ("up", "space", "tab", "tab", "right", "tab", "tab", "enter"):
                    entry.press({"input": "key", "key": given})
                frame = entry.frame(13)
                self.assertEqual(self.marks(frame, "positions.personal.instructions")[1],
                                 "suggested")
                self.assertEqual(self.element(frame, "execution.tool")["value"], "Claude Code")
                self.assertEqual((len(self.sent), entry.started), (1, first))

    def test_a_start_refused_for_a_required_body_is_drawn_with_next_steps(self):
        self.launcher()
        for code in ("role_body_unavailable", "object_digest_mismatch"):
            with self.subTest(code=code):
                entry = self.holding("tab", "tab", "enter")
                entry.answered(entry.started, "unavailable", "activating was refused", [code])
                self.assertEqual(self.element(entry.frame(5), "result.start")["label"],
                                 "시작하지 못함 · 필수 지침 본문을 쓸 수 없음 · 선택을 바꾸거나 "
                                 "본문 받기")

    def test_an_answer_handed_over_is_drawn_in_the_start_s_result(self):
        self.launcher()
        entry = self.holding("tab", "tab", "enter")
        entry.answered(entry.started, "unavailable", "activating was refused")
        frame = entry.frame(5)
        result = self.element(frame, "result.start")
        self.assertEqual((result["state"], result["label"]),
                         ("unavailable", "시작하지 못함 · activating was refused"))
        begin = self.element(frame, "action.start")
        self.assertEqual((begin["executing"], "state" in begin), (False, False))
        entry = self.holding("tab", "tab", "enter")
        entry.answered(entry.started, "unknown")
        result = self.element(entry.frame(5), "result.start")
        self.assertEqual((result["state"], result["label"]),
                         ("unknown", tui.CATALOG["ko"]["started"]))

    def test_an_answer_is_one_the_entry_draws_to_a_request_it_dispatched(self):
        self.launcher()
        entry = self.holding("tab", "tab", "enter")
        self.assertIsNotNone(entry.started)
        for state, reason, request_id in (("refused", "no", entry.started),
                                          ("refused", None, entry.started),
                                          ("unavailable", None, entry.started),
                                          ("unknown", "why", entry.started),
                                          ("unknown", None, bench.ident("req")),
                                          ("settled", "expired", entry.started)):
            with self.subTest(state=state, reason=reason), self.assertRaises(ValueError):
                entry.answered(request_id, state, reason)
        self.assertEqual(entry.answers, {})
        idle = self.holding()
        with self.assertRaises(ValueError):
            idle.answered(None, "unknown")

    def test_text_and_paste_go_into_the_note_as_given_and_nowhere_else(self):
        self.launcher()
        frames = self.drive("tab", {"input": "text", "text": "q s"}, "back_tab",
                            {"input": "text", "text": "첫\n"},
                            {"input": "paste", "text": "\x1b[31m"}, "backspace", "tab",
                            {"input": "paste", "text": "x"}, "backspace")
        self.assertEqual(frames[2]["elements"], frames[1]["elements"])
        self.assertEqual([self.element(f, "field.note")["value"] for f in frames[4:]],
                         ["첫\n", "첫\n\x1b[31m", "첫\n\x1b[31", "첫\n\x1b[31", "첫\n\x1b[31",
                          "첫\n\x1b[31"])
        self.assertEqual(self.sent, [])


class Unknown(Entering):
    def unknown_start(self, note: str = "다음: 재시도") -> tuple[dict, dict, str]:
        """A start composed with a note and activated with no answer, and the history read
        after it: the preparation, the activation's answer and the history request's digest."""
        self.launcher()
        basis = self.ask([self.repository, self.person.scope])
        self.prepared(basis, rationale="이전 메모")
        self.history(self.repository)
        prepared = self.prepared(basis, rationale=note)
        activated = self.activate(prepared)
        self.history(self.repository)
        held = self.bench.store().read("SELECT request_digest FROM requests WHERE operation = ? "
                                       "ORDER BY position DESC", (HISTORY,))
        return prepared, activated, held[0][0]

    def test_an_unknown_start_is_the_draft_and_its_check_is_focused(self):
        prepared, activated, history = self.unknown_start()
        draft = activated["result"]["request_id"]
        frame = self.drive()[0]
        self.assertEqual(self.ids(frame)[:4], ["context.location", "context.checkpoint",
                                               "result.draft", "action.check"])
        self.assertEqual(frame["view"]["draft_request_id"], draft)
        self.assertEqual(self.focus(frame), "action.check")
        self.assertEqual(self.element(frame, "context.checkpoint")["refers_to"],
                         {"ref": "record", "digest": canonical.digest_of(prepared)})
        self.assertEqual(self.element(frame, "context.checkpoint")["label"],
                         "이전 메모 · 다음: 재시도 (기록 당시)")
        found = self.element(frame, "result.draft")
        self.assertEqual((found["state"], found["refers_to"]),
                         ("unknown", {"ref": "request", "request_id": draft}))
        self.assertEqual(found["label"], "지난 시작의 결과를 아직 모름 · 이 기기만 확인함")
        self.assertEqual(frame["calls"], [{"operation": HISTORY, "reads": "inventory",
                                           "request_digest": history}])

    def test_the_check_dispatches_one_query_and_the_start_dispatches_nothing(self):
        _, activated, _ = self.unknown_start()
        draft = activated["result"]["request_id"]
        frames = self.drive("enter", "enter", "tab", "tab", "tab", "enter")
        self.assertEqual(len(self.sent), 1)
        sealed, carried = self.sent[0]
        asked = {"kind": "operation_query", "schema": 1, "request_id": draft}
        self.assertEqual(carried, [asked])
        self.assertEqual((sealed["operation"], sealed["target"], sealed["payload_digest"]),
                         ("operation.query", {"resource_id": draft}, canonical.digest_of(asked)))
        self.assertEqual(frames[1]["calls"], [{"operation": "operation.query", "reads": "nothing",
                                               "request_digest": canonical.digest_of(sealed)}])
        self.assertEqual(frames[1]["dispatched"], [sealed["request_id"]])
        for frame in frames[1:]:
            check = self.element(frame, "action.check")
            self.assertEqual((check["executing"], check["state"]), (True, "pending"))
        self.assertEqual(self.focus(frames[4]), "execution.permissions")
        self.assertEqual(self.focus(frames[5]), "action.start")
        held = frames[6]
        self.assertEqual(self.element(held, "action.start")["state"], "blocked")
        self.assertEqual(self.focus(held), "action.check")
        self.assertEqual((held["dispatched"], held["calls"]), ([], []))
        self.assertNotIn("result.start", self.ids(held))

    def test_the_check_s_answer_is_drawn_in_the_unknown_start_it_was_for(self):
        self.unknown_start()
        entry = self.holding("enter")
        entry.answered(entry.checking, "unknown")
        frame = entry.frame(2)
        draft = self.element(frame, "result.draft")
        self.assertEqual((draft["state"], draft["label"]),
                         ("unknown", "지난 시작의 결과를 아직 모름 · 이 기기만 확인함"))
        check = self.element(frame, "action.check")
        self.assertEqual((check["executing"], "state" in check), (False, False))
        entry = self.holding("enter")
        entry.answered(entry.checking, "unavailable", "request_not_held")
        draft = self.element(entry.frame(2), "result.draft")
        self.assertEqual((draft["state"], draft["label"]),
                         ("unavailable", "확인하지 못함 · request_not_held"))

    def test_a_check_answered_without_settling_its_start_can_be_asked_again(self):
        self.unknown_start()
        for state, reason in (("unknown", None), ("unavailable", "request_not_held")):
            with self.subTest(state=state):
                entry = self.holding("enter")
                first = entry.checking
                entry.answered(first, state, reason)
                entry.press({"input": "key", "key": "enter"})
                self.assertEqual([sealed["operation"] for sealed, _ in self.sent],
                                 ["operation.query", "operation.query"])
                self.assertNotEqual(entry.checking, first)
                check = self.element(entry.frame(2), "action.check")
                self.assertEqual((check["executing"], check["state"]), (True, "pending"))
        entry = self.holding("enter")
        entry.answered(entry.checking, "settled", "expired")
        entry.press({"input": "key", "key": "enter"})
        self.assertEqual(len(self.sent), 1)

    def test_a_check_that_finds_its_start_settled_draws_it_so_and_lets_the_next_start_run(self):
        self.unknown_start()
        for stage, state, key in (("expired", "unavailable", "settled.expired"),
                                  ("committed", "delivered", "settled.committed"),
                                  ("refused", "unavailable", "settled.other")):
            with self.subTest(stage=stage):
                entry = self.holding("tab", "tab", "tab", "enter", "enter")
                self.assertEqual(self.element(entry.frame(5), "action.start")["state"],
                                 "blocked")
                entry.answered(entry.checking, "settled", stage)
                frame = entry.frame(6)
                draft = self.element(frame, "result.draft")
                self.assertEqual((draft["state"], draft["label"]),
                                 (state, tui.CATALOG["ko"][key].format(stage=stage)))
                self.assertNotIn("state", self.element(frame, "action.start"))
                for given in ("tab", "tab", "tab", "enter"):
                    entry.press({"input": "key", "key": given})
                self.assertEqual([sealed["operation"] for sealed, _ in self.sent],
                                 ["operation.query", "preparation.compose"])
                self.assertIsNotNone(entry.started)

    def test_a_settled_start_is_no_longer_signalled_on_the_hub(self):
        self.unknown_start()
        entry = self.holding("enter")
        entry.answered(entry.checking, "settled", "expired")
        entry.press({"input": "key", "key": "escape"})
        hub = entry.frame(2)
        self.assertEqual(self.ids(hub), ["context.location", "job.prepare", "help.keys"])
        self.assertEqual(self.focus(hub), "job.prepare")

    def test_only_the_check_is_answered_settled_and_only_at_a_stage_no_longer_pending(self):
        self.unknown_start()
        entry = self.holding("enter")
        for request_id, stage in ((entry.checking, None), (entry.checking, "unknown"),
                                  (entry.checking, "partial"), (entry.checking, "executing"),
                                  (bench.ident("req"), "expired")):
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                entry.answered(request_id, "settled", stage)
        self.assertEqual(entry.answers, {})

    def test_the_history_read_is_cited_once_by_the_first_frame_that_shows_it(self):
        self.unknown_start()
        frames = self.drive("escape", "enter", "tab")
        self.assertEqual(len(frames[0]["calls"]), 1)
        for frame in frames[1:]:
            self.assertEqual(frame["calls"], [])

    def test_the_hub_signals_the_unknown_start_and_enter_returns_to_its_check(self):
        _, activated, _ = self.unknown_start()
        draft = activated["result"]["request_id"]
        frames = self.drive("tab", "escape", "enter")
        hub = frames[2]
        self.assertEqual(self.ids(hub), ["context.location", "signal.draft", "job.prepare",
                                         "help.keys"])
        signal = self.element(hub, "signal.draft")
        self.assertEqual((signal["marks"], signal["state"], signal["refers_to"]),
                         (["›", "?"], "unknown", {"ref": "request", "request_id": draft}))
        self.assertEqual(hub["view"]["draft_request_id"], draft)
        self.assertEqual(frames[3]["view"]["view"], "w01")
        self.assertEqual(self.focus(frames[3]), "action.check")

    def test_tab_from_a_position_goes_to_the_next_stop_after_the_check(self):
        self.unknown_start()
        self.authored(self.person.scope, RULES)
        frames = self.drive("down", "tab", "back_tab", "back_tab")
        self.assertEqual([self.focus(f) for f in frames[1:]],
                         ["positions.personal.instructions", "field.note", "action.check",
                          "action.start"])

    def test_enter_on_a_detail_while_the_unknown_start_holds_back_returns_to_its_check(self):
        self.unknown_start()
        self.authored(self.person.scope, RULES)
        frames = self.drive("down", "enter", "enter")
        held = frames[3]
        self.assertEqual(held["view"]["view"], "w01")
        self.assertEqual(self.element(held, "action.start")["state"], "blocked")
        self.assertEqual(self.focus(held), "action.check")
        self.assertEqual((held["dispatched"], self.sent), ([], []))

    def test_the_history_of_another_scope_is_not_this_entry_s(self):
        self.launcher()
        prepared = self.prepared(self.ask([self.repository, self.person.scope]), rationale="n")
        self.activate(prepared)
        self.history(self.person.scope)
        frame = self.drive()[0]
        self.assertNotIn("result.draft", self.ids(frame))
        self.assertEqual(frame["calls"], [])

    def test_a_start_the_owner_answered_is_no_draft(self):
        self.launcher()
        prepared = self.prepared(self.ask([self.repository, self.person.scope]))
        self.activate(prepared, entry=commits)
        self.history(self.repository)
        frame = self.drive()[0]
        self.assertNotIn("result.draft", self.ids(frame))
        self.assertNotIn("context.checkpoint", self.ids(frame))
        self.assertEqual(frame["calls"], [])

    def test_a_link_s_draft_is_checked_as_an_unknown_start(self):
        start = self.launcher(entrance="work_link")[0]
        draft = bench.ident("req")
        frame = self.drive(entrance="work_link", link={
            "target": {"ref": "route", "route_id": start["route_id"]},
            "draft_request_id": draft, "return_view": "w01"})[0]
        self.assertEqual(frame["view"]["draft_request_id"], draft)
        self.assertEqual(self.focus(frame), "action.check")
        self.assertEqual(self.element(frame, "result.draft")["state"], "unknown")


class Shown(Entering):
    def test_a_line_wider_than_its_row_is_clipped_and_one_below_the_last_row_is_off_screen(self):
        self.launcher(scope=self.person.scope)
        frames = self.drive({"input": "resize", "columns": 20, "rows": 5})
        self.assertEqual({e["shown"] for e in frames[0]["elements"]}, {"whole"})
        shown = {e["element_id"]: e["shown"] for e in frames[1]["elements"]}
        self.assertEqual(frames[1]["terminal"], {"columns": 20, "rows": 5})
        self.assertEqual(shown["context.location"], "whole")
        self.assertEqual(shown["positions.personal.instructions"], "clipped")
        self.assertEqual(shown["field.note"], "clipped")
        self.assertEqual(shown["execution.tool"], "off_screen")
        self.assertEqual(shown["action.start"], "off_screen")

    def test_the_marks_count_toward_the_line(self):
        self.launcher(scope=self.person.scope)
        memory = self.element(self.drive()[0], "positions.personal.memory")
        columns = tui.cells(" ".join(memory["marks"] + [memory["label"]])) + tui.GUTTER
        frame = self.drive({"input": "resize", "columns": columns - 1, "rows": 24})[1]
        self.assertEqual(self.element(frame, "positions.personal.memory")["shown"], "clipped")
        frame = self.drive({"input": "resize", "columns": columns, "rows": 24})[1]
        self.assertEqual(self.element(frame, "positions.personal.memory")["shown"], "whole")

    def test_a_note_is_clipped_past_three_lines(self):
        self.launcher(scope=self.person.scope)
        room = 40 - tui.GUTTER
        frames = self.drive({"input": "text", "text": "a" * room * 3},
                            {"input": "text", "text": "a"}, terminal=(40, 24), locale="en")
        self.assertEqual(self.element(frames[1], "field.note")["shown"], "whole")
        self.assertEqual(self.element(frames[2], "field.note")["shown"], "clipped")
        rows = {e["element_id"]: e["shown"] for e in self.drive(
            {"input": "text", "text": "a" * room * 3}, terminal=(40, 9),
            locale="en")[1]["elements"]}
        # The permissions start on the first row past the last.
        self.assertNotEqual(rows["execution.tool"], "off_screen")
        self.assertEqual(rows["execution.permissions"], "off_screen")

    def test_a_locale_changes_the_wording_and_the_marks_and_nothing_else(self):
        me = self.person.scope
        self.launcher(scope=me)
        self.authored(me, RULES)
        frames = self.drive({"input": "locale", "locale": "en"})
        self.assertEqual(frames[1]["locale"], "en")
        self.assertEqual(self.element(frames[1], "positions.personal.instructions")["marks"],
                         ["›", "[x]", "(suggested)"])
        self.assertEqual(self.element(frames[1], "action.start")["label"],
                         "Start a new Claude Code session")

        def bare(frame):
            return [{k: v for k, v in e.items() if k not in ("label", "marks")}
                    for e in frame["elements"]]
        self.assertEqual(bare(frames[1]), bare(frames[0]))


class Driving(Entering):
    def test_a_drive_is_a_pure_preview_that_keeps_nothing_it_dispatches(self):
        self.launcher()
        script = {"kind": "surface_script", "schema": 1,
                  "entrance": {"name": "host_launcher", "root_origin": "owner"},
                  "terminal": {"columns": 80, "rows": 24}, "locale": "ko",
                  "inputs": [{"input": "key", "key": key}
                             for key in ("tab", "tab", "enter")]}
        answer = self.run_with(tui.surface_drive,
                               bench.request(self.person, DRIVE, self.person.profile, script),
                               [script], now=LATER)
        self.assertEqual(answer["result"]["outcome"]["stage"], "previewed", gaps(answer))
        trace = answer["returned"][0]
        self.assertEqual({key: trace[key] for key in ("kind", "client", "mode", "at",
                                                      "script_digest")},
                         {"kind": "surface_trace",
                          "client": {"name": "agent-bios-entry", "version": "1"},
                          "mode": {"runs": "real"}, "at": LATER,
                          "script_digest": canonical.digest_of(script)})
        self.assertEqual(len(trace["frames"]), 4)
        self.assertEqual(len(trace["frames"][3]["dispatched"]), 1)
        store = self.bench.store()
        self.assertEqual(store.read("SELECT COUNT(*) FROM requests WHERE operation = ?",
                                    (COMPOSE,))[0][0], 0)


if __name__ == "__main__":
    unittest.main()
