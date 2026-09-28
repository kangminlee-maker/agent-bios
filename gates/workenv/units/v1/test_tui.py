"""The entry model (`workenv.tui`): what an entrance draws from what the owner holds, one frame per
input, and the one request an input dispatches. The conformance runner holds a trace without its
labels (D-20260928-380689), so the wording is held here, against the catalog."""
from __future__ import annotations

import contextlib
import string
import unittest

import bench
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
                 "position.more", "detail"}
        for locale, table in tui.CATALOG.items():
            fill = {"layer": longest(table, "layer."), "role": longest(table, "role."),
                    "action": longest(table, "action."),
                    "coverage": longest(table, "coverage."),
                    "state": longest(table, "state."), "more": "99",
                    "tool": max(tui.TOOLS.values(), key=tui.cells),
                    "choice": longest(table, "permissions.")}
            marks = {"position.empty": ["›", "[x]", table["suggested"]],
                     "position.configured": ["›", "[x]", table["suggested"]],
                     "tool": ["›", table["suggested"]],
                     "permissions": ["›", table["suggested"]]}
            for key, text in table.items():
                if key in named or key.startswith("key."):
                    continue
                line = " ".join([*marks.get(key, ["›"]),
                                 text.format(**{name: fill[name] for name in fields(text)})])
                with self.subTest(locale=locale, key=key):
                    self.assertLessEqual(tui.cells(line), room, line)
            keys = " · ".join(text for key, text in table.items() if key.startswith("key."))
            self.assertLessEqual(tui.cells(keys), room, keys)


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

    def bound(self, branch: str) -> None:
        """The repository bound from a checkout of ORIGIN on the branch."""
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

    def test_a_route_is_qualified_by_its_host_s_latest_probe_now_not_by_the_offer(self):
        claude = self.route(probe=self.probe())
        codex = self.route(probe=self.probe("codex"))
        self.offer_at("host_launcher", claude, codex)
        self.probe("codex", outcome="failed", at=LATER)
        frames = self.drive("tab", "tab", "tab")
        self.assertEqual(self.element(frames[0], "blocker.repository.use")["refers_to"],
                         {"ref": "route", "route_id": codex["route_id"]})
        self.assertEqual(self.element(frames[0], "blocker.repository.use")["label"],
                         tui.CATALOG["ko"]["blocker"].format(layer="레포", action="새 세션",
                                                             tool="Codex CLI"))
        self.assertEqual(self.element(frames[0], "execution.tool")["value"], "Claude Code")
        self.assertEqual(self.focus(frames[3]), "action.start")

    def test_one_start_is_offered_per_host(self):
        self.launcher(hosts=("claude-code", "claude-code"))
        frames = self.drive("tab", "tab", "tab")
        self.assertEqual(self.focus(frames[3]), "action.start")
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
                         ("checked_empty", "none", ["[ ]"]))
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
            state, selection, marks = self.marks(frame, "positions.personal.knowledge")
            self.assertEqual((state, selection, marks[-1:]), ("checked_empty", "none", ["[ ]"]))
        self.assertEqual(self.element(frames[0], "positions.personal.instructions")["marks"],
                         ["›", "[x]"])

    def test_a_source_registered_with_no_accepted_revision_is_configured(self):
        me = self.person.scope
        self.launcher(scope=me)
        registered = self.register(home(self.person, bench.ident("src")))
        self.assertEqual(registered["result"]["outcome"]["stage"], "committed", gaps(registered))
        frames = self.drive("down", "space")
        self.assertEqual(self.marks(frames[2], "positions.personal.knowledge"),
                         ("configured", "none", ["›", "[ ]"]))
        self.assertEqual(self.element(frames[2], "positions.personal.knowledge")["label"],
                         "개인 지식 · 확정된 판 없음")

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
        self.assertEqual(self.marks(frames[6], "positions.personal.memory")[1:],
                         ("none", ["›", "[ ]"]))
        for frame in frames:
            self.assertEqual(self.element(frame, "execution.tool")["selection"], "suggested")
        self.assertEqual(self.element(frames[1], "help.keys")["label"],
                         "Tab 이동 · ↑↓ 자료 · Space 선택 · ←→ 변경 · Enter 열기·시작 · Esc 뒤로")

    def test_the_keys_name_space_only_where_a_position_can_change(self):
        self.launcher(scope=self.person.scope)
        self.assertEqual(self.element(self.drive()[0], "help.keys")["label"],
                         "Tab 이동 · ↑↓ 자료 · ←→ 변경 · Enter 열기·시작 · Esc 뒤로")

    def test_the_keys_name_the_arrows_changing_a_setting_only_with_a_start(self):
        self.offer_at("host_launcher", self.route("use"))
        self.assertEqual(self.element(self.drive()[0], "help.keys")["label"],
                         "↑↓ 자료 · Enter 열기·시작 · Esc 뒤로")

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
    def test_focus_starts_on_the_first_position(self):
        self.launcher()
        self.assertEqual(self.focus(self.drive()[0]), "positions.repository.instructions")

    def test_tab_moves_through_the_stops_and_wraps(self):
        self.launcher()
        frames = self.drive("tab", "tab", "tab", "tab", "back_tab", "back_tab")
        self.assertEqual([self.focus(f) for f in frames],
                         ["positions.repository.instructions", "field.note",
                          "execution.permissions", "action.start", "field.note", "action.start",
                          "execution.permissions"])

    def test_the_tool_is_a_stop_only_when_it_has_an_alternative(self):
        self.launcher(hosts=("claude-code", "codex"))
        frames = self.drive("tab", "tab", "tab", "tab", "tab")
        self.assertEqual([self.focus(f) for f in frames[1:]],
                         ["field.note", "execution.tool", "execution.permissions",
                          "action.start", "field.note"])

    def test_back_tab_from_a_position_goes_to_the_stop_before_it(self):
        self.launcher()
        self.assertEqual(self.focus(self.drive("back_tab")[1]), "action.start")

    def test_the_arrows_move_through_the_positions_and_come_in_from_either_end(self):
        self.launcher()
        frames = self.drive("up", "down", "tab", "down", "tab", "up", "down")
        self.assertEqual([self.focus(f) for f in frames],
                         ["positions.repository.instructions", "positions.repository.instructions",
                          "positions.repository.knowledge", "field.note",
                          "positions.repository.instructions", "field.note",
                          "positions.personal.memory", "positions.personal.memory"])

    def test_keys_with_nothing_to_do_change_nothing(self):
        self.launcher()
        frames = self.drive("home", "page_up", "page_down", "backspace", "left", "enter", "tab",
                            "enter")
        for frame in frames[1:4]:
            self.assertEqual(frame["elements"], frames[0]["elements"])
        self.assertEqual(frames[7]["elements"], frames[6]["elements"])
        self.assertEqual(self.sent, [])


class Views(Entering):
    def test_enter_opens_a_position_s_detail_and_escape_returns_to_it_as_it_was(self):
        self.launcher()
        frames = self.drive("down", "enter", "escape")
        detail = frames[2]
        target = {"ref": "position", "view": "original",
                  "position": {"scope": self.repository, "role": "knowledge"}}
        self.assertEqual((detail["view"]["view"], detail["view"]["target"],
                          detail["view"]["return_view"]), ("w02", target, "w01"))
        self.assertEqual(self.ids(detail), ["context.location", "detail.repository.knowledge",
                                            "help.keys"])
        self.assertEqual(self.focus(detail), "detail.repository.knowledge")
        self.assertEqual(self.element(detail, "detail.repository.knowledge")["state"],
                         "checked_empty")
        self.assertEqual(self.element(detail, "help.keys")["label"], "Enter 열기·시작 · Esc 뒤로")
        self.assertEqual(frames[3]["view"], frames[1]["view"])
        self.assertEqual(frames[3]["elements"], frames[1]["elements"])

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
        self.assertEqual(self.focus(opened), "positions.team.instructions")
        self.assertEqual(frames[3]["view"], frames[0]["view"])
        self.assertEqual(self.focus(frames[4]), "positions.team.instructions")

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

    def test_a_link_to_a_route_not_offered_focuses_the_first_position(self):
        self.launcher(entrance="work_link")
        frames = self.drive(entrance="work_link", link={
            "target": {"ref": "route", "route_id": bench.ident("rte")}, "return_view": "hub"})
        self.assertEqual(self.focus(frames[0]), "positions.repository.instructions")

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
        self.assertEqual(self.marks(frames[9], "positions.personal.knowledge")[1:],
                         ("none", ["›", "[ ]"]))
        self.assertEqual(start["route_id"], begin["refers_to"]["route_id"])

    def test_the_tool_and_the_permissions_stay_once_the_start_is_sent(self):
        self.launcher(hosts=("claude-code", "codex"))
        frames = self.drive("tab", "tab", "tab", "tab", "enter", "back_tab", "right",
                            "back_tab", "right")
        self.assertEqual(self.focus(frames[7]), "execution.permissions")
        self.assertEqual(self.element(frames[7], "execution.permissions")["value"],
                         "host_settings")
        self.assertEqual(self.element(frames[7], "execution.permissions")["selection"],
                         "suggested")
        self.assertEqual(self.focus(frames[9]), "execution.tool")
        self.assertEqual(self.element(frames[9], "execution.tool")["value"], "Claude Code")
        self.assertEqual(self.element(frames[9], "execution.tool")["selection"], "suggested")

    def test_the_arrows_change_the_permissions_only_while_they_are_focused(self):
        self.launcher(hosts=("claude-code", "codex"))
        frames = self.drive("right", "tab", "tab", "tab", "right", "right", "left",
                            locale="en")
        for frame in frames[:5]:
            self.assertEqual(self.element(frame, "execution.permissions")["value"],
                             "host_settings")
        self.assertEqual(self.element(frames[3], "execution.tool")["value"], "Claude Code")
        skipped = self.element(frames[5], "execution.permissions")
        self.assertEqual((skipped["value"], skipped["selection"], skipped["marks"],
                          skipped["label"]),
                         ("skip_confirmations", "selected", ["›"],
                          "Permissions · run without confirmations"))
        self.assertNotIn("effects", skipped)
        again = self.element(frames[6], "execution.permissions")
        self.assertEqual((again["value"], again["selection"], again["marks"], again["effects"]),
                         ("host_settings", "selected", ["›"], ["permission_request"]))
        self.assertEqual(self.element(frames[7], "execution.permissions")["value"],
                         "skip_confirmations")
        self.assertEqual(self.element(frames[7], "execution.tool")["value"], "Claude Code")

    def test_a_start_that_includes_nothing_reads_nothing_and_carries_no_note(self):
        self.launcher()
        frames = self.drive("tab", "tab", "tab", "enter")
        sealed, carried = self.sent[0]
        self.assertEqual(carried[0]["basis"]["source_pins"], [])
        self.assertNotIn("rationale", sealed)
        self.assertEqual(frames[4]["calls"][0]["reads"], "nothing")

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
        frames = self.drive("tab", *long, {"input": "text", "text": "b"}, "tab", "tab", "enter",
                            "back_tab", "back_tab", "backspace", "tab", "tab", "enter")
        self.assertEqual(self.element(frames[7], "action.start")["state"], "blocked")
        self.assertEqual(self.element(frames[7], "action.start")["executing"], False)
        self.assertEqual(self.focus(frames[7]), "action.start")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][0]["rationale"], "a" * 2000)

    def test_text_and_paste_go_into_the_note_as_given_and_nowhere_else(self):
        self.launcher()
        frames = self.drive({"input": "text", "text": "q s"}, "tab",
                            {"input": "text", "text": "첫\n"},
                            {"input": "paste", "text": "\x1b[31m"}, "backspace", "tab",
                            {"input": "paste", "text": "x"}, "backspace")
        self.assertEqual(frames[1]["elements"], frames[0]["elements"])
        self.assertEqual([self.element(f, "field.note")["value"] for f in frames[3:]],
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
        frames = self.drive("down", "tab", "back_tab", "back_tab")
        self.assertEqual([self.focus(f) for f in frames[1:]],
                         ["positions.repository.instructions", "field.note", "action.check",
                          "action.start"])

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
        label = self.element(self.drive()[0], "positions.personal.memory")["label"]
        columns = tui.cells(label) + tui.GUTTER + 2
        frame = self.drive({"input": "resize", "columns": columns, "rows": 24})[1]
        self.assertEqual(self.element(frame, "positions.personal.memory")["shown"], "clipped")
        frame = self.drive({"input": "resize", "columns": columns + 2, "rows": 24})[1]
        self.assertEqual(self.element(frame, "positions.personal.memory")["shown"], "whole")

    def test_a_note_is_clipped_past_three_lines(self):
        self.launcher(scope=self.person.scope)
        room = 40 - tui.GUTTER
        frames = self.drive("tab", {"input": "text", "text": "a" * room * 3},
                            {"input": "text", "text": "a"}, terminal=(40, 24), locale="en")
        self.assertEqual(self.element(frames[2], "field.note")["shown"], "whole")
        self.assertEqual(self.element(frames[3], "field.note")["shown"], "clipped")
        rows = {e["element_id"]: e["shown"] for e in self.drive(
            "tab", {"input": "text", "text": "a" * room * 3}, terminal=(40, 9),
            locale="en")[2]["elements"]}
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
                             for key in ("tab", "tab", "tab", "enter")]}
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
        self.assertEqual(len(trace["frames"]), 5)
        self.assertEqual(len(trace["frames"][4]["dispatched"]), 1)
        store = self.bench.store()
        self.assertEqual(store.read("SELECT COUNT(*) FROM requests WHERE operation = ?",
                                    (COMPOSE,))[0][0], 0)


if __name__ == "__main__":
    unittest.main()
