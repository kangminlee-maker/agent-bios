#!/usr/bin/env python3
"""Textual Corpus Studio.

Imported only for an interactive launch.  The module contains no persistence
logic: every read, plan, and apply goes through the supplied ``CorpusStore``.
"""
from __future__ import annotations

import difflib
import json
import re
from typing import Any
from urllib.parse import unquote

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Markdown,
    MarkdownViewer,
    Select,
    Static,
    TextArea,
    Tree,
)

try:
    from corpus_catalog import CLAUDE_HOOK_EVENTS
except ImportError:  # pragma: no cover - package import from repository root
    from .corpus_catalog import CLAUDE_HOOK_EVENTS


SURFACES = ("always", "relevant", "requested", "event", "delegated")
VIEWS = ("effective", "installed", "change", "diff", "history")


class Confirmation(ModalScreen[bool]):
    """One bounded confirmation; the caller decides what the answer means."""

    DEFAULT_CSS = """
    Confirmation { align: center middle; }
    Confirmation > Vertical { width: 62; height: auto; border: round $warning;
                              padding: 1 2; background: $surface; }
    Confirmation Horizontal { height: auto; align-horizontal: right; }
    Confirmation Button { margin-left: 1; }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.message, id="confirm-message")
            with Horizontal():
                yield Button("Keep editing", id="confirm-no")
                yield Button("Discard", id="confirm-yes", variant="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")


class CorpusMarkdownViewer(MarkdownViewer):
    """Keep all links inside Studio; never hand a URL to the operating system."""

    async def _on_markdown_link_clicked(self, message: Markdown.LinkClicked) -> None:
        message.stop()
        if message.href.startswith("corpus://"):
            ref = unquote(message.href.removeprefix("corpus://"))
            await self.app.select_ref(ref)  # type: ignore[attr-defined]
        else:
            self.app.notify("External links are disabled in Corpus Studio.", severity="warning")


class CorpusStudio(App[None]):
    """Searchable corpus library, editor, and revision-bound Preview → Apply flow."""

    TITLE = "Corpus Studio"
    SUB_TITLE = "Private authoring for future activated sessions"
    BINDINGS = [
        Binding("ctrl+f", "focus_search", "Search"),
        Binding("ctrl+l", "focus_library", "Library"),
        Binding("v", "cycle_view", "View"),
        Binding("c", "create", "Create"),
        Binding("e", "edit", "Edit"),
        Binding("delete", "remove", "Remove"),
        Binding("r", "restore", "Restore"),
        Binding("shift+r", "recover", "Recover"),
        Binding("f2", "focus_surface", "Surface"),
        Binding("escape", "cancel", "Back"),
        Binding("q", "request_quit", "Quit"),
    ]
    CSS = """
    Screen { layout: vertical; }
    #toolbar { height: 6; padding: 0 1; }
    #search-row, #action-row { height: 3; }
    #search { width: 1fr; }
    #view-select { width: 18; margin-left: 1; }
    #action-row Button { width: 1fr; min-width: 8; }
    #workspace { height: 1fr; }
    #library { width: 34; min-width: 24; border-right: solid $primary; }
    #detail { width: 1fr; padding: 0 1; }
    #member-select { display: none; height: 3; }
    #wiki { height: 1fr; }
    #editor-panel, #preview-panel { display: none; height: 1fr; }
    #editor-title { height: 3; }
    #editor-surface { height: 3; width: 32; }
    #primary-member-row { display: none; height: 3; }
    #primary-member-label { width: 20; }
    #editor-primary-member { width: 1fr; }
    #hook-binding-row { display: none; height: 3; }
    #editor-hook-event { width: 26; }
    #editor-hook-matcher { width: 1fr; margin-left: 1; }
    #editor-body { height: 1fr; border: round $primary; }
    #preview-text { height: 1fr; overflow: auto; border: round $warning;
                    padding: 1; }
    .actions { height: 3; align-horizontal: right; }
    .actions Button { margin-left: 1; }
    #status-line { height: 1; padding: 0 1; color: $text-muted; }
    """

    def __init__(self, store: Any) -> None:
        super().__init__()
        self.store = store
        self.items: list[dict[str, Any]] = []
        self.current_ref: str | None = None
        self.editor_ref: str | None = None
        self.editor_item: dict[str, Any] | None = None
        self.editor_initial = ("", "", "requested")
        self.current_member: str | None = None
        self.view_item: dict[str, Any] | None = None
        self.member_drafts: dict[str, str] = {}
        self.pending_plan: dict[str, Any] | None = None
        self.mode = "view"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="toolbar"):
            with Horizontal(id="search-row"):
                yield Input(placeholder="Search title, content, ref, package, domain, or state", id="search")
                yield Select([(view.title(), view) for view in VIEWS], value="effective",
                             allow_blank=False, id="view-select")
            with Horizontal(id="action-row"):
                yield Button("Create", id="create", compact=True)
                yield Button("Edit", id="edit", compact=True)
                yield Button("Remove", id="remove", variant="warning", compact=True)
                yield Button("Restore", id="restore", compact=True)
                yield Button("Recover", id="recover", compact=True)
                yield Button("Reset", id="reset", variant="error", compact=True)
        with Horizontal(id="workspace"):
            yield Tree("Corpus", id="library")
            with Vertical(id="detail"):
                yield Select([], prompt="Bundle document", allow_blank=True, id="member-select")
                yield CorpusMarkdownViewer(
                    "# Corpus Studio\n\nSelect an item from the library.",
                    show_table_of_contents=False,
                    open_links=False,
                    id="wiki",
                )
                with Vertical(id="editor-panel"):
                    yield Input(placeholder="Title", id="editor-title")
                    yield Select(
                        [
                            ("Always in activated sessions", "always"),
                            ("When relevant", "relevant"),
                            ("When requested", "requested"),
                            ("On a matching event (adapter verification required)", "event"),
                            ("When delegated (adapter verification required)", "delegated"),
                        ],
                        value="requested", allow_blank=False, id="editor-surface",
                    )
                    with Horizontal(id="primary-member-row"):
                        yield Label("Reconcile primary", id="primary-member-label")
                        yield Select([], prompt="Choose member", allow_blank=True,
                                     id="editor-primary-member")
                    with Horizontal(id="hook-binding-row"):
                        yield Select(
                            [(event, event) for event in sorted(CLAUDE_HOOK_EVENTS)],
                            value=sorted(CLAUDE_HOOK_EVENTS)[0], allow_blank=False, id="editor-hook-event",
                        )
                        yield Input(placeholder="Hook matcher", id="editor-hook-matcher")
                    yield TextArea(language="markdown", id="editor-body")
                    with Horizontal(classes="actions"):
                        yield Button("Cancel", id="editor-cancel")
                        yield Button("Preview", id="preview", variant="primary")
                with Vertical(id="preview-panel"):
                    yield Static("", id="preview-text", markup=False)
                    with Horizontal(classes="actions"):
                        yield Button("Cancel plan", id="plan-cancel")
                        yield Button("Apply", id="apply", variant="success")
        yield Static("Stored privately; no host session is activated by this screen.", id="status-line")
        yield Footer()

    async def on_mount(self) -> None:
        await self.refresh_library()
        self.query_one("#search", Input).focus()

    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self.query_one("#member-select", Select).disabled = mode == "preview"
        # Read navigation cannot change the target of an open draft or prepared plan.
        for selector in ("#search", "#view-select", "#library", "#create", "#edit",
                         "#remove", "#restore", "#recover", "#reset"):
            self.query_one(selector).disabled = mode != "view"
        self.query_one("#wiki").display = mode == "view"
        self.query_one("#editor-panel").display = mode == "editor"
        self.query_one("#preview-panel").display = mode == "preview"

    async def refresh_library(self, query: str = "") -> None:
        if self.mode != "view":
            return
        tree = self.query_one("#library", Tree)
        tree.reset("Corpus")
        try:
            self.items = self.store.list_items(include_removed=True)
        except Exception as exc:
            self.items = []
            tree.root.add_leaf(f"Unavailable: {exc}")
            tree.root.expand()
            self.query_one("#status-line", Static).update(str(exc))
            return
        visible = [item for item in self.items if self._matches(item, query)]
        groups: dict[tuple[str, str], Any] = {}
        state_nodes: dict[str, Any] = {}
        for item in visible:
            state = str(item.get("state", "active"))
            package = str(item.get("package_id", "unknown"))
            if state not in state_nodes:
                state_nodes[state] = tree.root.add(state.title())
                state_nodes[state].expand()
            key = (state, package)
            if key not in groups:
                groups[key] = state_nodes[state].add(package)
                groups[key].expand()
            groups[key].add_leaf(
                f"{item.get('title', item.get('ref'))} · {item.get('surface', '?')}",
                data=item.get("ref"),
            )
        tree.root.expand()
        status = self.store.status()
        self.query_one("#status-line", Static).update(
            f"{len(visible)}/{len(self.items)} items · authoring revision {status.get('revision', '?')[:12]} · "
            "changes affect future activated sessions only"
        )
        if visible and (self.current_ref is None or not any(i.get("ref") == self.current_ref for i in visible)):
            await self.select_ref(str(visible[0]["ref"]))

    @staticmethod
    def _matches(item: dict[str, Any], query: str) -> bool:
        if not query:
            return True
        fields = [item.get(key, "") for key in (
            "ref", "title", "body", "surface", "tier", "kind", "state", "package_id"
        )]
        fields.extend(item.get("domains", []))
        return query.casefold() in "\n".join(str(value) for value in fields).casefold()

    def _row(self, ref: str | None = None) -> dict[str, Any] | None:
        wanted = ref or self.current_ref
        return next((item for item in self.items if item.get("ref") == wanted), None)

    @staticmethod
    def _recoverable(row: dict[str, Any]) -> bool:
        return row.get("state") == "removed" and (
            row.get("package_id") == "@local/personal"
            or row.get("learning_source") is True
        )

    async def select_ref(self, ref: str) -> None:
        if self.mode != "view":
            return
        row = self._row(ref)
        if row is None:
            self.notify(f"Unknown CorpusRef: {ref}", severity="error")
            return
        self.current_ref = ref
        self.current_member = None
        view_value = self.query_one("#view-select", Select).value
        view = view_value if isinstance(view_value, str) else "effective"
        try:
            result = self.store.show(ref, view=view)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        self.view_item = result.get("item") if view == "effective" else None
        self._select_members(self.view_item)
        markdown = self._render_item(row, result, view)
        await self.query_one("#wiki", CorpusMarkdownViewer).document.update(markdown)
        self.query_one("#edit", Button).disabled = row.get("state") == "removed"
        self.query_one("#remove", Button).disabled = row.get("state") == "removed"
        self.query_one("#restore", Button).disabled = not bool(row.get("baseline_ref"))
        self.query_one("#recover", Button).disabled = not self._recoverable(row)

    def _select_members(self, item: dict[str, Any] | None, preferred: str | None = None) -> None:
        selector = self.query_one("#member-select", Select)
        members = item.get("members", {}) if item else {}
        primary = item.get("primary_member") if item else None
        usable = isinstance(members, dict) and primary in members
        self.current_member = preferred if usable and preferred in members else primary if usable else None
        selector.set_options([(name + (" (primary)" if name == primary else ""), name)
                              for name in members] if usable else [])
        selector.value = self.current_member if self.current_member is not None else Select.NULL
        selector.styles.display = "block" if usable and len(members) > 1 else "none"

    def _editor_members(self) -> dict[str, str]:
        members = dict(self.member_drafts)
        if self.current_member in members:
            members[self.current_member] = self.query_one("#editor-body", TextArea).text
        return members

    @staticmethod
    def _render_item(row: dict[str, Any], result: dict[str, Any], view: str) -> str:
        if view == "effective" and isinstance(result.get("item"), dict):
            item = result["item"]
            links = "\n".join(
                f"- [{ref}](corpus://{ref})" for ref in item.get("dependencies", [])
            ) or "None"
            conflict = item.get("content_conflict")
            reconciliation = ""
            if isinstance(conflict, dict):
                members = ", ".join(str(path) for path in conflict.get("members", []))
                reconciliation = (
                    "\n> ⚠ Legacy content needs reconciliation before activation. "
                    "Edit the body to the intended member text, or choose a primary member through the API."
                    + (f" Available members: {members}." if members else "") + "\n"
                )
            return (
                f"# {item.get('title', item.get('ref'))}\n\n"
                f"`{item.get('ref')}` · **{row.get('state', 'active')}** · "
                f"{item.get('surface')} · {item.get('kind')}\n\n"
                f"{reconciliation}\n{item.get('body', '')}\n\n## Dependencies\n\n{links}\n"
                + ("\n## Native consumption\n\nRequires explicit `agent-launch --corpus-native`.\n"
                   if item.get("kind") == "hook" else "")
            )
        payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        return f"# {row.get('title', row.get('ref'))}\n\n## {view.title()}\n\n```json\n{payload}\n```\n"

    async def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if isinstance(event.node.data, str):
            await self.select_ref(event.node.data)

    async def on_markdown_link_clicked(self, message: Markdown.LinkClicked) -> None:
        # CorpusMarkdownViewer normally handles this before it bubbles.  Keeping
        # the app handler makes direct Markdown messages safe in tests and future layouts.
        if message.href.startswith("corpus://"):
            message.stop()
            await self.select_ref(unquote(message.href.removeprefix("corpus://")))

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            await self.refresh_library(event.value)

    async def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "view-select" and self.mode == "view" and isinstance(event.value, str) and self.current_ref:
            await self.select_ref(self.current_ref)
        elif event.select.id == "member-select" and isinstance(event.value, str):
            item = self.editor_item if self.mode == "editor" else self.view_item
            if not item or event.value not in item.get("members", {}) or event.value == self.current_member:
                return
            if self.mode == "editor":
                self.member_drafts = self._editor_members()
                self.current_member = event.value
                self.query_one("#editor-body", TextArea).text = self.member_drafts[event.value]
            elif self.mode == "view":
                self.current_member = event.value
                primary = item.get("primary_member")
                body = item["members"][event.value]
                if event.value == primary:
                    markdown = self._render_item(self._row() or item, {"item": item}, "effective")
                elif event.value.endswith(".md"):
                    markdown = f"# {event.value}\n\n{body}"
                else:
                    fence = "`" * (max(2, max((len(run) for run in re.findall(r'`+', body)), default=0)) + 1)
                    markdown = f"# {event.value}\n\n{fence}\n{body}\n{fence}\n"
                await self.query_one("#wiki", CorpusMarkdownViewer).document.update(markdown)

    def editor_dirty(self) -> bool:
        if self.mode != "editor":
            return False
        current = (
            self.query_one("#editor-title", Input).value,
            self._editor_members().get(self.editor_item.get("primary_member"), self.query_one("#editor-body", TextArea).text)
            if self.editor_item else self.query_one("#editor-body", TextArea).text,
            self.query_one("#editor-surface", Select).value,
            self.query_one("#editor-primary-member", Select).value
            if self.editor_item and isinstance(self.editor_item.get("content_conflict"), dict) else "",
            self.query_one("#editor-hook-event", Select).value if self.editor_item and self.editor_item.get("kind") == "hook" else "",
            self.query_one("#editor-hook-matcher", Input).value if self.editor_item and self.editor_item.get("kind") == "hook" else "",
        )
        return current != self.editor_initial or bool(self.editor_item and self.member_drafts
                                                     and self._editor_members() != self.editor_item.get("members", {}))

    def _open_editor(self, item: dict[str, Any] | None) -> None:
        if self.mode != "view":
            return
        preferred = self.current_member if item and item.get("ref") == self.current_ref else None
        self.editor_item = item
        self.editor_ref = str(item["ref"]) if item else None
        title = str(item.get("title", "")) if item else ""
        body = str(item.get("body", "")) if item else ""
        surface = str(item.get("surface", "requested")) if item else "requested"
        hook = item.get("hook") if item else None
        is_hook = bool(item and item.get("kind") == "hook")
        conflict = item.get("content_conflict") if item else None
        self.member_drafts = dict(item.get("members", {})) if item and not conflict else {}
        self._select_members(item if not conflict else None, preferred)
        conflict_members = conflict.get("members", []) if isinstance(conflict, dict) else []
        primary_select = self.query_one("#editor-primary-member", Select)
        primary_select.set_options([(str(path), str(path)) for path in conflict_members])
        primary_select.clear()
        self.query_one("#primary-member-row").styles.display = "block" if conflict_members else "none"
        self.query_one("#editor-title", Input).value = title
        self.query_one("#editor-body", TextArea).text = self.member_drafts.get(self.current_member, body)
        self.query_one("#editor-surface", Select).value = surface
        self.query_one("#hook-binding-row").styles.display = "block" if is_hook else "none"
        if is_hook:
            event = hook.get("event") if isinstance(hook, dict) else sorted(CLAUDE_HOOK_EVENTS)[0]
            matcher = hook.get("matcher") if isinstance(hook, dict) else ""
            self.query_one("#editor-hook-event", Select).value = event
            self.query_one("#editor-hook-matcher", Input).value = matcher
        else:
            self.query_one("#editor-hook-matcher", Input).value = ""
        self.editor_initial = (title, body, surface, primary_select.value if conflict_members else "",
                               event if is_hook else "", matcher if is_hook else "")
        self._set_mode("editor")
        self.query_one("#editor-title", Input).focus()

    def action_create(self) -> None:
        self._open_editor(None)

    def action_edit(self) -> None:
        row = self._row()
        if row is None or row.get("state") == "removed":
            self.notify("Select an active item first.", severity="warning")
            return
        self._open_editor(row)

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_focus_library(self) -> None:
        self.query_one("#library", Tree).focus()

    def action_focus_surface(self) -> None:
        if self.mode == "editor":
            self.query_one("#editor-surface", Select).focus()

    def action_cycle_view(self) -> None:
        view = self.query_one("#view-select", Select)
        current = view.value if isinstance(view.value, str) else VIEWS[0]
        view.value = VIEWS[(VIEWS.index(current) + 1) % len(VIEWS)]

    def _stage_current_operation(self, operation: str) -> None:
        if self.mode != "view":
            return
        row = self._row()
        if row is None:
            self.notify("Select an item first.", severity="warning")
            return
        if operation == "remove" and row.get("state") == "removed":
            self.notify("The selected item is already removed.", severity="warning")
            return
        if operation == "restore" and not row.get("baseline_ref"):
            self.notify("Restore is available only for an installed item.", severity="warning")
            return
        if operation == "recover" and not self._recoverable(row):
            self.notify(
                "Recover is available only for a removed personal item or learning.",
                severity="warning",
            )
            return
        payload: dict[str, Any] = {"operation": operation, "ref": row["ref"]}
        if operation == "remove":
            payload["item_digest"] = row.get("digest")
        self._stage_plan(payload, f"{operation.title()} {row['ref']} for future snapshots.")

    def action_remove(self) -> None:
        self._stage_current_operation("remove")

    def action_restore(self) -> None:
        self._stage_current_operation("restore")

    def action_recover(self) -> None:
        self._stage_current_operation("recover")

    async def action_cancel(self) -> None:
        if self.mode == "preview":
            self.pending_plan = None
            self._set_mode("view")
            if self.current_ref:
                await self.select_ref(self.current_ref)
        elif self.mode == "editor":
            await self._cancel_editor()
        else:
            await self.action_request_quit()

    async def _cancel_editor(self) -> None:
        if not self.editor_dirty():
            self._set_mode("view")
            if self.current_ref:
                await self.select_ref(self.current_ref)
            return
        self.push_screen(Confirmation("Discard the unsaved draft?"), self._discard_editor)

    async def _discard_editor(self, discard: bool | None) -> None:
        if discard:
            self._set_mode("view")
            if self.current_ref:
                await self.select_ref(self.current_ref)

    async def action_request_quit(self) -> None:
        if self.editor_dirty():
            self.push_screen(Confirmation("Discard the unsaved draft and exit Studio?"), self._discard_and_exit)
        else:
            self.exit()

    def _discard_and_exit(self, discard: bool | None) -> None:
        if discard:
            self.exit()

    def _editor_payload(self) -> tuple[dict[str, Any], str]:
        title = self.query_one("#editor-title", Input).value.strip()
        body = self.query_one("#editor-body", TextArea).text
        members = self._editor_members()
        if self.editor_item and self.member_drafts:
            body = members[self.editor_item["primary_member"]]
        value = self.query_one("#editor-surface", Select).value
        surface = value if isinstance(value, str) else "requested"
        if not title:
            raise ValueError("Title is required.")
        if self.editor_item is None:
            item = {
                "title": title, "body": body, "surface": surface,
                "tier": "env-personal", "domains": ["personal"], "kind": "rule",
                "members": {"content.md": body},
            }
            return {"operation": "create", "item": item}, f"Create {title!r} on {surface}."
        old = str(self.editor_item.get("body", ""))
        patch = {
            "title": title, "body": body, "surface": surface,
        }
        if self.member_drafts and members != self.editor_item.get("members", {}):
            patch["members"] = members
        if isinstance(self.editor_item.get("content_conflict"), dict):
            primary = self.query_one("#editor-primary-member", Select).value
            if not isinstance(primary, str):
                raise ValueError("Choose the primary member to reconcile legacy content.")
            patch["primary_member"] = primary
        if self.editor_item.get("kind") == "hook":
            event = self.query_one("#editor-hook-event", Select).value
            matcher = self.query_one("#editor-hook-matcher", Input).value
            if not isinstance(event, str) or event not in CLAUDE_HOOK_EVENTS:
                raise ValueError("Choose a supported Claude hook event.")
            if not matcher or "\n" in matcher or "\r" in matcher:
                raise ValueError("Hook matcher must be one non-empty line.")
            patch["hook"] = {"event": event, "matcher": matcher}
        diff = "".join(difflib.unified_diff(
            old.splitlines(True), body.splitlines(True), fromfile="current", tofile="planned",
        )) or "(content unchanged; metadata will change)"
        if "members" in patch:
            diff = "\n".join("".join(difflib.unified_diff(
                self.editor_item["members"][name].splitlines(True), value.splitlines(True),
                fromfile=f"current/{name}", tofile=f"planned/{name}",
            )) for name, value in members.items() if value != self.editor_item["members"][name])
        hook_summary = ""
        if "hook" in patch:
            hook_summary = f"\nHook binding: {patch['hook']['event']} / {patch['hook']['matcher']}"
        return {
            "operation": "update", "ref": self.editor_item["ref"],
            "item_digest": self.editor_item["digest"], "patch": patch,
        }, diff + hook_summary

    def _stage_plan(self, payload: dict[str, Any], summary: str) -> None:
        try:
            plan = self.store.plan(payload)
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        self.pending_plan = plan
        preview = (
            f"{summary}\n\nPlan: {plan['plan_id']}\n"
            f"Expected revision: {plan['expected_revision']}\n"
            f"Result revision: {plan['result_revision']}\n\n"
            "Pinned/running sessions will not change. Apply affects future activated sessions only.\n\n"
            f"Details:\n{json.dumps(plan.get('details', {}), ensure_ascii=False, indent=2, sort_keys=True)}"
        )
        self.query_one("#preview-text", Static).update(preview)
        self._set_mode("preview")

    async def _apply_pending(self) -> None:
        if self.pending_plan is None:
            return
        try:
            result = self.store.apply(
                self.pending_plan["plan_id"],
                expected_revision=self.pending_plan["expected_revision"],
            )
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return
        ref = result.get("details", {}).get("ref")
        self.pending_plan = None
        self._set_mode("view")
        await self.refresh_library(self.query_one("#search", Input).value)
        if isinstance(ref, str) and self._row(ref):
            await self.select_ref(ref)
        self.notify("Applied. Future activated sessions use the new revision.")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        if button == "create":
            self.action_create()
        elif button == "edit":
            self.action_edit()
        elif button == "editor-cancel":
            await self._cancel_editor()
        elif button == "preview":
            try:
                payload, summary = self._editor_payload()
            except ValueError as exc:
                self.notify(str(exc), severity="error")
            else:
                self._stage_plan(payload, summary)
        elif button == "plan-cancel":
            await self.action_cancel()
        elif button == "apply":
            await self._apply_pending()
        elif button in {"remove", "restore", "recover"}:
            self._stage_current_operation(button)
        elif button == "reset":
            self._stage_plan(
                {"operation": "reset"},
                "Reset future authoring to the last successful install tuple; preserve sources, history, and pins.",
            )


def run(store: Any) -> None:
    CorpusStudio(store).run()
