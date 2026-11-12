#!/usr/bin/env python3
"""Where S11 and S12 are allowed to write, resolved before the first effect (WP-21 commit 1).

Design §10.5 with amendment N#4. Every writer S11 and S12 run resolves its destination from the
environment the run hands it; each destination must be INSIDE the root its class declares in
`run.json.destinations`; and `destinations.resolved.json` records the whole set before the first
`planned` journal record exists. A destination outside its root is `DESTINATION_OUTSIDE_ROOT` and a
required override that is unset is `OVERRIDE_MISSING` — both refusals, both before any effect.

Why an unset override is a refusal even when its fallback looks harmless: a fallback is a path the
run did not declare. `update-state.py` falls back through `pathlib.Path.home()`, which reads HOME
when it is set and the password database when it is not, so the same code that writes into a fixture
in one process writes into the real home of whoever runs it in another. This repository has paid for
that once already (a control exercising a `pw_dir` fallback wrote a run into the owner's home during
a commit hook). The confinement is therefore the declaration, never the fallback.

This module writes nothing except `destinations.resolved.json`, and performs no effect of any kind.
It is the first commit of WP-21 on purpose: the code that confines writes lands before the code that
writes.

    destinations.py --self-test
"""
import json
import os
import pathlib
import sys

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import declare, records  # noqa: E402
from runlib.records import Refused  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
REPO = HERE.parent
TABLE_PATH = HERE / "tables" / "destinations.json"
OUTPUT = "destinations.resolved.json"
# The declared classes come from the declaration's own schema, through declare.py, so this module
# cannot disagree with what a run is allowed to declare.
CLASSES = declare.DESTINATIONS
_TABLE = {}


def table():
    """The writer inventory, read once."""
    if not _TABLE:
        _TABLE.update(json.loads(TABLE_PATH.read_text(encoding="utf-8")))
    return _TABLE


def writers():
    return tuple(table()["writers"])


def pairs():
    """Every (writer, override, class) the table declares, in table order."""
    held = []
    for row in writers():
        for entry in row.get("destinations") or ():
            held.append((row.get("writer"), entry.get("override"), entry.get("class")))
    return tuple(held)


def required_overrides():
    """Every environment name some writer's destination depends on, sorted."""
    return tuple(sorted({override for _writer, override, _cls in pairs()}))


def class_of_override():
    """Each override's class, and the overrides two writers place in different classes.

    An environment variable has one value, so a variable two writers read must resolve to one class
    for both; otherwise its single value would have to be inside two roots at once, which is
    satisfiable only by accident. The disagreement is a table defect, reported by name.
    """
    held, conflicts = {}, {}
    for writer, override, cls in pairs():
        if override in held and held[override] != cls:
            conflicts.setdefault(override, {held[override]}).add(cls)
        held.setdefault(override, cls)
    return held, conflicts


def table_problems():
    """What is wrong with the table itself, by name.

    A writer naming a class the declaration does not hold cannot be confined, and a declared class
    no writer uses is a stale declaration — the same bar the lexicon gate applies to a concept home
    that matches no file.
    """
    problems, rows = [], writers()
    if not rows:
        problems.append("WRITER_SET_EMPTY: a destination manifest over no writer confines nothing")
        return problems
    for row in rows:
        if not row.get("writer"):
            problems.append("WRITER_UNNAMED: a row with no writer")
            continue
        named = [entry.get("class") for entry in row.get("destinations") or ()]
        if row.get("writes_without_override"):
            named.append(row["writes_without_override"])
        if not named:
            problems.append(f"DESTINATION_UNDECLARED {row['writer']}: the row names no class, by "
                            f"override or otherwise")
        for cls in named:
            if cls not in CLASSES:
                problems.append(f"DESTINATION_UNDECLARED {row['writer']}: class {cls!r} is not one "
                                f"of {', '.join(CLASSES)}")
        if row.get("destinations") and row.get("writes_without_override"):
            problems.append(f"DESTINATION_BOTH_WAYS {row['writer']}: a writer resolves its "
                            f"destination from overrides or declares one directly, never both")
        if not row.get("$comment"):
            problems.append(f"WRITER_UNREASONED {row['writer']}: every row carries its own reason")
    _held, conflicts = class_of_override()
    for override, names in sorted(conflicts.items()):
        problems.append(f"OVERRIDE_CLASS_SPLIT {override}: placed in {', '.join(sorted(names))} by "
                        f"different writers, but one variable has one value")
    used = set()
    for row in rows:
        used.update(entry.get("class") for entry in row.get("destinations") or ())
        if row.get("writes_without_override"):
            used.add(row["writes_without_override"])
    for name in CLASSES:
        if name not in used:
            problems.append(f"DESTINATION_CLASS_UNWRITTEN {name}: a declared class no writer writes "
                            f"under is a stale declaration")
    return problems


def fidelity_problems():
    """Where the table's stated fallback is no longer the one its writer carries.

    The fallback is a restatement, tolerated because this makes its drift decidable: the literal must
    still be present in the writer's own source. A row whose source file is gone fails too — the
    inventory would otherwise go on describing a writer that no longer exists.
    """
    problems = []
    for row in writers():
        source = row.get("fallback_source")
        if source is None:
            if row.get("fallbacks"):
                problems.append(f"FALLBACK_UNSOURCED {row['writer']}: a fallback is stated with no "
                                f"source to hold it against")
            continue
        path = REPO / source
        if not path.is_file():
            problems.append(f"WRITER_SOURCE_ABSENT {row['writer']}: {source} does not exist")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for held in row.get("fallbacks") or ():
            if held["literal"] not in text:
                problems.append(f"FALLBACK_MOVED {row['writer']} {held['override']}: {source} no "
                                f"longer carries {held['literal']!r}")
    return problems


def inside(path, root):
    """Public name for the containment question, so one module answers it.

    `journal.py` asks it of its own file: the journal is `runtime_state`, and a journal written
    outside its declared root is the hole this module exists to close.
    """
    return _inside(path, root)


def _inside(path, root):
    """Whether `path` is the root itself or beneath it, decided on normalized absolute paths.

    No `resolve()`: a symlink is followed by the writer, so the question is what the writer will
    open, and `/var` against `/private/var` has cost this repository a green pretrial and a red hook
    before. Normalizing without resolving keeps the answer the same in both places.
    """
    path = pathlib.PurePosixPath(os.path.normpath(str(path)))
    root = pathlib.PurePosixPath(os.path.normpath(str(root)))
    return path == root or root in path.parents


def resolved_rows(declaration, environ):
    """One row per writer: `{class, writer, path, root, inside}` as N#4 names it.

    `path` is what the writer will actually write under, taken from the environment the run hands it
    — never from this process's own environment unless the caller passes it.
    """
    roots = (declaration or {}).get("destinations") or {}
    rows = []
    for row in writers():
        # One row per (writer, override), so a single escaping value cannot hide behind a sibling
        # of the same writer that is in root.
        for entry in row.get("destinations") or ():
            override, cls = entry.get("override"), entry.get("class")
            root, value = roots.get(cls), environ.get(override)
            if not value:
                rows.append({"class": cls, "writer": f"{row['writer']} [{override}]", "path": None,
                             "root": root, "inside": False, "unset": [override]})
                continue
            rows.append({"class": cls, "writer": f"{row['writer']} [{override}]", "path": value,
                         "root": root, "inside": bool(root) and _inside(value, root)})
        if row.get("writes_without_override"):
            cls = row["writes_without_override"]
            root = roots.get(cls)
            rows.append({"class": cls, "writer": row["writer"], "path": root, "root": root,
                         "inside": bool(root)})
    return rows


def resolution_problems(rows):
    """The refusals the resolved set carries, by name, in the order a reader needs them.

    `OVERRIDE_MISSING` comes first: an unset override means the path in the row is not what the
    writer would use, so judging that path for escape would be judging a value nobody will write to.
    """
    problems = []
    for row in rows:
        for name in row.get("unset") or ():
            problems.append(f"OVERRIDE_MISSING {row['writer']} {name}: unset, so this writer would "
                            f"resolve through a fallback the run did not declare")
    for row in rows:
        if row.get("unset"):
            continue
        if not row.get("root"):
            problems.append(f"DESTINATION_ROOT_ABSENT {row['writer']}: the run declares no root for "
                            f"class {row['class']}")
            continue
        if not row["inside"]:
            problems.append(f"DESTINATION_OUTSIDE_ROOT {row['writer']}: {row['path']} is not inside "
                            f"{row['root']}")
    return problems


def problems(declaration, environ):
    """Everything wrong, table and resolution together. Empty means apply may take its first effect."""
    held = table_problems() + fidelity_problems()
    if held:
        return held
    return resolution_problems(resolved_rows(declaration, environ))


def document(declaration, environ):
    """The manifest `apply` writes before any effect, or Refused naming what stops it."""
    rows = resolved_rows(declaration, environ)
    held = table_problems() + fidelity_problems() + resolution_problems(rows)
    if held:
        raise Refused("; ".join(held))
    return {"stage": "S11", "resolved": rows,
            "overrides_required": list(required_overrides()),
            "classes": list(CLASSES),
            "$comment": "design §10.5 / N#4: every writer's destination, resolved from the "
                        "environment the run hands it and asserted inside its declared root before "
                        "the first effect."}


def write(run_dir, declaration, environ):
    """Write the manifest into the run. Nothing is written when anything refuses.

    The path is absolute beneath the run and the file is registered with the stage, for the reason
    `stage_propose.run` states: `records.write_json` confines its path, so a bare name resolves
    against the working directory and is refused, and an unregistered output leaves the next stage's
    staleness check nothing to read.
    """
    run_dir = pathlib.Path(run_dir)
    doc = document(declaration, environ)       # refuses before the stage record is opened
    # No declared input: the run declaration is the run's own root, not a stage output, so naming it
    # as one is refused (`INPUT_INVALID S0: no record for the stage that produces run.json`). Every
    # stage that reads only the declaration opens its record the same way.
    with records.run_stage(run_dir, "S11") as stage:
        records.write_json(run_dir, run_dir / OUTPUT, doc)
        stage.output(OUTPUT)
        return stage, doc


# ---- self-test ---------------------------------------------------------------------------------


def self_test():
    failures, ran = [], []

    def control(name, got, want):
        ran.append(name)
        if want not in str(got):
            failures.append((name, f"expected {want!r} in {str(got)[:400]!r}"))

    def clean(name, held):
        ran.append(name)
        if held:
            failures.append((name, f"expected nothing, got {held}"))

    def guarded(call):
        """The call's answer, or the exception as text.

        Without this a revert that removes a guard raises out of the control and the trial reads a
        traceback where it needed a named failure: a control that dies is not a control.
        """
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - the exception IS the answer here
            return f"RAISED {type(exc).__name__}: {exc}"

    def refusal(call):
        try:
            call()
        except Refused as exc:
            return str(exc)
        return ""

    # The declaration's own fixture, so the roots this suite judges are the ones a real run declares
    # rather than a shape invented here.
    FIXTURE = declare.fixture()
    root = str(pathlib.PurePosixPath(FIXTURE["destinations"][CLASSES[0]]).parent.parent)

    def fx_declaration(**over):
        held = dict(FIXTURE["destinations"])
        held.update(over)
        return {**FIXTURE, "destinations": held}

    def fx_env(**over):
        held = {override: f"{root}/destinations/{cls}/{override.lower()}"
                for override, cls in class_of_override()[0].items()}
        held.update(over)
        return held

    # ---- the table itself ------------------------------------------------------------------------
    clean("the writer inventory is well formed and every class it names is a declared one",
          table_problems())
    clean("and every stated fallback is still the literal its writer's source carries",
          fidelity_problems())
    def declared_classes():
        held = set()
        for row in writers():
            held.update(entry["class"] for entry in row.get("destinations") or ())
            if row.get("writes_without_override"):
                held.add(row["writes_without_override"])
        return held

    clean("every declared destination class is written by some writer, so no class is a stale "
          "declaration", [name for name in CLASSES if name not in declared_classes()])
    clean("and no override is placed in two classes, since one variable has one value",
          sorted(class_of_override()[1]))
    control("the overrides are read from the table rather than named here",
            next(line for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                 if line.strip().startswith("return tuple(sorted({override")), "pairs()")
    control("the classes come from the declaration's schema rather than a list here",
            next(line for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()
                 if line.startswith("CLASSES = ")), "declare.DESTINATIONS")
    clean("the required overrides are the union of the table's own pairs, with nothing invented",
          sorted(set(required_overrides()) - {override for _w, override, _c in pairs()}))
    control("and update-state.py's nudge override is among them, since its fallback reads the "
            "password database", ", ".join(required_overrides()),
            "AGENT_BIOS_SESSION_DISTILL_STATE")

    def with_table(mutate, call):
        """Run `call` with the table mutated, restoring it however the call ends."""
        held = json.loads(json.dumps(table()))
        try:
            mutate(_TABLE)
            return call()
        finally:
            _TABLE.clear()
            _TABLE.update(held)

    control("a writer naming a class the declaration does not hold is refused by name",
            with_table(lambda t: t["writers"][0]["destinations"][0].__setitem__("class", "elsewhere"),
                       lambda: "; ".join(table_problems())),
            "DESTINATION_UNDECLARED install.sh")
    control("a class no writer writes under is refused as a stale declaration",
            with_table(lambda t: t.__setitem__(
                "writers", [r for r in t["writers"]
                            if not any(e["class"] == "nudge" for e in r.get("destinations") or ())]),
                       lambda: "; ".join(table_problems())),
            "DESTINATION_CLASS_UNWRITTEN nudge")
    control("one variable placed in two classes by two writers is refused: its single value cannot "
            "be inside two roots",
            with_table(lambda t: t["writers"][2]["destinations"][1].__setitem__("class", "recovery"),
                       lambda: "; ".join(table_problems())),
            "OVERRIDE_CLASS_SPLIT AGENT_BIOS_STATE_DIR")
    control("a writer that both takes overrides and declares a class directly is refused, because "
            "then two answers exist for one destination",
            with_table(lambda t: t["writers"][0].__setitem__("writes_without_override", "checkout"),
                       lambda: "; ".join(table_problems())),
            "DESTINATION_BOTH_WAYS install.sh")
    control("a row that names no class at all is refused",
            with_table(lambda t: (t["writers"][4].__setitem__("writes_without_override", None)),
                       lambda: "; ".join(table_problems())),
            "DESTINATION_UNDECLARED git")
    control("an empty writer set is refused, because a manifest over no writer confines nothing",
            with_table(lambda t: t.__setitem__("writers", []),
                       lambda: "; ".join(table_problems())),
            "WRITER_SET_EMPTY")
    control("a writer row without its own reason is refused",
            with_table(lambda t: t["writers"][0].pop("$comment"),
                       lambda: "; ".join(table_problems())),
            "WRITER_UNREASONED install.sh")
    control("a fallback whose literal has left its writer's source is named with the file",
            with_table(lambda t: t["writers"][0]["fallbacks"][0].__setitem__(
                           "literal", "${CLAUDE_CONFIG_DIR:-$HOME/.claude-gone}"),
                       lambda: "; ".join(fidelity_problems())),
            "FALLBACK_MOVED install.sh CLAUDE_CONFIG_DIR")
    control("and a row whose source file is gone is named too, rather than raising",
            with_table(lambda t: t["writers"][0].__setitem__("fallback_source", "install-gone.sh"),
                       lambda: guarded(lambda: "; ".join(fidelity_problems()))),
            "WRITER_SOURCE_ABSENT install.sh")

    # ---- the resolution --------------------------------------------------------------------------
    rows = resolved_rows(fx_declaration(), fx_env())
    clean("with every override set inside its class's root, nothing refuses", resolution_problems(rows))
    clean("every writer in the inventory is answered for", [row["writer"] for row in writers()
                                                            if not any(r["writer"].startswith(row["writer"])
                                                                       for r in rows)])
    control("and every (writer, override) pair has its own row, so the count is the pair count plus "
            "the writers that take none",
            f'{len(rows)}', f'{len(pairs()) + len([r for r in writers() if r.get("writes_without_override")])}')
    clean("and every row says which class, which root and whether it is inside",
          [r["writer"] for r in rows if set(r) < {"class", "writer", "path", "root", "inside"}])
    control("a writer with several overrides is answered once per override, so one escaping value "
            "cannot hide behind a sibling in root",
            str(len([r for r in rows if r["writer"].startswith("install.sh [")])), "3")

    # OVERRIDE_MISSING: the case that writes into a real home through a fallback.
    unset = resolution_problems(resolved_rows(fx_declaration(),
                                              {k: v for k, v in fx_env().items()
                                               if k != "AGENT_BIOS_SESSION_DISTILL_STATE"}))
    control("an unset override is refused before anything else, naming the writer and the variable",
            "; ".join(unset), "OVERRIDE_MISSING session-distill/update-state.py "
                              "[AGENT_BIOS_SESSION_DISTILL_STATE] AGENT_BIOS_SESSION_DISTILL_STATE")
    control("and the refusal says why a fallback is not an answer", "; ".join(unset),
            "a fallback the run did not declare")
    clean("an unset override is not also reported as an escape, since the path in the row is not "
          "the one the writer would use",
          [p for p in unset if "DESTINATION_OUTSIDE_ROOT" in p
           and "update-state" in p])
    control("the unset override is reported before any escape in the same resolution",
            "|".join(p.split()[0] for p in resolution_problems(resolved_rows(
                fx_declaration(),
                {**{k: v for k, v in fx_env().items() if k != "ZDOTDIR"},
                 "CODEX_HOME": f"{root}-other/codex"}))),
            "OVERRIDE_MISSING")

    # DESTINATION_OUTSIDE_ROOT: an actual escape, under a second fixture root.
    escaped = resolution_problems(resolved_rows(
        fx_declaration(), fx_env(AGENT_BIOS_SESSION_DISTILL_STATE=f"{root}-other/nudge/state.json")))
    control("a destination under a second root is refused by name with both paths",
            "; ".join(escaped), f"DESTINATION_OUTSIDE_ROOT session-distill/update-state.py "
                                f"[AGENT_BIOS_SESSION_DISTILL_STATE]: {root}-other/nudge/state.json")
    control("and the refusal names the root it is not inside", "; ".join(escaped),
            f"not inside {root}/destinations/nudge")
    clean("a path that IS the root is inside it, not an escape",
          resolution_problems(resolved_rows(
              fx_declaration(), fx_env(AGENT_BIOS_SESSION_DISTILL_STATE=f"{root}/destinations/nudge"))))
    control("a sibling directory whose name merely starts with the root's is an escape, not a child",
            "; ".join(resolution_problems(resolved_rows(
                fx_declaration(),
                fx_env(AGENT_BIOS_SESSION_DISTILL_STATE=f"{root}/destinations/nudge-other/s.json")))),
            "DESTINATION_OUTSIDE_ROOT")
    control("a traversal that climbs out of the root is an escape even though its text begins inside",
            "; ".join(resolution_problems(resolved_rows(
                fx_declaration(),
                fx_env(AGENT_BIOS_SESSION_DISTILL_STATE=f"{root}/destinations/nudge/../../out.json")))),
            "DESTINATION_OUTSIDE_ROOT")
    clean("and one that climbs and comes back is inside, because the question is what the writer opens",
          resolution_problems(resolved_rows(
              fx_declaration(),
              fx_env(AGENT_BIOS_SESSION_DISTILL_STATE=f"{root}/destinations/nudge/d/../s.json"))))
    control("a run that declares no root for a class is refused rather than defaulting to one",
            "; ".join(resolution_problems(resolved_rows(
                {"destinations": {k: v for k, v in fx_declaration()["destinations"].items()
                                  if k != "checkout"}}, fx_env()))),
            "DESTINATION_ROOT_ABSENT")

    # ---- the document and the write --------------------------------------------------------------
    doc = document(fx_declaration(), fx_env())
    control("the document carries one resolved row per answered writer",
            str(len(doc["resolved"])), str(len(rows)))
    control("and the overrides the run must set", json.dumps(doc["overrides_required"]),
            "AGENT_BIOS_SESSION_DISTILL_STATE")
    clean("with every row inside its root", [r["writer"] for r in doc["resolved"] if not r["inside"]])
    control("a document over an escaping environment is refused instead of written",
            refusal(lambda: document(fx_declaration(),
                                     fx_env(CODEX_HOME=f"{root}-other/codex"))),
            "DESTINATION_OUTSIDE_ROOT")
    control("and so is one over a mutated table, so the manifest cannot be written from a broken "
            "inventory",
            with_table(lambda t: t.__setitem__("writers", []),
                       lambda: refusal(lambda: document(fx_declaration(), fx_env()))),
            "WRITER_SET_EMPTY")

    import shutil
    import tempfile
    held_root = pathlib.Path(tempfile.mkdtemp(prefix="dest-", dir="/tmp"))
    try:
        run_dir = held_root / "r1"
        declare.create(run_dir, fx_declaration())
        declaration = records.read_json(run_dir / "run.json")
        try:
            _stage, written = write(run_dir, declaration, fx_env())
        except Refused as exc:
            written = {"problem": str(exc)}
        control("the manifest is written inside the run", str((run_dir / OUTPUT).is_file()), "True")
        clean("and holds what the document held",
              [] if (run_dir / OUTPUT).is_file()
              and records.read_json(run_dir / OUTPUT).get("resolved") == written.get("resolved")
              else [f"{written}"])
        record = records.read_json(records.record_path(run_dir, "S11"))
        control("registered with the stage, so a later stage can read its staleness",
                json.dumps([o.get("artifact") for o in record.get("outputs") or []]), OUTPUT)
        # Nothing is written when anything refuses: the escape case must leave no manifest at all.
        other = held_root / "r2"
        declare.create(other, fx_declaration())
        said = refusal(lambda: write(other, declaration, fx_env(CODEX_HOME=f"{root}-other/codex")))
        control("a refused resolution writes nothing", said, "DESTINATION_OUTSIDE_ROOT")
        clean("not even an empty manifest, and no stage record either",
              [name for name in (OUTPUT, "records") if (other / name).exists() and name == OUTPUT]
              + ([f"an S11 record exists"] if records.record_path(other, "S11").exists() else []))
        clean("and the escape target itself was never touched: it is a fixture path and has no file",
              [] if not pathlib.Path(f"{root}-other/codex").exists() else ["/elsewhere/codex exists"])
    finally:
        shutil.rmtree(held_root, ignore_errors=True)

    # This module performs no effect, which is the whole reason it is the first commit. Asserted on
    # its own source, in both directions, so a later edit that adds one is caught here.
    import ast
    own = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    spawners = sorted({ast.unparse(node.func) for node in ast.walk(own) if isinstance(node, ast.Call)
                       and ast.unparse(node.func).split(".")[0] in ("subprocess", "os")
                       and ast.unparse(node.func) not in ("os.path.normpath", "os.environ.get")})
    clean("this module runs nothing and spawns nothing: the code that confines writes cannot itself "
          "be a writer", spawners)
    control("and the only file it writes is its own manifest",
            ", ".join(sorted({ast.unparse(node.func) for node in ast.walk(own)
                              if isinstance(node, ast.Call)
                              and ast.unparse(node.func).startswith("records.write_")})),
            "records.write_json")

    print(f"destinations --self-test: {'FAILED' if failures else 'OK'} ({len(ran)} controls: the "
          f"writer inventory held against its writers' own sources, OVERRIDE_MISSING before any "
          f"escape judgement, an escape under a second fixture root, the root itself and a "
          f"name-prefix sibling, traversal in both directions, and a refused resolution writing "
          f"nothing)")
    for name, detail in failures:
        print(f"destinations --self-test [FAIL] {name}: {detail}")
    return 1 if failures else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    print(json.dumps({"classes": list(CLASSES), "overrides_required": list(required_overrides()),
                      "writers": [{"writer": r["writer"], "class": r["class"],
                                   "overrides": r.get("overrides") or []} for r in writers()]},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
