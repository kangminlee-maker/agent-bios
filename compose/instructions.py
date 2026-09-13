#!/usr/bin/env python3
"""Instructions Studio and machine CLI over the private, revision-checked instructions store.

The command is deliberately a client.  It renders records and translates user
input into semantic plan payloads; ``InstructionsStore`` remains the only writer and
owns ids, revisions, paths, serialization, validation, and publication.
"""
from __future__ import annotations

import argparse
import difflib
import importlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from typing import Any, Sequence

try:
    from instructions_store import InstructionsStore, InstructionsStoreError
except ImportError:  # package-style import in tests
    from .instructions_store import InstructionsStore, InstructionsStoreError


SURFACES = ("always", "relevant", "requested", "event", "delegated")


def default_repo() -> Path:
    return Path(os.environ.get("AGENT_BIOS_REPO", Path(__file__).resolve().parents[1]))


def venv_python() -> Path | None:
    roots: list[Path] = []
    if override := os.environ.get("AGENT_LAUNCH_VENV"):
        roots.append(Path(override).expanduser())
    roots.append(Path.home() / ".local/share/agent-launch/venv")
    for root in roots:
        interpreter = root / "bin" / "python"
        if interpreter.is_file() and os.access(interpreter, os.X_OK):
            return interpreter
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-bios instructions",
        description="Inspect and change the private instructions used by future activated sessions.",
    )
    parser.add_argument("--repo", type=Path, default=default_repo())
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--user-dir", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    sub = parser.add_subparsers(dest="command")

    list_cmd = sub.add_parser("list", help="list instructions items")
    list_cmd.add_argument("--active-only", action="store_true")

    search = sub.add_parser("search", help="search item text and metadata")
    search.add_argument("query")
    search.add_argument("--active-only", action="store_true")

    show = sub.add_parser("show", help="show one instructions item")
    show.add_argument("ref")
    show.add_argument(
        "--view", default="effective",
        choices=("effective", "installed", "change", "diff", "history"),
    )

    plan = sub.add_parser("plan", help="validate a semantic change without publishing it")
    plan.add_argument("--input", default="-", metavar="FILE")

    apply_cmd = sub.add_parser("apply", help="publish a previously validated plan")
    apply_cmd.add_argument("plan")
    apply_cmd.add_argument("--expected-revision")

    history = sub.add_parser("history", help="list recoverable authoring revisions")
    history.add_argument("ref", nargs="?")

    sub.add_parser("status", help="show private store state")

    snapshot = sub.add_parser("snapshot", help="compose current authoring or inspect an immutable snapshot")
    snapshot_view = snapshot.add_mutually_exclusive_group(required=True)
    snapshot_view.add_argument("--host", choices=("claude", "codex"))
    snapshot_view.add_argument("--content-ref", help="read this stored snapshot without resolving current authoring")
    snapshot.add_argument("--native", action="store_true", help="opt into selected native hooks on either host and Claude agents for this snapshot")
    snapshot.add_argument("--selection-mode", choices=("default", "selected", "none"))
    snapshot.add_argument("--select", action="append", help="one-session package/domain/item selection")
    snapshot.add_argument("--cwd", type=Path, help="project scope for this snapshot")

    install = sub.add_parser("install", help="record the current package as a private baseline")
    install.add_argument("--domains", help="comma-separated qualified selection values")
    return parser


def _load_json(source: str) -> dict[str, Any]:
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
        payload = json.loads(text)
    except (OSError, ValueError) as exc:
        raise InstructionsStoreError(f"cannot read plan input {source!r}: {exc}") from exc
    if not isinstance(payload, dict):
        raise InstructionsStoreError("plan input must be one JSON object")
    return payload


def _matches(item: dict[str, Any], query: str) -> bool:
    needle = query.casefold()
    values: list[str] = []
    for key in ("ref", "title", "body", "surface", "tier", "kind", "state", "package_id"):
        value = item.get(key)
        if isinstance(value, str):
            values.append(value)
    values.extend(str(value) for value in item.get("domains", []) if isinstance(value, str))
    return needle in "\n".join(values).casefold()


def search_items(store: InstructionsStore, query: str, *, include_removed: bool = True) -> list[dict[str, Any]]:
    return [item for item in store.list_items(include_removed=include_removed) if _matches(item, query)]


def _human_item(item: dict[str, Any]) -> str:
    state = item.get("state", "active")
    return f"{item.get('ref', '?')}\t{state}\t{item.get('surface', '?')}\t{item.get('title', '')}"


def _human_show(result: dict[str, Any]) -> str:
    item = result.get("item")
    if isinstance(item, dict):
        metadata = (
            f"`{item.get('ref', result.get('ref', ''))}` · {result.get('state', 'active')} · "
            f"{item.get('surface', '?')} · {item.get('kind', '?')}"
        )
        return f"# {item.get('title', item.get('ref', 'Instructions item'))}\n\n{metadata}\n\n{item.get('body', '')}"
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)


def emit(value: Any, *, as_json: bool, command: str) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if command in {"list", "search"} and isinstance(value, list):
        for item in value:
            print(_human_item(item))
    elif command == "show" and isinstance(value, dict):
        print(_human_show(value))
    elif command == "history" and isinstance(value, list):
        for row in value:
            print(f"{row.get('history_id', '?')}\t{row.get('revision', '?')}\t{row.get('path', '')}")
    elif command == "status" and isinstance(value, dict):
        for key, current in value.items():
            print(f"{key}: {json.dumps(current, ensure_ascii=False)}")
    elif command == "snapshot" and isinstance(value, dict):
        print(f"content_ref: {value.get('content_ref')}\npath: {value.get('path')}\nrevision: {value.get('revision')}")
        if value.get("unavailable"):
            print("activation unverified or unavailable:")
            for row in value["unavailable"]:
                print(f"- {row.get('ref')}: {row.get('reason')}")
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def run_command(args: argparse.Namespace, store: InstructionsStore) -> Any:
    command = args.command
    if command == "list":
        return store.list_items(include_removed=not args.active_only)
    if command == "search":
        return search_items(store, args.query, include_removed=not args.active_only)
    if command == "show":
        return store.show(args.ref, view=args.view)
    if command == "plan":
        return store.plan(_load_json(args.input))
    if command == "apply":
        return store.apply(args.plan, expected_revision=args.expected_revision)
    if command == "history":
        return store.history(args.ref)
    if command == "status":
        return store.status()
    if command == "snapshot":
        if args.content_ref:
            if args.native or args.selection_mode or args.select or args.cwd:
                raise InstructionsStoreError("a stored snapshot is immutable; selection and scope options require --host")
            return store.snapshot_inventory(args.content_ref)
        return store.snapshot(args.host, selection=args.select, native=args.native,
                              selection_mode=args.selection_mode or ("selected" if args.select is not None else None),
                              cwd=args.cwd)
    if command == "install":
        domains = None
        if args.domains is not None:
            domains = [part.strip() for part in args.domains.split(",") if part.strip()]
            if domains == ["none"]:
                domains = []
        return store.install(domains=domains)
    raise InstructionsStoreError(f"unknown instructions command: {command}")


def _draft_text(initial: str = "") -> str:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        with tempfile.TemporaryDirectory(prefix="agent-bios-instructions-draft-") as directory:
            path = Path(directory) / "draft.md"
            path.write_text(initial, encoding="utf-8")
            try:
                completed = subprocess.run([*shlex.split(editor), str(path)], check=False)
            except OSError as exc:
                raise InstructionsStoreError(f"cannot run editor: {exc}") from exc
            if completed.returncode != 0:
                raise InstructionsStoreError(f"editor exited with status {completed.returncode}")
            return path.read_text(encoding="utf-8")
    print("Enter Markdown. Finish with a line containing only '.'")
    if initial:
        print("Current body follows; enter a complete replacement.")
        print(initial)
    lines: list[str] = []
    while True:
        line = input()
        if line == ".":
            return "\n".join(lines) + ("\n" if lines else "")
        lines.append(line)


def _choose_surface(current: str = "requested") -> str:
    print("Consumption surface:")
    for index, surface in enumerate(SURFACES, 1):
        marker = " *" if surface == current else ""
        print(f"  {index}. {surface}{marker}")
    raw = input(f"Select [default {SURFACES.index(current) + 1}]: ").strip()
    if not raw:
        return current
    try:
        return SURFACES[int(raw) - 1]
    except (ValueError, IndexError) as exc:
        raise InstructionsStoreError("invalid surface selection") from exc


def _preview_and_apply(store: InstructionsStore, payload: dict[str, Any], preview: str) -> None:
    plan = store.plan(payload)
    print(preview)
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    if input("Apply this plan? [y/N]: ").strip().casefold() not in {"y", "yes"}:
        print("Plan was not applied.")
        return
    applied = store.apply(plan["plan_id"], expected_revision=plan["expected_revision"])
    print(json.dumps(applied, ensure_ascii=False, indent=2, sort_keys=True))
    print("Future activated sessions use the new authoring state; this running session is unchanged.")


def run_numbered(store: InstructionsStore) -> int:
    """Useful fallback when Textual is unavailable; canonical writes still use the store."""
    while True:
        items = store.list_items(include_removed=True)
        print("\nInstructions Studio (numbered fallback)")
        for index, item in enumerate(items, 1):
            print(f"  {index}. {_human_item(item)}")
        print("  c. create   e. edit   r. remove   s. restore   v. recover   x. reset   /. search   q. quit")
        choice = input("Choice: ").strip()
        if choice.casefold() == "q":
            return 0
        if choice == "/":
            query = input("Search: ")
            for item in search_items(store, query):
                print(_human_item(item))
            continue
        if choice.casefold() == "c":
            title = input("Title: ").strip()
            body = _draft_text()
            surface = _choose_surface()
            item = {"title": title, "body": body, "surface": surface,
                    "tier": "env-personal", "domains": ["personal"], "kind": "rule",
                    "members": {"content.md": body}}
            _preview_and_apply(store, {"operation": "create", "item": item}, f"Create {title!r} on {surface}.")
            continue
        if choice.casefold() == "x":
            _preview_and_apply(store, {"operation": "reset"}, "Reset future instructions authoring to the last successful install tuple.")
            continue
        if choice.casefold() in {"e", "r", "s", "v"}:
            ref = input("InstructionsRef: ").strip()
            row = next((item for item in items if item.get("ref") == ref), None)
            if row is None:
                print("Unknown InstructionsRef.", file=sys.stderr)
                continue
            if choice.casefold() == "e":
                body = _draft_text(str(row.get("body", "")))
                surface = _choose_surface(str(row.get("surface", "requested")))
                patch = {"body": body, "surface": surface}
                if row.get("kind") == "hook":
                    try:
                        from instructions_catalog import HOOK_EVENTS
                    except ImportError:  # package-style import from repository root
                        from .instructions_catalog import HOOK_EVENTS
                    binding = row.get("hook") if isinstance(row.get("hook"), dict) else {}
                    default_event = str(binding.get("event", sorted(HOOK_EVENTS)[0]))
                    while True:
                        event = input(f"Hook event [{default_event}]: ").strip() or default_event
                        if event in HOOK_EVENTS:
                            break
                        print("Unsupported hook event.", file=sys.stderr)
                    default_matcher = str(binding.get("matcher", ""))
                    matcher = input(f"Hook matcher [{default_matcher}]: ")
                    matcher = matcher if matcher else default_matcher
                    if not matcher or "\n" in matcher or "\r" in matcher:
                        print("Hook matcher must be one non-empty line.", file=sys.stderr)
                        continue
                    patch["hook"] = {"event": event, "matcher": matcher}
                diff = "".join(difflib.unified_diff(
                    str(row.get("body", "")).splitlines(True), body.splitlines(True),
                    fromfile="current", tofile="planned",
                )) or "(metadata-only change)"
                hook_preview = (f"\nHook binding: {patch['hook']['event']} / {patch['hook']['matcher']}"
                                if "hook" in patch else "")
                _preview_and_apply(store, {"operation": "update", "ref": ref,
                                           "item_digest": row["digest"], "patch": patch}, diff + hook_preview)
            elif choice.casefold() == "r":
                _preview_and_apply(store, {"operation": "remove", "ref": ref,
                                           "item_digest": row.get("digest")}, f"Remove {ref} from future snapshots.")
            elif choice.casefold() == "s":
                _preview_and_apply(store, {"operation": "restore", "ref": ref},
                                   f"Restore {ref} from the selected installed baseline.")
            else:
                _preview_and_apply(store, {"operation": "recover", "ref": ref},
                                   f"Recover personal item {ref} for future snapshots.")
            continue
        try:
            index = int(choice) - 1
            print(_human_show(store.show(items[index]["ref"])))
        except (ValueError, IndexError):
            print("Invalid choice.", file=sys.stderr)


def _run_tui_or_fallback(args: argparse.Namespace, store: InstructionsStore) -> int:
    module_name = f"{__package__}.instructions_ui" if __package__ else "instructions_ui"
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        missing_ui_dependency = any(exc.name == name or (exc.name or "").startswith(name + ".")
                                    for name in ("textual", "rich"))
        if not missing_ui_dependency and exc.name not in {"instructions_ui", module_name}:
            raise
        interpreter = venv_python()
        if (
            missing_ui_dependency
            and interpreter is not None
            and Path(sys.executable).absolute() != interpreter.absolute()
            and os.environ.get("AGENT_BIOS_INSTRUCTIONS_TUI_REEXEC") != "1"
        ):
            env = os.environ.copy()
            env["AGENT_BIOS_INSTRUCTIONS_TUI_REEXEC"] = "1"
            try:
                os.execve(
                    str(interpreter),
                    [str(interpreter), str(Path(__file__).resolve()), *sys.argv[1:]],
                    env,
                )
            except OSError as reexec_error:
                print(
                    f"agent-bios instructions: managed Textual runtime is unusable ({reexec_error}); "
                    "using numbered fallback.",
                    file=sys.stderr,
                )
        return run_numbered(store)
    app = module.InstructionsStudio(store)
    app.run()
    return 0


def _run_bundled_tui(store: InstructionsStore) -> int:
    try:
        from instructions_ui_runtime import activate_ui_runtime
        activate_ui_runtime(Path(__file__).resolve().parents[1])
        module_name = f"{__package__}.instructions_ui" if __package__ else "instructions_ui"
        module = importlib.import_module(module_name)
    except (ImportError, OSError, RuntimeError) as exc:
        raise InstructionsStoreError(f"bundled terminal UI could not start: {exc}") from exc
    app = module.InstructionsStudio(store)
    app.run()
    return 0


def main(argv: Sequence[str] | None = None, *, bundled_ui: bool = False) -> int:
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    # Machine callers naturally put --json after the verb.  argparse only accepts
    # a parent option before a subparser, so normalize this one order-independent
    # presentation flag without changing any semantic argument.
    json_requested = "--json" in raw
    raw = [value for value in raw if value != "--json"]
    args = parser.parse_args(raw)
    args.as_json = args.as_json or json_requested
    store = InstructionsStore(args.repo, state_root=args.state_dir, user_root=args.user_dir)
    try:
        if args.command is None:
            if sys.stdin.isatty() and sys.stdout.isatty():
                if bundled_ui:
                    return _run_bundled_tui(store)
                return _run_tui_or_fallback(args, store)
            args.command = "list"
            args.active_only = False
        result = run_command(args, store)
        emit(result, as_json=args.as_json, command=args.command)
        return 0
    except InstructionsStoreError as exc:
        print(f"agent-bios instructions: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(bundled_ui=True))
