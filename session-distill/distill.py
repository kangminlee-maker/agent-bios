#!/usr/bin/env python3
"""Session distill driver: one subcommand per stage, one run directory per run.

  distill.py declare --run-id ID --from DECLARATION.json   S0: write run.json (declaration_seq 0)
  distill.py declare --run-id ID --set PATH=VALUE ...      edit it in place, until a stage has read it
  distill.py declare --run-id ID --amend --reason TEXT --set PATH=VALUE ... [--scope S2,S3]
                                                           [--invalidates S1]
  distill.py declare --self-test                           the declaration's controls
  distill.py --self-test                                   declare -> stage -> amend -> stage, on real files
  distill.py census --run-id ID [--coverage PATH]          S1: census.json and coverage.json into the run directory
  distill.py inventory --run-id ID [--pin HOST:SESSION]   S2: inventory/<reference>.json, the units per layer
  distill.py census --run-id ID --reconcile RESULTS.json   S3's results folded back into the statuses and the coverage
  distill.py views --run-id ID                             S2: the immutable copies, the redaction projection, the
                                                           windows, the search index and the evidence store
  distill.py <stage command> --run-id ID                   S3-S12: named, and refused until implemented

A run lives in `session-distill/out/<run-id>/` (`--out` names another root): `run.json`,
`amendments.jsonl`, `stages/<stage>/record.json`, and per-call directories. The declaration,
its amendments and the stage records are `runlib/declare.py` and `runlib/records.py`; the
record schemas every stage keeps (claim, evidence, expected observation) are
`schemas/*.schema.json`, loaded through `runlib/claims.py`; the declaration's own structure is
`schemas/run.schema.json`. The census (S1) is `runlib/census.py`, over the readers of `runlib/sources.py`,
`runlib/lineage.py` and the coverage state of `runlib/coverage.py`. The views (S2) are `runlib/views.py`,
over `runlib/redaction.py`, `runlib/search.py` and the evidence store of `runlib/evidence.py`.
Design: §3, §4, §4.1, §5.1-§5.5.
"""
import argparse
import contextlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

# Before the command's module graph is imported, not inside the functions that load modules by
# path: `runlib.projection` loads `learn/redact.py` at import, and a cache write lands beside the
# file it caches — in the checkout, or in a frozen copy this run is about to hash (GB#7).
sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from runlib import census, coverage, declare, inventory, projection, records, stagelock, views
from runlib.records import Refused

OUT = pathlib.Path(__file__).resolve().parent / "out"
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
HOME = str(pathlib.Path.home())


def say(text, stream=None):
    """One line this command publishes, through the floor's own entry point (GC#6).

    A diagnostic is an artifact: a person reads it and whatever captured the terminal keeps it, so
    printing a line the write boundary would refuse is the same leak by another route. Everything
    this driver prints — a report, a refusal, a stage that is not implemented, an argument the parser
    did not understand — leaves through here. `--bad api_key=shortpass` and
    `--run-id api_key=shortpass` each repeated the secret on stderr before a line of the command ran,
    because `parse_args` and `print(str(exc))` stood outside every boundary this run has."""
    print(projection.diagnostic(text, HOME), file=stream or sys.stdout)


class Parser(argparse.ArgumentParser):
    """`argparse`, with every message it prints passing the floor first.

    `error()` echoes the argument it did not understand and `print_usage`/`print_help` echo the
    metavars; all three go through `_print_message`, which is the one place to put the boundary."""

    def _print_message(self, message, file=None):
        if message:
            super()._print_message(projection.diagnostic(message, HOME), file)

# Subcommand -> the stage it runs (design §4). `declare` is S0 and has no stage record.
STAGE_COMMANDS = {
    "census": "S1", "views": "S2", "inventory": "S2", "read": "S3", "form": "S4", "retrieve": "S5",
    "judge": "S6", "propose": "S7", "review-proposals": "S7b", "test": "S8", "render": "S9",
    "review-korean": "S9b", "parse-decisions": "S10", "adjudicate": "S10", "confirm": "S10b",
    "apply": "S11", "close": "S12",
}


def run_dir_of(args):
    """`--out`/`<run-id>`: the run id is one path component, and the directory it names resolves
    to a place beneath `--out`. Nothing — no lock, no directory — is created before this holds."""
    if not RUN_ID.fullmatch(args.run_id):
        raise Refused(f"RUN_ID_INVALID {args.run_id!r}: a run id is one path component of letters, digits, '.', '_' and '-'")
    run_dir = records.contained(args.out, args.run_id)
    if run_dir is None:
        raise Refused(f"RUN_DIR_ESCAPE {args.run_id!r}: {pathlib.Path(args.out) / args.run_id} resolves outside {args.out}")
    return run_dir


def split_csv(text):
    return [item for item in (text or "").split(",") if item]


def assignments_of(args):
    pairs = []
    for item in args.set or []:
        path, equals, value = item.partition("=")
        if not (path and equals):
            raise Refused(f"DECLARATION_INVALID --set {item!r}: expected PATH=VALUE")
        pairs.append((path, declare.parse_value(value)))
    return pairs


def cmd_declare(args):
    if args.self_test:
        return declare.self_test()
    if not args.run_id:
        raise Refused("DECLARATION_INVALID --run-id: declare needs the run it declares")
    run_dir = run_dir_of(args)
    if args.from_file and (args.amend or args.set):
        raise Refused("DECLARATION_INVALID --from: a new declaration takes no --set or --amend")
    if args.amend:
        amendment = declare.amend(run_dir, assignments_of(args), args.reason or "", split_csv(args.scope),
                                  split_csv(args.invalidates))
        say(f"amended {run_dir}: declaration_seq {amendment['seq']}, invalidates {amendment['invalidates']}")
    elif args.from_file:
        run = declare.create(run_dir, json.loads(pathlib.Path(args.from_file).read_text(encoding="utf-8")))
        say(f"declared {run_dir}: declaration_seq {run['declaration_seq']}")
    elif args.set:
        declare.set_fields(run_dir, assignments_of(args))
        say(f"set {len(args.set)} field(s) in {run_dir}/run.json")
    else:
        raise Refused("DECLARATION_INVALID declare: give --from, --set, --amend or --self-test")
    return 0


def cmd_census(args):
    run_dir = run_dir_of(args)
    if args.reconcile:
        before = json.loads((run_dir / "census.json").read_text(encoding="utf-8"))
        state = coverage.load(run_dir / "coverage.json")[0]
        results = json.loads(pathlib.Path(args.reconcile).read_text(encoding="utf-8"))
        done, after, flags = census.reconcile(before, state, results, before["kind"])
        records.write_text(run_dir, run_dir / "census.reconciled.json", census.dump(done))
        records.write_json(run_dir, run_dir / "coverage.reconciled.json", after)
        counts = census.window_counts(done["transcripts"])
        say(f"reconciled {run_dir}: accounted {flags['accounted']} ({counts['accounted']}/{counts['eligible']} sessions), "
            f"fully read {flags['fully_read']} ({counts['fully_read']}/{counts['eligible']})")
        return 0
    say("\n".join(census.report_lines(census.run(run_dir, args.coverage, args.originators, args.jobs))))
    return 0


def cmd_inventory(args):
    """S2's inventory: `inventory/<reference>.json` for every reference point of design §6.1."""
    out_dir = run_dir_of(args) if args.run_id else pathlib.Path(args.to or "")
    if not args.run_id and not args.to:
        raise Refused("INPUT_INVALID inventory: give --run-id, or --to DIR to write outside a run")
    repo = pathlib.Path(__file__).resolve().parents[1]
    state_root = None if args.no_state else (args.state_root or os.environ.get(
        "AGENT_BIOS_STATE_DIR", str(pathlib.Path.home() / ".local/share/agent-bios")))
    user_root = None if args.no_state else (args.user_root or os.environ.get(
        "AGENT_BIOS_INSTRUCTIONS_DIR", str(pathlib.Path.home() / ".config/agent-bios/corpus")))
    # A project is its canonical path. Keyed by basename, two checkouts both called `source` were
    # one project, and one's memory entries were read as the other's (GA#4). A project root is a
    # protected WRITE target: no native file is read, here or anywhere (the 1548 amendment §5).
    #
    # The checkout is ALWAYS one of them: `--project` adds roots to it and never replaces it. It
    # arrived here as the default value of `--project`, so naming any project at all took the
    # checkout out of the protected set and a destination inside it became writable (GC#0 through
    # `--project`). `protected_roots` carries the same rule for every other caller.
    projects = inventory.project_identities([str(repo), *(args.project or [])])
    native = {"projects": {identity["path"]: pathlib.Path(identity["path"]) for identity in projects.values()}}
    # The destination is judged before anything is locked, captured or recorded: a stage record is
    # a write, and a write under a protected root must be refused before it happens (GB#0).
    overlap = inventory.overlap_problems(
        [out_dir], inventory.protected_roots(state_root, user_root, native,
                                             host_homes=[spec["home"] for spec in inventory.NATIVE.values()],
                                             checkout=repo),
        home=HOME)
    if overlap:
        raise Refused("; ".join(overlap))
    # A standalone `--to` enters no stage and reads no declaration, so a run's artifacts are not
    # its to replace (GC#3 by another route).
    if not args.run_id:
        standalone = inventory.standalone_problems(out_dir, HOME)
        if standalone:
            raise Refused("; ".join(standalone))
    ledger_path = pathlib.Path(args.ledger or (repo / inventory.LEDGER_REL))
    ledger = records.read_json(ledger_path) if ledger_path.is_file() else None
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True)
    # The transcripts come from the run's own census (S1), through its readers and bound to its
    # record. Outside a run there is no census, and every native layer is `unknown` with that reason.
    run_dir = out_dir if args.run_id else None

    def produce():
        return inventory.run(repo, state_root, user_root, out_dir, pin=args.pin, native_roots=native,
                             ledger=ledger, commit=(head.stdout.strip() or None), run_dir=run_dir)

    if args.run_id:
        # S2 holds two producers; this is the inventory part, and views owns the other
        # (records.STAGE_PARTS).
        with records.run_stage(out_dir, "S2", part="inventory") as stage:
            manifest = produce()
            for reference in inventory.REFERENCES:
                stage.output(f"inventory/{reference}.json")
            stage.output("inventory/manifest.json")
        # The stage record is a document this run wrote, so it answers the same question every
        # other written document answers.
        disclosed = inventory.stage_record_problems(out_dir, "S2", str(pathlib.Path.home()))
        if disclosed:
            raise Refused("; ".join(disclosed[:4]))
    else:
        manifest = produce()
    say("\n".join(inventory.report_lines(manifest, HOME)))
    return 0


def cmd_views(args):
    say("\n".join(views.report_lines(views.run(run_dir_of(args), reservation=args.output_cap))))
    return 0


def cmd_stage(args):
    stage = STAGE_COMMANDS[args.command]
    if args.command == "close" and args.recovery:
        say("RECOVERY_RESERVED close --recovery: the recovery close is reserved and not implemented", sys.stderr)
        return 2
    say(f"STAGE_NOT_IMPLEMENTED {args.command} ({stage}): no stage logic has landed for it", sys.stderr)
    return 2


def build_parser():
    parser = Parser(prog="distill.py", description=__doc__.split("\n")[0])
    parser.add_argument("--self-test", action="store_true", help="declare -> stage -> amend -> stage on real files")
    commands = parser.add_subparsers(dest="command")

    def common(sub):
        sub.add_argument("--run-id", help="the run directory name under --out")
        sub.add_argument("--out", default=str(OUT), help="root of the run directories")

    sub = commands.add_parser("declare", help="S0: the run declaration and its amendments")
    common(sub)
    sub.add_argument("--from", dest="from_file", help="a declaration to write as run.json")
    sub.add_argument("--set", action="append", help="PATH=VALUE (dotted path, JSON value); repeatable")
    sub.add_argument("--amend", action="store_true", help="record the change as an amendment")
    sub.add_argument("--reason", help="why (required with --amend)")
    sub.add_argument("--scope", help="comma-separated stages licensed to read the amendment (default: all)")
    sub.add_argument("--invalidates", help="comma-separated stages whose results it makes stale")
    sub.add_argument("--self-test", action="store_true", help="the declaration's controls")
    sub.set_defaults(handler=cmd_declare)
    for name, stage in STAGE_COMMANDS.items():
        helps = {"census": f"{stage}: the census", "views": f"{stage}: the reading views, the search index and the evidence store"}
        sub = commands.add_parser(name, help=helps.get(name, f"{stage}: not implemented yet"))
        common(sub)
        if name == "close":
            sub.add_argument("--recovery", action="store_true", help="the recovery close (reserved)")
        if name == "views":
            # the cap the S3 call will declare for its answer: check (d) reserves exactly that, and there
            # is no constant standing in for it (the ruling of 2026-10-22). The dispatcher reads the same
            # number from the stage that makes the call.
            sub.add_argument("--output-cap", type=int, required=True,
                             help="S3's output-token cap, which the window's (d) check reserves")
        if name == "inventory":
            sub.add_argument("--to", help="write inventory/<reference>.json here instead of into a run directory")
            sub.add_argument("--pin", help="HOST:SESSION_ID, the activation pin whose selection and release to read")
            sub.add_argument("--state-root", help="the owner's state root (default: the installed one)")
            sub.add_argument("--user-root", help="the owner's authoring root (default: the installed one)")
            sub.add_argument("--no-state", action="store_true", help="read no state root at all")
            sub.add_argument("--project", action="append",
                             help="a project root: a protected write target, and the scope a recorded "
                                  "injection is attributed to; repeatable")
            sub.add_argument("--ledger", help="the ledger to read the incubating and keep layers from")
        if name == "census":
            sub.add_argument("--coverage", help="the coverage state the declaration pinned (default: session-distill/coverage.json)")
            sub.add_argument("--originators", help="the originator table; refused unless it is the one the declaration names (source 'originators')")
            sub.add_argument("--jobs", type=int, default=8, help="parallel transcript reads")
            sub.add_argument("--reconcile", help="S3's results (a JSON list): fold them back instead of counting")
        sub.set_defaults(handler={"census": cmd_census, "views": cmd_views, "inventory": cmd_inventory}.get(name, cmd_stage))
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command is None:
        if args.self_test:
            return self_test()
        build_parser().print_help()
        return 2
    try:
        return args.handler(args)
    except (Refused, stagelock.Locked, stagelock.Escaped) as exc:
        say(str(exc), sys.stderr)
        return 1
    except Exception as exc:
        # An unexpected failure is a diagnostic like any other, and an unexpected one is the one most
        # likely to carry a path: an OSError's message IS a path, and a traceback printed by the
        # interpreter crosses no boundary at all. The type is named so the failure is still
        # diagnosable, and the message passes the floor (GC#6).
        say(f"COMMAND_FAILED {args.command}: {type(exc).__name__}: {exc}", sys.stderr)
        return 1


def self_test():
    """The golden end to end: declare, run a stub stage, amend, run another, and judge the
    declaration order of the recorded stages from the files on disk."""
    failures, ran = [], []

    def control(name, ok, detail=""):
        ran.append(name)
        if not ok:
            failures.append(f"{name}: {detail}")

    with tempfile.TemporaryDirectory() as td:
        scratch = pathlib.Path(td)
        out = scratch / "out"
        out.mkdir()
        run_dir = out / "r1"
        (out / "declaration.json").write_text(json.dumps(declare.fixture()), encoding="utf-8")

        def cli(*argv):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                try:
                    code = main([*argv, "--out", str(out)])
                except SystemExit as exc:  # argparse's own exit: a named control failure, not a dead suite
                    code, _ = (exc.code if isinstance(exc.code, int) else 2), err.write(f"EXITED {exc.code!r}")
                except Exception as exc:  # a reverted check fails its control by name, not by a traceback
                    code, _ = 99, err.write(f"RAISED {exc!r}")
            return code, err.getvalue()

        def stage(name, inputs=(), at=None):
            """A stub stage: it consumes `inputs`, writes one output, and finishes complete.

            A stage with parts (`records.STAGE_PARTS`) is written as one of them: these controls are
            about declarations and inputs, and a part-less write there is refused by name."""
            where = at or run_dir
            part = "views" if name in records.STAGE_PARTS else None
            with records.run_stage(where, name, inputs, part=part) as run:
                (pathlib.Path(where) / f"{name}.out").write_text(f"{name}\n", encoding="utf-8")
                run.output(f"{name}.out")

        def refused(name, inputs=()):
            try:
                stage(name, inputs)
            except Refused as exc:
                return str(exc)
            return ""

        def need(stage_name):
            return [{"artifact": f"{stage_name}.out", "producer_stage": stage_name}]

        code, err = cli("declare", "--run-id", "r1", "--from", str(out / "declaration.json"))
        control("declare writes run.json at declaration_seq 0",
                code == 0 and records.read_json(records.run_json_path(run_dir))["declaration_seq"] == 0, err)
        bad = {**declare.fixture(), "seats": {**declare.fixture()["seats"], "S4": "claude:claude-opus-9-9/high"}}
        (out / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
        code, err = cli("declare", "--run-id", "r2", "--from", str(out / "bad.json"))
        control("declare refuses a seat no prompting guide covers",
                code == 1 and "SEAT_UNCOVERED claude:claude-opus-9-9/high" in err
                and not records.run_json_path(out / "r2").exists(), err)
        code, err = cli("declare", "--run-id", "r1", "--set", "budget.reserve=0.3")
        control("declare --set before any stage is applied", code == 0
                and records.read_json(records.run_json_path(run_dir))["budget"]["reserve"] == 0.3, err)

        stage("S1")  # a stub stage, at declaration_seq 0
        code, err = cli("declare", "--run-id", "r1", "--set", "budget.reserve=0.4")
        control("declare --set after a stage recorded is refused", code == 1 and "AMEND_REQUIRED S1" in err, err)
        code, err = cli("declare", "--run-id", "r1", "--amend", "--reason", "raise the reserve", "--scope", "S2,S3",
                        "--set", "budget.reserve=0.4")
        control("the same change as an amendment is accepted",
                code == 0 and records.read_json(records.run_json_path(run_dir))["declaration_seq"] == 1, err)
        stage("S2", need("S1"))  # amended, S2 licensed, S1 not invalidated
        stage("S3", need("S2"))
        control("a stage consuming across a licensed amendment pins both sequences",
                records.producing_part(records.read_json(records.record_path(run_dir, "S2")),
                                       "S2.out")[1]["inputs"][0]["producer_seq"] == 0
                and records.producing_part(records.read_json(records.record_path(run_dir, "S2")),
                                           "S2.out")[1]["declaration_seq"] == 1)
        code, err = cli("declare", "--run-id", "r1", "--set", "checks.view_complete_share_min=0.95")
        control("declare --set of checks{} after S3 recorded is refused naming S3 and changes nothing",
                code == 1 and "AMEND_REQUIRED" in err and "S3" in err
                and records.read_json(records.run_json_path(run_dir))["checks"]["view_complete_share_min"] == 0.9, err)
        code, err = cli("declare", "--run-id", "r1", "--amend", "--reason", "tighten the criterion",
                        "--set", "checks.view_complete_share_min=0.95")
        amendments = records.read_amendments(run_dir)
        control("an amendment of checks{} after S3 marks S3 invalidated",
                code == 0 and amendments[-1]["invalidates"] == ["S3"], f"{err} {amendments}")
        control("S4 refuses the stale S3", "INPUT_STALE S3" in refused("S4", need("S3")))
        stage("S3", need("S2"))  # S3 re-run under declaration 2; S2 (declaration 1) is licensed and not invalidated
        stage("S4", need("S3"))
        control("S3 re-run under the new declaration is accepted, and S4 consumes it",
                records.read_json(records.record_path(run_dir, "S3"))["declaration_seq"] == 2
                and records.read_json(records.record_path(run_dir, "S4"))["inputs"][0]["producer_seq"] == 2)

        # check_declaration_order on the real files: every recorded input, then the log with an amendment removed
        def recorded_pairs():
            # A stage with parts keeps one entry per producer, so the pairs come from the entries
            # rather than from the record's top level (records.STAGE_PARTS).
            entries = []
            for record in records.stage_records(run_dir).values():
                entries += list((record.get("parts") or {}).values()) or [record]
            return [(r["stage"], r["declaration_seq"], i["producer_stage"], i["producer_seq"])
                    for r in entries for i in r.get("inputs", [])]

        pairs, log = recorded_pairs(), records.amendments_path(run_dir).read_text(encoding="utf-8")
        control("recorded stages pass the declaration order", len(pairs) == 3 and not any(
            records.check_declaration_order(c, cs, p, ps, records.read_amendments(run_dir)) for c, cs, p, ps in pairs),
            str(pairs))
        lines = log.splitlines()  # the declaration (seq 0), then amendments 1 and 2: drop amendment 1
        records.amendments_path(run_dir).write_text("\n".join(lines[:1] + lines[2:]) + "\n", encoding="utf-8")
        control("an amendment removed from the log is a silent advance",
                "DECLARATION_DRIFT S2" in "\n".join(
                    e for c, cs, p, ps in pairs
                    for e in records.check_declaration_order(c, cs, p, ps, records.read_amendments(run_dir))))
        control("a log that no longer ends at declaration_seq stops the next stage",
                "DECLARATION_DRIFT" in refused("S5", need("S4")))
        records.amendments_path(run_dir).write_text(log, encoding="utf-8")
        run = records.read_json(records.run_json_path(run_dir))
        records.run_json_path(run_dir).write_text(records.json_text({**run, "question": "edited by hand"}), encoding="utf-8")
        control("run.json edited by hand stops the next stage", "DECLARATION_DRIFT S5" in refused("S5", need("S4")))
        records.run_json_path(run_dir).write_text(records.json_text(run), encoding="utf-8")
        stage("S5", need("S4"))
        control("the restored declaration lets the next stage start",
                records.read_json(records.record_path(run_dir, "S5"))["status"] == "complete")

        # a run id cannot name a place outside --out, and nothing is created before that is known
        elsewhere = scratch / "elsewhere"
        elsewhere.mkdir()
        (out / "link").symlink_to(elsewhere)

        def listing():
            return sorted(str(p.relative_to(scratch)) for p in scratch.rglob("*"))
        before = listing()
        for run_id, why in ((str(elsewhere / "abs"), "absolute"), ("../escape", "parent traversal"), ("a/b", "two components"),
                            ("..", "dot-dot"), (".", "dot"), (".hidden", "leading dot")):
            code, err = cli("declare", "--run-id", run_id, "--from", str(out / "declaration.json"))
            control(f"run id {why} is refused as RUN_ID_INVALID", code == 1 and "RUN_ID_INVALID" in err, err)
        code, err = cli("declare", "--run-id", "link", "--from", str(out / "declaration.json"))
        control("run id naming a symlink out of --out is refused as RUN_DIR_ESCAPE", code == 1 and "RUN_DIR_ESCAPE" in err, err)
        control("a refused run id created nothing, in or beside --out or in the escape target",
                before == listing(), f"{before} -> {listing()}")
        code, err = cli("declare", "--run-id", "r-2.a_b", "--from", str(out / "declaration.json"))
        control("an ordinary run id with '.', '_' and '-' is accepted", code == 0 and records.run_json_path(out / "r-2.a_b").is_file(), err)

        # the same run with every path spelled relative to the working directory: declare, a stub stage, an
        # amendment, another stub stage — each file lands at <cwd>/<out>/<run-id>/..., and no doubled path exists
        cwd = scratch / "cwd"
        cwd.mkdir()
        (cwd / "declaration.json").write_text(json.dumps(declare.fixture()), encoding="utf-8")
        here = pathlib.Path.cwd()
        os.chdir(cwd)
        try:
            relative = pathlib.Path("rel-out") / "r1"

            def relative_cli(*argv):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    try:
                        code = main([*argv, "--out", "rel-out"])
                    except Exception as exc:
                        code, _ = 99, err.write(f"RAISED {exc!r}")
                return code, err.getvalue()

            def relative_stage(name, inputs=()):
                """The stub stage over the relative spelling; what it raises is its control's detail."""
                try:
                    stage(name, inputs, at=relative)
                    return ""
                except Exception as exc:
                    return f"RAISED {exc!r}"

            code, err = relative_cli("declare", "--run-id", "r1", "--from", "declaration.json")
            control("a relative --out declares the run at <cwd>/<out>/<run-id>", code == 0 and (cwd / relative / "run.json").is_file(), err)
            detail = relative_stage("S1")
            control("a stub stage runs over the relative spelling of the run directory", not detail, detail)
            code, err = relative_cli("declare", "--run-id", "r1", "--amend", "--reason", "raise the reserve", "--set", "budget.reserve=0.4")
            control("a relative --out amends the run after a stage recorded", code == 0
                    and records.read_json(cwd / relative / "run.json")["declaration_seq"] == 1, err)
            detail = relative_stage("S2", [{"artifact": "S1.out", "producer_stage": "S1"}])
            control("a second stub stage consumes the first across the amendment", not detail, detail)
            found = sorted(str(path.relative_to(cwd)) for path in cwd.rglob("*") if path.is_file())
            expected = sorted(f"rel-out/r1/{name}" for name in (
                "run.json", "amendments.jsonl", "S1.out", "S2.out", "locks/declaration.lock", "locks/stage-S1.lock",
                "locks/stage-S2.lock", "stages/S1/record.json", "stages/S2/record.json")) + ["declaration.json"]
            control("a relative run keeps every file under <cwd>/<out>/<run-id> and creates no doubled path",
                    found == sorted(expected), f"found {found}")
        finally:
            os.chdir(here)

        implemented = ("census", "views", "inventory")  # each has its own controls below; the rest are named and refused
        for command, stage_id in STAGE_COMMANDS.items():
            if command in implemented:
                continue
            code, err = cli(command, "--run-id", "r1")
            control(f"{command} ({stage_id}) is named and refused",
                    code == 2 and f"STAGE_NOT_IMPLEMENTED {command} ({stage_id})" in err, err)
        # inventory (S2) reads no stage of this run, so it refuses on what it cannot resolve rather
        # than on a missing input: with neither a run directory nor an output directory it has nowhere
        # to write, and that is the refusal the driver owns
        code, err = cli("inventory")
        control("inventory (S2) refuses by name with no run and no output directory",
                code == 1 and "INPUT_INVALID inventory" in err, f"{code} {err}")
        # No mode reads a host home any more, so there is no inspection to label and no native root
        # to validate: a run outside a run directory has no census, and every native layer is
        # `unknown` with that reason (the 1548 amendment §5, §8).
        bare_to = scratch / "inv-bare"
        code, err = cli("inventory", "--to", str(bare_to), "--no-state")
        document = json.loads((bare_to / "inventory" / "current.json").read_text(encoding="utf-8")) if code == 0 else {}
        statuses = {row["layer"]: row["status"] for row in document.get("layers", [])}
        reasons = "; ".join(document.get("reference", {}).get("incomplete_reasons", []))
        control("inventory (S2) outside a run reports every native layer unknown, with the reason",
                code == 0 and all(statuses.get(layer) == "unknown" for layer in inventory.NATIVE_LAYERS)
                and "census" in reasons, f"{code} {err} {statuses}")
        control("and it names no mode that reads a host home",
                "mode" not in document.get("produced_by", {}) and "--native-live" not in err,
                f"{sorted(document.get('produced_by', {}))}")
        # ---- GC#0 through `--project`: the checkout is a protected root whatever is declared, and
        # the refusal is observed as an attempted write that did not happen.
        checkout = pathlib.Path(__file__).resolve().parents[1]
        in_checkout = checkout / "session-distill" / "out" / "a-destination-no-run-owns"
        other_project = scratch / "another-project"
        other_project.mkdir()
        before_write = in_checkout.exists()
        code, err = cli("inventory", "--to", str(in_checkout), "--no-state",
                        "--project", str(other_project))
        control("inventory (S2) refuses a destination inside the checkout when another project is declared",
                code == 1 and "PROTECTED_OVERLAP" in err, f"{code} {err}")
        control("and the attempted write did not happen",
                not before_write and not in_checkout.exists(),
                f"{in_checkout} exists after a refused run")
        # This fixture destination is inside the checkout, which is the whole point of it. When the
        # rule under test is taken out — a revert, which is how this control is proven to fire — the
        # write really does land here, and a leftover would make the NEXT run answer about the
        # destination instead of about the rule: it refuses with INVENTORY_PRESENT, a second reason,
        # and `before_write` is already true. So the control removes exactly the path it named,
        # after judging it, and never anything else.
        shutil.rmtree(in_checkout, ignore_errors=True)
        # ---- GC#3 by another route: a standalone `--to` is not a way into a run's artifacts. The
        # run's own bytes and its stage record are the subject: both must be exactly as they were.
        standalone_run = out / "r-standalone"
        standalone_run.mkdir(parents=True)
        for name in ("run.json", "amendments.jsonl"):
            (standalone_run / name).write_text((out / "r1" / name).read_text(encoding="utf-8"), encoding="utf-8")
        (standalone_run / "inventory").mkdir()
        (standalone_run / "inventory" / "current.json").write_text(
            '{"units": ["the bytes a census-backed run produced"]}\n', encoding="utf-8")
        with records.run_stage(standalone_run, "S2", part="inventory") as held:
            held  # a recorded S2, so the refusal is about the destination and not about the run
        kept_bytes = (standalone_run / "inventory" / "current.json").read_bytes()
        kept_record = records.record_path(standalone_run, "S2").read_bytes()
        code, err = cli("inventory", "--to", str(standalone_run), "--no-state")
        control("inventory (S2) refuses a standalone --to that names a declared run",
                code == 1 and "RUN_DESTINATION" in err, f"{code} {err}")
        code, err = cli("inventory", "--to", str(standalone_run / "inventory"), "--no-state")
        control("and one inside that run directory",
                code == 1 and "RUN_DESTINATION" in err, f"{code} {err}")
        control("the run's inventory bytes and its stage record are unchanged",
                kept_bytes == (standalone_run / "inventory" / "current.json").read_bytes()
                and kept_record == records.record_path(standalone_run, "S2").read_bytes(),
                "a refused standalone attempt changed the run")
        held_elsewhere = scratch / "inv-held"
        (held_elsewhere / "inventory").mkdir(parents=True)
        (held_elsewhere / "inventory" / "current.json").write_text("{}\n", encoding="utf-8")
        code, err = cli("inventory", "--to", str(held_elsewhere), "--no-state")
        control("and a destination that already holds an inventory",
                code == 1 and "INVENTORY_PRESENT" in err, f"{code} {err}")
        # ---- GC#6: what the CLI prints crosses the disclosure boundary. `parse_args` and the
        # refusal printer both stood outside every boundary this run has.
        secret_argument = "api_key=shortpass"
        code, err = cli("--bad", secret_argument)
        control("an argument the parser did not understand is not echoed unprojected",
                "shortpass" not in err and "REDACTED" in err, f"{code} {err}")
        code, err = cli("inventory", "--run-id", secret_argument)
        control("a refusal naming the argument it refused is not printed unprojected",
                code == 1 and "shortpass" not in err and "RUN_ID_INVALID" in err, f"{code} {err}")
        missing_under_home = f"{HOME}/a-file-no-run-of-this-suite-creates.json"
        code, err = cli("declare", "--run-id", "r-file-error", "--from", missing_under_home)
        control("an unexpected file error is a projected diagnostic, not a raw traceback",
                code == 1 and HOME not in err and "<HOME>" in err and "COMMAND_FAILED" in err,
                f"{code} {err}")
        # The destination is judged before anything is written, locked or recorded: the run
        # directory itself is a write, so a destination under the state root must be refused by the
        # CLI and must leave nothing behind (GB#0).
        guarded_state = scratch / "guarded-state"
        (guarded_state / "runtime").mkdir(parents=True)
        inside = guarded_state / "out"
        code, err = cli("inventory", "--to", str(inside), "--state-root", str(guarded_state),
                        "--user-root", str(scratch / "guarded-user"))
        control("inventory (S2) refuses a destination inside the owner's state root",
                code == 1 and "PROTECTED_OVERLAP" in err, f"{code} {err}")
        control("and writes nothing there", not inside.exists(), f"{sorted(p.name for p in inside.rglob('*'))}"
                if inside.exists() else "")
        # The same destination as a RUN: the stage record is the first write, so the refusal has to
        # come before the stage is entered at all.
        # `cli` appends its own --out, so the guarded run lives under it and the state root is that
        # same directory: the run directory is then inside a root this inventory reads.
        declared_run = out / "r-guarded"
        declared_run.mkdir(parents=True)
        for name in ("run.json", "amendments.jsonl"):  # a declared run, so the refusal is about the destination
            (declared_run / name).write_text((out / "r1" / name).read_text(encoding="utf-8"), encoding="utf-8")
        code, err = cli("inventory", "--run-id", "r-guarded",
                        "--state-root", str(out), "--user-root", str(scratch / "guarded-user"))
        control("inventory (S2) refuses a run directory inside the owner's state root",
                code == 1 and "PROTECTED_OVERLAP" in err, f"{code} {err}")
        control("and enters no stage, so no stage record is written",
                not (declared_run / "stages").exists(),
                f"{sorted(p.name for p in (declared_run / 'stages').rglob('*'))}"
                if (declared_run / "stages").exists() else "")
        code, err = cli("views", "--run-id", "r1", "--output-cap", "32000")
        control("views (S2) refuses by name when the census it reads is not in the run",
                code == 1 and "INPUT_INVALID S1" in err, err)
        # the ruling of 2026-10-22: (d) reserves the cap the S3 call declares, so the stage cannot be run
        # without one - argparse refuses it, and the refusal names the flag
        code, err = cli("views", "--run-id", "r1")
        control("views (S2) cannot run without the output cap its (d) check reserves",
                code == 2 and "--output-cap" in err, f"{code} {err}")
        # the census (S1) through the driver: a declared run over sources that are not there is unknown coverage, not zero
        coverage_file = scratch / "coverage.json"
        coverage_file.write_text(records.json_text(coverage.new_state()), encoding="utf-8")
        table = {"name": census.ORIGINATORS_SOURCE, "path": str(census.ORIGINATORS_PATH), "sha256": census.load_originators()[1]}
        pinned = {**declare.fixture(), "starting_hashes": {**declare.fixture()["starting_hashes"], "coverage": coverage.load(coverage_file)[1]}}
        pinned["sources"] = [*pinned["sources"], table]
        (out / "pinned.json").write_text(json.dumps(pinned), encoding="utf-8")
        cli("declare", "--run-id", "rc", "--from", str(out / "pinned.json"))
        code, err = cli("census", "--run-id", "rc", "--coverage", str(coverage_file))
        document = json.loads((out / "rc" / "census.json").read_text(encoding="utf-8")) if (out / "rc" / "census.json").is_file() else {}
        control("census over sources that are not there succeeds and reports them unknown",
                code == 0 and {n: s["totals"] for n, s in document.get("sources", {}).items() if s["state"] == "missing"}
                == {"claude_projects": None, "codex_sessions": None} and document["transcripts"] == [], err)
        control("census recorded its stage", records.read_json(records.record_path(out / "rc", "S1"))["status"] == "complete")
        pinned_stale = {**pinned, "starting_hashes": {**pinned["starting_hashes"], "coverage": "1" * 64}}
        (out / "stale.json").write_text(json.dumps(pinned_stale), encoding="utf-8")
        cli("declare", "--run-id", "rs", "--from", str(out / "stale.json"))
        code, err = cli("census", "--run-id", "rs", "--coverage", str(coverage_file))
        control("census over a coverage state the declaration did not pin is refused", code == 1 and "COVERAGE_BASE_STALE" in err, err)
        code, err = cli("census", "--run-id", "nobody", "--coverage", str(coverage_file))
        control("census of a run that was never declared is refused", code == 1 and "RUN_UNDECLARED" in err, err)
        results = scratch / "results.json"
        results.write_text("[]", encoding="utf-8")
        code, err = cli("census", "--run-id", "rc", "--reconcile", str(results))
        reconciled = (out / "rc" / "census.reconciled.json").is_file() and (out / "rc" / "coverage.reconciled.json").is_file()
        control("census --reconcile folds S3's (empty) results back into new files beside S1's own", code == 0 and reconciled, err)

        code, err = cli("close", "--run-id", "r1", "--recovery")
        control("close --recovery is reserved", code == 2 and "RECOVERY_RESERVED" in err, err)
        code, err = cli("declare", "--run-id", "r1")
        control("declare with nothing to do is refused", code == 1 and "DECLARATION_INVALID" in err, err)
        code, err = cli("declare", "--run-id", "r1", "--set", "budget.reserve")
        control("--set without a value is refused", code == 1 and "expected PATH=VALUE" in err, err)
        code, err = cli("declare", "--set", "budget.reserve=1")
        control("declare without a run is refused", code == 1 and "needs the run it declares" in err, err)
        code, err = cli("declare", "--run-id", "r1", "--from", str(out / "declaration.json"), "--set", "budget.reserve=1")
        control("a new declaration takes no --set", code == 1 and "takes no --set or --amend" in err, err)
        code, err = cli("declare", "--run-id", "r1", "--from", str(out / "declaration.json"))
        control("a declaration is never replaced", code == 1 and "RUN_EXISTS" in err, err)

    for failure in failures:
        print(f"distill --self-test [FAIL] {failure}")
    if failures:
        return 1
    for name in ran:
        print(f"  control {name}")
    print(f"distill --self-test: OK ({len(ran)} controls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
