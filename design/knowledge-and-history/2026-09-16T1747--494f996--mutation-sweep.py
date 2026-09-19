#!/usr/bin/env python3
"""Remove one refusal at a time from the bound evaluator and ask whether the helper notices.

Author-side measurement for this bundle; it is not a gate and never edits the bundle.
A refusal is an `errs.append(...)` / `errors.append(...)` statement, or a `return` of a
non-empty list literal (including `return <list> + [...]`). Each mutant replaces exactly
one refusal with `pass`, is written over the validator inside a throwaway copy of every
bound member, and the bound regression helper runs against that copy. A mutant the helper
still reports as `passed` is an undetected refusal.

usage: python3 <this file> [plan] [--json OUT]
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / "2026-09-16T1747--494f996--development-plan.json"
NAMES = {"errs", "errors"}


def refusals(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if (isinstance(func, ast.Attribute) and func.attr == "append"
                    and isinstance(func.value, ast.Name) and func.value.id in NAMES):
                found.append(node)
        elif isinstance(node, ast.Return) and node.value is not None:
            value = node.value
            if isinstance(value, ast.List) and value.elts:
                found.append(node)
            elif (isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add)
                  and isinstance(value.right, ast.List) and value.right.elts):
                found.append(node)
    return sorted(found, key=lambda node: (node.lineno, node.col_offset))


class Remove(ast.NodeTransformer):
    def __init__(self, target):
        self.target = target

    def visit(self, node):
        if node is self.target:
            return ast.copy_location(ast.Pass(), node)
        return super().visit(node)


def mutant(source, index):
    tree = ast.parse(source)
    return ast.unparse(ast.fix_missing_locations(Remove(refusals(tree)[index]).visit(tree)))


def run_mutant(job):
    index, plan_path, plan, source = job
    with tempfile.TemporaryDirectory(prefix="agent-bios-mutant-") as folder:
        folder = Path(folder)
        names = {row["path"] for row in plan["document_bindings"]} | {plan["validator"], plan["regression_tests"]}
        for name in names:
            shutil.copyfile(plan_path.parent / name, folder / name)
        shutil.copyfile(plan_path, folder / plan_path.name)
        (folder / plan["validator"]).write_text(mutant(source, index), encoding="utf-8")
        done = subprocess.run([sys.executable, "-B", str(folder / plan["regression_tests"]), str(folder / plan_path.name)],
                              capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
                              env={**os.environ, "PYTHONUTF8": "1"}, timeout=600, check=False)
    try:
        result = json.loads(done.stdout)
        return index, result.get("status"), [row["check"] for row in result.get("failures", [])]
    except json.JSONDecodeError:
        return index, "crash", [done.stderr.strip()[-200:]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", nargs="?", type=Path, default=DEFAULT)
    parser.add_argument("--json", type=Path, help="write every mutant's outcome here")
    args = parser.parse_args()
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    source = (plan_path.parent / plan["validator"]).read_text(encoding="utf-8")
    targets = refusals(ast.parse(source))
    if not targets:
        print("mutation sweep: the evaluator has no refusal to remove, so this measured nothing")
        return 1
    rows = [None] * len(targets)
    jobs = [(index, plan_path, plan, source) for index in range(len(targets))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        for index, status, failed in pool.map(run_mutant, jobs):
            node = targets[index]
            rows[index] = {"line": node.lineno,
                           "statement": ast.get_source_segment(source, node).splitlines()[0].strip()[:110],
                           "helper": status, "caught_by": failed[:3]}
    undetected = [row for row in rows if row["helper"] == "passed"]
    print(f"refusals: {len(rows)}  detected: {len(rows) - len(undetected)}  undetected: {len(undetected)}")
    for row in undetected:
        print(f"  L{row['line']:<4} {row['statement']}")
    if args.json:
        args.json.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
