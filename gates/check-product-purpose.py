#!/usr/bin/env python3
"""Keep the project purpose visible and single-sourced; do not judge its meaning.

AGENTS.md owns the marked purpose block. README.md projects it and CLAUDE.md
imports AGENTS.md. --emit updates only the README block. The offline gate and
its planted negative controls run in check-parity.sh.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- product-purpose:start -->"
END = "<!-- product-purpose:end -->"
SUBJECTS = ("AGENTS.md", "README.md", "CLAUDE.md", "gates/check-parity.sh")


def block(text: str, name: str) -> tuple[int, int, str]:
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError(f"{name}: requires exactly one purpose marker pair")
    begin, end = text.index(START) + len(START), text.index(END)
    if end <= begin or not text[begin:end].strip():
        raise ValueError(f"{name}: purpose block is empty or reversed")
    return begin, end, text[begin:end]


def load(root: Path) -> dict[str, str]:
    values = {}
    for name in SUBJECTS:
        p = root / name
        if not p.is_file():
            raise ValueError(f"{name}: required purpose subject is missing")
        values[name] = p.read_text(encoding="utf-8")
    return values


def problems(values: dict[str, str]) -> list[str]:
    failures = []
    try:
        source = block(values["AGENTS.md"], "AGENTS.md")[2]
        destination = block(values["README.md"], "README.md")[2]
        if source != destination:
            failures.append("README.md: purpose differs from AGENTS.md; run --emit")
    except ValueError as exc:
        failures.append(str(exc))
    if values["CLAUDE.md"].splitlines().count("@AGENTS.md") != 1:
        failures.append("CLAUDE.md: requires exactly one @AGENTS.md import")
    runner = values["gates/check-parity.sh"]
    for suffix, label in ((r" --self-test", "self-test"), ("", "check")):
        pattern = r"^\s*python3 gates/check-product-purpose\.py" + suffix + r"(?:\s*\\)?\s*$"
        if not re.search(pattern, runner, re.M):
            failures.append(f"gates/check-parity.sh: missing product purpose {label} call")
    return failures


def project(values: dict[str, str]) -> str:
    source = block(values["AGENTS.md"], "AGENTS.md")[2]
    begin, end, _ = block(values["README.md"], "README.md")
    return values["README.md"][:begin] + source + values["README.md"][end:]


def self_test() -> None:
    purpose = "\nWorkers select, share, and inherit a work environment.\n"
    good = {
        "AGENTS.md": "# Project\n" + START + purpose + END + "\nRules stay here.\n",
        "README.md": "# Service\n" + START + purpose + END + "\nUsage stays here.\n",
        "CLAUDE.md": "@AGENTS.md\n",
        "gates/check-parity.sh": "python3 gates/check-product-purpose.py --self-test\npython3 gates/check-product-purpose.py\n",
    }
    script = Path(__file__).resolve()
    cases = []
    for name in SUBJECTS:
        mutated = dict(good)
        del mutated[name]
        cases.append((f"missing {name}", mutated, name))
    for name in ("AGENTS.md", "README.md"):
        cases.append((f"empty {name}", dict(good, **{name: START + "\n " + END}), name))
        cases.append((f"duplicate {name}", dict(good, **{name: good[name] + START + purpose + END}), name))
        cases.append((f"reversed {name}", dict(good, **{name: END + purpose + START}), name))
    cases.extend([
        ("divergent projection", dict(good, **{"README.md": good["README.md"].replace("Workers", "Other workers")}), "README.md"),
        ("wrong import", dict(good, **{"CLAUDE.md": "@claude/CLAUDE.md\n"}), "CLAUDE.md"),
        ("duplicate import", dict(good, **{"CLAUDE.md": "@AGENTS.md\n@AGENTS.md\n"}), "CLAUDE.md"),
        ("missing check call", dict(good, **{"gates/check-parity.sh": "python3 gates/check-product-purpose.py --self-test\n"}), "gates/check-parity.sh"),
        ("missing self-test call", dict(good, **{"gates/check-parity.sh": "python3 gates/check-product-purpose.py\n"}), "gates/check-parity.sh"),
    ])
    with tempfile.TemporaryDirectory(prefix="product-purpose-") as td:
        root = Path(td)

        def run(values: dict[str, str], *flags: str):
            for name in SUBJECTS:
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                if name in values:
                    p.write_text(values[name], encoding="utf-8")
                elif p.exists():
                    p.unlink()
            return subprocess.run([sys.executable, str(script), "--root", str(root), *flags],
                                  capture_output=True, text=True)

        positive = run(good)
        if positive.returncode:
            raise AssertionError(f"positive control failed: {positive.stdout}{positive.stderr}")
        for label, values, subject in cases:
            result = run(values)
            if result.returncode == 0 or subject not in result.stdout + result.stderr:
                raise AssertionError(f"{label}: did not fail by subject name")
        stale = dict(good, **{"README.md": good["README.md"].replace("Workers", "Other workers")})
        result = run(stale, "--emit")
        if result.returncode or (root / "README.md").read_text() != good["README.md"]:
            raise AssertionError("emit failed to preserve unrelated README text")
        if project(good) != good["README.md"]:
            raise AssertionError("projection is not idempotent")
    print(f"check-product-purpose --self-test: OK (positive, {len(cases)} negative, emit, idempotence)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--emit", action="store_true")
    action.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    try:
        values = load(args.root)
        if args.emit:
            output = project(values)
            (args.root / "README.md").write_text(output, encoding="utf-8")
            values["README.md"] = output
        failures = problems(values)
    except (ValueError, OSError) as exc:
        failures = [str(exc)]
    for failure in failures:
        print(f"check-product-purpose: FAIL {failure}")
    if failures:
        return 1
    print("check-product-purpose: OK (AGENTS owner, README projection, CLAUDE import, parity calls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
