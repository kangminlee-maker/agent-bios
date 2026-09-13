#!/usr/bin/env python3
"""Textual Instructions Studio.

Imported only for an interactive launch.  The module contains no persistence
logic: every read, plan, and apply goes through the supplied ``InstructionsStore``.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote, unquote

from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
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
    from instructions_catalog import HOOK_EVENTS
except ImportError:  # pragma: no cover - package import from repository root
    from .instructions_catalog import HOOK_EVENTS


SURFACES = ("always", "relevant", "requested", "event", "delegated")
VIEWS = ("effective", "installed", "change", "diff", "history")


def availability_label(state: str) -> str:
    return "available" if state == "active" else state


def guide_pointers(item: dict[str, Any], inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Display literal guide references, not inferred dependencies or new routing."""
    if item.get("kind") != "rule":
        return []
    paths = dict.fromkeys(re.findall(r"\bguides/[A-Za-z0-9][A-Za-z0-9_./-]*\.md\b", item.get("body", "")))
    result = []
    for path in paths:
        if ".." in PurePosixPath(path).parts:
            continue
        matches = [candidate for candidate in inventory
                   if candidate.get("package_id") == item.get("package_id")
                   and candidate.get("kind") == "guide" and path in candidate.get("members", {})]
        result.append({"path": path, "target": matches[0] if len(matches) == 1 else None,
                       "problem": "Ambiguous guide reference" if matches else "Not found in this package"})
    return result


def library_label(item: dict[str, Any], inventory: list[dict[str, Any]]) -> Text:
    pointers = guide_pointers(item, inventory)
    label = Text()
    mark = "-" if item.get("state") == "removed" else "x" if item.get("enabled", True) else " "
    label.append(f"[{mark}]" + ("* " if item.get("enabled_pending") else " "))
    if pointers:
        label.append("→ GUIDE ", style="bold cyan")
        label.append(", ".join(PurePosixPath(pointer["path"]).stem for pointer in pointers))
        label.append(" · ")
    label.append(f"{item.get('title', item.get('ref'))} · {item.get('surface', '?')}")
    return label


def render_member_body(body: str, member: str | None, kind: str | None = None) -> str:
    """Render prose as Markdown and preserve source files as literal code."""
    suffix = PurePosixPath(member).suffix.lower() if member else ""
    if suffix in {".md", ".markdown"} or (not member and kind != "hook"):
        return body
    language = {".py": "python", ".json": "json", ".toml": "toml",
                ".sh": "bash", ".zsh": "bash", ".yaml": "yaml", ".yml": "yaml",
                ".js": "javascript", ".ts": "typescript"}.get(suffix, "")
    fence = "`" * max(3, 1 + max((len(run) for run in re.findall(r"`+", body)), default=0))
    return f"{fence}{language}\n{body}\n{fence}"


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


class InstructionsMarkdownViewer(MarkdownViewer):
    """Keep all links inside Studio; never hand a URL to the operating system."""

    BINDINGS = [
        Binding("left", "left_or_library", "Library", show=False),
        Binding("up", "up_or_controls", "Controls", show=False),
        Binding("down", "down_or_pending", "Pending choices", show=False),
    ]

    def action_left_or_library(self) -> None:
        if self.scroll_x <= 0:
            self.app.action_focus_library()
        else:
            self.action_scroll_left()

    def action_up_or_controls(self) -> None:
        if self.scroll_y <= 0:
            if not self.app._focus_id("member-select"):
                self.app._focus_controls()
        else:
            self.action_scroll_up()

    def action_down_or_pending(self) -> None:
        if self.scroll_y >= self.max_scroll_y:
            self.app._focus_id("enablement-preview")
        else:
            self.action_scroll_down()

    async def _on_markdown_link_clicked(self, message: Markdown.LinkClicked) -> None:
        # stop() prevents bubbling, not the inherited MarkdownViewer handler.
        # Its default go() would try to load instructions:// as a filesystem path.
        message.prevent_default()
        message.stop()
        if message.href.startswith("instructions://"):
            ref = unquote(message.href.removeprefix("instructions://"))
            await self.app.select_ref(ref)  # type: ignore[attr-defined]
        else:
            self.app.notify("External links are disabled in Instructions Studio.", severity="warning")


class InstructionsSearch(Input):
    """Leave search with arrows without taking editing keys away from text."""

    BINDINGS = [
        Binding("down", "focus_controls", "Controls", show=False),
        Binding("right", "right_or_view", "View", show=False),
    ]

    def action_focus_controls(self) -> None:
        self.app._focus_controls()

    def action_right_or_view(self) -> None:
        if self.selection.start == self.selection.end == len(self.value):
            self.app._focus_id("view-select")
        else:
            self.action_cursor_right()


class InstructionsTree(Tree):
    """Space is local to the library, never intercepted in text inputs."""

    BINDINGS = [
        Binding("space", "toggle_item", "On/off"),
        Binding("up", "up_or_controls", "Controls", show=False),
        Binding("down", "down_or_pending", "Pending choices", show=False),
        Binding("right", "focus_document", "Document", show=False),
    ]

    def action_up_or_controls(self) -> None:
        if self.cursor_line <= 0:
            self.app._focus_controls()
        else:
            self.action_cursor_up()

    def action_down_or_pending(self) -> None:
        before = self.cursor_node
        self.action_cursor_down()
        if self.cursor_node is before:
            self.app._focus_id("enablement-preview")

    def action_focus_document(self) -> None:
        self.app._focus_document()

    async def action_toggle_item(self) -> None:
        node = self.cursor_node
        if node is not None and isinstance(node.data, str):
            await self.app.toggle_enabled(node.data)
        else:
            self.action_toggle_node()


class InstructionsStudio(App[None]):
    """Searchable instructions library, editor, and revision-bound Preview → Apply flow."""

    TITLE = "Instructions Studio"
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
    #enablement-bar { height: 3; display: none; }
    #enablement-summary { width: 1fr; padding: 1; }
    #enablement-bar Button { margin-right: 1; }
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
        self.toggle_drafts: dict[str, bool] = {}
        self.toggle_original: dict[str, bool] = {}
        self.toggle_revision: str | None = None
        self.mode = "view"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="toolbar"):
            with Horizontal(id="search-row"):
                yield InstructionsSearch(placeholder="Search title, content, ref, package, domain, or state (↓ controls)", id="search")
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
            yield InstructionsTree("Instructions", id="library")
            with Vertical(id="detail"):
                yield Select([], prompt="Bundle document", allow_blank=True, id="member-select")
                yield InstructionsMarkdownViewer(
                    "# Instructions Studio\n\nSelect an item from the library.",
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
                            [(event, event) for event in sorted(HOOK_EVENTS)],
                            value=sorted(HOOK_EVENTS)[0], allow_blank=False, id="editor-hook-event",
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
        with Horizontal(id="enablement-bar"):
            yield Static("", id="enablement-summary", markup=False)
            yield Button("Preview on/off", id="enablement-preview", variant="primary")
            yield Button("Discard on/off", id="enablement-discard")
        yield Static("Stored privately; no host session is activated by this screen.", id="status-line")
        yield Footer()

    async def on_mount(self) -> None:
        await self.refresh_library()
        self.query_one("#search", Input).focus()

    @staticmethod
    def _focusable(widget: Any) -> bool:
        return widget.focusable and all(getattr(node, "display", True) for node in [widget, *widget.ancestors])

    def _focus_id(self, *ids: str) -> bool:
        # Query the current screen only: arrows must never escape a modal.
        for ident in ids:
            for widget in self.screen.query(f"#{ident}"):
                if self._focusable(widget):
                    widget.focus()
                    return True
        return False

    def _focus_controls(self) -> None:
        for button in self.screen.query("#action-row Button"):
            if self._focusable(button):
                button.focus()
                return
        self._focus_id("library" if getattr(self.focused, "id", None) == "search" else "search")

    def _focus_document(self) -> None:
        if self.mode != "view" or self._focus_id("member-select"):
            return
        for viewer in self.screen.query("#wiki"):
            if self._focusable(viewer.document):
                viewer.document.focus()

    def on_key(self, event: Key) -> None:
        focused = self.focused
        moved = False
        if isinstance(focused, Button) and focused.parent is not None:
            siblings = [button for button in focused.parent.query(Button)
                        if button.parent is focused.parent and self._focusable(button)]
            if event.key in {"left", "right"} and focused in siblings:
                index = siblings.index(focused) + (-1 if event.key == "left" else 1)
                if 0 <= index < len(siblings):
                    siblings[index].focus()
                    moved = True
            elif event.key in {"up", "down"} and len(self.screen_stack) == 1:
                if focused.parent.id == "action-row":
                    moved = self._focus_id("search" if event.key == "up" else "library")
                elif focused.parent.id == "enablement-bar":
                    moved = self._focus_id("library")
                elif self.mode == "editor" and event.key == "up":
                    moved = self._focus_id("editor-body")
        elif isinstance(focused, Select) and not focused.expanded and self.mode == "view":
            if event.key == "left" and focused.id in {"view-select", "member-select"}:
                moved = self._focus_id("search" if focused.id == "view-select" else "library")
            elif event.key == "right" and focused.id == "member-select":
                for viewer in self.screen.query("#wiki"):
                    if self._focusable(viewer.document):
                        viewer.document.focus()
                        moved = True
        if moved:
            event.prevent_default()
            event.stop()

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
        self._toggle_controls()
        # Hiding a panel does not reliably release its focused child. Choose a
        # visible, non-destructive entry point for the next screen state.
        if mode == "preview":
            self._focus_id("plan-cancel")
        elif mode == "view":
            self._focus_id("enablement-preview", "library")

    def _display_items(self) -> list[dict[str, Any]]:
        return [dict(row, enabled=self.toggle_drafts[row["ref"]], enabled_pending=True)
                if row.get("ref") in self.toggle_drafts else row for row in self.items]

    def _toggle_controls(self) -> None:
        pending = bool(self.toggle_drafts)
        self.query_one("#enablement-bar").display = pending and self.mode == "view"
        self.query_one("#enablement-summary", Static).update(
            f"{len(self.toggle_drafts)} unapplied on/off change(s) · * = pending")
        if self.mode == "view":
            for selector in ("#create", "#reset"):
                self.query_one(selector).disabled = pending
            if pending:
                for selector in ("#edit", "#remove", "#restore", "#recover"):
                    self.query_one(selector).disabled = True

    async def _repaint_enablement(self) -> None:
        displayed = self._display_items()
        by_ref = {row["ref"]: row for row in displayed}
        nodes = [self.query_one("#library", Tree).root]
        while nodes:
            node = nodes.pop()
            if isinstance(node.data, str) and node.data in by_ref:
                node.set_label(library_label(by_ref[node.data], displayed))
            nodes.extend(node.children)
        self._toggle_controls()
        if self.current_ref:
            await self.select_ref(self.current_ref)

    async def toggle_enabled(self, ref: str) -> None:
        if self.mode != "view":
            return
        row = self._row(ref)
        if row is None or row.get("state") == "removed":
            self.notify("Recover or restore this item before changing its use.", severity="warning")
            return
        if not self.toggle_drafts:
            self.toggle_revision = row["revision"]
        original = self.toggle_original.setdefault(ref, row["enabled"])
        value = not self.toggle_drafts.get(ref, row["enabled"])
        if value == original:
            self.toggle_drafts.pop(ref, None)
            self.toggle_original.pop(ref, None)
        else:
            self.toggle_drafts[ref] = value
        if not self.toggle_drafts:
            self.toggle_revision = None
        await self._repaint_enablement()

    def _clear_toggle_drafts(self) -> None:
        self.toggle_drafts.clear()
        self.toggle_original.clear()
        self.toggle_revision = None

    async def _discard_toggles(self) -> None:
        self._clear_toggle_drafts()
        self._toggle_controls()
        await self.refresh_library(self.query_one("#search", Input).value)
        if self.current_ref:
            await self.select_ref(self.current_ref)
        self._focus_id("library")

    def _preview_toggles(self) -> None:
        if not self.toggle_drafts or self.mode != "view":
            return
        summary = "Use in future sessions (no content is deleted):\n" + "\n".join(
            f"{'ON' if enabled else 'OFF'}  {ref}" for ref, enabled in self.toggle_drafts.items())
        self._stage_plan({"operation": "enable", "items": dict(self.toggle_drafts),
                          "expected_revision": self.toggle_revision}, summary)

    async def refresh_library(self, query: str = "") -> None:
        if self.mode != "view":
            return
        tree = self.query_one("#library", Tree)
        tree.reset("Instructions")
        try:
            self.items = self.store.list_items(include_removed=True)
        except Exception as exc:
            self.items = []
            tree.root.add_leaf(f"Unavailable: {exc}")
            tree.root.expand()
            self.query_one("#status-line", Static).update(str(exc))
            return
        visible = [item for item in self.items if self._matches(item, query)]
        displayed = self._display_items()
        display_by_ref = {item["ref"]: item for item in displayed}
        groups: dict[tuple[str, str], Any] = {}
        state_nodes: dict[str, Any] = {}
        for item in visible:
            state = str(item.get("state", "active"))
            package = str(item.get("package_id", "unknown"))
            if state not in state_nodes:
                state_nodes[state] = tree.root.add(availability_label(state).title())
                state_nodes[state].expand()
            key = (state, package)
            if key not in groups:
                groups[key] = state_nodes[state].add(package)
                groups[key].expand()
            groups[key].add_leaf(
                library_label(display_by_ref[item["ref"]], displayed),
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
        self._toggle_controls()

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
            self.notify(f"Unknown InstructionsRef: {ref}", severity="error")
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
        await self.query_one("#wiki", InstructionsMarkdownViewer).document.update(markdown)
        self.query_one("#edit", Button).disabled = row.get("state") == "removed"
        self.query_one("#remove", Button).disabled = row.get("state") == "removed"
        self.query_one("#restore", Button).disabled = not bool(row.get("baseline_ref"))
        self.query_one("#recover", Button).disabled = not self._recoverable(row)
        self._toggle_controls()

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

    def _render_item(self, row: dict[str, Any], result: dict[str, Any], view: str) -> str:
        if view == "effective" and isinstance(result.get("item"), dict):
            item = result["item"]
            links = "\n".join(
                f"- [{ref}](instructions://{ref})" for ref in item.get("dependencies", [])
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
            body = render_member_body(item.get("body", ""), item.get("primary_member"), item.get("kind"))
            displayed = self._display_items()
            display_row = next((entry for entry in displayed if entry.get("ref") == item.get("ref")), row)
            pointers = guide_pointers(item, displayed)
            guide_links = ""
            if pointers:
                lines = []
                for pointer in pointers:
                    target = pointer["target"]
                    if target is None:
                        lines.append(f"- `{pointer['path']}` — {pointer['problem']}")
                    else:
                        destination = quote(target["ref"], safe="@/:")
                        use = "ON" if target.get("enabled", True) else "OFF — linked guide disabled"
                        lines.append(f"- [{pointer['path']}](instructions://{destination}) — "
                                     f"**{target['surface']}** · {availability_label(target.get('state', 'active'))} · {use}")
                guide_links = (
                    "## Guide pointer\n\nThis rule explicitly references the following guide(s). "
                    "The rule keeps its own consumption surface; these links do not change "
                    "delivery or prove that a guide was loaded.\n\n" + "\n".join(lines) + "\n\n## Rule\n\n"
                )
            return (
                f"# {item.get('title', item.get('ref'))}\n\n"
                f"`{item.get('ref')}` · **{availability_label(row.get('state', 'active'))}** · "
                f"{item.get('surface')} · {item.get('kind')}\n\n"
                f"Use in future sessions: **{'ON' if display_row.get('enabled', True) else 'OFF'}**"
                + (" (pending; not applied)" if display_row.get("enabled_pending") else " (saved selection)")
                + ". Inclusion is not proof of loading or permission to execute.\n\n"
                f"{guide_links}{reconciliation}\n{body}\n\n## Dependencies\n\n{links}\n"
                + ("\n## Native consumption\n\nRequires explicit `agent-launch --instructions-native`.\n"
                   if item.get("kind") == "hook" else "")
            )
        payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        return f"# {row.get('title', row.get('ref'))}\n\n## {view.title()}\n\n```json\n{payload}\n```\n"

    async def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if isinstance(event.node.data, str):
            await self.select_ref(event.node.data)

    async def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        tree = self.query_one("#library", Tree)
        # Ignore queued highlights superseded by another cursor move or tree rebuild.
        if self.mode != "view" or event.node is not tree.cursor_node:
            return
        if isinstance(event.node.data, str):
            await self.select_ref(event.node.data)
            return
        # A group is not the previously displayed item: never leave its edit/delete
        # actions live while the cursor points at a different kind of node.
        self.current_ref = None
        self.view_item = None
        self._select_members(None)
        for selector in ("#edit", "#remove", "#restore", "#recover"):
            self.query_one(selector, Button).disabled = True
        label = str(event.node.label.plain)
        await self.query_one("#wiki", InstructionsMarkdownViewer).document.update(
            f"# Instructions group\n\n{label}\n\nMove the cursor to an instruction item to read it."
        )

    async def on_markdown_link_clicked(self, message: Markdown.LinkClicked) -> None:
        # InstructionsMarkdownViewer normally handles this before it bubbles.  Keeping
        # the app handler makes direct Markdown messages safe in tests and future layouts.
        if message.href.startswith("instructions://"):
            message.stop()
            await self.select_ref(unquote(message.href.removeprefix("instructions://")))

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
                else:
                    markdown = f"# {event.value}\n\n{render_member_body(body, event.value)}\n"
                await self.query_one("#wiki", InstructionsMarkdownViewer).document.update(markdown)

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
        if self.toggle_drafts:
            self.notify("Apply or discard on/off changes first.", severity="warning")
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
            event = hook.get("event") if isinstance(hook, dict) else sorted(HOOK_EVENTS)[0]
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
        elif self.toggle_drafts:
            self.push_screen(Confirmation("Discard unapplied on/off changes and exit Studio?"), self._discard_and_exit)
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
            if not isinstance(event, str) or event not in HOOK_EVENTS:
                raise ValueError("Choose a supported hook event.")
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
        if self.toggle_drafts and payload.get("operation") != "enable":
            self.notify("Apply or discard on/off changes first.", severity="warning")
            return
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
        if result.get("details", {}).get("operation") == "enable":
            self._clear_toggle_drafts()
        self.pending_plan = None
        self._set_mode("view")
        await self.refresh_library(self.query_one("#search", Input).value)
        if isinstance(ref, str) and self._row(ref):
            await self.select_ref(ref)
        self.notify("Applied. Future activated sessions use the new revision.")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        if button == "enablement-preview":
            self._preview_toggles()
        elif button == "enablement-discard":
            await self._discard_toggles()
        elif button == "create":
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
    InstructionsStudio(store).run()
