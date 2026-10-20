#!/usr/bin/env python3
"""Session distill driver: one subcommand per stage, one run directory per run.

  distill.py declare --run-id ID --from DECLARATION.json   S0: write run.json (declaration_seq 0)
  distill.py declare --run-id ID --set PATH=VALUE ...      edit it in place, until a stage has read it
  distill.py declare --run-id ID --amend --reason TEXT --set PATH=VALUE ... [--scope S2,S3]
                                                           [--invalidates S1]
  distill.py declare --self-test                           the declaration's controls
  distill.py --self-test                                   declare -> stage -> amend -> stage, on real files
  distill.py census --run-id ID [--coverage PATH]          S1: census.json and coverage.json into the run directory
  distill.py census --run-id ID --reconcile RESULTS.json   S3's results folded back into the statuses and the coverage
  distill.py <stage command> --run-id ID                   S2-S12: named, and refused until implemented

A run lives in `session-distill/out/<run-id>/` (`--out` names another root): `run.json`,
`amendments.jsonl`, `stages/<stage>/record.json`, and per-call directories. The declaration,
its amendments and the stage records are `runlib/declare.py` and `runlib/records.py`; the
record schemas every stage keeps (claim, evidence, expected observation) are
`schemas/*.schema.json`, loaded through `runlib/claims.py`; the declaration's own structure is
`schemas/run.schema.json`. The census (S1) is `runlib/census.py`, over the readers of `runlib/sources.py`,
`runlib/lineage.py` and the coverage state of `runlib/coverage.py`. Design: §3, §4, §4.1, §5.1-§5.3.
"""
import argparse
import contextlib
import io
import json
import os
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from runlib import census, coverage, declare, records, stagelock
from runlib.records import Refused

OUT = pathlib.Path(__file__).resolve().parent / "out"
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

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
        print(f"amended {run_dir}: declaration_seq {amendment['seq']}, invalidates {amendment['invalidates']}")
    elif args.from_file:
        run = declare.create(run_dir, json.loads(pathlib.Path(args.from_file).read_text(encoding="utf-8")))
        print(f"declared {run_dir}: declaration_seq {run['declaration_seq']}")
    elif args.set:
        declare.set_fields(run_dir, assignments_of(args))
        print(f"set {len(args.set)} field(s) in {run_dir}/run.json")
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
        print(f"reconciled {run_dir}: accounted {flags['accounted']} ({counts['accounted']}/{counts['eligible']} sessions), "
              f"fully read {flags['fully_read']} ({counts['fully_read']}/{counts['eligible']})")
        return 0
    print("\n".join(census.report_lines(census.run(run_dir, args.coverage, args.originators, args.jobs))))
    return 0


def cmd_stage(args):
    stage = STAGE_COMMANDS[args.command]
    if args.command == "close" and args.recovery:
        print("RECOVERY_RESERVED close --recovery: the recovery close is reserved and not implemented",
              file=sys.stderr)
        return 2
    print(f"STAGE_NOT_IMPLEMENTED {args.command} ({stage}): no stage logic has landed for it", file=sys.stderr)
    return 2


def build_parser():
    parser = argparse.ArgumentParser(prog="distill.py", description=__doc__.split("\n")[0])
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
        sub = commands.add_parser(name, help=f"{stage}: the census" if name == "census" else f"{stage}: not implemented yet")
        common(sub)
        if name == "close":
            sub.add_argument("--recovery", action="store_true", help="the recovery close (reserved)")
        if name == "census":
            sub.add_argument("--coverage", help="the coverage state the declaration pinned (default: session-distill/coverage.json)")
            sub.add_argument("--originators", help="the originator table; refused unless it is the one the declaration names (source 'originators')")
            sub.add_argument("--jobs", type=int, default=8, help="parallel transcript reads")
            sub.add_argument("--reconcile", help="S3's results (a JSON list): fold them back instead of counting")
        sub.set_defaults(handler=cmd_census if name == "census" else cmd_stage)
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
        print(str(exc), file=sys.stderr)
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
                except Exception as exc:  # a reverted check fails its control by name, not by a traceback
                    code, _ = 99, err.write(f"RAISED {exc!r}")
            return code, err.getvalue()

        def stage(name, inputs=(), at=None):
            """A stub stage: it consumes `inputs`, writes one output, and finishes complete."""
            where = at or run_dir
            with records.run_stage(where, name, inputs) as run:
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
                records.read_json(records.record_path(run_dir, "S2"))["inputs"][0]["producer_seq"] == 0
                and records.read_json(records.record_path(run_dir, "S2"))["declaration_seq"] == 1)
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
            return [(r["stage"], r["declaration_seq"], i["producer_stage"], i["producer_seq"])
                    for r in records.stage_records(run_dir).values() for i in r["inputs"]]

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

        for command, stage_id in STAGE_COMMANDS.items():
            if command == "census":
                continue  # implemented: its own controls follow
            code, err = cli(command, "--run-id", "r1")
            control(f"{command} ({stage_id}) is named and refused",
                    code == 2 and f"STAGE_NOT_IMPLEMENTED {command} ({stage_id})" in err, err)
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
