"""Textual installation client over the shared setup controller."""
from __future__ import annotations

import copy
import json
import re
import threading
from pathlib import Path
from typing import Any

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button, Checkbox, Collapsible, Header, Input, Label,
    LoadingIndicator, Select, SelectionList, Static, TextArea,
)
from textual.widgets.selection_list import Selection

try:
    from corpus_setup import SetupError, format_setup_result, review_summary
    import corpus_setup_i18n as i18n
except ImportError:
    from .corpus_setup import SetupError, format_setup_result, review_summary
    from . import corpus_setup_i18n as i18n


STAGES = ("Choose corpus", "Prepare personal instructions", "Choose dependencies", "Review setup")
LANGUAGE_TITLE = "Language / 언어 / 言語"
LANGUAGE_CONTINUE = "Continue / 계속 / 続ける"
LANGUAGE_CANCEL = "Cancel / 취소 / 中止"


def visible(value: Any) -> str:
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", " ", str(value))


class SetupApp(App[dict[str, Any]]):
    """Four guided screens; only the controller's Apply performs setup effects."""

    TITLE = "agent-bios setup"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+c", "cancel", "Cancel", show=False, priority=True),
        Binding("ctrl+q", "cancel", "Cancel", show=False, priority=True),
    ]
    CSS = """
    Screen { background: $background; }
    #frame { padding: 0 1; height: 1fr; }
    #step-title { height: 2; text-style: bold; color: $accent; }
    #language-select { margin-bottom: 1; }
    #language-continue { width: auto; min-width: 28; dock: right; }
    #key-help { height: auto; max-height: 2; color: $text-muted; padding: 0 1; }
    #body { height: 1fr; }
    .stage { height: auto; }
    Label { width: 100%; height: auto; margin-bottom: 1; }
    #corpus-mode { margin-bottom: 1; }
    #corpus-choices { height: 9; margin-bottom: 1; }
    #corpus-help, #source-help, #dependency-help, #retained-corpus-help, #app-bridge-help { color: $text-muted; }
    #retained-corpus-choices { height: auto; max-height: 6; margin-bottom: 1; }
    #app-bridge-help { height: auto; margin: 1 0; }
    #project-actions { height: 3; }
    #project-path { width: 1fr; }
    #add-project, #clear-projects { min-width: 12; width: auto; }
    #project-list, #source-notes { height: auto; margin: 1 0; }
    #source-choices { height: 10; }
    #dependency-choices { height: 12; }
    #dependency-detail { height: auto; margin-top: 1; }
    #source-selection, #dependency-selection, #source-detail, #inventory-reference { width: 100%; height: auto; }
    #summary { height: auto; padding: 0 1; }
    #exact-json, #operation-log { height: 12; }
    Collapsible { height: auto; margin-top: 1; }
    #status { width: 100%; height: auto; max-height: 4; margin-top: 1; }
    #working { height: 1; }
    #actions { height: 3; margin-top: 1; }
    #actions Button { min-width: 12; margin-right: 1; }
    #next, #apply, #done { dock: right; }
    """

    def __init__(self, installer: Any, *, dry_run: bool = False,
                 initial_plan: dict[str, Any] | None = None, controller: Any = None):
        super().__init__()
        self.installer = installer
        self.language = i18n.detect_language(getattr(installer, "env", {}))
        self.dry_run = dry_run
        self.initial_plan = copy.deepcopy(initial_plan)
        self.controller = controller
        self.plan: dict[str, Any] = {}
        self.preview_result: dict[str, Any] | None = None
        self.result: dict[str, Any] | None = None
        self.backend_error: Exception | None = None
        self.step = -1
        self.ready = False
        self.busy = False
        self.applying = False
        self.started_effects = False
        self.closing = False
        self.cancel_requested = threading.Event()
        self.discovery_serial = 0
        self.sources: list[dict[str, Any]] = []
        self.source_omitted: list[dict[str, Any]] = []
        self.sources_loaded = False
        self.operation_output: list[str] = []
        self.status_message = "Choose your language to continue."
        self.status_values: dict[str, Any] = {}

    def _t(self, message: str, **values) -> str:
        return i18n.translate(self.language, message, **values)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="frame"):
            yield Static(self._t(LANGUAGE_TITLE), id="step-title")
            with VerticalScroll(id="body"):
                with Vertical(id="language-panel", classes="stage"):
                    yield Label(self._t("Choose your language to continue."), id="language-help")
                    yield Select(i18n.LANGUAGES, value=self.language, allow_blank=False, id="language-select")
                with Vertical(id="corpus-panel", classes="stage"):
                    yield Label(self._t("Choose what future activated launches may use. App tasks require their own explicit use."), id="corpus-help")
                    yield Select([
                        (self._t("No active corpus"), "none"),
                        (self._t("All available corpus"), "all"),
                        (self._t("Choose supplied packages or domains"), "selected"),
                        (self._t("Keep saved/default selection"), "keep"),
                    ], value="none", allow_blank=False, id="corpus-mode")
                    yield SelectionList(id="corpus-choices")
                    with Vertical(id="retained-corpus-panel"):
                        yield Label(self._t("Already on this device — kept unchanged. This does not turn on corpus use."), id="retained-corpus-help")
                        yield SelectionList(id="retained-corpus-choices", disabled=True)
                    yield Checkbox(self._t("Connect to the Codex app"), id="app-bridge")
                    yield Static(self._t("Adds the $agent-bios command to Codex app conversations for setup and personal instruction management. Choose separately which tasks use the instructions."), id="app-bridge-help")
                with Vertical(id="sources-panel", classes="stage"):
                    yield Label(self._t("Optional: capture existing instructions for later model review. Space toggles a source; originals stay unchanged."), id="source-help")
                    with Horizontal(id="project-actions"):
                        yield Input(placeholder=self._t("Project folder path (optional)"), id="project-path")
                        yield Button(self._t("Add folder"), id="add-project")
                        yield Button(self._t("Clear folders"), id="clear-projects")
                    yield Static(self._t("Global instruction files only"), id="project-list")
                    yield SelectionList(id="source-choices")
                    yield Static(self._t("No sources selected"), id="source-selection")
                    yield Static("", id="source-detail")
                    yield Static("", id="source-notes")
                with Vertical(id="dependencies-panel", classes="stage"):
                    yield Label(self._t("Available dependencies are checked and locked. Choose only additional installations; missing items without an installer stay unchecked."), id="dependency-help")
                    yield SelectionList(id="dependency-choices")
                    yield Static(self._t("No dependency installation selected"), id="dependency-selection")
                    yield Static("", id="dependency-detail")
                    with Collapsible(title=self._t("Every dependency: purpose and location"), id="inventory-details"):
                        yield Static("", id="inventory-reference")
                with Vertical(id="review-panel", classes="stage"):
                    yield Static("", id="summary")
                    with Collapsible(title=self._t("Exact commands, paths and plan"), id="details"):
                        yield TextArea(read_only=True, soft_wrap=True, show_line_numbers=False, id="exact-json")
                    with Collapsible(title=self._t("Operation output"), id="logs"):
                        yield TextArea(read_only=True, soft_wrap=True, show_line_numbers=False, id="operation-log")
            yield Static(self._t("Choose your language to continue."), id="status")
            yield LoadingIndicator(id="working")
            with Horizontal(id="actions"):
                yield Button(self._t(LANGUAGE_CONTINUE), id="language-continue", variant="primary")
                yield Button(self._t("Back"), id="back")
                yield Button(self._t("Cancel"), id="cancel")
                yield Button(self._t("Next"), id="next", variant="primary")
                yield Button(self._t("Apply setup"), id="apply", variant="success")
                yield Button(self._t("Close"), id="done", variant="primary")
        yield Static(self._t("Esc / Ctrl+C: Cancel   Tab: Move   Space: Toggle"), id="key-help")

    def on_mount(self) -> None:
        self._localize()
        self._show_step()

    def _from_worker(self, callback, *args) -> None:
        if not self.closing:
            try:
                self.call_from_thread(callback, *args)
            except RuntimeError:
                if not self.closing:
                    raise

    @work(thread=True, exit_on_error=False)
    def _initialize(self) -> None:
        try:
            if self.controller is None:
                try:
                    from corpus_setup import SetupController
                except ImportError:
                    from .corpus_setup import SetupController
                controller = SetupController(self.installer)
            else:
                controller = self.controller
            plan = controller.default_plan()
            if self.initial_plan is not None:
                plan.update(copy.deepcopy(self.initial_plan))
            self._from_worker(self._initialized, controller, plan)
        except Exception as exc:
            self._from_worker(self._initialization_failed, exc)

    def _initialized(self, controller, plan) -> None:
        self.controller = controller
        self.plan = copy.deepcopy(plan)
        self.ready = True
        self.busy = False
        self.step = 0
        self._localize()
        self._set_status("No installation changes yet. Choose only what you want to use.")
        self._show_step()

    def _render_options(self) -> None:
        choices = self.query_one("#corpus-choices", SelectionList)
        selected = self.plan.get("targets") or []
        known = {row["target"] for row in self.controller.choices}
        choices.clear_options()
        choices.add_options([Selection(Text(visible(i18n.choice_label(self.language, row))), row["target"], row["target"] in selected)
                             for row in self.controller.choices])
        choices.add_options([Selection(Text(self._t("All available corpus") if value == "all" else self._t("Selected item: {item}", item=visible(value))), value, True)
                             for value in selected if value not in known])
        mode = self.plan.get("selection_mode")
        mode_value = "keep" if mode is None else "all" if selected == ["all"] else "selected" if mode == "selected" else "none"
        self.query_one("#corpus-mode", Select).value = mode_value
        self.query_one("#app-bridge", Checkbox).value = bool(self.plan.get("app_bridge"))
        retained = getattr(self.controller, "retained_corpus", [])
        local = self.query_one("#retained-corpus-choices", SelectionList)
        local.clear_options()
        local.add_options([
            Selection(Text(visible(self._t("{name} — {count} items retained", name=self._t(row["label"]), count=row["item_count"]))),
                      row["target"], True, disabled=True)
            for row in retained
        ])
        self.query_one("#retained-corpus-panel").display = bool(retained)
        dependencies = self.query_one("#dependency-choices", SelectionList)
        requested = set(self.plan.get("dependencies") or [])
        display = [i18n.dependency_display(self.language, row) for row in self.controller.dependencies]
        dependencies.clear_options()
        dependencies.add_options([
            Selection(Text(visible(f"{row['title']} — {row['status']} {row.get('version', '')}")), row["id"],
                      raw.get("status") == "available" or (row["id"] in requested and bool(row.get("install_argv"))),
                      disabled=raw.get("status") == "available" or not bool(row.get("install_argv")))
            for raw, row in zip(self.controller.dependencies, display)
        ])
        self.query_one("#inventory-reference", Static).update(Text(visible("\n\n".join(
            f"{row['title']} — {row['status']} {row.get('version', '')}\n{row['purpose']}"
            + ("\n" + self._t("Location: {path}", path=row["install_scope"]) if row.get("install_scope") else "")
            + ("\n" + row["manual_reason"] if row.get("manual_reason") else "")
            for row in display))))
        if self.sources_loaded:
            self._render_sources(self.plan.get("project_roots") or [], self.plan.get("import_paths") or [])

    def _localize(self) -> None:
        self.title = self._t("agent-bios setup")
        messages = {
            "language-help": "Choose your language to continue.",
            "corpus-help": "Choose what future activated launches may use. App tasks require their own explicit use.",
            "retained-corpus-help": "Already on this device — kept unchanged. This does not turn on corpus use.",
            "app-bridge-help": "Adds the $agent-bios command to Codex app conversations for setup and personal instruction management. Choose separately which tasks use the instructions.",
            "source-help": "Optional: capture existing instructions for later model review. Space toggles a source; originals stay unchanged.",
            "dependency-help": "Available dependencies are checked and locked. Choose only additional installations; missing items without an installer stay unchecked.",
            "key-help": "Esc / Ctrl+C: Cancel   Tab: Move   Space: Toggle",
        }
        for identifier, message in messages.items():
            self.query_one("#" + identifier, Static).update(Text(self._t(message)))
        mode = self.query_one("#corpus-mode", Select)
        old_value = mode.value
        mode.set_options([(self._t("No active corpus"), "none"), (self._t("All available corpus"), "all"),
                          (self._t("Choose supplied packages or domains"), "selected"), (self._t("Keep saved/default selection"), "keep")])
        mode.value = old_value
        mode.mutate_reactive(Select.value)
        self.query_one("#project-path", Input).placeholder = self._t("Project folder path (optional)")
        for identifier, message in (("add-project", "Add folder"), ("clear-projects", "Clear folders"),
                                    ("back", "Back"), ("next", "Next"), ("apply", "Apply setup")):
            self.query_one("#" + identifier, Button).label = self._t(message)
        for identifier, message in (("details", "Exact commands, paths and plan"), ("logs", "Operation output"),
                                    ("inventory-details", "Every dependency: purpose and location")):
            self.query_one("#" + identifier, Collapsible).title = self._t(message)
        self.query_one("#app-bridge", Checkbox).label = self._t("Connect to the Codex app")
        for identifier, message in (("source-selection", "No sources selected"),
                                    ("dependency-selection", "No dependency installation selected"),
                                    ("project-list", "Global instruction files only")):
            self.query_one("#" + identifier, Static).update(Text(self._t(message)))
        if self.ready:
            self._render_options()
        self._set_status(self.status_message, **self.status_values)

    def _initialization_failed(self, exc: Exception) -> None:
        self.backend_error = exc
        self.busy = False
        self.result = {"applied": False, "setup_error": str(exc)}
        self.query_one("#summary", Static).update(Text(self._t("Setup could not be prepared.\n\n{error}", error=visible(exc))))
        self.step = 3
        self._show_step()
        self._set_status("No setup plan was applied. Close to see the diagnostic.")

    def _set_status(self, message: str, **values) -> None:
        self.status_message = message
        self.status_values = values
        self.query_one("#status", Static).update(Text(visible(self._t(message, **values))))

    def _append_output(self, output: str) -> None:
        if output:
            self.operation_output.append(visible(output))
            self.query_one("#operation-log", TextArea).load_text("\n".join(self.operation_output)[-60000:])

    def _show_step(self, *, focus: bool = True) -> None:
        language_stage = self.step == -1
        self.query_one("#language-panel").display = language_stage
        self.query_one("#language-panel").disabled = self.busy
        panels = ("corpus-panel", "sources-panel", "dependencies-panel", "review-panel")
        for index, identifier in enumerate(panels):
            panel = self.query_one("#" + identifier)
            panel.display = index == self.step
            panel.disabled = self.busy and index != 3
        title = self._t(LANGUAGE_TITLE) if language_stage else self._t("Setup result") if self.result is not None else self._t("{step} of 4 — {stage}", step=self.step + 1, stage=self._t(STAGES[self.step]))
        self.query_one("#step-title", Static).update(Text(title))
        self.query_one("#working").display = self.busy
        self.query_one("#language-continue", Button).display = language_stage
        self.query_one("#language-continue", Button).disabled = self.busy
        self.query_one("#back", Button).display = not language_stage
        self.query_one("#back", Button).disabled = self.busy or self.result is not None
        self.query_one("#next", Button).display = 0 <= self.step < 3 and self.result is None
        self.query_one("#next", Button).disabled = self.busy or not self.ready
        self.query_one("#apply", Button).display = self.step == 3 and self.result is None and not self.dry_run
        self.query_one("#apply", Button).disabled = self.busy or self.preview_result is None
        self.query_one("#done", Button).display = self.result is not None or (self.step == 3 and self.dry_run)
        self.query_one("#done", Button).disabled = self.busy
        self.query_one("#done", Button).label = self._t("Close preview") if self.dry_run and self.result is None else self._t("Close")
        self.query_one("#cancel", Button).display = self.result is None
        self.query_one("#cancel", Button).label = self._t(LANGUAGE_CANCEL) if language_stage else self._t("Stop request") if self.applying else self._t("Cancel")
        self.query_one("#corpus-choices").display = self.query_one("#corpus-mode", Select).value == "selected"
        self.query_one("#logs").display = bool(self.operation_output) or self.applying
        self.query_one("#body", VerticalScroll).scroll_home(animate=False)
        if focus and not self.busy:
            target = "#language-select" if language_stage else "#done" if self.result is not None or (self.dry_run and self.step == 3) else (
                "#corpus-mode", "#project-path", "#dependency-choices", "#back")[self.step]
            self.query_one(target).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "language-select" and event.value in {code for _label, code in i18n.LANGUAGES}:
            self.language = event.value
            self._localize()
            self._show_step(focus=False)
        elif event.select.id == "corpus-mode":
            self.query_one("#corpus-choices").display = event.value == "selected"

    def _requested_dependencies(self) -> list[str]:
        selectable = {row["id"] for row in self.controller.dependencies
                      if row.get("install_argv") and row.get("status") != "available"}
        return [value for value in self.query_one("#dependency-choices", SelectionList).selected
                if value in selectable]

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        if self.controller is None:
            return
        widget = event.selection_list
        if widget.id == "corpus-choices":
            return
        elif widget.id == "source-choices":
            message = self._t("Selected files:\n{paths}", paths="\n".join(widget.selected)) if widget.selected else self._t("No sources selected")
            identifier = "#source-selection"
        elif widget.id == "dependency-choices":
            labels = {row["id"]: i18n.dependency_display(self.language, row)["title"] for row in self.controller.dependencies}
            requested = self._requested_dependencies()
            message = self._t("Install: {dependencies}", dependencies=", ".join(labels.get(value, value) for value in requested)) if requested else self._t("No dependency installation selected")
            identifier = "#dependency-selection"
        else:
            return
        self.query_one(identifier, Static).update(Text(visible(message)))

    def on_selection_list_selection_highlighted(self, event: SelectionList.SelectionHighlighted) -> None:
        if event.selection_list.id == "dependency-choices" and self.controller is not None:
            row = next((entry for entry in self.controller.dependencies if entry["id"] == event.selection.value), None)
            if row:
                row = i18n.dependency_display(self.language, row)
                lines = [row["purpose"]]
                if row.get("version"):
                    lines.append(self._t("Detected: {version}", version=row["version"]))
                if row.get("install_scope"):
                    lines.append(self._t("Installation location: {path}", path=row["install_scope"]))
                if row.get("manual_reason"):
                    lines.append(row["manual_reason"])
                self.query_one("#dependency-detail", Static).update(Text(visible("\n".join(lines))))
        elif event.selection_list.id == "source-choices":
            self.query_one("#source-detail", Static).update(Text(visible(event.selection.value)))

    def _collect(self, *, validate: bool = True) -> None:
        if self.step == 0:
            mode = self.query_one("#corpus-mode", Select).value
            chosen = list(self.query_one("#corpus-choices", SelectionList).selected)
            if validate and mode == "selected" and not chosen:
                raise ValueError("Choose at least one corpus, or select No active corpus.")
            self.plan["selection_mode"] = None if mode == "keep" else "none" if mode == "none" else "selected"
            self.plan["targets"] = None if mode == "keep" else ["all"] if mode == "all" else chosen if mode == "selected" else []
            self.plan["app_bridge"] = self.query_one("#app-bridge", Checkbox).value
        elif self.step == 1:
            self.plan["import_paths"] = list(self.query_one("#source-choices", SelectionList).selected)
        elif self.step == 2:
            self.plan["dependencies"] = self._requested_dependencies()

    def _discover(self) -> None:
        self.discovery_serial += 1
        self.busy = True
        self._show_step(focus=False)
        self._set_status("Finding instruction files in the selected locations…")
        self._discover_worker(self.discovery_serial, list(self.plan.get("project_roots") or []),
                              list(self.plan.get("import_paths") or []))

    @work(thread=True, group="discovery", exclusive=True, exit_on_error=False)
    def _discover_worker(self, serial: int, roots: list[str], selected: list[str]) -> None:
        try:
            result = self.controller.discover(roots)
            self._from_worker(self._discovered, serial, roots, selected, result)
        except Exception as exc:
            self._from_worker(self._discovery_failed, serial, exc)

    def _discovered(self, serial, roots, selected, result) -> None:
        if serial != self.discovery_serial:
            return
        self.sources = result.get("sources", [])
        self.source_omitted = result.get("omitted", [])
        self.sources_loaded = True
        self._render_sources(roots, selected)
        self.busy = False
        self._set_status("Capture is independent of corpus selection and needs later model review.")
        self._show_step()

    def _render_sources(self, roots, selected) -> None:
        widget = self.query_one("#source-choices", SelectionList)
        widget.clear_options()
        widget.add_options([Selection(Text(visible(f"{Path(row['path']).name} — {self._t(row.get('scope', {}).get('kind', 'source'))}: {Path(row['path']).parent}")),
                                      row["path"], row["path"] in selected) for row in self.sources])
        self.query_one("#project-list", Static).update(Text(self._t("Project folders:\n{paths}", paths="\n".join(visible(value) for value in roots))
                                                           if roots else self._t("Global instruction files only; add a project folder to include its files.")))
        notes = [self._t("{count} eligible file(s); selecting none is valid.", count=len(self.sources))]
        notes.extend(self._t("Skipped {path}: {reason}", path=row.get("path", self._t("source")),
                            reason=row.get("reason", self._t("unavailable"))) for row in self.source_omitted)
        self.query_one("#source-notes", Static).update(Text(visible("\n".join(notes))))

    def _discovery_failed(self, serial, exc) -> None:
        if serial != self.discovery_serial:
            return
        self.query_one("#source-choices", SelectionList).clear_options()
        self.busy = False
        self._set_status("Could not inspect those locations: {error}", error=str(exc))
        self._show_step()

    def _add_project(self) -> None:
        value = self.query_one("#project-path", Input).value.strip()
        if not value:
            self._set_status("Enter a project folder path, or continue without adding one.")
            return
        path = Path(value).expanduser()
        if not path.is_absolute() or not path.is_dir():
            self._set_status("Choose an existing absolute project folder path.")
            return
        roots = list(self.plan.get("project_roots") or [])
        normalized = str(path.resolve())
        if normalized not in roots:
            roots.append(normalized)
        self.plan["project_roots"] = roots
        self.plan["import_paths"] = list(self.query_one("#source-choices", SelectionList).selected)
        self.query_one("#project-path", Input).value = ""
        self._discover()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "project-path" and not self.busy:
            self._add_project()

    @work(thread=True, group="preview", exclusive=True, exit_on_error=False)
    def _preview_worker(self, plan: dict[str, Any]) -> None:
        try:
            preview = self.controller.preview(plan)
            self._from_worker(self._previewed, preview)
        except Exception as exc:
            self._from_worker(self._preview_failed, exc)

    def _previewed(self, preview) -> None:
        self.preview_result = preview
        self.step = 3
        self.busy = False
        self.query_one("#summary", Static).update(Text(review_summary(self.plan, self.controller.dependencies, self.controller.choices, self.language)))
        self.query_one("#exact-json", TextArea).load_text(json.dumps(preview, ensure_ascii=False, indent=2, sort_keys=True))
        self._set_status("Read-only preview. No Apply is available in dry-run mode." if self.dry_run else "Review the effects, then choose Apply setup.")
        self._show_step()

    def _preview_failed(self, exc) -> None:
        self.busy = False
        self.preview_result = None
        self._set_status("Preview refused: {error}", error=str(exc))
        self._show_step()

    @work(thread=True, group="apply", exclusive=True, exit_on_error=False)
    def _apply_worker(self, plan, preview) -> None:
        try:
            result = self.controller.apply(plan, preview=preview, progress=self._progress,
                                           should_cancel=self.cancel_requested.is_set)
            self._from_worker(self._applied, result)
        except SetupError as exc:
            self._from_worker(self._apply_failed if self.started_effects else self._apply_refused, exc)
        except Exception as exc:
            self._from_worker(self._apply_failed, exc)

    def _progress(self, event: dict[str, Any]) -> None:
        self._from_worker(self._progressed, event)

    def _progressed(self, event: dict[str, Any]) -> None:
        if event.get("stage") in {"dependency", "install", "extras"}:
            self.started_effects = True
        message = event.get("message")
        stage = event.get("stage")
        if stage == "dependency":
            identifier = event.get("dependency", event.get("id", ""))
            row = next((row for row in self.controller.dependencies if row["id"] == identifier), None)
            name = i18n.dependency_display(self.language, row)["title"] if row else identifier
            if "returncode" not in event:
                self._set_status("Installing {dependency}…", dependency=name)
            elif event["returncode"] is None:
                self._set_status("Could not start {dependency}", dependency=name)
            else:
                self._set_status("Finished {dependency}", dependency=name)
        elif stage == "install":
            self._set_status("Installing the private runtime")
        elif stage == "extras":
            self._set_status("Preparing app registration and selected instruction capture")
        elif stage == "complete":
            self._set_status("Setup complete")
        elif message:
            self._set_status(str(message))
        self._append_output(str(event.get("stdout") or "") + str(event.get("stderr") or ""))

    def _apply_refused(self, exc) -> None:
        self.applying = False
        self.busy = False
        self.preview_result = None
        self.step = 2
        self._set_status("Apply refused before changes: {error} Choose Next to review a fresh plan.", error=str(exc))
        self._show_step()

    def _applied(self, result) -> None:
        self.result = result
        self.busy = False
        self.applying = False
        self.query_one("#summary", Static).update(Text(visible(format_setup_result(result, language=self.language))))
        self.query_one("#exact-json", TextArea).load_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        self._set_status("Stopped at a safe boundary; the outcome lists any retained changes." if result.get("cancelled")
                         else "The accepted operation finished. Its completed effects remain." if self.cancel_requested.is_set()
                         else "Review the outcome before closing.")
        self._show_step()

    def _apply_failed(self, exc) -> None:
        self.backend_error = exc
        self.result = {"applied": False, "execution_error": str(exc), "unknown_outcome": True}
        self.busy = False
        self.applying = False
        self.query_one("#summary", Static).update(Text(self._t("Setup stopped with an error.\n\n{error}\n\nEarlier completed effects may remain. Inspect status before retrying.", error=visible(exc))))
        self.query_one("#exact-json", TextArea).load_text(json.dumps(self.result, indent=2))
        self._set_status("No rollback is claimed. Close to return the diagnostic.")
        self._show_step()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        if button == "cancel":
            self.action_cancel()
            return
        if self.busy:
            return
        if button == "language-continue":
            if self.ready:
                self.step = 0
                self._localize()
                self._set_status("Your choices are preserved. Edit this section or continue.")
                self._show_step()
            else:
                self.busy = True
                self._set_status("Checking available setup options…")
                self._show_step(focus=False)
                self._initialize()
        elif button == "done":
            result = self.result if self.result is not None else {**copy.deepcopy(self.preview_result or {}),
                                                                  "applied": False, "dry_run": True}
            self._finish(result)
        elif button == "back" and self.step >= 0 and self.result is None:
            self._collect(validate=False)
            self.step -= 1
            self.preview_result = None
            self._set_status("Your choices are preserved. Edit this section or continue.")
            self._show_step()
        elif button == "add-project":
            self._add_project()
        elif button == "clear-projects":
            self.plan["project_roots"] = []
            self.plan["import_paths"] = list(self.query_one("#source-choices", SelectionList).selected)
            self._discover()
        elif button == "next":
            if self.step == 1 and self.query_one("#project-path", Input).value.strip():
                self._add_project()
                return
            try:
                self._collect()
            except ValueError as exc:
                self._set_status(str(exc))
                return
            if self.step == 2:
                self.busy = True
                self._show_step(focus=False)
                self._set_status("Validating the exact setup plan…")
                self._preview_worker(copy.deepcopy(self.plan))
            else:
                self.step += 1
                if self.step == 2:
                    self._set_status("Select missing capabilities to install. Next shows the exact effects before Apply.")
                self._show_step()
                if self.step == 1:
                    self._discover()
        elif button == "apply" and self.preview_result is not None and not self.dry_run:
            self.cancel_requested.clear()
            self.started_effects = False
            self.applying = True
            self.busy = True
            self._show_step(focus=False)
            self._set_status("Applying the accepted setup. Completed changes will be reported.")
            self._apply_worker(copy.deepcopy(self.plan), copy.deepcopy(self.preview_result))

    def _finish(self, result) -> None:
        self.closing = True
        self.exit(result)

    def action_cancel(self) -> None:
        if self.applying:
            self.cancel_requested.set()
            self._set_status("Stop requested. Waiting for the current step to finish safely; completed changes are retained.")
        elif self.result is not None:
            self._finish(self.result)
        else:
            self._finish({"cancelled": True, "applied": False})

    def action_quit(self) -> None:
        self.action_cancel()


def run_setup_ui(installer: Any, *, dry_run: bool = False,
                 initial_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    app = SetupApp(installer, dry_run=dry_run, initial_plan=initial_plan)
    result = app.run()
    if app.backend_error is not None:
        app.backend_error.ui_language = app.language
        raise app.backend_error
    return {**(result if result is not None else {"cancelled": True, "applied": False}), "ui_language": app.language}
