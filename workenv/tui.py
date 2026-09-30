"""The entry model (C12 `surface.drive`): what an entrance draws from what the owner holds, one
frame per input, and the one owner request an input dispatches.

The model is a function of the drive request, the `surface_script` and what the owner keeps. It
writes nothing. A start or a check it dispatches goes to the dispatcher it was given. The
terminal's dispatcher has the request answered (`workenv.commands`) and hands the model the
answer (`answered`); `surface.drive`'s only records it, which is why a drive is a pure preview
and never shows an answer.

What it reads, and what a frame's `calls` name:

  - the latest route offer this installation holds from the script's entrance, and the probe
    each route names;
  - for each position of the basis, the collection the owner holds there, else the sources it
    holds there with their accepted revisions;
  - the binding of a selected repository;
  - the latest history answer the journal holds for the selected scope. The first frame that
    shows its checkpoint or its unknown start cites that held request (`reads: inventory`).

V1 has no owner operation that lists a scope's sources, so the kept records above are read
directly. `calls` names the requests a frame rests on: that history read, and the request an
input dispatches.

The grammar (design records `2026-09-28T1601--4e305e5--v1-slice5-entry-grammar-design.md` and
`2026-09-29T0402--69ebae1--v1-slice5-terminal-design.md`):

  - **Views.** The Studio hub opens `hub`, and every other entrance `w01`. A link opens `w01` at
    its target, with its draft and return view. `w02` is one position's detail. Enter opens a
    view over the current one and Esc returns to it; Esc on a `w01` nothing else lies under opens
    the hub over it. Nothing opens from a detail, so Enter there starts, from the `w01` under it.
  - **W01**, in order: where the work is; the last checkpoint; an unknown start with its check;
    the positions of the basis (the selected scope's, then the person's, each Instructions,
    knowledge, memory); the note; the tool; the permissions; a blocker for each route not
    qualified now; the start; the keys. After a start, its result.
  - **Selection.** A position whose collection the owner holds shows that recorded choice. With
    no collection, an Instructions source with an accepted revision is `suggested` and included,
    while knowledge and memory are not included: their bodies are read only for a task. Space
    makes the choice the person's, `selected` or `none`. The start pins what this frame
    includes and no collection already applies. A position with nothing to choose (no source
    there, none with an accepted revision, or a collection that includes nothing) is marked
    `[-]` and unavailable in words, and focus never lands on it. A source a collection switches
    on that does not resolve, read as composition reads it (`preparation.resolved`), is named on
    its position, which is `partial`, or `missing` where nothing it switches on resolves. So is
    an Instructions member selected there whose body is not held (`preparation.unheld`), which
    composition delivers no body for, and a repository-authored one whose checkout document
    changed since it was admitted (`roles.drifted`), which a start refuses while it is included.
  - **Focus and keys.** Focus starts on the check of an unknown start, else a link's target,
    else the first position there is something to choose at, else the first Tab stop. Tab stops
    are the check, the note, the tool (when it has alternatives), the permissions and the start.
    The arrows move through the positions there is something to choose at, and ← → change the
    tool or the permissions until a start is dispatched. The
    permissions are the host's own settings, suggested, until changed; they are an argument of
    the launch, not of the composition. Text and paste go into a focused field code point for
    code point, and nowhere else, so no letter is a shortcut; Space in a focused field is a
    space.
  - **Dispatch.** Enter on the start, or on a position's detail, dispatches one
    `preparation.compose` for the basis, with the note as its rationale. From a detail it first
    returns to the `w01` under it, focused on the start. While a start is unknown it dispatches
    nothing, and the start shows `blocked` and hands focus to the check. Enter on the check
    dispatches one `operation.query` for the unknown request, and asks again once that one is
    answered with the start still not settled. A dispatched action stays
    `executing` and `pending` until its answer is handed over. Then its result element shows it:
    the start's result, or the unknown start the check was for. An unknown outcome stays
    `unknown`, and a refusal or a failure is `unavailable`, labelled with the owner's reason;
    a start refused `working_bytes_moved` is labelled in the locale's words with its next steps,
    leaving the repository's Instructions out or admitting the document again. A
    check can also find its start settled, no longer pending, at the stage it now stands at
    (`settled`): the start is drawn as settled on the same screen, `delivered` where its session
    reported and `unavailable` otherwise, the start is no longer held back by it, and the hub no
    longer signals it.
  - **`shown`.** An element is one line of `columns - 2` cells (wide characters take two cells,
    combining marks and Hangul medial and final jamo none, and a control character two), and a
    field's value takes up to three more lines. The line is its marks and label, then each effect
    it states in the locale's words (`drawn`), so an effect sits on what has it. An element wider
    is `clipped`, and one starting below the last row is `off_screen`.

The wording lives in `CATALOG`, one table for `ko`, `en` and `ja`. The conformance runner does not
compare labels (D-20260928-380689); the unit tests hold the catalog.
"""
from __future__ import annotations

import dataclasses
import json
import unicodedata

from workenv import cli, journal, preparation, roles, storage
from workenv.contracts import c07, canonical

# The client a trace names: this model, versioned by its grammar.
CLIENT = {"name": "agent-bios-entry", "version": "1"}
ROLES = ("instructions", "knowledge", "memory")
HUB, W01, W02 = "hub", "w01", "w02"
START, COMPOSE, QUERY = "use", "preparation.compose", "operation.query"
SESSION_START = "session.routing.activate"
HISTORY = "operation.history.read"
# The stage a history entry shows as a pending start, by the stage its request was confirmed at.
PENDING = {"unknown": "unknown", "partial": "partial", "in_review": "pending",
           "approved": "pending", "executing": "pending"}
# The cells focus takes before each line, and the most lines a field's value takes.
GUTTER, VALUE_LINES = 2, 3
# Hosts by the name a probe gives them.
TOOLS = {"claude-code": "Claude Code", "codex": "Codex CLI"}
# What a session's permissions can start as: the host's own settings, suggested, or its
# confirmations skipped. A launch argument, not part of the composition (D-20260929-e1d487).
PERMISSIONS = ("host_settings", "skip_confirmations")
RATIONALE = 2000
# What an answer handed to the entry is drawn as.
ANSWERED = ("unknown", "unavailable", "settled")
# The stages a settled start has its own words for; any other is named as it is.
SETTLED = ("committed", "expired")
# The states of a position with nothing to choose: nothing held there, or nothing accepted.
UNAVAILABLE = ("checked_empty", "configured")

CATALOG = {
    "ko": {
        "suggested": "(제안)", "unavailable": "(선택 불가)",
        "layer.repository": "레포", "layer.personal": "개인", "layer.team": "팀",
        "role.instructions": "지침", "role.knowledge": "지식", "role.memory": "결정 기록",
        "action.use": "새 세션", "action.decide": "결정", "action.other": "{action}",
        "location.repository": "{name} · 로컬 레포 · {branch}",
        "location.personal": "개인 · 이 기기",
        "location.team": "팀 · {name}",
        "checkpoint": "이전 메모 · {note} (기록 당시)",
        "draft": "지난 시작의 결과를 아직 모름 · {coverage}",
        "coverage.local_only": "이 기기만 확인함",
        "coverage.local_and_provider": "이 기기와 제공자를 확인함",
        "check": "이 요청 결과 확인",
        "position": "{layer} {role} · {name}",
        "position.more": "{layer} {role} · {name} 외 {more}개",
        "position.empty": "{layer} {role} · 아직 없음",
        "position.configured": "{layer} {role} · 확정된 판 없음",
        "position.unresolved": "{position} · {missing}",
        "unresolved": "쓸 수 없는 원본 {source}",
        "unresolved.more": "쓸 수 없는 원본 {source} 외 {more}개",
        "unheld": "본문 없음 {member}", "unheld.more": "본문 없음 {member} 외 {more}개",
        "changed": "등록 뒤 바뀜 {member}", "changed.more": "등록 뒤 바뀜 {member} 외 {more}개",
        "not_started.moved": "시작하지 못함 · 레포 문서가 등록 뒤 바뀜 · Space로 빼거나 다시 등록",
        "effect.model_calls": "모델 호출", "effect.file_changes": "파일 변경",
        "effect.permission_request": "권한 요청",
        "detail": "{position} · 원본 · {state}",
        "state.installed": "설치됨", "state.not_checked": "본문은 아직 확인하지 않음",
        "state.checked_empty": "비어 있음", "state.configured": "확정된 판 없음",
        "state.partial": "일부 원본을 쓸 수 없음", "state.missing": "원본을 쓸 수 없음",
        "note": "메모 · 시작 요청에 함께 기록",
        "tool": "도구 {tool} · 새 세션",
        "permissions": "권한 · {choice}",
        "permissions.host_settings": "호스트 설정대로 확인",
        "permissions.skip_confirmations": "확인 없이 실행",
        "blocker": "{layer} {action}: {tool}에서 확인 안 됨 · 이 호스트에서 확인 필요",
        "start": "{tool} 새 세션 시작",
        "started": "시작 요청을 보냈습니다 · 결과 확인 중",
        "not_started": "시작하지 못함 · {reason}",
        "not_checked": "확인하지 못함 · {reason}",
        "settled.committed": "지난 시작 · 세션이 시작을 알려와 확정됨 · 새로 시작 가능",
        "settled.expired": "지난 시작 · 세션이 시작을 알리지 않음으로 기록됨 · 새로 시작 가능",
        "settled.other": "지난 시작 · {stage}(으)로 끝남 · 새로 시작 가능",
        "job.prepare": "새 세션 준비",
        "signal": "결과 모름 · 지난 시작",
        "key.tab": "Tab 이동", "key.arrows": "↑↓ 자료", "key.space": "Space 선택",
        "key.change": "←→ 변경", "key.enter": "Enter 열기·시작", "key.escape": "Esc 뒤로",
        "key.start": "Enter 시작",
    },
    "en": {
        "suggested": "(suggested)", "unavailable": "(unavailable)",
        "layer.repository": "Repository", "layer.personal": "Personal", "layer.team": "Team",
        "role.instructions": "Instructions", "role.knowledge": "knowledge",
        "role.memory": "decision records",
        "action.use": "new session", "action.decide": "decide", "action.other": "{action}",
        "location.repository": "{name} · local repository · {branch}",
        "location.personal": "Personal · this device",
        "location.team": "Team · {name}",
        "checkpoint": "Earlier note · {note} (as written then)",
        "draft": "Last start: result unknown · {coverage}",
        "coverage.local_only": "checked on this device only",
        "coverage.local_and_provider": "checked on this device and with the provider",
        "check": "Check this request",
        "position": "{layer} {role} · {name}",
        "position.more": "{layer} {role} · {name} and {more} more",
        "position.empty": "{layer} {role} · none yet",
        "position.configured": "{layer} {role} · no accepted revision",
        "position.unresolved": "{position} · {missing}",
        "unresolved": "unresolved source {source}",
        "unresolved.more": "unresolved source {source} and {more} more",
        "unheld": "body not held {member}", "unheld.more": "body not held {member} and {more} more",
        "changed": "changed since admitted {member}",
        "changed.more": "changed since admitted {member} and {more} more",
        "not_started.moved": "Not started · repository document changed · leave it out (Space) "
                             "or re-admit",
        "effect.model_calls": "model calls", "effect.file_changes": "file changes",
        "effect.permission_request": "permission requests",
        "detail": "{position} · original · {state}",
        "state.installed": "installed", "state.not_checked": "body not checked yet",
        "state.checked_empty": "empty", "state.configured": "no accepted revision",
        "state.partial": "some sources unresolved", "state.missing": "sources unresolved",
        "note": "Note · recorded with the start",
        "tool": "Tool {tool} · new session",
        "permissions": "Permissions · {choice}",
        "permissions.host_settings": "confirm as the host is set",
        "permissions.skip_confirmations": "run without confirmations",
        "blocker": "{layer} {action}: not confirmed in {tool} · confirm on this host",
        "start": "Start a new {tool} session",
        "started": "Start sent · checking the result",
        "not_started": "Not started · {reason}",
        "not_checked": "Not checked · {reason}",
        "settled.committed": "Last start: the session reported it began · you can start again",
        "settled.expired": "Last start: recorded as not reported by its session · you can "
                           "start again",
        "settled.other": "Last start: ended as {stage} · you can start again",
        "job.prepare": "Prepare a new session",
        "signal": "Result unknown · last start",
        "key.tab": "Tab move", "key.arrows": "↑↓ items", "key.space": "Space select",
        "key.change": "←→ change", "key.enter": "Enter open·start", "key.escape": "Esc back",
        "key.start": "Enter start",
    },
    "ja": {
        "suggested": "(提案)", "unavailable": "(選択不可)",
        "layer.repository": "リポジトリ", "layer.personal": "個人", "layer.team": "チーム",
        "role.instructions": "指示", "role.knowledge": "知識", "role.memory": "決定記録",
        "action.use": "新しいセッション", "action.decide": "決定", "action.other": "{action}",
        "location.repository": "{name} · ローカルリポジトリ · {branch}",
        "location.personal": "個人 · この端末",
        "location.team": "チーム · {name}",
        "checkpoint": "以前のメモ · {note} (記録時点)",
        "draft": "前回の開始の結果はまだ不明 · {coverage}",
        "coverage.local_only": "この端末でのみ確認",
        "coverage.local_and_provider": "この端末と提供元で確認",
        "check": "このリクエストの結果を確認",
        "position": "{layer}{role} · {name}",
        "position.more": "{layer}{role} · {name} ほか{more}件",
        "position.empty": "{layer}{role} · まだありません",
        "position.configured": "{layer}{role} · 確定した版なし",
        "position.unresolved": "{position} · {missing}",
        "unresolved": "使えない原本 {source}",
        "unresolved.more": "使えない原本 {source} ほか{more}件",
        "unheld": "本文なし {member}", "unheld.more": "本文なし {member} ほか{more}件",
        "changed": "登録後に変更 {member}", "changed.more": "登録後に変更 {member} ほか{more}件",
        "not_started.moved": "開始できません · リポジトリ文書が登録後に変更 · Spaceで外すか再登録",
        "effect.model_calls": "モデル呼び出し", "effect.file_changes": "ファイル変更",
        "effect.permission_request": "権限の確認",
        "detail": "{position} · 原本 · {state}",
        "state.installed": "インストール済み", "state.not_checked": "本文は未確認",
        "state.checked_empty": "空", "state.configured": "確定した版なし",
        "state.partial": "一部の原本を使えない", "state.missing": "原本を使えない",
        "note": "メモ · 開始リクエストと一緒に記録",
        "tool": "ツール {tool} · 新しいセッション",
        "permissions": "権限 · {choice}",
        "permissions.host_settings": "ホストの設定どおり確認",
        "permissions.skip_confirmations": "確認なしで実行",
        "blocker": "{layer}{action}: {tool} で未確認 · このホストで確認が必要",
        "start": "{tool} の新しいセッションを開始",
        "started": "開始リクエストを送信しました · 結果を確認中",
        "not_started": "開始できませんでした · {reason}",
        "not_checked": "確認できませんでした · {reason}",
        "settled.committed": "前回の開始 · セッションが開始を報告し確定 · 新しく開始できます",
        "settled.expired": "前回の開始 · セッションの報告なしとして記録 · 新しく開始できます",
        "settled.other": "前回の開始 · {stage} で終了 · 新しく開始できます",
        "job.prepare": "新しいセッションを準備",
        "signal": "結果不明 · 前回の開始",
        "key.tab": "Tab 移動", "key.arrows": "↑↓ 資料", "key.space": "Space 選択",
        "key.change": "←→ 変更", "key.enter": "Enter 開く・開始", "key.escape": "Esc 戻る",
        "key.start": "Enter 開始",
    },
}


def cells(text: str) -> int:
    """The terminal cells a text takes."""
    width = 0
    for char in text:
        point = ord(char)
        if point < 0x20 or point == 0x7F:
            width += 2
        elif unicodedata.combining(char) or 0x1160 <= point <= 0x11FF or \
                unicodedata.category(char) in ("Mn", "Me", "Cf"):
            continue
        elif unicodedata.east_asian_width(char) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def scope_id(scope: dict) -> str:
    return journal.scope_id(scope)


def position_ref(scope: dict, role: str) -> dict:
    return {"ref": "position", "position": {"scope": scope, "role": role}, "view": "original"}


# What the owner holds.

@dataclasses.dataclass
class Position:
    scope: dict
    role: str
    state: str
    names: list[str]
    pins: list[dict]
    collection: bool
    included: bool
    chosen: bool = False
    # The sources a collection selects here that do not resolve, as composition reads them.
    unresolved: list[str] = dataclasses.field(default_factory=list)
    # The Instructions members selected here whose bodies are not held (`preparation.unheld`).
    unheld: list[str] = dataclasses.field(default_factory=list)
    # The repository-authored members whose checkout document changed since admitted
    # (`roles.drifted`): a start that includes them is refused.
    changed: list[str] = dataclasses.field(default_factory=list)

    @property
    def layer(self) -> str:
        return self.scope["layer"]

    @property
    def element_id(self) -> str:
        return f"positions.{self.layer}.{self.role}"

    @property
    def available(self) -> bool:
        return self.state not in UNAVAILABLE

    @property
    def toggles(self) -> bool:
        # A position a collection applies carries no pins, so only an uncollected one toggles.
        return bool(self.pins)

    @property
    def selection(self) -> str:
        if self.collection:
            return "selected" if self.included else "none"
        if not self.chosen and self.included:
            return "suggested"
        return "selected" if self.included else "none"


@dataclasses.dataclass
class Route:
    route: dict
    probe: dict | None
    qualified: bool

    @property
    def tool(self) -> str:
        name = (self.probe or {}).get("client", {}).get("name", "")
        return TOOLS.get(name, name)


def latest_offer(store: storage.Store, entrance: str) -> dict | None:
    for (returned,) in store.read("SELECT returned FROM requests WHERE operation = ? AND "
                                  "stage = 'committed' ORDER BY position DESC", ("route.offer",)):
        for digest in json.loads(returned):
            offer = store.get(digest)
            if isinstance(offer, dict) and offer.get("kind") == cli.OFFER and \
                    offer["entrance"]["name"] == entrance:
                return offer
    return None


def routes_of(store: storage.Store, offer: dict | None) -> list[Route]:
    found = []
    for route in (offer or {}).get("offered", []):
        probe = cli.held(store, route["support"].get("probe_digest"), cli.PROBE)
        found.append(Route(route, probe, cli.qualifies(
            store, probe, cli.NEEDS.get(route["supported_action"]))))
    return found


def revision_names(store: storage.Store, revision: str | None) -> list[str]:
    manifest = store.get(revision) if revision else None
    return [member["path"] for member in manifest["members"]] if isinstance(manifest, dict) \
        else []


def drawn(element: dict, locale: str) -> str:
    """One element's line as the terminal draws it: its marks and label, then each effect it
    states, in the locale's words, so the effect sits on the element it is an effect of."""
    words = [CATALOG[locale][f"effect.{effect}"] for effect in element.get("effects", [])]
    return " · ".join([" ".join(element["marks"] + [element["label"]])] + words)


def position_of(store: storage.Store, scope: dict, role: str) -> Position:
    def read(pinned: list[tuple[str, str | None, list[dict] | None]]) -> tuple[list, list, list]:
        """The member names the pins hold usable bodies for, the members they lack bodies for,
        and the members whose checkout document changed since they were admitted. Only
        Instructions bodies reach a session at its start; knowledge is read for a task."""
        names, lacking, changed = [], [], []
        for source_id, revision, declared in pinned:
            manifest = store.get(revision) if revision else None
            if role != preparation.INSTRUCTIONS or not isinstance(manifest, dict):
                names += revision_names(store, revision)
                continue
            gone = preparation.unheld(store.path.parent, revision, manifest, declared)
            digests = {member["path"]: member["digest"] for member in manifest["members"]}
            moved = [path for path in ([unit["member"] for unit in declared] if declared
                                       else list(digests))
                     if path in digests and path not in gone
                     and roles.drifted(store, source_id, path, digests[path])]
            lacking += gone
            changed += moved
            names += [name for name in revision_names(store, revision)
                      if name not in gone and name not in moved]
        return names, lacking, changed

    collection_id = preparation.held_collection(store, scope, role)
    if collection_id is not None:
        collection = store.get(journal.head_of(store, collection_id))
        entries = [entry for entry in collection["entries"] if entry["switch"] == "on"] \
            if collection["switch"] == "on" else []
        unresolved = [entry for entry in entries if preparation.resolved(store, entry, role)[0]]
        resolving = [entry for entry in entries if entry not in unresolved]
        names, lacking, changed = read([(entry["source_id"],
                                         entry.get("pin", {}).get("revision_digest"),
                                         entry.get("units")) for entry in resolving])
        unusable = lacking + changed
        state = ("checked_empty" if not entries
                 else "missing" if not resolving or (unusable and not names)
                 else "partial" if unresolved or unusable
                 else "installed" if role == preparation.INSTRUCTIONS else "not_checked")
        return Position(scope, role, state,
                        names or ([] if unusable else [entry["source_id"] for entry in resolving]),
                        [], True, bool(entries),
                        unresolved=[entry["source_id"] for entry in unresolved], unheld=lacking,
                        changed=changed)
    held = store.read("SELECT source_id, revision_digest FROM sources WHERE scope = ? AND "
                      "role = ? ORDER BY rowid", (journal.scope_key(scope), role))
    pins = [{"source_id": source, "revision_digest": revision}
            for source, revision in held if revision]
    names, lacking, changed = read([(pin["source_id"], pin["revision_digest"], None)
                                    for pin in pins])
    unusable = lacking + changed
    if pins:
        state = ("missing" if unusable and not names else "partial" if unusable
                 else "installed" if role == preparation.INSTRUCTIONS else "not_checked")
    else:
        state = "configured" if held else "checked_empty"
    return Position(scope, role, state, names, pins, False,
                    bool(pins) and role == preparation.INSTRUCTIONS, unheld=lacking,
                    changed=changed)


def history_of(store: storage.Store, scope: dict) -> tuple[dict, str] | None:
    """The latest history answer the journal holds for the scope, and its request's digest."""
    for digest, returned in store.read("SELECT request_digest, returned FROM requests WHERE "
                                       "operation = ? AND stage = 'previewed' ORDER BY "
                                       "position DESC", (HISTORY,)):
        for held in json.loads(returned):
            history = store.get(held)
            if isinstance(history, dict) and history.get("kind") == "recent_history" and \
                    history["scope"] == scope:
                return history, digest
    return None


def location_of(store: storage.Store, scope: dict) -> dict:
    """What the location's label is made of."""
    if scope["layer"] == "repository":
        found = store.read("SELECT binding_digest FROM repositories WHERE repository_id = ?",
                           (scope["repository_id"],))
        binding = store.get(found[0][0]) if found else None
        observed = (binding or {}).get("observed", {})
        locator = observed.get("locator", scope["repository_id"]).rstrip("/")
        name = locator.rsplit("/", 1)[-1].rsplit(":", 1)[-1].removesuffix(".git")
        return {"key": "location.repository", "name": name,
                "branch": observed.get("branch", "")}
    if scope["layer"] == "team":
        return {"key": "location.team", "name": scope_id(scope)[4:12]}
    return {"key": "location.personal"}


# The model.

class Entry:
    def __init__(self, store: storage.Store, request: dict, script: dict, dispatch=None):
        self.store, self.request, self.script = store, request, script
        self.dispatch = dispatch or (lambda sealed, carried: None)
        self.locale, self.terminal = script["locale"], dict(script["terminal"])
        actor = request["actor"]
        self.person = {"layer": "personal", "principal_id": actor["principal_id"]}
        self.routes = routes_of(store, latest_offer(store, script["entrance"]["name"]))
        self.starts: list[Route] = []
        for route in self.routes:
            if route.route["supported_action"] == START and route.qualified and \
                    route.tool not in {start.tool for start in self.starts}:
                self.starts.append(route)
        self.tool, self.tool_chosen = 0, False
        self.permission, self.permission_chosen = 0, False
        self.scope = self.starts[0].route["scope"] if self.starts else self.person
        layers = [self.scope] + ([self.person] if self.scope != self.person else [])
        self.positions = [position_of(store, scope, role) for scope in layers for role in ROLES]
        found = history_of(store, self.scope)
        self.history, self.history_digest = found if found else (None, None)
        entries = [entry for entry in (self.history or {}).get("entries", [])
                   if entry["confirmed_stage"] in PENDING]
        self.draft = entries[-1] if entries else None
        checkpoints = (self.history or {}).get("checkpoints", [])
        self.checkpoint = checkpoints[-1] if checkpoints else None
        self.cited = False
        self.note = ""
        self.started: str | None = None
        self.checking: str | None = None
        self.blocked = False
        link = script.get("link")
        self.link_return = link.get("return_view") if link else None
        base = {"view": HUB if script["entrance"]["name"] == "studio_hub" else W01,
                "target": link["target"] if link else None, "focus": None}
        if link and "draft_request_id" in link:
            self.draft = {"request_id": link["draft_request_id"], "confirmed_stage": "unknown",
                          "coverage": "local_only"}
        self.nav = [base]
        base["focus"] = self.first_focus(base["view"])
        self.calls: list[dict] = []
        self.sent: list[str] = []
        # The answers handed over, by request: the state drawn and the owner's reason.
        self.answers: dict[str, tuple[str, str | None]] = {}
        self.refusals: dict[str, list[str]] = {}

    # What the frame holds.

    @property
    def here(self) -> dict:
        return self.nav[-1]

    @property
    def start(self) -> Route | None:
        return self.starts[self.tool] if self.starts else None

    @property
    def permissions(self) -> str:
        return PERMISSIONS[self.permission]

    def text(self, key: str, **values) -> str:
        return CATALOG[self.locale][key].format(**values)

    def layer_name(self, layer: str) -> str:
        return self.text(f"layer.{layer}")

    def action_name(self, action: str) -> str:
        key = f"action.{action}"
        return self.text(key) if key in CATALOG[self.locale] else self.text("action.other",
                                                                            action=action)

    def position_label(self, position: Position) -> str:
        values = {"layer": self.layer_name(position.layer),
                  "role": self.text(f"role.{position.role}")}
        if position.state == "checked_empty":
            return self.text("position.empty", **values)
        if position.state == "configured":
            return self.text("position.configured", **values)
        unresolved, lacking, changed = position.unresolved, position.unheld, position.changed
        missing = " · ".join(
            ([self.text("unresolved.more" if len(unresolved) > 1 else "unresolved",
                        source=unresolved[0][:12], more=len(unresolved) - 1)]
             if unresolved else []) +
            ([self.text("unheld.more" if len(lacking) > 1 else "unheld", member=lacking[0],
                        more=len(lacking) - 1)] if lacking else []) +
            ([self.text("changed.more" if len(changed) > 1 else "changed", member=changed[0],
                        more=len(changed) - 1)] if changed else [])) or None
        if not position.names:
            return self.text("position", name=missing or "-", **values)
        held = self.text("position.more", name=position.names[0],
                         more=len(position.names) - 1, **values) \
            if len(position.names) > 1 else self.text("position", name=position.names[0],
                                                      **values)
        return self.text("position.unresolved", position=held, missing=missing) if missing \
            else held

    def blockers(self) -> list[tuple[str, Route]]:
        found, used = [], set()
        for route in self.routes:
            if route.qualified:
                continue
            base = f"blocker.{route.route['scope']['layer']}.{route.route['supported_action']}"
            name, number = base, 1
            while name in used:
                number += 1
                name = f"{base}.{number}"
            used.add(name)
            found.append((name, route))
        return found

    def tab_stops(self) -> list[str]:
        if self.here["view"] != W01:
            return [element for element in self.ids() if element.startswith(("job.", "signal."))]
        stops = []
        if self.draft:
            stops.append("action.check")
        if self.start:
            stops.append("field.note")
            if len(self.starts) > 1:
                stops.append("execution.tool")
            stops.append("execution.permissions")
            stops.append("action.start")
        return stops

    def ids(self) -> list[str]:
        return [element["element_id"] for element in self.elements()]

    def settled(self) -> str | None:
        """The stage the check found its unknown start settled at, or None."""
        checked = self.answers.get(self.checking) if self.checking else None
        return checked[1] if checked and checked[0] == "settled" else None

    def holds_back(self) -> bool:
        """Whether an unknown start holds the next one back: until a check finds it settled."""
        return self.draft is not None and self.settled() is None

    def first_focus(self, view: str) -> str | None:
        if view == HUB:
            return "signal.draft" if self.holds_back() else "job.prepare"
        if view == W02:
            return None
        if self.draft:
            return "action.check"
        target = self.here["target"] if self.nav else None
        if target and target.get("ref") == "route" and self.start and \
                target["route_id"] == self.start.route["route_id"]:
            return "action.start"
        choices = [position for position in self.positions if position.available]
        if choices:
            return choices[0].element_id
        stops = self.tab_stops()
        return stops[0] if stops else None

    def element(self, element_id: str, role: str, label: str, marks=(), **more) -> dict:
        focused = self.here["focus"] == element_id
        found = {"element_id": element_id, "role": role, "label": label,
                 "marks": (["›"] if focused else []) + list(marks), "focused": focused,
                 "selection": more.pop("selection", "none"),
                 "executing": more.pop("executing", False), "shown": "whole"}
        found.update({key: value for key, value in more.items() if value is not None})
        return found

    def draws_history(self) -> bool:
        return self.history is not None and (self.draft is not None or
                                             self.checkpoint is not None)

    def location(self) -> dict:
        parts = location_of(self.store, self.scope)
        return self.element("context.location", "context",
                            self.text(parts.pop("key"), **parts),
                            refers_to={"ref": "scope", "scope": self.scope})

    def w01(self) -> list[dict]:
        found = [self.location()]
        if self.checkpoint:
            found.append(self.element("context.checkpoint", "context",
                                      self.text("checkpoint", note=self.checkpoint["note"]
                                                if "note" in self.checkpoint else "-"),
                                      refers_to={"ref": "record",
                                                 "digest": self.checkpoint["digest"]}))
        if self.draft:
            request = {"ref": "request", "request_id": self.draft["request_id"]}
            checked = self.answers.get(self.checking) if self.checking else None
            stage = self.settled()
            if stage is not None:
                label = self.text(f"settled.{stage}" if stage in SETTLED else "settled.other",
                                  stage=stage)
                state = "delivered" if stage == "committed" else "unavailable"
            elif checked and checked[1]:
                label, state = self.text("not_checked", reason=checked[1]), checked[0]
            else:
                label = self.text("draft", coverage=self.text(f"coverage.{self.draft['coverage']}"))
                state = checked[0] if checked else PENDING[self.draft["confirmed_stage"]]
            found.append(self.element("result.draft", "result", label, state=state,
                                      refers_to=request))
            checking = self.checking is not None and checked is None
            found.append(self.element("action.check", "action", self.text("check"),
                                      executing=checking,
                                      state="pending" if checking else None,
                                      refers_to=request))
        suggested = self.text("suggested")
        for position in self.positions:
            if not position.available:
                marks = ["[-]", self.text("unavailable")]
            else:
                marks = ["[x]" if position.included else "[ ]"]
                if position.selection == "suggested":
                    marks.append(suggested)
            found.append(self.element(position.element_id, "selection",
                                      self.position_label(position), marks,
                                      selection=position.selection, state=position.state,
                                      refers_to=position_ref(position.scope, position.role)))
        start = self.start
        if start:
            found.append(self.element("field.note", "field", self.text("note"),
                                      value=self.note))
            found.append(self.element("execution.tool", "setting",
                                      self.text("tool", tool=start.tool),
                                      [] if self.tool_chosen else [suggested],
                                      selection="selected" if self.tool_chosen
                                      else "suggested",
                                      value=start.tool, effects=["model_calls"]))
            found.append(self.element(
                "execution.permissions", "setting",
                self.text("permissions", choice=self.text(f"permissions.{self.permissions}")),
                [] if self.permission_chosen else [suggested],
                selection="selected" if self.permission_chosen else "suggested",
                value=self.permissions,
                effects=["permission_request"] if self.permissions == "host_settings" else None))
        tool = start.tool if start else ""
        for element_id, route in self.blockers():
            found.append(self.element(element_id, "blocker", self.text(
                "blocker", layer=self.layer_name(route.route["scope"]["layer"]),
                action=self.action_name(route.route["supported_action"]),
                tool=route.tool or tool),
                state="blocked", refers_to={"ref": "route",
                                            "route_id": route.route["route_id"]}))
        answer = self.answers.get(self.started) if self.started else None
        if start:
            executing = self.started is not None and answer is None
            found.append(self.element("action.start", "action",
                                      self.text("start", tool=start.tool),
                                      executing=executing,
                                      state="pending" if executing else
                                      "blocked" if self.blocked else None,
                                      refers_to={"ref": "route",
                                                 "route_id": start.route["route_id"]},
                                      effects=["file_changes", "model_calls"]))
        found.append(self.help())
        if self.started:
            moved = c07.WORKING_BYTES_MOVED in self.refusals.get(self.started, [])
            found.append(self.element("result.start", "result", self.text(
                "not_started.moved") if answer and moved else self.text(
                "not_started", reason=answer[1]) if answer and answer[1] else self.text("started"),
                state=answer[0] if answer else "pending",
                refers_to={"ref": "request", "request_id": self.started}))
        return found

    def w02(self) -> list[dict]:
        target = self.here["target"]["position"]
        position = next(p for p in self.positions
                        if p.scope == target["scope"] and p.role == target["role"])
        return [self.location(),
                self.element(f"detail.{position.layer}.{position.role}", "detail",
                             self.text("detail", position=self.position_label(position),
                                       state=self.text(f"state.{position.state}")),
                             state=position.state,
                             refers_to=position_ref(position.scope, position.role)),
                self.help()]

    def hub(self) -> list[dict]:
        found = [self.location()]
        if self.holds_back():
            found.append(self.element("signal.draft", "signal", self.text("signal"), ["?"],
                                      state=PENDING[self.draft["confirmed_stage"]],
                                      refers_to={"ref": "request",
                                                 "request_id": self.draft["request_id"]}))
        found.append(self.element("job.prepare", "action", self.text("job.prepare")))
        found.append(self.help())
        return found

    def help(self) -> dict:
        view = self.here["view"]
        keys = []
        if view == W01:
            if len(self.tab_stops()) > 1:
                keys.append("key.tab")
            if any(position.available for position in self.positions):
                keys.append("key.arrows")
            if any(position.toggles for position in self.positions):
                keys.append("key.space")
            if self.start:
                keys.append("key.change")
        if view != W02:
            keys.append("key.enter")
        elif self.start:
            keys.append("key.start")
        if view != HUB or len(self.nav) > 1 or self.link_return:
            keys.append("key.escape")
        return self.element("help.keys", "help", " · ".join(self.text(key) for key in keys))

    def elements(self) -> list[dict]:
        view = self.here["view"]
        return self.w01() if view == W01 else self.w02() if view == W02 else self.hub()

    def frame(self, after: int) -> dict:
        elements = self.elements()
        if self.draws_history() and not self.cited and any(
                element["element_id"] in ("context.checkpoint", "result.draft", "signal.draft")
                for element in elements):
            self.cited = True
            self.calls.insert(0, {"operation": HISTORY, "reads": "inventory",
                                  "request_digest": self.history_digest})
        self.fit(elements)
        view = {"view": self.here["view"], "origin": self.script["entrance"],
                "selected_scope": self.scope, "missing_bodies": []}
        if self.here["target"]:
            view["target"] = self.here["target"]
        if self.draft:
            view["draft_request_id"] = self.draft["request_id"]
        returning = self.nav[-2]["view"] if len(self.nav) > 1 else self.link_return
        if returning:
            view["return_view"] = returning
        found = {"after": after, "terminal": dict(self.terminal), "locale": self.locale,
                 "access": "active", "view": view, "elements": elements,
                 "dispatched": list(self.sent), "calls": list(self.calls)}
        self.calls, self.sent = [], []
        return found

    def fit(self, elements: list[dict]) -> None:
        room = max(self.terminal["columns"] - GUTTER, 1)
        row = 0
        for element in elements:
            line = drawn(element, self.locale)
            lines = 1
            clipped = cells(line) > room
            if element["role"] == "field":
                value = cells(element.get("value", ""))
                used = max(1, -(-value // room))
                clipped = clipped or used > VALUE_LINES
                lines += min(used, VALUE_LINES)
            element["shown"] = ("off_screen" if row >= self.terminal["rows"]
                                else "clipped" if clipped else "whole")
            row += lines

    # Inputs.

    def press(self, given: dict) -> None:
        kind = given["input"]
        if kind == "resize":
            self.terminal = {"columns": given["columns"], "rows": given["rows"]}
        elif kind == "locale":
            self.locale = given["locale"]
        elif kind in ("text", "paste"):
            if self.here["focus"] == "field.note":
                self.note += given["text"]
        else:
            getattr(self, f"key_{given['key']}", lambda: None)()

    def move(self, step: int) -> None:
        stops = self.tab_stops()
        if not stops:
            return
        order = self.ids()
        focus = self.here["focus"]
        if focus in stops:
            index = stops.index(focus) + step
        else:
            place = order.index(focus) if focus in order else -1
            later = [stop for stop in stops if order.index(stop) > place]
            earlier = [stop for stop in stops if order.index(stop) < place]
            index = stops.index(later[0]) if step > 0 and later else \
                stops.index(earlier[-1]) if step < 0 and earlier else (0 if step > 0 else -1)
        self.here["focus"] = stops[index % len(stops)]

    def key_tab(self) -> None:
        self.move(1)

    def key_back_tab(self) -> None:
        self.move(-1)

    def arrow(self, step: int) -> None:
        ids = [position.element_id for position in self.positions if position.available]
        if self.here["view"] != W01 or not ids:
            return
        focus = self.here["focus"]
        if focus in ids:
            index = min(max(ids.index(focus) + step, 0), len(ids) - 1)
        else:
            index = 0 if step > 0 else len(ids) - 1
        self.here["focus"] = ids[index]

    def key_down(self) -> None:
        self.arrow(1)

    def key_up(self) -> None:
        self.arrow(-1)

    def key_space(self) -> None:
        if self.here["focus"] == "field.note":
            self.note += " "
            return
        position = self.focused_position()
        if position is not None and position.toggles and self.started is None:
            position.chosen, position.included = True, not position.included

    def turn(self, step: int) -> None:
        if self.started is not None:
            return
        if self.here["focus"] == "execution.tool" and len(self.starts) > 1:
            self.tool, self.tool_chosen = (self.tool + step) % len(self.starts), True
        elif self.here["focus"] == "execution.permissions":
            self.permission = (self.permission + step) % len(PERMISSIONS)
            self.permission_chosen = True

    def key_left(self) -> None:
        self.turn(-1)

    def key_right(self) -> None:
        self.turn(1)

    def key_backspace(self) -> None:
        if self.here["focus"] == "field.note":
            self.note = self.note[:-1]

    def focused_position(self) -> Position | None:
        return next((p for p in self.positions if p.element_id == self.here["focus"]), None)

    def key_escape(self) -> None:
        if len(self.nav) > 1:
            self.nav.pop()
        elif self.link_return:
            view = self.link_return
            self.link_return = None
            self.here.update(view=view, target=None)
            if view != W01:
                self.here["focus"] = self.first_focus(view)
        elif self.here["view"] == W01:
            self.nav.append({"view": HUB, "target": None, "focus": self.first_focus(HUB)})

    def key_enter(self) -> None:
        view, focus = self.here["view"], self.here["focus"]
        if view == HUB:
            self.leave_hub(focus)
        elif view == W01:
            position = self.focused_position()
            if position is not None:
                self.nav.append({"view": W02, "target": position_ref(position.scope,
                                                                     position.role),
                                 "focus": f"detail.{position.layer}.{position.role}"})
            elif focus == "action.start":
                self.begin()
            elif focus == "action.check":
                self.check()
        elif view == W02 and self.start:
            self.nav.pop()
            self.here["focus"] = "action.start"
            self.begin()

    def leave_hub(self, focus: str | None) -> None:
        if focus not in ("job.prepare", "signal.draft"):
            return
        if len(self.nav) > 1:
            self.nav.pop()
        else:
            self.nav.append({"view": W01, "target": None, "focus": None})
            self.here["focus"] = self.first_focus(W01)
        if focus == "signal.draft":
            self.here["focus"] = "action.check"

    # Dispatch.

    def seal(self, operation: str, target: str, payload: dict, **more) -> dict:
        row = journal.OPERATIONS[operation]
        return {"kind": "operation_request", "schema": 1, "request_id": journal.mint("req"),
                "operation": operation, "effect_class": row["effect"],
                "actor": self.request["actor"],
                "local_access_generation": self.request["local_access_generation"],
                "action": row["action"], "owner": self.person,
                "target": {"resource_id": target}, "policy_digests": [],
                "control_digests": [], "proof_digests": [],
                "payload_digest": canonical.digest_of(payload), **more}

    def send(self, sealed: dict, payload: dict, reads: str) -> None:
        self.dispatch(sealed, [payload])
        self.calls.append({"operation": sealed["operation"], "reads": reads,
                           "request_digest": canonical.digest_of(sealed)})
        self.sent.append(sealed["request_id"])

    def begin(self) -> None:
        if self.started is not None:
            return
        if self.holds_back() or len(self.note) > RATIONALE:
            self.blocked = True
            if self.holds_back():
                self.here["focus"] = "action.check"
            return
        # A position a collection applies carries no pins: the composition applies it.
        pins = [pin for position in self.positions if position.included for pin in position.pins]
        applied = any(position.included for position in self.positions)
        scopes = [self.scope] + ([self.person] if self.scope != self.person else [])
        basis = {"kind": "preparation_request", "schema": 1,
                 "basis": {"from": "ad_hoc", "scopes": scopes, "source_pins": pins},
                 "declared_operation": {"action": START, "name": SESSION_START}}
        sealed = self.seal(COMPOSE, self.person["principal_id"], basis,
                           **({"rationale": self.note} if self.note else {}))
        self.send(sealed, basis, "bodies" if applied else "nothing")
        self.started = sealed["request_id"]

    def answered(self, request_id: str, state: str, reason: str | None = None,
                 codes=()) -> None:
        """Hand over the answer to a request this entry dispatched: `unknown`; `unavailable` with
        the owner's reason and the gap codes it stated; or, for the check, `settled` with the
        stage its start now stands at, which is no longer pending."""
        if state not in ANSWERED or (state == "unknown") == bool(reason) or request_id is None or \
                request_id not in (self.started, self.checking) or \
                (state == "settled" and (request_id != self.checking or reason in PENDING)) or \
                (codes and state != "unavailable"):
            raise ValueError(f"no answer {state!r} to {request_id} is drawn here")
        self.answers[request_id] = (state, reason)
        self.refusals[request_id] = list(codes)
        if state == "settled":
            self.blocked = False

    def check(self) -> None:
        if self.checking is not None and (self.checking not in self.answers or
                                          self.settled() is not None):
            return
        asked = {"kind": "operation_query", "schema": 1,
                 "request_id": self.draft["request_id"]}
        sealed = self.seal(QUERY, self.draft["request_id"], asked)
        self.send(sealed, asked, "nothing")
        self.checking = sealed["request_id"]


def drive(store: storage.Store, request: dict, script: dict, at: str, dispatch=None) -> dict:
    """The trace of a whole script: the first frame, then one frame after each input."""
    entry = Entry(store, request, script, dispatch)
    frames = [entry.frame(0)]
    for index, given in enumerate(script["inputs"], start=1):
        entry.press(given)
        frames.append(entry.frame(index))
    return {"kind": "surface_trace", "schema": 1, "script_digest": canonical.digest_of(script),
            "client": dict(CLIENT), "mode": {"runs": "real"}, "frames": frames, "at": at}


def surface_drive(call) -> dict:
    """C12 `surface.drive`: the trace of the script, with a dispatcher that only records."""
    store = storage.of(call.state)
    trace = drive(store, call.request, journal.payload(call), journal.now(call))
    return journal.answered(call, "previewed", [trace])
