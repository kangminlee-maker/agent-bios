#!/usr/bin/env python3
"""The MCP servers agent-bios ships are derived from code, not written down.

DEPENDENCIES.md said app delivery adds no MCP server, and nothing noticed when the
Claude Desktop server made that false: the only gate reading the file checks one
unrelated string. This derives the facts and owns the paragraph stating them, in
DEPENDENCIES.md and in its Korean reference, so adding or removing a server changes
the text or fails here instead of going quietly stale.

Each fact is derived:
  servers    shipped Python files (package.json files[]) whose string literals
             include both "tools/list" and "tools/call" — files that answer MCP's
             tool methods. A literal must equal the method name, so a docstring or
             comment that mentions one does not make a server.
  bundlers   other shipped Python files naming a server's path as a string literal
  launcher   launch/agent-launch.toml capabilities offering the mcp-stdio-v1 adapter

The default run checks both marked blocks; --emit rewrites them; --self-test plants
each drift and requires a failure naming it. A scan that judged no shipped Python
fails rather than reporting a clean inventory of nothing.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import shutil
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- mcp-inventory:start -->"
END = "<!-- mcp-inventory:end -->"
DOCS = ("DEPENDENCIES.md", "ko/DEPENDENCIES.md")
ADAPTER = "mcp-stdio-v1"
METHODS = ("tools/list", "tools/call")


def shipped_python(root: Path) -> list[Path]:
    files = json.loads((root / "package.json").read_text(encoding="utf-8")).get("files", [])
    found: set[Path] = set()
    for entry in files:
        path = root / entry
        if path.is_dir():
            found.update(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
        elif path.suffix == ".py" and path.is_file():
            found.add(path)
    return sorted(found)


def literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}


def derive(root: Path) -> dict:
    sources = shipped_python(root)
    if not sources:
        raise ValueError("package.json files[] reaches no shipped Python; the scan judged nothing")
    strings = {path.relative_to(root).as_posix(): literals(path) for path in sources}
    servers = sorted(name for name, values in strings.items() if all(m in values for m in METHODS))
    bundlers = {server: sorted(name for name, values in strings.items() if name != server and server in values)
                for server in servers}
    launch = tomllib.loads((root / "launch/agent-launch.toml").read_text(encoding="utf-8"))
    capabilities = launch.get("capabilities")
    if not isinstance(capabilities, dict) or not capabilities:
        raise ValueError("launch/agent-launch.toml declares no capabilities; the launcher leg judged nothing")
    offering = sorted(name for name, body in capabilities.items()
                      if any(isinstance(offer, dict) and offer.get("adapter") == ADAPTER
                             for offer in (body or {}).get("offers", [])))
    return {"servers": servers, "bundlers": bundlers, "capabilities": offering, "scanned": len(sources)}


def _paths(names: list[str]) -> str:
    return ", ".join(f"`{name}`" for name in names)


def render(facts: dict, doc: str) -> str:
    public = {key: facts[key] for key in ("servers", "bundlers", "capabilities")}
    lines = [START, f"<!-- facts: {json.dumps(public, sort_keys=True)} -->"]
    servers, capabilities = facts["servers"], facts["capabilities"]
    if doc.startswith("ko/"):
        listed = [f"{_paths([s])}({_paths(facts['bundlers'][s])}가 번들에 넣음)" if facts["bundlers"][s] else _paths([s])
                  for s in servers]
        lines.append("- **MCP 서버** — `gates/check-mcp-inventory.py`가 소스에서 도출한 내용이다.")
        lines.append(f"  함께 배포되는 서버: {', '.join(listed) if listed else '없음'}.")
        if capabilities:
            lines.append(f"  `{ADAPTER}` 어댑터를 제공하는 launch capability: {_paths(capabilities)}. launcher는 이 어댑터를 "
                         "선언한 capability를 선택했을 때만 해당 서버를 등록한다.")
        else:
            lines.append(f"  `{ADAPTER}` 어댑터를 제공하는 launch capability: 없음. 따라서 기본 제공 review method는 MCP를 "
                         "요구하지 않으며, launcher는 이 어댑터를 선언한 capability를 사용자가 선택했을 때만 사용자별 서버를 등록한다.")
    else:
        listed = [f"{_paths([s])} (bundled by {_paths(facts['bundlers'][s])})" if facts["bundlers"][s] else _paths([s])
                  for s in servers]
        lines.append("- **MCP servers** — derived from source by `gates/check-mcp-inventory.py`.")
        lines.append(f"  Shipped servers: {', '.join(listed) if listed else 'none'}.")
        if capabilities:
            lines.append(f"  Launch capabilities offering `{ADAPTER}`: {_paths(capabilities)}; the launcher registers "
                         "a server only through a selected capability that declares it.")
        else:
            lines.append(f"  Launch capabilities offering `{ADAPTER}`: none, so no shipped review method requires MCP; "
                         "the launcher registers a user-specific server only through a selected capability that declares it.")
    lines.append(END)
    return "\n".join(lines)


def _block(text: str, doc: str) -> tuple[int, int]:
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError(f"{doc}: requires exactly one MCP inventory marker pair")
    begin, end = text.index(START), text.index(END) + len(END)
    if end <= begin:
        raise ValueError(f"{doc}: MCP inventory markers are reversed")
    return begin, end


def _documented(block: str) -> dict:
    for line in block.splitlines():
        if line.startswith("<!-- facts: ") and line.endswith(" -->"):
            try:
                return json.loads(line[len("<!-- facts: "):-len(" -->")])
            except ValueError:
                break
    return {}


def problems(root: Path, facts: dict) -> list[str]:
    failures = []
    for doc in DOCS:
        path = root / doc
        if not path.is_file():
            failures.append(f"{doc}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        try:
            begin, end = _block(text, doc)
        except ValueError as exc:
            failures.append(str(exc))
            continue
        current = text[begin:end]
        if current == render(facts, doc):
            continue
        before = _documented(current)
        changes = []
        for key in ("servers", "capabilities"):
            added = sorted(set(facts[key]) - set(before.get(key, [])))
            removed = sorted(set(before.get(key, [])) - set(facts[key]))
            changes += [f"{key} added: {', '.join(added)}"] if added else []
            changes += [f"{key} removed: {', '.join(removed)}"] if removed else []
        if before.get("bundlers") != facts["bundlers"] and not changes:
            changes.append("bundlers changed")
        detail = "; ".join(changes) or "text differs from its projection"
        failures.append(f"{doc}: MCP inventory is stale ({detail}); run gates/check-mcp-inventory.py --emit")
    return failures


def emit(root: Path, facts: dict) -> None:
    for doc in DOCS:
        path = root / doc
        text = path.read_text(encoding="utf-8")
        begin, end = _block(text, doc)
        path.write_text(text[:begin] + render(facts, doc) + text[end:], encoding="utf-8")


def run(root: Path, *, write: bool = False) -> list[str]:
    try:
        facts = derive(root)
        if write:
            emit(root, facts)
        return problems(root, facts)
    except (ValueError, OSError, SyntaxError, tomllib.TOMLDecodeError) as exc:
        return [str(exc)]


def self_test() -> int:
    server = 'def handle(m):\n    return {"tools/list": 1, "tools/call": 2}.get(m)\n'
    base = {
        "package.json": json.dumps({"files": ["pkg/", "tool.py"]}),
        "pkg/server.py": server,
        "pkg/builder.py": 'SOURCE = "pkg/server.py"\n',
        "tool.py": 'print("no protocol here")\n',
        "launch/agent-launch.toml": '[capabilities.panel]\ncommand = "x"\n'
                                    'offers = [{ operation = "review", adapter = "exec-stdio-v1", hosts = ["claude"] }]\n',
        "DEPENDENCIES.md": f"# Dependencies\n\n{START}\n{END}\n\nAfter.\n",
        "ko/DEPENDENCIES.md": f"# 의존성\n\n{START}\n{END}\n\n뒤.\n",
    }
    failures: list[str] = []

    def tree(files: dict[str, str | None]) -> Path:
        root = Path(tempfile.mkdtemp(prefix="mcp-inventory-"))
        for name, body in files.items():
            if body is None:
                continue
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(body, encoding="utf-8")
        return root

    def emitted(files: dict[str, str | None]) -> Path:
        root = tree(files)
        result = run(root, write=True)
        if result:
            failures.append(f"positive control did not emit cleanly: {result}")
        return root

    clean = emitted(base)
    try:
        if run(clean):
            failures.append(f"positive control failed after emit: {run(clean)}")
        text = (clean / "DEPENDENCIES.md").read_text()
        if "`pkg/server.py` (bundled by `pkg/builder.py`)" not in text:
            failures.append("positive control did not state the server and its bundler")
        first = {doc: (clean / doc).read_bytes() for doc in DOCS}
        run(clean, write=True)
        if first != {doc: (clean / doc).read_bytes() for doc in DOCS}:
            failures.append("emit is not idempotent")
        # Mentions are not servers; unshipped servers are not shipped.
        quiet = [("docstring mention", "pkg/notes.py", '"""Handles tools/list and tools/call."""\n# tools/call\n'),
                 ("unshipped server", "scratch/probe.py", server)]
        for label, name, body in quiet:
            (clean / name).parent.mkdir(parents=True, exist_ok=True)
            (clean / name).write_text(body)
            if run(clean):
                failures.append(f"{label} was counted: {run(clean)}")
            (clean / name).unlink()
    finally:
        shutil.rmtree(clean)

    cases = [
        ("new shipped server", {"pkg/second.py": server}, "pkg/second.py"),
        ("server removed", {"pkg/server.py": 'print("gone")\n'}, "servers removed: pkg/server.py"),
        ("capability offers the adapter", {"launch/agent-launch.toml": base["launch/agent-launch.toml"]
                                           + '[capabilities.vendor]\ncommand = "y"\noffers = [{ operation = "review", '
                                             f'adapter = "{ADAPTER}", hosts = ["codex"] }}]\n'}, "capabilities added: vendor"),
        ("bundler dropped", {"pkg/builder.py": 'SOURCE = "elsewhere"\n'}, "bundlers changed"),
        ("hand edit", None, "text differs from its projection"),
        ("Korean markers missing", {"ko/DEPENDENCIES.md": "# 의존성\n"}, "ko/DEPENDENCIES.md: requires exactly one"),
        ("markers reversed", {"DEPENDENCIES.md": f"# Dependencies\n{END}\n{START}\n"}, "DEPENDENCIES.md: MCP inventory markers are reversed"),
        ("Korean reference missing", {"ko/DEPENDENCIES.md": None}, "ko/DEPENDENCIES.md: missing"),
        ("nothing shipped", {"package.json": json.dumps({"files": []})}, "judged nothing"),
        ("no capabilities", {"launch/agent-launch.toml": "[other]\nx = 1\n"}, "launcher leg judged nothing"),
    ]
    for label, change, expected in cases:
        root = emitted(base)
        try:
            if change is None:
                doc = root / "DEPENDENCIES.md"
                doc.write_text(doc.read_text().replace("Shipped servers:", "Servers we ship:"))
            else:
                for name, body in change.items():
                    if body is None:
                        (root / name).unlink()
                        continue
                    (root / name).parent.mkdir(parents=True, exist_ok=True)
                    (root / name).write_text(body)
            result = run(root)
            if not any(expected in failure for failure in result):
                failures.append(f"{label}: expected a failure naming {expected!r}, got {result}")
        finally:
            shutil.rmtree(root)
    if failures:
        for failure in failures:
            print(f"check-mcp-inventory --self-test: FAIL {failure}")
        return 1
    print(f"check-mcp-inventory --self-test: OK (positive, idempotent emit, 2 quiet controls, {len(cases)} negative)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--emit", action="store_true")
    action.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    failures = run(args.root, write=args.emit)
    for failure in failures:
        print(f"check-mcp-inventory: FAIL {failure}")
    if failures:
        return 1
    facts = derive(args.root)
    print(f"check-mcp-inventory: OK ({facts['scanned']} shipped Python files scanned, "
          f"{len(facts['servers'])} server(s), {len(facts['capabilities'])} launch capability offering {ADAPTER})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
