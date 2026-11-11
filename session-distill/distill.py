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
  distill.py form --run-id ID --dry [--index ROWS.json]    S4 up to its call: the barrier, the lifecycle intake and the
                                                           formation packet held to its bound; the record stays partial
  distill.py form --run-id ID --cells DIR [--golden-plan PLAN.json] [--index ROWS.json]
                                                           S4: the one formation call, live (the token only as
                                                           CLAUDE_RUN_TOKEN_FILE) or, with a plan, golden
  distill.py retrieve --run-id ID                          S5: the retrieval, the quotes verified again, the sessions and
                                                           the recurrence, into checks.json; no model is called
  distill.py judge --run-id ID --dry                       S6 up to its calls: the judged population, every judgment
                                                           packet built and measured per judge; the record stays partial
  distill.py judge --run-id ID --cells DIR [--golden-plan PLAN.json]
                                                           S6: each judged candidate to Judge A and Judge B
  distill.py <stage command> --run-id ID                   S3, S6-S12: named, and refused until implemented

A run lives in `<run root>/<run-id>/`: `run.json`, `amendments.jsonl`,
`stages/<stage>/record.json`, and per-call directories. The run root is `--out`, or, unset, the
XDG state directory `default_out()` resolves; a checkout passes `session-distill/out/<...>`
explicitly, as the runbook does. The declaration, its amendments and the stage records are
`runlib/declare.py` and `runlib/records.py`; the
record schemas every stage keeps (claim, evidence, expected observation) are
`schemas/*.schema.json`, loaded through `runlib/claims.py`; the declaration's own structure is
`schemas/run.schema.json`. The census (S1) is `runlib/census.py`, over the readers of `runlib/sources.py`,
`runlib/lineage.py` and the coverage state of `runlib/coverage.py`. The views (S2) are `runlib/views.py`,
over `runlib/redaction.py`, `runlib/search.py` and the evidence store of `runlib/evidence.py`. Formation (S4) is
`runlib/stage_form.py`, over the lifecycle intake of `runlib/lifecycle_intake.py`. Retrieval and its checks (S5) are
`runlib/stage_retrieve.py`, over the derivations' tables read by `runlib/derive.py`.
Design: §3, §4, §4.1, §5.1-§5.5, §6.2, §7.1, §7.4, §9.
"""
import argparse
import ast
import contextlib
import inspect
import io
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import types

# Before the command's module graph is imported, not inside the functions that load modules by
# path: `runlib.projection` loads `learn/redact.py` at import, and a cache write lands beside the
# file it caches — in the checkout, or in a frozen copy this run is about to hash (GB#7).
sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

def _diagnostic_home():
    """The owner home a diagnostic masks, resolved without ever failing.

    This runs at import, before either startup boundary, and `pathlib.Path.home()` RAISES
    `RuntimeError` when `$HOME` is unset and the account has no password-database entry — so a
    machine in that state could not run `--out DIR`, or `--help`, or anything at all (review Y r2
    #3). `None` is what every consumer of this value already takes as its default (`entry.say`,
    `entry.failed`, `inventory.overlap_problems`, `projection.project`, which expands `~` itself),
    so an unresolvable home masks exactly what the floor's own default masks and costs no startup."""
    try:
        return str(pathlib.Path.home())
    except (RuntimeError, OSError, KeyError):
        return None


HOME = _diagnostic_home()
# The bootstrap, and the only thing in this file that runs before the boundary exists. It is
# stdlib only and its line carries NO path, because what failed is the very code that would have
# projected one: `from runlib import entry` stood outside every boundary this command has, so an
# `entry` that cannot import left a traceback on stderr with the importer's absolute paths in it
# (r3 #2). `BaseException`, because a module can exit during import; a `SystemExit` already carries
# the code its raiser chose, so it is re-raised rather than relabelled.
STARTUP_UNAVAILABLE = ("COMMAND_FAILED startup: session distill could not load the boundary that "
                       "describes its own failures, so it says nothing further about this one")
STARTUP_UNAVAILABLE_CODE = 3

# The boundary every entry point of this command runs inside, and the one owner of the fixed line
# printed when even the floor cannot load. It imports nothing but the standard library and reaches
# the floor lazily, so importing it is unlikely to be the failure it is there to describe — and the
# bootstrap above answers for the case where it is anyway (R2#2, R2#3, r3 #2).
try:
    from runlib import entry
except SystemExit:
    raise
except BaseException:
    # Imported as a module, the caller owns the failure and gets the exception. Run as a command,
    # there is nothing left to describe it with, so the fixed line stands in for the whole floor.
    if __name__ != "__main__":
        raise
    sys.stderr.write(STARTUP_UNAVAILABLE + "\n")
    raise SystemExit(STARTUP_UNAVAILABLE_CODE)
STARTUP_WITHHELD = entry.WITHHELD

try:
    from runlib import census, coverage, declare, inventory, projection, records, sources, stage_form, stage_judge, \
        stage_propose, stage_retrieve, stage_review_proposals, stagelock, views
    from runlib import ledger as ledger_lib
    from runlib.records import Refused
except BaseException as _startup_exc:   # SystemExit included: `validate` exits at import time
    # The imports used to stand OUTSIDE every boundary this command has: `runlib.validate` exits
    # during import when its jsonschema pin is unreadable, interpolating the absolute pin path, and
    # that path reached stderr unprojected (R1#3). The floor is asked for a projection if it loaded;
    # if the floor itself is what failed, the fixed line stands instead.
    sys.exit(entry.failed(_startup_exc, HOME, label="STARTUP_FAILED", code=2))

def _password_home():
    """This process's own home directory, as the password database states it.

    A named seam rather than an inline lookup, deliberately: it is the one home a control cannot
    override, so the relative-HOME control below reached the REAL account home and created a run
    under `~/.local/state/agent-bios/distill/runs/` while a commit hook was running (review Y r2
    #1). A control states the account home it means by replacing this function; production never
    does, and the resolver it feeds is exercised against the real database by a control of its own."""
    import pwd
    return pwd.getpwuid(os.getuid()).pw_dir


def _account_home():
    """The account's own home directory, which does not come from the environment.

    `pathlib.Path.home()` reads `$HOME`, so it answered `relative-home` for a relative `$HOME` and
    the "ignored" value came straight back as the base — the default then resolved against the
    working directory and a control of mine wrote a run into this checkout. The password database
    is the authority that cannot be relative. If it cannot be read, no default is better than one
    resolved against whatever directory the caller happens to stand in."""
    try:
        home = _password_home()
    except Exception:                      # no pwd (Windows), or no entry for this uid
        home = None
    if home and pathlib.PurePath(home).is_absolute():
        return pathlib.Path(home)
    raise Refused("DEFAULT_OUT_UNRESOLVED: this account has no absolute home directory, so the "
                  "default run root cannot be resolved; pass --out DIR")


def default_out(environ=None, home=None):
    """The root of the run directories when the caller names none.

    `${XDG_STATE_HOME:-~/.local/state}/agent-bios/distill/runs`. Three things decide it:

    * it is NOT inside the package. A run writes `run.json`, stage records and per-call directories;
      writing them next to the code would put a user's work inside a tree the next install replaces.
    * it is NOT inside the owner's state root either. That root — pins, receipts, the ledger — is one
      of the roots `inventory.protected_roots` forbids writing into, because a run once wrote four
      artifacts into it (R1#1), and the answer to this was not to carve an exception out of that
      sentence.
    * the XDG STATE directory, not the data directory: a run is regenerable output, while the data
      directory holds what is the owner's.

    A checkout passes `--out session-distill/out/<...>` explicitly; the runbook does.

    Both inputs are taken only when they are ABSOLUTE. A relative `XDG_STATE_HOME` — `.` is the
    one a shell hands over by accident — resolved against the working directory, which during
    development is this checkout, so the default landed inside the package it must stay out of.
    A relative value is therefore ignored, loudly, rather than honoured or refused: the caller gets
    the documented default and a line saying why. The same rule for `HOME`, whose relative value
    `pathlib.Path.home()` would not have produced either.

    Where the resolved default lands is a second question, and it is not this function's: nothing
    here can know the owner's roots. `destination_of` judges it before any lock or write.
    """
    environ = os.environ if environ is None else environ
    notes = []
    # XDG FIRST, and the home only when XDG gives no absolute base. An absolute `XDG_STATE_HOME`
    # determines the whole answer, so resolving a home it does not need let an unreadable account
    # entry refuse a destination that was already decided (review Y r2 #4).
    raw_base = environ.get("XDG_STATE_HOME")
    if raw_base is not None and raw_base != "" and not pathlib.PurePath(raw_base).is_absolute():
        notes.append(f"XDG_STATE_HOME={raw_base!r} is relative and is ignored for the default run "
                     f"root; the XDG base-directory contract names absolute paths only")
        raw_base = None
    base = pathlib.Path(raw_base) if raw_base else None
    if base is None:
        raw_home = home if home is not None else environ.get("HOME")
        if raw_home is not None and not pathlib.PurePath(str(raw_home)).is_absolute():
            notes.append(f"HOME={str(raw_home)!r} is relative and is ignored for the default run root")
            raw_home = None
        base = (pathlib.Path(raw_home) if raw_home else _account_home()) / ".local" / "state"
    for note in notes:
        say(f"DEFAULT_OUT_INPUT_IGNORED {note}", sys.stderr)
    return pathlib.Path(base).expanduser() / "agent-bios" / "distill" / "runs"

# The inline programs this file's own suite runs, as module-level constants rather than locals: a
# `python -c` program is admitted by DECLARATION (`runlib/dispatch.py` `INLINE_PROGRAMS`, which pins
# each one's sha256), and a local's text is only visible where it is built, so a local cannot be
# declared or pinned at all (r3 S3).
#
# A TERM-ignoring descendant of a child that exits on TERM: the bound must end the TREE, and a
# descendant holding the pipe is what kept a runaway filling the disk (r3 #1). Finite on its own.
# Both sleeps outlast the whole bound — the timeout, `GROUP_DRAIN` and the SIGKILL rounds — so
# within the control's window only the kill can end either process. A natural lifetime shorter than
# that bound made the control pass over a removed kill: the descendant was gone because its three
# seconds were up (r4 R2). Finite all the same, so a cleanup defect ends on its own.
IGNORES_TERM = ("import signal, subprocess, sys, time\n"
                "g = subprocess.Popen([sys.executable, '-c', 'import signal, time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(90)'])\n"
                "print('DESCENDANT', g.pid, flush=True)\n"
                "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))\n"
                "time.sleep(90)\n")
# A child that outlives its bound and nothing else, for the group-ownership control.
SLEEPS_BRIEFLY = "import time; time.sleep(3)\n"
# The ordinary shape: the leader exits first while a descendant holds the pipe for a moment.
LEADER_FIRST = ("import subprocess, sys\n"
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(1)'])\n"
                "print('LEADER DONE', flush=True)\n")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


def say(text, stream=None):
    """One line this command publishes, through the floor's own entry point (GC#6).

    A diagnostic is an artifact: a person reads it and whatever captured the terminal keeps it, so
    printing a line the write boundary would refuse is the same leak by another route. Everything
    this driver prints — a report, a refusal, a stage that is not implemented, an argument the parser
    did not understand — leaves through here. `--bad api_key=shortpass` and
    `--run-id api_key=shortpass` each repeated the secret on stderr before a line of the command ran,
    because `parse_args` and `print(str(exc))` stood outside every boundary this run has.

    `runlib.entry` holds the line and the floor behind it, so the driver and `runlib/inventory.py`'s
    own entry point publish through the same code rather than through two copies of it."""
    entry.say(text, stream if stream is not None else sys.stdout, HOME)


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


def protection_for(args, repo):
    """Every root this invocation must not write into, assembled as S2 assembles it.

    `configured_roots` resolves the owner's roots whether or not this run reads them, and the
    checkout is always one of the protected projects — that is `inventory`'s rule and this reuses
    it rather than keeping a second copy."""
    declared_state, declared_user = inventory.configured_roots(
        getattr(args, "state_root", None), getattr(args, "user_root", None))
    projects = inventory.project_identities([str(repo), *(getattr(args, "project", None) or [])])
    native = {"projects": {identity["path"]: pathlib.Path(identity["path"])
                           for identity in projects.values()}}
    return inventory.protected_roots(declared_state, declared_user, native, checkout=repo, repo=repo)


def destination_of(args):
    """`--out` when the caller named one, else the default — and whether it was the default.

    A DEFAULT destination is judged here, before a run id is checked and long before a lock or a
    directory: `default_out` cannot know the owner's roots, and an environment can put the XDG
    state directory anywhere, including inside the package or inside the data root that holds the
    pins and the receipts. `declare` had no protection of its own — only `inventory` checked — so
    `XDG_STATE_HOME=$HOME/.local/share` was enough to write a run into the owner's state (review Y
    #2). An explicit `--out` keeps its own per-command verdict (`PROTECTED_OVERLAP`); this one is
    about the path the driver chooses for the caller."""
    if getattr(args, "out", None):
        return str(args.out), False
    repo = pathlib.Path(__file__).resolve().parents[1]
    chosen = default_out()
    problems = inventory.overlap_problems([chosen], protection_for(args, repo), home=HOME)
    if problems:
        raise Refused(
            f"DEFAULT_OUT_PROTECTED {chosen}: the default run root resolves inside a root this "
            f"driver must not write into ({'; '.join(problems)}). Nothing was written. Pass "
            f"--out DIR to name a destination outside the owner's roots and outside the package.")
    return str(chosen), True


def run_dir_of(args):
    """`--out`/`<run-id>`: the run id is one path component, and the directory it names resolves
    to a place beneath `--out`. Nothing — no lock, no directory — is created before this holds."""
    out, _from_default = destination_of(args)
    args.out = out
    if not RUN_ID.fullmatch(args.run_id):
        raise Refused(f"RUN_ID_INVALID {args.run_id!r}: a run id is one path component of letters, digits, '.', '_' and '-'")
    run_dir = records.contained(out, args.run_id)
    if run_dir is None:
        raise Refused(f"RUN_DIR_ESCAPE {args.run_id!r}: {pathlib.Path(out) / args.run_id} resolves outside {out}")
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
        before = census.load(run_dir)
        state = coverage.load(run_dir / "coverage.json")[0]
        results = json.loads(pathlib.Path(args.reconcile).read_text(encoding="utf-8"))
        done, after, flags = census.reconcile(before, state, results, before["kind"])
        records.write_text(run_dir, run_dir / "census.reconciled.json", census.dump(done))
        records.write_json(run_dir, run_dir / "coverage.reconciled.json", after)
        counts = census.window_counts(census.rows(done))
        say(f"reconciled {run_dir}: accounted {flags['accounted']} ({counts['accounted']}/{counts['eligible']} sessions), "
            f"fully read {flags['fully_read']} ({counts['fully_read']}/{counts['eligible']})")
        return 0
    say("\n".join(census.report_lines(census.run(run_dir, args.coverage, args.originators, args.jobs))))
    return 0


def register_inventory_outputs(stage, manifest):
    """Every artifact inventory's manifest lists, the shared inventories among them (step 0 S-22), as an
    output of the stage, and the manifest itself, whose own digest lives here rather than in its own
    list. The list is inventory's, never one of this driver's: a file it wrote and this did not name
    would ship unseen."""
    for artifact in manifest.get("artifacts") or []:
        stage.output(artifact["path"])
    stage.output("inventory/manifest.json")


def cmd_inventory(args):
    """S2's inventory: `inventory/<reference>.json` for every reference point of design §6.1."""
    out_dir = run_dir_of(args) if args.run_id else pathlib.Path(args.to or "")
    if not args.run_id and not args.to:
        raise Refused("INPUT_INVALID inventory: give --run-id, or --to DIR to write outside a run")
    repo = pathlib.Path(__file__).resolve().parents[1]
    # Two questions, not one value. The roots are resolved for PROTECTION whatever this run reads,
    # and `--no-state` decides only the reading pair. Setting both to None before the protected set
    # was built made the flag that says "read nothing" also say "write anywhere" (R1#1).
    declared_state, declared_user = inventory.configured_roots(args.state_root, args.user_root)
    state_root = None if args.no_state else str(declared_state)
    user_root = None if args.no_state else str(declared_user)
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
        [out_dir], inventory.protected_roots(declared_state, declared_user, native,
                                             checkout=repo, repo=repo),
        home=HOME)
    if overlap:
        raise Refused("; ".join(overlap))
    # A standalone `--to` enters no stage and reads no declaration, so a run's artifacts are not
    # its to replace (GC#3 by another route).
    if not args.run_id:
        standalone = inventory.standalone_problems(out_dir, HOME)
        if standalone:
            raise Refused("; ".join(standalone))
    # The ledger: what `--ledger` names, else the state root's own (`<state>/distill/ledger.json`).
    # The checkout's ledger under `design/` is not a default any more — a packaged user has no such
    # directory, and the runbook passes the path when a run is meant to read the owner's (WP-24).
    ledger_path = ledger_lib.ledger_path(state_root, args.ledger)
    ledger = records.read_json(ledger_path) if ledger_path and ledger_path.is_file() else None
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True)
    # The transcripts come from the run's own census (S1), through its readers and bound to its
    # record. Outside a run there is no census, and every native layer is `unknown` with that reason.
    run_dir = out_dir if args.run_id else None

    def produce(zstd=None):
        return inventory.run(repo, state_root, user_root, out_dir, pin=args.pin, native_roots=native,
                             ledger=ledger, commit=(head.stdout.strip() or None), run_dir=run_dir,
                             zstd=zstd, declared_state=str(declared_state), declared_user=str(declared_user),
                             ledger_ref=(str(args.ledger) if args.ledger else None))

    if args.run_id:
        # S2 holds two producers; this is the inventory part, and views owns the other
        # (records.STAGE_PARTS). The census is its S1 input, declared as `views.run` declares it, so
        # a census changed after S1 recorded it is refused by name instead of read (#11).
        with records.run_stage(out_dir, "S2", [{"artifact": inventory.CENSUS, "producer_stage": "S1"}],
                               part="inventory") as stage:
            # A compressed transcript is read with the decoder the run DECLARES, taken the way
            # `views.run` takes it: none was passed, so a zstd rollout could not be read here at all
            # (#11). It is the declaration the stage was admitted against, never a read of run.json,
            # which an amendment landing after the admission could have changed (X review of WP-08 r2).
            manifest = produce(sources.declared(stage.declaration).get("zstd"))
            register_inventory_outputs(stage, manifest)
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
    say("\n".join(views.report_lines(views.run(run_dir_of(args)))))
    return 0


def cmd_form(args):
    """S4 (runlib/stage_form.py): dry, up to the call; otherwise its one call through a supervisor made before the stage
    is entered, so a live run without its token is refused before anything is recorded."""
    run_dir = run_dir_of(args)
    index_rows = json.loads(pathlib.Path(args.index).read_text(encoding="utf-8")) if args.index else None
    if args.dry:
        if args.cells or args.golden_plan:
            raise Refused("INPUT_INVALID form --dry: a dry run makes no call, so it takes no --cells or --golden-plan")
        summary = stage_form.run(run_dir, None, dry=True, index_rows=index_rows,
                                 ledger_ref=args.checkout_ledger)
    else:
        if not args.cells:
            raise Refused("INPUT_INVALID form --cells: the formation call runs in a cell under a cell root; give --cells "
                          "DIR, or --dry to stop before the call")
        summary = stage_form.run(run_dir, stage_form.supervisor(run_dir, args.cells, args.golden_plan),
                                 index_rows=index_rows, ledger_ref=args.checkout_ledger)
    say("\n".join(stage_form.report_lines(summary)))
    return 0


def name_checkout_ledger(args):
    """Set the module-level reference `lifecycle_intake.ledger_of` reads, from this caller's flag.

    The hook the intake documents for an author-side caller: the stages that read the pinned ledger
    take no parameter for it, and a driver that guessed the path would be reading whatever file the
    guess lands on. Unset without the flag, so the stage is refused by name."""
    if getattr(args, "checkout_ledger", None):
        from runlib import lifecycle_intake
        lifecycle_intake.CHECKOUT_LEDGER = args.checkout_ledger


def cmd_retrieve(args):
    """S5 (runlib/stage_retrieve.py): code only, over S4's population."""
    name_checkout_ledger(args)
    say("\n".join(stage_retrieve.report_lines(stage_retrieve.run(run_dir_of(args)))))
    return 0


def cmd_judge(args):
    """S6 (runlib/stage_judge.py): dry, up to the calls; otherwise both judges' calls through a supervisor made before
    the stage is entered, so a live run without its token is refused before anything is recorded."""
    name_checkout_ledger(args)
    run_dir = run_dir_of(args)
    if args.dry:
        if args.cells or args.golden_plan:
            raise Refused("INPUT_INVALID judge --dry: a dry run makes no call, so it takes no --cells or --golden-plan")
        summary = stage_judge.run(run_dir, dry=True)
    else:
        if not args.cells:
            raise Refused("INPUT_INVALID judge --cells: the judgment calls run in cells under a cell root; give --cells "
                          "DIR, or --dry to stop before the calls")
        summary = stage_judge.run(run_dir, stage_judge.supervisor(run_dir, args.cells, args.golden_plan))
    say("\n".join(stage_judge.report_lines(summary)))
    return 0


def cmd_propose(args):
    """S7 (runlib/stage_propose.py): the packets, or a golden run over answers the caller supplies.

    The live call is NOT wired here. The stage and its contract are complete and judged on golden
    answers; what is missing is the supervised call, and a driver that pretended otherwise would
    start a model from a command whose refusal path nobody has exercised."""
    run_dir = run_dir_of(args)
    if args.dry:
        derivations = records.read_json(run_dir / "judgments" / "derivations.json")
        candidates = records.read_json(run_dir / "checked-candidates.json")
        measures = []
        for row in candidates.get("candidates") or []:
            built = stage_propose.packet_for(row, derivations,
                                             (derivations.get("verdicts") or {}).get(row["candidate_id"]))
            measures.append(f"{row['candidate_id']}: packet {len(built)} bytes")
        say("\n".join(["S7 dry: the packets this run would send",
                        *measures,
                        f"unknowns in force: {len(stage_propose.named_states(derivations))}"]))
        return 0
    if not args.answers:
        say("CALL_NOT_WIRED propose: the supervised call has not landed; give --answers PATH to run "
            "the stage over answers already in hand, or --dry for the packets", sys.stderr)
        return 2
    answers = records.read_json(pathlib.Path(args.answers))
    stage, doc = stage_propose.run(run_dir, answers)
    say(f"S7: {doc['counts']['proposed']} proposed, {doc['counts']['returned']} returned, "
        f"{doc['counts']['awaiting_R']} awaiting R")
    return 0


def cmd_review_proposals(args):
    """S7b (runlib/stage_review_proposals.py): golden over reviews the caller supplies; see cmd_propose."""
    run_dir = run_dir_of(args)
    if not args.reviews:
        say("CALL_NOT_WIRED review-proposals: the supervised call has not landed; give --reviews PATH "
            "to run the stage over reviews already in hand", sys.stderr)
        return 2
    reviews = records.read_json(pathlib.Path(args.reviews))
    stage, doc = stage_review_proposals.run(run_dir, reviews)
    say(f"S7b: {doc['counts']['reviewed']} reviewed, {doc['counts']['disagreements']} disagreements, "
        f"{doc['counts']['returned']} returned, {doc['counts']['unreviewed']} unreviewed")
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
        sub.add_argument("--out", default=None,
                         help="root of the run directories (default: the XDG state directory's "
                              "agent-bios/distill/runs, which is inside neither the package nor the state root)")

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
        helps = {"census": f"{stage}: the census", "views": f"{stage}: the reading views, the search index and the evidence store",
                 "form": f"{stage}: candidate formation and the lifecycle intake",
                 "retrieve": f"{stage}: retrieval, quote and session checks, and recurrence",
                 "judge": f"{stage}: the judges A and B"}
        sub = commands.add_parser(name, help=helps.get(name, f"{stage}: not implemented yet"))
        common(sub)
        if name == "close":
            sub.add_argument("--recovery", action="store_true", help="the recovery close (reserved)")
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
        if name == "judge":
            sub.add_argument("--dry", action="store_true", help="stop before the calls: every judgment packet's measure")
            sub.add_argument("--cells", help="the cell root the judgment calls run under (made mode 700)")
            sub.add_argument("--golden-plan", help="a golden hosts' plan: the calls are answered from it and start no model")
        if name in ("retrieve", "judge"):
            # S5 and S6 read the pinned ledger through `lifecycle_intake.ledger_of`, which refuses
            # LEDGER_UNNAMED rather than guessing a checkout's layout. Without this flag neither
            # command could run from a checkout at all — the refusal came from the merge of the
            # ship-driver history, where the installed ledger became a parameter, with the two
            # stages that read it on the other side.
            sub.add_argument("--checkout-ledger", help="the ledger's path INSIDE the declaration's checkout "
                                                       "destination, which the caller names because the layout of a "
                                                       "checkout is not this driver's to assume; without it the "
                                                       "stage is refused LEDGER_UNNAMED rather than reading a guess")
        if name == "form":
            sub.add_argument("--dry", action="store_true", help="stop before the call: the intake and the packet's measure")
            sub.add_argument("--cells", help="the cell root the formation call runs under (made mode 700)")
            sub.add_argument("--golden-plan", help="a golden host's plan: realization golden, no model is started")
            sub.add_argument("--index", help="the occasion index's rows (a JSON list; WP-21, golden until it lands)")
            sub.add_argument("--checkout-ledger", help="the ledger's path INSIDE the declaration's checkout "
                                                       "destination, which the caller names because the layout of a "
                                                       "checkout is not this driver's to assume; without it the "
                                                       "stage is refused LEDGER_UNNAMED rather than reading a guess")
        if name == "propose":
            sub.add_argument("--dry", action="store_true", help="stop before any call: the packets this run would send")
            sub.add_argument("--answers", help="a JSON object of answers by candidate id, for a golden run")
        if name == "review-proposals":
            sub.add_argument("--reviews", help="a JSON object of reviews by item id, for a golden run")
        sub.set_defaults(handler={"census": cmd_census, "views": cmd_views, "inventory": cmd_inventory,
                                  "form": cmd_form, "retrieve": cmd_retrieve, "judge": cmd_judge,
                                  "propose": cmd_propose,
                                  "review-proposals": cmd_review_proposals}.get(name, cmd_stage))
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command is None:
            # The self-test is INSIDE this boundary. It was invoked above it, so an ordinary file
            # failure in a fixture — a scratch directory that cannot be made, a fixture read that is
            # refused — left an unprojected traceback carrying whatever path it named (R2#2).
            if args.self_test:
                return self_test()
            build_parser().print_help()
            return 2
        return args.handler(args)
    except (Refused, stagelock.Locked, stagelock.Escaped) as exc:
        # A HANDLED refusal is an abort too: the suite runs inside this boundary, and a refusal
        # raised from inside it used to leave with every collected failure line unpublished, because
        # only the unexpected-failure handler below published (r4 R1). Empty on every normal path.
        entry.publish_collected(lambda line: entry.emit(line, sys.stderr), through_floor=True)
        say(str(exc), sys.stderr)
        return 1
    except Exception as exc:
        # An unexpected failure is a diagnostic like any other, and an unexpected one is the one most
        # likely to carry a path: an OSError's message IS a path, and a traceback printed by the
        # interpreter crosses no boundary at all. The type is named so the failure is still
        # diagnosable, and the message passes the floor (GC#6).
        # The label names the command, and the suite's label is spelled WITHOUT the flag's dashes:
        # the judge admits the suite argv only where a suite is entered in this process, and buying
        # an exception for a diagnostic label would widen a rule that exists to keep a child from
        # being handed a suite (G3).
        # This handler, not `entry.failed`, is what an abort inside the suite reaches, so the
        # collected report is published here too — before the failure is described.
        entry.publish_collected(lambda line: entry.emit(line, sys.stderr), through_floor=True)
        say(f"COMMAND_FAILED {args.command or 'self-test'}: {type(exc).__name__}: {exc}", sys.stderr)
        return 1


def self_test():
    """The golden end to end: declare, run a stub stage, amend, run another, and judge the
    declaration order of the recorded stages from the files on disk."""
    # Set where this suite begins publishing its report. Past that point a control is not in the
    # number the summary published, and the summary has already said OK — which is a conclusion
    # printed before the judging. The helpers below refuse past it rather than trusting placement.
    reporting = []
    failures, ran = entry.self_test_failures("distill --self-test"), []
    # Registered while this suite runs; removed by `report`, which is where this suite reports. An
    # abort between the two publishes what was collected rather than taking it away.
    entry.SELF_TEST_COLLECTED.append(("distill --self-test", failures))

    def control(name, ok, detail=""):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}: this suite has begun publishing its "
                               f"report, so `control` is not in the count it published")
        # A boolean-style helper given a problem LIST passed on whatever its needle said, because a
        # non-empty list is truthy: three controls in this package read correctly and asked nothing
        # until S8a found them. The signature is enforced here rather than remembered.
        if not isinstance(ok, bool):
            raise TypeError(f"CONTROL_CONDITION_NOT_BOOL {name}: this file's `control` judges a "
                            f"boolean condition and was given {type(ok).__name__}")
        ran.append(name)
        if not ok:
            failures.append((name, detail))

    def type_refusal(call):
        """The message a self-test helper raises when it is given the wrong KIND of argument. The
        control below catches it here, so asking the guard does not fail the suite."""
        try:
            call()
        except TypeError as exc:
            return str(exc)
        return ""

    control("a boolean-style control given a problem list is refused by name",
            "CONTROL_CONDITION_NOT_BOOL" in type_refusal(lambda: control("a planted non-boolean", ["a problem"])),
            "the guard admitted a non-boolean condition, so a control in the other file's style would pass on a truthy list")

    # Chosen and judged by the same rule production uses, never probed: this suite writes run
    # directories, fixture state roots and a copy of the checkout (R1#5).
    with inventory.self_test_scratch("wp07-driver-self-test-") as scratch:
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

        # each implemented command has its own controls (form's and retrieve's runs in runlib/stage_form.py's and
        # runlib/stage_retrieve.py's suites, as a process); the rest are named and refused
        implemented = ("census", "views", "inventory", "form", "retrieve", "judge", "propose",
                       "review-proposals")
        for command, stage_id in STAGE_COMMANDS.items():
            if command in implemented:
                continue
            code, err = cli(command, "--run-id", "r1")
            control(f"{command} ({stage_id}) is named and refused",
                    code == 2 and f"STAGE_NOT_IMPLEMENTED {command} ({stage_id})" in err, err)
        # `propose` and `review-proposals` left the loop above when they gained handlers, so their own
        # refusal paths are controlled here instead: moving a command out of "named and refused"
        # without controlling what it now does would be two controls removed and none added.
        def no_stage_record():
            return not (out / "r1" / "stages" / "S7.json").exists() \
                   and not (out / "r1" / "stages" / "S7b.json").exists()
        code, err = cli("propose", "--run-id", "r1")
        control("propose (S7) without --answers says the supervised call is not wired, and records no "
                "stage", code == 2 and "CALL_NOT_WIRED propose" in err and no_stage_record(), f"{code} {err}")
        code, err = cli("review-proposals", "--run-id", "r1")
        control("review-proposals (S7b) without --reviews says the same, by its own name",
                code == 2 and "CALL_NOT_WIRED review-proposals" in err and no_stage_record(),
                f"{code} {err}")
        code, err = cli("propose", "--run-id", "r1", "--dry")
        control("propose --dry over a run S6 has not written is refused by name, and still records no "
                "stage", code != 0 and "derivations.json" in err and no_stage_record(), f"{code} {err}")
        def stage_files():
            return {str(p): p.read_bytes() for p in sorted((out / "r1" / "stages").rglob("*")) if p.is_file()}
        before = stage_files()
        code, err = cli("retrieve", "--run-id", "r1")
        control("retrieve (S5) over a run S4 has not run is refused by name, and no stage record is written or changed",
                code == 1 and "INPUT_INVALID S4" in err and stage_files() == before, f"{code} {err}")
        before = stage_files()
        code, err = cli("judge", "--run-id", "r1")
        control("judge (S6) with neither --dry nor --cells is refused by name before anything is recorded",
                code == 1 and "INPUT_INVALID judge --cells" in err and stage_files() == before, f"{code} {err}")
        code, err = cli("judge", "--run-id", "r1", "--dry", "--cells", str(out / "judge-cells"))
        control("judge --dry (S6) with --cells is refused by name: a dry run makes no call",
                code == 1 and "INPUT_INVALID judge --dry" in err and stage_files() == before, f"{code} {err}")
        held_token = os.environ.pop("CLAUDE_RUN_TOKEN_FILE", None)
        try:
            code, err = cli("judge", "--run-id", "r1", "--cells", str(out / "judge-cells"))
        finally:
            if held_token is not None:
                os.environ["CLAUDE_RUN_TOKEN_FILE"] = held_token
        control("a live judge (S6) with no CLAUDE_RUN_TOKEN_FILE is refused by name before its cell root or any stage "
                "record is made", code == 1 and "TOKEN_FILE_UNSET S6" in err and not (out / "judge-cells").exists()
                and stage_files() == before, f"{code} {err}")
        code, err = cli("judge", "--run-id", "r1", "--dry")
        control("judge --dry (S6) over a run S5 has not run is refused by name, and no stage record is written or changed",
                code == 1 and "INPUT_INVALID S5" in err and stage_files() == before, f"{code} {err}")
        code, err = cli("form", "--run-id", "r-form")
        control("form (S4) with neither --dry nor --cells is refused by name before anything is recorded",
                code == 1 and "INPUT_INVALID form --cells" in err and not (out / "r-form").exists(), err)
        code, err = cli("form", "--run-id", "r-form", "--dry", "--cells", str(out / "form-cells"))
        control("form --dry with a cell root is refused by name: a dry run makes no call",
                code == 1 and "INPUT_INVALID form --dry" in err, err)
        held_token = os.environ.pop("CLAUDE_RUN_TOKEN_FILE", None)
        try:
            code, err = cli("form", "--run-id", "r-form", "--cells", str(out / "form-cells"))
        finally:
            if held_token is not None:
                os.environ["CLAUDE_RUN_TOKEN_FILE"] = held_token
        control("a live form with no CLAUDE_RUN_TOKEN_FILE is refused by name before its cell root or any record is made",
                code == 1 and "TOKEN_FILE_UNSET S4" in err and not (out / "form-cells").exists()
                and not (out / "r-form").exists(), err)
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
        #
        # The destination has to be inside "the checkout", which is the one root this rule is about —
        # so the checkout under test is a DISPOSABLE COPY and the driver run is that copy's own. The
        # first version used the review checkout and then removed the destination unconditionally: a
        # failing control appended its failure and execution carried on to the `rmtree`, so a
        # leftover from an interrupted revert — or anything else that happened to be at that path —
        # was deleted inside the reviewer's tree (R1#2). Nothing here deletes anything: the copy
        # lives under the judged scratch parent and goes with it.
        protect_copy = scratch / "protection-checkout"
        inventory.checkout_copy(protect_copy)
        other_project = scratch / "another-project"
        other_project.mkdir()

        def copy_cli(*argv):
            """The COPY's own driver, as a real process: `repo` is resolved from `__file__`, so only
            the copy's driver treats the copy as the checkout."""
            # The program is produced by `inventory.copied_member`, the owner of "a closure member
            # inside a tree this process copied": that call is what the closure gate admits, so the
            # admission is bound to this call and not to text elsewhere in this file (R2#5).
            ran = entry.bounded(lambda: subprocess.Popen(
                [sys.executable,
                 str(inventory.copied_member(protect_copy, "session-distill/distill.py")),
                 *argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=True), what="the copy's own driver")
            return ran.returncode, ran.stdout + ran.stderr

        @contextlib.contextmanager
        def owning(name):
            """A control's own fixtures. A crash inside is a failure of THIS name, not a dead suite:
            under a revert the write these controls expect to be refused actually lands, and a
            `mkdir` in the next control then raised `FileExistsError` out of the whole run — which
            is also why no two of them share a destination any more."""
            ran.append(name)
            try:
                yield
            except Exception as exc:
                failures.append((name, f"RAISED {exc!r}"))

        with owning("the checkout-protection controls' own fixtures"):
            # Each control owns its destination, and no other control names it.
            in_checkout = protect_copy / "session-distill" / "out" / "a-destination-no-run-owns"
            code, err = copy_cli("inventory", "--to", str(in_checkout), "--no-state",
                                 "--project", str(other_project))
            control("inventory (S2) refuses a destination inside the checkout when another project is declared",
                    code == 1 and "PROTECTED_OVERLAP" in err, f"{code} {err}")
            control("and the attempted write did not happen", not in_checkout.exists(),
                    f"{in_checkout} exists after a refused run")
            # The shape the old cleanup would have destroyed: a destination that already exists,
            # holding something this test does not own. It is still refused, and the sentinel is
            # still there afterwards — nothing here removes anything.
            existing = protect_copy / "session-distill" / "out" / "a-destination-that-already-exists"
            sentinel = existing / "sentinel.txt"
            existing.mkdir(parents=True, exist_ok=True)
            sentinel.write_text("left here by something that is not this test\n", encoding="utf-8")
            code, err = copy_cli("inventory", "--to", str(existing), "--no-state",
                                 "--project", str(other_project))
            control("a pre-existing destination inside the checkout is refused and nothing of it is removed",
                    code == 1 and "PROTECTED_OVERLAP" in err and sentinel.is_file()
                    and sentinel.read_text(encoding="utf-8").startswith("left here"),
                    f"{code} {sentinel.exists()} {err[:200]}")

        def cli_refused_before_run(*argv):
            """`(code, err, reached)`: the CLI's answer with `inventory.run` replaced by a recorder.

            Protection is enforced in two layers — the driver judges the destination, and
            `inventory.run` judges it again over its own protected set. With both in place a
            refusal cannot be attributed to either, so reverting one layer left the other refusing
            and the control stayed green (R1#1, and the same shape at #17). Here the producer is
            not there to refuse anything: what is observed is that THIS layer refused, and that the
            producer was never reached."""
            reached = []
            kept = inventory.run
            try:
                inventory.run = lambda *args, **kwargs: (reached.append(argv) or
                                                         {"references": {}, "state_root_unchanged": True})
                return (*cli(*argv), reached)
            finally:
                inventory.run = kept

        # The CLI layer alone, for each of the two destinations it must refuse: inside the checkout
        # when another project is declared, and inside the owner's state root under `--no-state`.
        # The first destination is inside THIS checkout, because that is the root the rule names and
        # the in-process driver's own `repo`. Nothing writes there in either direction: the producer
        # is the recorder, and the driver creates no destination of its own — the control asserts it
        # afterwards rather than trusting that.
        unwritten = pathlib.Path(__file__).resolve().parents[1] / "out" / "a-cli-layer-destination"
        cli_checkout = scratch / "cli-layer-reachable-destination"
        guarded_state_cli = scratch / "cli-layer-state"
        (guarded_state_cli / "runtime").mkdir(parents=True)
        code, err, reached = cli_refused_before_run(
            "inventory", "--to", str(unwritten), "--no-state", "--project", str(other_project))
        control("the driver itself refuses a destination inside the checkout, before the producer is called",
                code == 1 and "PROTECTED_OVERLAP" in err and not reached, f"{code} {reached} {err}")
        control("and that destination inside this checkout was never created",
                not unwritten.exists(), f"{unwritten} exists after the control ran")
        code, err, reached = cli_refused_before_run(
            "inventory", "--to", str(guarded_state_cli / "out"), "--state-root", str(guarded_state_cli),
            "--user-root", str(scratch / "cli-layer-user"), "--no-state")
        control("the driver itself refuses a destination inside the unread state root, before the producer is called",
                code == 1 and "PROTECTED_OVERLAP" in err and not reached, f"{code} {reached} {err}")
        control("and the producer is reachable at all when the destination is not protected",
                bool(cli_refused_before_run("inventory", "--to", str(cli_checkout), "--no-state")[2]),
                "the recorder was never called, so the two controls above judge nothing")

        # ---- r7 R17b: "the checkout is ALWAYS a project" was watched only through a REFUSAL, and
        # `inventory.run` refuses the same destination over its own protected set. With the checkout
        # dropped from this set the driver admitted the destination and the producer refused it, so
        # the control stayed green while the rule was gone. What is read here is the set itself, as
        # the driver hands it over, at a destination nothing refuses.
        handed = {}
        kept_producer = inventory.run
        try:
            inventory.run = lambda *a, **k: (handed.update(k) or
                                             {"references": {}, "state_root_unchanged": True})
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                main(["inventory", "--to", str(scratch / "project-set-reader"), "--no-state",
                      "--project", str(other_project)])
        finally:
            inventory.run = kept_producer
        handed_projects = sorted((handed.get("native_roots") or {}).get("projects") or {})
        # Observe only that the CALL happened. Its condition used to be `len(handed_projects) == 2`,
        # which is the next control's subject: with the set wrong both failed, and this one's message
        # said the producer was never reached when it had been (r8 R17b). Two controls, two facts.
        control("and that project set was read from a call that really happened",
                "native_roots" in handed, f"{sorted(handed)} — the producer was never reached")
        control("the project set the driver hands over names the other project AND this checkout",
                str(pathlib.Path(__file__).resolve().parents[1]) in handed_projects
                and str(pathlib.Path(other_project).resolve()) in handed_projects,
                f"{handed_projects}")

        # ---- r3 #7: the driver's own preflight over a CONFIGURED host home. The host homes are
        # protected whether or not a run reads them, and which directory each one IS comes from
        # `CLAUDE_CONFIG_DIR` and `CODEX_HOME` (R2#1). The controls above never set either, so
        # restoring `NATIVE`'s defaults at this call site alone was unobserved by all of them.
        #
        # Asked of THIS layer: the producer is a recorder, so nothing downstream can refuse on the
        # driver's behalf, and the destination is named with `--run-id` so that a stage record —
        # itself a write — would be entered before `inventory.run` could be reached at all.
        def cli_with_environment(environment, *argv):
            """`(code, err, reached)` for one invocation under `environment`, producer recorded.

            The driver reads the environment where it resolves roots, not where it starts, so the
            variables are placed for the duration of the call and taken away afterwards."""
            reached, kept_run, kept_environ = [], inventory.run, dict(os.environ)
            try:
                inventory.run = lambda *a, **k: (reached.append(argv) or
                                                 {"references": {}, "state_root_unchanged": True})
                os.environ.update(environment)
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    try:
                        code = main(list(argv))
                    except SystemExit as exc:
                        code, _ = (exc.code if isinstance(exc.code, int) else 2), err.write(f"EXITED {exc.code!r}")
                    except Exception as exc:
                        code, _ = 99, err.write(f"RAISED {exc!r}")
                return code, err.getvalue(), reached
            finally:
                inventory.run = kept_run
                os.environ.clear()
                os.environ.update(kept_environ)

        host_home_fixture = scratch / "configured-host-homes"
        (host_home_fixture / "home").mkdir(parents=True)
        fixture_environment = {"HOME": str(host_home_fixture / "home"),
                               "CLAUDE_CONFIG_DIR": str(host_home_fixture / "elsewhere" / "claude"),
                               "CODEX_HOME": str(host_home_fixture / "elsewhere" / "codex")}
        moved_homes = [str(home) for home in inventory.host_homes(fixture_environment)]
        control("the two variables really move the homes this driver protects",
                moved_homes == [fixture_environment["CLAUDE_CONFIG_DIR"],
                                fixture_environment["CODEX_HOME"]], f"{moved_homes}")
        for variable in ("CLAUDE_CONFIG_DIR", "CODEX_HOME"):
            configured = pathlib.Path(fixture_environment[variable])
            # A run directory under the configured home, named through `--out` and `--run-id`, so
            # the refusal has to come before `records.run_stage` is entered.
            code, err, reached = cli_with_environment(
                fixture_environment, "inventory", "--run-id", "r-host-home",
                "--out", str(configured / "runs"), "--no-state",
                "--state-root", str(host_home_fixture / "state"),
                "--user-root", str(host_home_fixture / "user"))
            control(f"the driver itself refuses a run destination inside the home {variable} names",
                    code == 1 and "PROTECTED_OVERLAP" in err and not reached,
                    f"{code} {reached} {err.strip()[:300]}")
            written = sorted(str(path.relative_to(host_home_fixture))
                             for path in host_home_fixture.rglob("record.json"))
            control(f"and nothing of that run exists afterwards, so no stage was entered ({variable})",
                    not configured.exists() and not written,
                    f"{configured} exists={configured.exists()} records={written}")
        # The same environment with a destination OUTSIDE those homes: the recorder is reached, so
        # the two refusals above are the configured homes' doing and not this environment refusing
        # every destination. It is a standalone `--to`, because a run id would need a declaration
        # and `RUN_UNDECLARED` is a different refusal that would satisfy the same control.
        reachable_out = scratch / "configured-host-homes-reachable"
        code, err, reached = cli_with_environment(
            fixture_environment, "inventory", "--to", str(reachable_out), "--no-state",
            "--state-root", str(host_home_fixture / "state"),
            "--user-root", str(host_home_fixture / "user"))
        control("and the same run outside those homes reaches the producer", len(reached) == 1,
                f"the recorder was called {len(reached)} time(s): {code} {err.strip()[:300]}")
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
        # ---- #11: the inventory part through the driver. Its census is an S1 input, so a census
        # changed after S1 recorded it is refused by name, and a compressed transcript is read with the
        # decoder the run declares. Both used to be missing: the part declared no input and was handed
        # no decoder, so a zstd rollout was unreadable to it and a moved census was read anyway.
        inventory_run = out / "r-inventory"
        code, err = cli("declare", "--run-id", "r-inventory", "--from", str(out / "declaration.json"))
        control("a fixture run for the inventory part is declared", code == 0, f"{code}")
        rollouts = scratch / "inventory-transcripts"
        rollouts.mkdir()
        block_marker = "the block a compressed rollout carried"
        plain_rollout = rollouts / "rollout-2026-10-10T09-00-00-cccc.jsonl"
        plain_rollout.write_text(json.dumps(
            {"type": "session_meta", "timestamp": "2026-10-10T09:00:00+00:00",
             "payload": {"id": "cccc", "cwd": str(scratch),
                         "base_instructions": {"text": f"# Codex\n\n- {block_marker}\n"}}})
            + "\n", encoding="utf-8")
        plain_bytes = plain_rollout.read_bytes()
        compressed_rollout = rollouts / "rollout-2026-10-10T09-00-00-cccc.jsonl.zst"

        def zstd_frame(data):
            """TEST ONLY, never called by a product path: `data` as one zstd frame (RFC 8878 §3.1.1)
            holding raw, uncompressed blocks only, split into blocks of at most 128 KB. A real zstd
            file, written without starting a program, so this suite runs no program dispatch.py has
            not admitted; the declared decoder still reads it, through `sources.checked_zstd`."""
            size = len(data)
            header = (bytes([0x20]) + size.to_bytes(1, "little") if size < 256 else
                      bytes([0x60]) + (size - 256).to_bytes(2, "little") if size < 65792 else
                      bytes([0xA0]) + size.to_bytes(4, "little"))
            chunks = [data[at:at + 131072] for at in range(0, size, 131072)] or [b""]
            return (0xFD2FB528).to_bytes(4, "little") + header + b"".join(
                ((len(chunk) << 3) | (index == len(chunks) - 1)).to_bytes(3, "little") + chunk
                for index, chunk in enumerate(chunks))

        compressed_rollout.write_bytes(zstd_frame(plain_bytes))
        plain_rollout.unlink()
        zstd = sources.declared(declare.fixture()).get("zstd")

        def read_back(path):
            """What the declared decoder makes of `path`, or None: a machine without it fails the
            controls that need it by name, and none of them is skipped."""
            try:
                return b"".join(sources.read_lines(path, zstd))
            except Exception:
                return None

        # The frame itself, positively: without this, a broken frame and an undelivered decoder would
        # both look like a rollout with no event. Every size branch of the frame is read back - the
        # fixture rollout, a two-byte content size, and a payload split into three blocks.
        framed = {"the fixture rollout": (compressed_rollout, plain_bytes)}
        for label, payload in (("a two-byte content size", b"y" * 999 + b"\n"),
                               ("three blocks", b"x" * 299_999 + b"\n")):
            framed[label] = (rollouts / f"frame-{len(payload)}.jsonl.zst", payload)
            framed[label][0].write_bytes(zstd_frame(payload))
        back = {label: read_back(path) == payload for label, (path, payload) in framed.items()}
        control("the test-only zstd frame is read back byte for byte by the declared decoder",
                all(back.values()), f"{back}")
        bound = records.sha256_bytes(plain_bytes)
        # a Codex row holds its file in segments (D-20261103-a7128a)
        inventory_census = {"transcripts": [{
            "host": "codex", "id": "cccc", "source": "codex_sessions", "status": "eligible", "parent": None,
            "segments": [{"stem": census.stem_of(compressed_rollout), "source": "codex_sessions", "path": str(compressed_rollout),
                          "sha256": bound, "versions": [{"sha": bound, "record_count": 1, "prefix_sha": bound}],
                          "owned": [], "work": {"version": 0, "in_window": [], "backlog": []}}]}]}
        with records.run_stage(inventory_run, "S1") as recorded:
            records.write_text(inventory_run, inventory_run / "census.json", json.dumps(inventory_census))
            recorded.output("census.json")
        code, err = cli("inventory", "--run-id", "r-inventory", "--no-state")
        control("an ordinary run of the inventory part through the driver succeeds", code == 0, f"{code}")
        inventory_part = ((records.stage_records(inventory_run).get("S2") or {}).get("parts") or {}).get("inventory") or {}
        recorded_outputs = {row.get("artifact"): row.get("sha256") for row in inventory_part.get("outputs") or []}
        written_outputs = {path.relative_to(inventory_run).as_posix(): records.sha256_file(path)
                           for path in (inventory_run / "inventory").rglob("*") if path.is_file()}
        control("every file the inventory part wrote is an output its stage record names, by its bytes",
                code == 0 and len(written_outputs) >= 5 and recorded_outputs == written_outputs,
                f"written={len(written_outputs)} recorded={len(recorded_outputs)}")
        current_path = inventory_run / "inventory" / "current.json"
        current_units = (json.loads(current_path.read_text(encoding="utf-8"))["units"]
                         if code == 0 and current_path.is_file() else [])
        control("a zstd-compressed Codex rollout yields its event, by the decoded block's own text",
                any(block_marker in unit["text"] for unit in current_units if unit["layer"] == "native_undivided"),
                f"units={len(current_units)}")
        census_bytes = (inventory_run / "census.json").read_bytes()
        (inventory_run / "census.json").write_bytes(census_bytes.replace(b'"cccc"', b'"dddd"'))
        code, err = cli("inventory", "--run-id", "r-inventory", "--no-state")
        control("a census changed after S1 recorded it is refused by name",
                code == 1 and "INPUT_INVALID S1" in err and "census.json is not the output S1 recorded" in err,
                f"{code}")
        (inventory_run / "census.json").write_bytes(census_bytes)
        # X review of WP-08 r2: the inventory part takes the declaration it was admitted against, whichever side of the
        # admission an amendment lands on
        for when in ("before", "after"):
            seq_before = records.read_json(records.run_json_path(inventory_run))["declaration_seq"]
            given, real_declared = [], sources.declared
            sources.declared = lambda declaration: (given.append(declaration.get("declaration_seq")), real_declared(declaration))[1]
            try:
                with records.fx_amended_at_admission("S2", [("question", f"amended {when} the inventory's admission")], when):
                    code, err = cli("inventory", "--run-id", "r-inventory", "--no-state")
            finally:
                sources.declared = real_declared
            admitted_seq = (((records.stage_records(inventory_run).get("S2") or {}).get("parts") or {})
                            .get("inventory") or {}).get("declaration_seq")
            landed = records.read_json(records.run_json_path(inventory_run))["declaration_seq"]
            control(f"X r2: an amendment just {when} the inventory part's admission leaves it reading the declaration it "
                    "was admitted against", code == 0 and given and given[-1] == admitted_seq and landed == seq_before + 1
                    and admitted_seq == (landed if when == "before" else seq_before),
                    f"{code} given={given} admitted={admitted_seq} run.json {seq_before}->{landed}")

        # ---- S-22 (lead, P2.4b): the inventory part registers every artifact inventory's OWN manifest lists,
        # the shared inventories among them, by its bytes, and the manifest. Asked of the registration itself
        # over a planted output, inside a real stage: the --no-state run above writes no shared inventory.
        code, err = cli("declare", "--run-id", "r-register", "--from", str(out / "declaration.json"))
        control("a fixture run for the registration is declared", code == 0, f"{code}")
        register_run = out / "r-register"
        shared_paths = [f"inventory/shared/selection-{inventory.inventory_id('selection', 'a' * 64)}.json",
                        f"inventory/shared/release-{inventory.inventory_id('release', 'ref-a')}.json"]
        single_paths = [f"inventory/{name}.json" for name in (*inventory.REFERENCES, inventory.SESSIONS)] \
            + [f"inventory/{inventory.STORE_REL}"]
        every_path = single_paths + shared_paths + ["inventory/manifest.json"]
        for n, path in enumerate(every_path):
            (register_run / path).parent.mkdir(parents=True, exist_ok=True)
            records.write_text(register_run, register_run / path, json.dumps({"planted": n}))
        registered_error = None
        try:
            with records.run_stage(register_run, "S2", part="inventory") as stage:
                register_inventory_outputs(stage, {"artifacts": [{"path": path} for path in single_paths + shared_paths]})
        except Exception as exc:  # the control names what refused, never the suite
            registered_error = exc
        register_part = ((records.stage_records(register_run).get("S2") or {}).get("parts") or {}).get("inventory") or {}
        registered = {row.get("artifact"): row.get("sha256") for row in register_part.get("outputs") or []}
        control("the inventory part registers every artifact inventory's manifest lists, a shared selection and a "
                "shared release among them, by its bytes, and the manifest",
                registered_error is None and set(registered) == set(every_path)
                and all(registered.get(path) == records.sha256_file(register_run / path)
                        for path in shared_paths + ["inventory/manifest.json"]),
                f"{type(registered_error).__name__ if registered_error else None} registered={sorted(registered)}")

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
        # The same destination with `--no-state`, which says "read no state root at all". Protection
        # and reading were one value here: the flag set both roots to None before the protected set
        # was built, so this exact command exited 0 and wrote current.json, release.json,
        # selection.json and manifest.json under the owner's own state root (R1#1).
        code, err = cli("inventory", "--to", str(inside), "--state-root", str(guarded_state),
                        "--user-root", str(scratch / "guarded-user"), "--no-state")
        control("inventory (S2) refuses that destination with --no-state as well",
                code == 1 and "PROTECTED_OVERLAP" in err, f"{code} {err}")
        control("and the attempted write under the unread state root did not happen",
                not inside.exists() and sorted(p.name for p in guarded_state.rglob("*")) == ["runtime"],
                f"{sorted(str(p.relative_to(guarded_state)) for p in guarded_state.rglob('*'))}")
        guarded_user = scratch / "guarded-user-root"
        guarded_user.mkdir()
        code, err = cli("inventory", "--to", str(guarded_user / "out"), "--state-root", str(guarded_state),
                        "--user-root", str(guarded_user), "--no-state")
        control("and the authoring root it does not read is protected under the same flag",
                code == 1 and "PROTECTED_OVERLAP" in err and not (guarded_user / "out").exists(),
                f"{code} {err}")
        # The DEFAULT destination has to satisfy that same protection, or the driver would refuse
        # its own default when a user runs it with no `--out`. The default is not carved out of the
        # protected set: it is placed outside it. Judged with the CLI's own predicate, under a HOME
        # no part of this suite writes to, so the answer is about the rule and not about this tree.
        default_home = scratch / "default-home"
        (default_home / ".local" / "state").mkdir(parents=True)
        default_environ = {"HOME": str(default_home), "PATH": os.environ.get("PATH", "")}
        default_root = default_out(default_environ, home=default_home)
        default_state, default_user = inventory.configured_roots(environ=default_environ, home=default_home)
        package_tree = pathlib.Path(__file__).resolve().parents[1]
        default_native = {"projects": {str(package_tree): package_tree}}
        default_protected = inventory.protected_roots(default_state, default_user, default_native,
                                                      checkout=package_tree, environ=default_environ,
                                                      repo=package_tree)
        control("the default run root is outside every protected root",
                not inventory.overlap_problems([default_root], default_protected, home=str(default_home)),
                f"{default_root} :: {inventory.overlap_problems([default_root], default_protected, home=str(default_home))}")
        control("and outside the package tree, so an install does not replace a user's runs",
                package_tree not in default_root.resolve().parents
                and default_root.resolve() != package_tree,
                f"{default_root} under {package_tree}")
        # review Y #2: where the DEFAULT lands is decided by the environment, and the environment
        # can put it inside the package or inside the owner's data root. `declare` had no
        # protection of its own, so the only thing standing between those values and a write was
        # that nobody had tried them. Each case runs the real CLI with no `--out` at all.
        def no_out(*argv, **overrides):
            kept = {name: os.environ.get(name) for name in ("HOME", "XDG_STATE_HOME")}
            err = io.StringIO()
            try:
                for name, value in overrides.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    try:
                        code = main(list(argv))
                    except SystemExit as exc:
                        code, _ = (exc.code if isinstance(exc.code, int) else 2), err.write(f"EXITED {exc.code!r}")
                    except Exception as exc:
                        code, _ = 99, err.write(f"RAISED {exc!r}")
            finally:
                for name, value in kept.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value
            return code, err.getvalue()

        fake_home = scratch / "y2-home"
        (fake_home / ".local" / "share" / "agent-bios").mkdir(parents=True)
        (fake_home / ".local" / "state").mkdir(parents=True)
        declaration = scratch / "y2-declaration.json"
        declaration.write_text(json.dumps(declare.fixture()), encoding="utf-8")
        state_root_xdg = str(fake_home / ".local" / "share")
        code, err = no_out("declare", "--run-id", "y2-data-root", "--from", str(declaration),
                           HOME=str(fake_home), XDG_STATE_HOME=state_root_xdg)
        control("review Y #2: a default run root inside the owner's DATA root is refused, by name",
                code == 1 and "DEFAULT_OUT_PROTECTED" in err, f"{code} {err[:300]}")
        control("and nothing is written under it",
                not (fake_home / ".local" / "share" / "agent-bios" / "distill").exists(),
                f"{sorted(q.name for q in (fake_home / '.local' / 'share' / 'agent-bios').rglob('*'))}")
        linked = scratch / "y2-link"
        linked.symlink_to(fake_home / ".local" / "share")
        code, err = no_out("declare", "--run-id", "y2-link", "--from", str(declaration),
                           HOME=str(fake_home), XDG_STATE_HOME=str(linked))
        control("review Y #2: a SYMLINKED base that lands in the same root is refused too",
                code == 1 and "DEFAULT_OUT_PROTECTED" in err, f"{code} {err[:300]}")
        code, err = no_out("declare", "--run-id", "y2-relative-xdg", "--from", str(declaration),
                           HOME=str(fake_home), XDG_STATE_HOME=".")
        control("review Y #2: a RELATIVE XDG_STATE_HOME is ignored and said so, not resolved "
                "against the working directory",
                code == 0 and "DEFAULT_OUT_INPUT_IGNORED" in err and "is relative" in err,
                f"{code} {err[:300]}")
        control("and the run landed under the documented default instead",
                (fake_home / ".local" / "state" / "agent-bios" / "distill" / "runs"
                 / "y2-relative-xdg").is_dir(),
                f"{sorted(q.name for q in (fake_home / '.local' / 'state').rglob('*'))[:6]}")
        here = pathlib.Path.cwd()
        # review Y r2 #1: with a relative $HOME and no XDG, the destination comes from the password
        # database — the one home this suite could not state, so the run landed in the REAL account
        # home and a commit hook created `~/.local/state/agent-bios/distill/runs/y2-relative-home/`
        # there. The control now states the account home it means through the production seam, and a
        # CANARY reads the real one (names only, never contents) to prove nothing arrived in it.
        real_account = pathlib.Path(_password_home())
        canary_root = real_account / ".local" / "state" / "agent-bios"
        canary_before = (sorted(str(q.relative_to(canary_root)) for q in canary_root.rglob("*"))
                         if canary_root.is_dir() else None)
        account = scratch / "account-home"
        account.mkdir()
        kept_seam = globals()["_password_home"]
        try:
            globals()["_password_home"] = lambda: str(account)
            code, err = no_out("declare", "--run-id", "y2-relative-home", "--from", str(declaration),
                               HOME="relative-home", XDG_STATE_HOME=None)
        finally:
            globals()["_password_home"] = kept_seam
        landed = account / ".local" / "state" / "agent-bios" / "distill" / "runs" / "y2-relative-home"
        control("review Y #2: a RELATIVE HOME is ignored for the default run root as well",
                "DEFAULT_OUT_INPUT_IGNORED" in err and "HOME=" in err, f"{code} {err[:300]}")
        control("review Y r2 #1: and the run lands in the account home the password database states, "
                "which this control states for itself",
                code == 0 and (landed / "run.json").is_file(), f"{code} {landed} {err[:200]}")
        canary_after = (sorted(str(q.relative_to(canary_root)) for q in canary_root.rglob("*"))
                        if canary_root.is_dir() else None)
        control("review Y r2 #1: and the REAL account home is untouched by this suite",
                canary_after == canary_before,
                f"{canary_root}: before {None if canary_before is None else len(canary_before)} "
                f"after {None if canary_after is None else len(canary_after)}; "
                f"new {sorted(set(canary_after or []) - set(canary_before or []))[:5]}")
        # review Y r2 #4: an absolute XDG base determines the whole answer, so a home it does not
        # need must not be able to refuse it. The home resolution ran FIRST, and an account whose
        # database home is unreadable then raised DEFAULT_OUT_UNRESOLVED over a destination that was
        # already fully decided.
        kept_seam = globals()["_password_home"]
        try:
            globals()["_password_home"] = lambda: "not-absolute"
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    xdg_only = default_out({"HOME": "relative-home", "XDG_STATE_HOME": str(scratch / "xdg")})
            except Refused as exc:
                # The pre-fix order raises here, and a raised refusal must read as THIS control's
                # failure rather than ending the suite: a control whose text never prints is a
                # control a reader cannot act on.
                xdg_only = f"REFUSED {exc}"
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    refused = f"RETURNED {default_out({'HOME': 'relative-home'})}"
            except Refused as exc:
                refused = str(exc)
        finally:
            globals()["_password_home"] = kept_seam
        control("review Y r2 #4: an absolute XDG_STATE_HOME is the base even when no home resolves",
                isinstance(xdg_only, pathlib.Path)
                and xdg_only == scratch / "xdg" / "agent-bios" / "distill" / "runs", str(xdg_only))
        control("review Y r2 #4: and with no XDG base, an unresolvable home is still refused by name",
                refused.startswith("DEFAULT_OUT_UNRESOLVED"), refused)
        # review Y r2 #3: an account with no password-database entry and no $HOME. `HOME =
        # str(pathlib.Path.home())` ran at IMPORT, before either startup boundary, and `Path.home()`
        # raises in that state — so the machine could not run the command at all, with `--out` or
        # without, and no boundary could describe why.
        #
        # Two decidable controls rather than a re-execution of the module body. Running this file
        # again as `__main__` (through a child or through `runpy`) is the shape the closure inventory
        # refuses: a child needs a program a declaration can name, and `runpy.run_path` of a runtime
        # path is a load the trace cannot resolve. Both refusals are right — this suite has no
        # business starting the driver again — so the import-time property is asserted where it
        # lives: in the function that answers, and in the module's own top level.
        stub = types.ModuleType("pwd")
        stub.getpwuid = stub.getpwnam = lambda *_a, **_k: (_ for _ in ()).throw(KeyError("no entry"))
        stub.error = KeyError
        kept = {"pwd": sys.modules.get("pwd"), "home": os.environ.get("HOME")}
        try:
            sys.modules["pwd"] = stub
            os.environ.pop("HOME", None)
            answered = _diagnostic_home()
            raised = None
        except BaseException as exc:                      # the defect, reported rather than fatal
            answered, raised = "RAISED", f"{type(exc).__name__}: {exc}"
        finally:
            if kept["pwd"] is None:
                sys.modules.pop("pwd", None)
            else:
                sys.modules["pwd"] = kept["pwd"]
            if kept["home"] is not None:
                os.environ["HOME"] = kept["home"]
        control("review Y r2 #3: with no $HOME and no account entry, the home a diagnostic masks is "
                "None rather than an exception",
                answered is None, f"{answered!r} {raised}")
        # And nothing at the module's TOP LEVEL may ask for a home, which is what made the failure
        # unreachable by any boundary. Asked of the module's own source, so the next edit that puts
        # such a call back fails here.
        def asks_for_a_home(node):
            return any(isinstance(inner, ast.Attribute) and inner.attr in ("home", "expanduser")
                       for inner in ast.walk(node))

        module = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
        top = [node for node in module.body
               if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
               and asks_for_a_home(node)]
        control("review Y r2 #3: and no statement of this module's top level asks for a home at all",
                not top, [f"line {node.lineno}" for node in top])
        # That the PRODUCTION path goes through the seam is asserted on the source, not by reverting
        # it: reverting an inline lookup back into `_account_home` has exactly one observable, a run
        # written into the owner's real home, which is the damage the fix exists to prevent. A text
        # assertion is decidable and costs nothing, so an edit that inlines the lookup again fails
        # here instead of in someone's home directory.
        resolver = inspect.getsource(_account_home)
        control("review Y r2 #1: the production resolver reaches the account home only through the "
                "seam a control can state",
                "_password_home()" in resolver and "getpwuid" not in resolver,
                resolver.splitlines()[-6:])
        # The production resolver itself, against the real database, reading and writing nothing:
        # the seam above is a control's instrument, and a seam nothing exercises for real is a
        # second implementation.
        control("review Y r2 #1: and the production resolver reads an absolute home from the account "
                "database itself",
                _account_home().is_absolute(), str(_account_home()))
        # And the fallback is the ACCOUNT's home, not `Path.home()`, which reads the same relative
        # $HOME back: this control wrote `relative-home/.local/state/...` into the checkout the
        # first time it ran, which is the defect it now holds shut.
        control("and nothing is written relative to the working directory",
                not (here / "relative-home").exists(),
                f"{sorted(q.name for q in (here / 'relative-home').rglob('*'))[:5]}"
                if (here / "relative-home").exists() else "")
        # The function's own answer, not the write's: a relative $HOME used to come straight back
        # through `pathlib.Path.home()`, and the only thing that then stopped the write was the
        # checkout being a protected root — which a packaged install does not have. So the default
        # is required to be ABSOLUTE at the source, from the account's own home.
        kept_home = os.environ.get("HOME")
        try:
            os.environ["HOME"] = "relative-home"      # the ambient value too, or the fallback hides
            with contextlib.redirect_stderr(io.StringIO()):
                resolved = default_out({"HOME": "relative-home"})
        finally:
            if kept_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = kept_home
        control("review Y #2: the default run root is absolute even when $HOME is not",
                resolved.is_absolute() and "relative-home" not in resolved.parts, str(resolved))
        code, err = no_out("declare", "--run-id", "y2-ordinary", "--from", str(declaration),
                           HOME=str(fake_home), XDG_STATE_HOME=None)
        control("and an ordinary environment still declares a run without being told a destination",
                code == 0 and (fake_home / ".local" / "state" / "agent-bios" / "distill" / "runs"
                               / "y2-ordinary").is_dir(), f"{code} {err[:300]}")
        control("and it is the XDG state directory's, not the data directory's",
                default_root == default_home / ".local" / "state" / "agent-bios" / "distill" / "runs"
                and str(default_state) not in str(default_root),
                f"{default_root} / state root {default_state}")
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
        code, err = cli("views", "--run-id", "r1")
        control("views (S2) refuses by name when the census it reads is not in the run",
                code == 1 and "INPUT_INVALID S1" in err, err)
        # the ruling of 2026-10-22: (d) reserves the cap the S3 call declares. WP-08 gave it a home in run.json
        # (`output_caps`), so the flag that stood in for it is gone: a caller cannot cut against another number
        code, err = cli("views", "--run-id", "r1", "--output-cap", "32000")
        control("views (S2) takes its output cap from run.json, not from a flag",
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

        # ---- R1#3: startup and this suite's own output cross the same boundary.
        #
        # A startup failure is a real process: the imports run before anything this file controls, so
        # the only way to observe them is to start the driver with the failure in place. The fixture
        # is `runlib/validate.py`'s own refusal — it exits during import when the jsonschema pin is
        # unreadable, interpolating the absolute pin path — reproduced in a COPY of the checkout, so
        # nothing in this one is touched and `validate.py`'s exits are left exactly as they are (other
        # modules and gates import it).
        startup_copy = scratch / "startup-checkout"
        inventory.checkout_copy(startup_copy)
        pin_file = startup_copy / "launch" / "provision-venv.sh"
        pin_file.write_text("JSONSCHEMA_PIN is not where this reads it from\n", encoding="utf-8")
        # The child's HOME is the fixture's, so "the owner's home" is a path this control owns and
        # the floor has something to mask. Without it the fixture sits under the system temp
        # directory, which is nobody's home, and the control would pass on a message that happened
        # to carry no home path rather than on one the floor projected.
        startup_env = {**os.environ, "HOME": str(scratch)}
        startup = entry.bounded(lambda: subprocess.Popen(
            [sys.executable,
             str(inventory.copied_member(startup_copy, "session-distill/distill.py")),
             "inventory", "--to", str(scratch / "startup-out"), "--no-state"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=startup_env,
            start_new_session=True), what="the copy's driver at startup")
        control("an unreadable pin at startup is a projected diagnostic, not an unprojected path",
                startup.returncode != 0 and "JSONSCHEMA_PIN_UNREADABLE" in startup.stderr
                and str(startup_copy) not in startup.stderr and "<HOME>" in startup.stderr,
                f"{startup.returncode} {startup.stdout[-200:]} {startup.stderr[-400:]}")
        control("and it wrote no artifact", not (scratch / "startup-out").exists(),
                "a refused startup still wrote its output directory")
        # The other half: when the FLOOR is what failed, there is nothing that can project a message,
        # so a fixed path-free line with a constant code stands instead of an exception text.
        (startup_copy / "learn" / "redact.py").write_text(
            "raise RuntimeError('the floor is broken')\n", encoding="utf-8")
        floorless = entry.bounded(lambda: subprocess.Popen(
            [sys.executable,
             str(inventory.copied_member(startup_copy, "session-distill/distill.py")),
             "inventory", "--to", str(scratch / "floorless-out"), "--no-state"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=startup_env,
            start_new_session=True), what="the copy's driver with no floor")
        control("a startup whose floor cannot load prints the fixed path-free line",
                floorless.returncode != 0 and floorless.stderr.strip() == STARTUP_WITHHELD,
                f"{floorless.returncode} {floorless.stderr[-300:]}")
        # Earlier in startup than both: the boundary module itself does not import, so only the
        # bootstrap at the top of this file can answer (r3 #2). Its line and its own code, and nothing
        # after them: without the exit the bootstrap falls through to `entry.WITHHELD`, and the
        # NameError's traceback carries the copy's paths under code 1. Inventory's suite asks this of
        # the copy too; this suite asks it of its own entry point, so removing the exit fails here.
        (startup_copy / "session-distill" / "runlib" / "entry.py").unlink()
        boundaryless = entry.bounded(lambda: subprocess.Popen(
            [sys.executable,
             str(inventory.copied_member(startup_copy, "session-distill/distill.py")),
             "inventory", "--to", str(scratch / "boundaryless-out"), "--no-state"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=startup_env,
            start_new_session=True), what="the copy's driver with no boundary")
        control("a startup whose boundary module cannot load prints the bootstrap's line, exits with its code "
                "and prints no traceback",
                boundaryless.returncode == STARTUP_UNAVAILABLE_CODE
                and boundaryless.stderr.strip() == STARTUP_UNAVAILABLE
                and "Traceback" not in boundaryless.stderr and str(startup_copy) not in boundaryless.stderr
                and not (scratch / "boundaryless-out").exists(),
                f"{boundaryless.returncode} {boundaryless.stderr[-300:]}")
        # This suite's own failure lines leave through `say`, so a planted path in one is masked. The
        # printer is called directly with rows this control builds, which is the only way to observe
        # a FAILING self-test without failing this one.
        planted_failure = io.StringIO()
        with contextlib.redirect_stderr(planted_failure):
            code = report([("a fixture control", f"read {HOME}/Documents/x")], [], "fixture --self-test")
        printed = planted_failure.getvalue()
        control("a self-test failure line carrying the owner's home path is projected",
                code == 1 and HOME not in printed and "<HOME>" in printed, f"{code} {printed!r}")

        # ---- N3: `main`'s OWN boundary, observed alone and in this process. A real child cannot
        # tell the two layers apart: `main`'s handler and the `entry.guarded` around `__main__` both
        # print a COMMAND_FAILED line, so moving the self-test back outside `main`'s `try` left every
        # control green — the outer layer caught the same failure and said the same thing. Here the
        # suite is replaced by one that raises a file error carrying a path, `main` is called
        # directly, and the failure has to be caught, named with the command, and projected without
        # the exception leaving `main` at all. The inner layer names the command; the outer does not.
        # What is patched is the SUITE'S SCRATCH, not the suite: `self_test_scratch` is this suite's
        # first operation, so an ordinary file failure there is the real shape — the inner run gets
        # no further and cannot recurse. This replaced a child process running the whole suite, which
        # is what made recursion possible at all (S4).
        held_scratch = inventory.self_test_scratch
        inner_stream, inner_code = io.StringIO(), "RAISED nothing"
        try:
            def _unwritable_scratch(*_args, **_kwargs):
                raise PermissionError(13, "Permission denied", f"{HOME}/Documents/fixture-scratch")
            inventory.self_test_scratch = _unwritable_scratch
            with contextlib.redirect_stderr(inner_stream):
                inner_code = main(["--self-test"])
        except BaseException as escaped:
            inner_code = f"RAISED {type(escaped).__name__}"
        finally:
            inventory.self_test_scratch = held_scratch
        inner_text = inner_stream.getvalue()
        control("a file failure inside the self-test is caught by main's own boundary, not the one outside it",
                inner_code == 1 and "COMMAND_FAILED self-test:" in inner_text
                and HOME not in inner_text and "<HOME>" in inner_text,
                f"{inner_code} {inner_text!r}")
        control("and the interpreter printed no traceback and no raw fixture path",
                "Traceback" not in inner_text and f"{HOME}/Documents" not in inner_text,
                f"{inner_text!r}")

        # The layer OUTSIDE `main` needs its own control, and the two layers are behaviourally
        # indistinguishable from a child process: everything `main` catches it also names, and what
        # only the outer layer catches — a `BaseException` that is not an `Exception`, a `SystemExit`
        # carrying a message — cannot be provoked through the CLI from outside. So the layer is
        # asked in two parts: what it does, in this process, and that `__main__` is wired to it.
        exit_stream = io.StringIO()
        exit_code = entry.guarded(lambda: (_ for _ in ()).throw(SystemExit(f"{HOME}/Documents/x")),
                                  home=HOME, stream=exit_stream)
        exit_text = exit_stream.getvalue()
        control("the layer outside main projects an exit message main never sees",
                exit_code == 2 and HOME not in exit_text and "<HOME>" in exit_text,
                f"{exit_code} {exit_text!r}")
        entry_calls = [node for node in ast.walk(ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8")))
                       if isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'"
                       for node in ast.walk(node) if isinstance(node, ast.Call)
                       and ast.unparse(node.func) == "entry.guarded"]
        control("and this entry point is wired to that layer rather than calling main itself",
                len(entry_calls) == 1 and "main" in ast.unparse(entry_calls[0]),
                f"{[ast.unparse(call) for call in entry_calls]}")

        # ---- R2#7, in this process. The judged parent is what decides where this suite writes,
        # and both halves of it are decidable here: with a fixture `TMPDIR` inside a fixture host
        # home the one scratch function REFUSES by name and creates nothing, and with an ordinary
        # one the directory it returns has that parent. Observing this used to take a child running
        # the whole suite, with `--self-test` in its argv — which is how one revert recursed 594
        # deep. No child of this suite runs a suite any more (S4).
        fixture_home = scratch / "entry-fixture-home"
        guarded_tmp = fixture_home / ".claude" / "tmp"
        guarded_tmp.mkdir(parents=True)
        guarded_env = {"HOME": str(fixture_home), "CLAUDE_CONFIG_DIR": str(fixture_home / ".claude"),
                       "TMPDIR": str(guarded_tmp), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        refused_scratch = ""
        try:
            with inventory.self_test_scratch("wp07-refused-", environ=guarded_env):
                refused_scratch = "the judged parent accepted a location inside a host home"
        except Exception as exc:
            refused_scratch = f"{type(exc).__name__}: {exc}"
        control("the driver's self-test passes the judged parent to TemporaryDirectory",
                "PROTECTED_OVERLAP" in refused_scratch, refused_scratch[:300])
        control("and nothing was created in the location the judgement refused",
                not any(guarded_tmp.iterdir()),
                f"{sorted(path.name for path in guarded_tmp.iterdir())}")
        # The other half: the fixtures really do land under the parent the rule chose. This is what
        # the child's own report line used to say from outside.
        open_tmp = scratch / "open-tmp"
        open_tmp.mkdir()
        open_env = {**guarded_env, "TMPDIR": str(open_tmp)}
        with inventory.self_test_scratch("wp07-accepted-", environ=open_env) as nested_scratch:
            placed = (nested_scratch.parent, nested_scratch.is_dir())
        control("and the suite's own fixtures are created under that parent, nowhere else",
                placed == (inventory.scratch_parent(open_env), True)
                and inventory.scratch_parent(open_env) == open_tmp,
                f"{inventory.masked(placed[0])} vs {inventory.masked(open_tmp)} created={placed[1]}")
        # ---- the child bound ends a TREE, not a process. Returning as soon as the leader exited
        # left every descendant running, and a descendant holding the pipe is what kept a runaway
        # filling the disk after each kill (r3 #1). Both fixtures are FINITE — three seconds and
        # gone — so a cleanup defect here ends on its own instead of leaving a process behind.
        held_group = entry.bounded(lambda: subprocess.Popen(
            [sys.executable, "-c", IGNORES_TERM], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True), timeout=0.5, what="a TERM-ignoring descendant")
        descendant = [int(line.split()[1]) for line in held_group.stdout.splitlines()
                      if line.startswith("DESCENDANT")]
        control("a bound reached with a descendant holding the pipe is a named failure, not a wait",
                held_group.returncode == entry.TIMED_OUT
                and "CHILD_TIMEOUT" in held_group.stderr, f"{held_group.returncode} {held_group.stderr!r}")
        def process_alive(pid):
            """Whether THIS PROCESS still stands. The descendant leads no group of its own, so
            `group_alive` asked `killpg` about a group that never existed and read the
            `ProcessLookupError` as "gone" whether the descendant lived or not — the control passed
            over a removed kill (r4 R2). It is reparented and reaped by init when its leader dies, so
            a pid that is gone raises here rather than lingering as a zombie."""
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                return False
            except PermissionError:      # it exists and is not ours to signal
                return True

        control("and the descendant that outlived its leader is gone afterwards",
                len(descendant) == 1 and not process_alive(descendant[0]),
                f"{descendant} alive={[process_alive(pid) for pid in descendant]} {held_group.stdout!r}")
        control("and that pid was really a process this control could have seen alive",
                len(descendant) == 1 and descendant[0] > 1, f"{descendant}")
        # ---- r4 R2: that SIGTERM and that SIGKILL, asked of `end_group` ALONE. No process, no
        # fixture and no `finish_group`: the leader reports itself exited the moment the SIGTERM is
        # recorded, which is the shape the unconditional SIGKILL exists for — returning as soon as
        # the leader exited left every descendant running (r3 #1). A control that reads a fixture's
        # aftermath cannot tell a kill that fired from a lifetime that ran out.
        class _ExitsOnTerm:
            """A leader that is not a process: it reports running until the group is signalled, and
            exited after. `end_group` reads only `poll`, `pid` and `kill`."""
            args, returncode, pid = ("a leader that exits on SIGTERM",), None, 4322

            def poll(self):
                return 0 if group_signals else None

            def kill(self):
                group_signals.append((self.pid, "kill()"))

        held_killpg, group_signals = os.killpg, []
        try:
            os.killpg = lambda pgid, sig: group_signals.append((pgid, sig))
            end_note = entry.end_group(_ExitsOnTerm(), 4322)
        finally:
            os.killpg = held_killpg
        control("end_group signals SIGTERM and then SIGKILL even though the leader exited after the SIGTERM",
                group_signals == [(4322, signal.SIGTERM), (4322, signal.SIGKILL)] and end_note == "",
                f"{group_signals} note={end_note!r}")
        control("and os.killpg is the real one again after that control",
                os.killpg is held_killpg, f"{os.killpg}")
        # The same, for a leader that never exits: the second signal still goes, and nothing waits on
        # the group emptying — that is `finish_group`'s question, not this one's.
        held_killpg, standing_signals = os.killpg, []

        class _NeverExits(_ExitsOnTerm):
            def poll(self):
                return None

        try:
            os.killpg = lambda pgid, sig: standing_signals.append((pgid, sig))
            # It waits out its own eight quarter-second rounds per signal, which is the real
            # behaviour and costs four seconds; nothing here is a process, so nothing is left behind.
            standing_note = entry.end_group(_NeverExits(), 4322)
        finally:
            os.killpg = held_killpg
        control("and a leader that never exits is sent both signals too, without waiting for the group to empty",
                standing_signals == [(4322, signal.SIGTERM), (4322, signal.SIGKILL)] and standing_note == "",
                f"{standing_signals} note={standing_note!r}")

        # ---- the group-end ROUND, which S4 added and no control read: with `for _ in range(rounds)`
        # emptied, every suite of this package stayed green (S8b's probe). Driven IN THIS PROCESS with
        # a counting probe in place of `entry.group_alive` and a counting `os.killpg`, so no process
        # and no waiting on one is involved. What the round says is that the group is SIGNALLED once
        # per round until it is empty — "it returns False" is not the rule: a group that never empties
        # gives False with no rounds at all, which is exactly what the emptied loop does.
        class _NeverAnswers:
            """A child that never answers, and is not a process. `bounded`'s timeout path reads only
            these members; `poll` reports an exited leader so `end_group` waits on nothing."""
            args, returncode, pid = ("a child that never answers",), None, 4321

            def communicate(self, timeout=None):
                raise subprocess.TimeoutExpired(self.args, timeout)

            def kill(self):
                pass

            def poll(self):
                return 0

        held_alive, held_killpg, held_getpgid = entry.group_alive, os.killpg, os.getpgid
        held_finish, asked, signalled = entry.finish_group, [], []
        try:
            entry.group_alive = lambda pgid: (asked.append(pgid), True)[1]
            os.killpg = lambda pgid, sig: signalled.append((pgid, sig))
            standing = entry.finish_group(4321, rounds=2)
            standing_kills, standing_asked = list(signalled), list(asked)
            asked.clear()
            signalled.clear()
            answers = [True, False]
            entry.group_alive = lambda pgid: (asked.append(pgid),
                                              answers.pop(0) if answers else False)[1]
            cleared, cleared_asked = entry.finish_group(4321, rounds=5), None
            cleared_asked = list(asked)
            # The NAME the round's failure carries belongs to `bounded`, which is the round's only
            # caller. Reached with the same probe and a two-round bound, so this leg waits on nothing
            # either; the round logic itself is the real one.
            entry.group_alive = lambda pgid: (asked.append(pgid), True)[1]
            entry.finish_group = lambda pgid, rounds=2: held_finish(pgid, rounds=rounds)
            os.getpgid = lambda _pid: 4321
            never = entry.bounded(_NeverAnswers, timeout=0.01, what="a child that never answers")
        finally:
            entry.group_alive, os.killpg, os.getpgid = held_alive, held_killpg, held_getpgid
            entry.finish_group = held_finish
        control("the group-end round signals the group once per round until it is empty",
                standing is False and len(standing_kills) == 2
                and all(sig == signal.SIGKILL for _pgid, sig in standing_kills)
                and cleared is True and len(cleared_asked) >= 2,
                f"standing={standing} kills={standing_kills} asked={standing_asked}/{cleared_asked} "
                f"cleared={cleared}")
        control("and every swap this control made is back, so no later control runs against a fake",
                (entry.group_alive, os.killpg, os.getpgid, entry.finish_group)
                == (held_alive, held_killpg, held_getpgid, held_finish),
                f"{entry.group_alive} {os.killpg} {os.getpgid} {entry.finish_group}")
        control("and a group that never empties is named, not waited on",
                never.returncode == entry.TIMED_OUT
                and "CHILD_CLEANUP_UNFINISHED" in never.stderr
                and "still holds a process after" in never.stderr,
                f"{never.returncode} {never.stderr!r}")

        # Ownership not established is child-only. `os.getpgid` refusing used to fall back to the
        # child's pid as the group id, which points `killpg` at whatever group the child is in — this
        # process's own, when the child was started without a session (G1).
        held_getpgid, held_killpg, signalled = os.getpgid, os.killpg, []
        try:
            os.getpgid = lambda _pid: (_ for _ in ()).throw(OSError(3, "No such process"))
            os.killpg = lambda pgid, sig: signalled.append((pgid, sig))
            unowned = entry.bounded(lambda: subprocess.Popen(
                [sys.executable, "-c", SLEEPS_BRIEFLY], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, start_new_session=True),
                timeout=0.5, what="a child whose group cannot be established")
        finally:
            os.getpgid, os.killpg = held_getpgid, held_killpg
        control("a child whose group cannot be established is ended alone, with no group signalled",
                signalled == [] and unowned.returncode == entry.TIMED_OUT
                and "could not be established" in unowned.stderr,
                f"{signalled} {unowned.returncode} {unowned.stderr!r}")

        # ---- S8f: default-deny at spawn. A child that leads no group of its own is one no bound
        # here can end, so it is refused rather than recorded — r8's W6 showed the shape, where the
        # shell was ended and the tree it had started was not, and only a control written for that
        # one fixture noticed. `os.killpg` is a recorder, as in the branch above, so "no group was
        # signalled" is READ and not assumed; the child is finite either way.
        started, held_killpg, signalled_group = [], os.killpg, []
        try:
            os.killpg = lambda pgid, sig: signalled_group.append((pgid, sig))
            no_session = entry.bounded(lambda: started.append(subprocess.Popen(
                [sys.executable, "-c", SLEEPS_BRIEFLY], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True)) or started[-1],
                timeout=20, what="a child without a session of its own")
        finally:
            os.killpg = held_killpg
        control("a child started without a session of its own is refused by name, and no group is signalled",
                no_session.returncode == entry.NOT_GROUP_LEADER
                and "CHILD_NOT_GROUP_LEADER" in no_session.stderr and signalled_group == [],
                f"{no_session.returncode} {no_session.stderr!r} {signalled_group}")
        control("and that child is gone, ended alone rather than left to the bound",
                len(started) == 1 and started[0].poll() is not None,
                f"{[proc.poll() for proc in started]}")
        control("and os.killpg is the real one again, so no later control reads a recorder",
                os.killpg is held_killpg, f"{os.killpg}")

        # The ordinary shape: the leader exits first and a descendant holds the pipe for a moment.
        # The bound must not fire, and the leader's own code must come back.
        early = entry.bounded(lambda: subprocess.Popen(
            [sys.executable, "-c", LEADER_FIRST], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True), timeout=20, what="a leader that exits first")
        control("a leader that exits before its descendant still returns its own result",
                early.returncode == 0 and "LEADER DONE" in early.stdout
                and "CHILD_TIMEOUT" not in early.stderr,
                f"{early.returncode} {early.stdout!r} {early.stderr!r}")

        # A suite inside a suite inside a suite is the recursion, and the depth is counted in this
        # process rather than in an environment a child would inherit. Depth 2 is this file's own
        # inner run above and stays allowed; depth 3 is refused by name.
        held_depth = inventory.SELF_TEST_DEPTH[0]
        too_deep = ""
        try:
            inventory.SELF_TEST_DEPTH[0] = inventory.SELF_TEST_DEPTH_LIMIT
            with inventory.self_test_scratch("wp07-too-deep-"):
                too_deep = "a third suite was given a scratch directory"
        except Exception as exc:
            too_deep = f"{type(exc).__name__}: {exc}"
        finally:
            inventory.SELF_TEST_DEPTH[0] = held_depth
        control("a suite starting inside a suite at the depth limit is refused by name",
                "SELF_TEST_TOO_DEEP" in too_deep, too_deep[:200])

        # ---- r4 R1: THIS runner's own abort handlers, driven. `main`'s handled-refusal handler said
        # the refusal and returned, so a refusal raised inside the suite took every collected failure
        # line with it; only the unexpected-failure handler published. The claim was read out of the
        # source in inventory's suite, where any handler of a file reaching the call satisfied it.
        # The handler is exercised here instead, through `main` with a planted command handler.
        held_handler = globals()["cmd_census"]
        for kind, planted_exc in (("a refusal", Refused("a planted refusal")),
                                  ("a stage lock held elsewhere", stagelock.Locked("a planted lock")),
                                  ("an escaped path", stagelock.Escaped("a planted escape")),
                                  ("an unexpected failure", RuntimeError("a planted failure"))):
            planted_row = ("a planted suite --self-test", ["a failure an abort must not swallow"])
            entry.SELF_TEST_COLLECTED.append(planted_row)
            buffer = io.StringIO()
            try:
                def raising_handler(_args, _exc=planted_exc):
                    raise _exc

                globals()["cmd_census"] = raising_handler
                held_stderr, sys.stderr = sys.stderr, buffer
                try:
                    code = main(["census"])
                finally:
                    sys.stderr = held_stderr
            finally:
                globals()["cmd_census"] = held_handler
                entry.SELF_TEST_COLLECTED.remove(planted_row)
            control(f"main publishes the failures the suite collected when the command raises {kind}",
                    "a failure an abort must not swallow" in buffer.getvalue() and code == 1,
                    f"code={code} out={buffer.getvalue()[:300]!r}")
        control("and the real census handler is back, so no later control runs a raiser",
                globals()["cmd_census"] is held_handler, f"{globals()['cmd_census']}")
        clean_buffer = io.StringIO()
        held_stderr, sys.stderr = sys.stderr, clean_buffer
        try:
            entry.SELF_TEST_COLLECTED.append(("a planted suite --self-test", ["a failure nothing aborted"]))
            try:
                main(["--help"])
            except SystemExit:
                pass
        finally:
            sys.stderr = held_stderr
            entry.SELF_TEST_COLLECTED.pop()
        control("and a command that does not abort publishes nothing of what a suite collected",
                "a failure nothing aborted" not in clean_buffer.getvalue(),
                f"{clean_buffer.getvalue()[:200]!r}")

        # ---- Stop at the first failure (`entry.STOP_AT_FIRST_FAILURE`). A planted miniature suite in
        # this process, collecting through `entry.self_test_failures` and run through the same
        # `entry.guarded` the real suites run inside: two passing controls around two failing ones.
        # This suite's own row is set aside while it runs, so an abort of the miniature publishes only
        # the miniature's lines, and the variable is put back as this suite found it.
        def miniature(results, outcomes=(True, False, False, True), nested=None, publish=None, add="append"):
            def suite():
                mini_failures, mini_ran = entry.self_test_failures("a planted suite --self-test", publish), []
                results["list"] = type(mini_failures).__name__
                entry.SELF_TEST_COLLECTED.append(("a planted suite --self-test", mini_failures))
                if nested is not None:
                    results["nested"] = nested()
                for at, ok in enumerate(outcomes):
                    mini_ran.append(f"planted control {at}")
                    planted = [] if ok else [(f"planted control {at}", "planted to fail")]
                    if add == "+=":
                        # Every control adds, a passing one nothing, as projection's `+=` of a
                        # comprehension does: an empty addition must not stop the suite.
                        mini_failures += planted
                    elif planted:
                        mini_failures.append(planted[0])
                results["ran"] = len(mini_ran)
                entry.SELF_TEST_COLLECTED.remove(("a planted suite --self-test", mini_failures))
                for name, detail in mini_failures:
                    entry.emit(entry.failure_text("a planted suite --self-test", name, detail), sys.stderr)
                if mini_failures:
                    return 1
                say(f"a planted suite --self-test: OK ({len(mini_ran)} controls)")
                return 0
            return suite

        def run_miniature(stop, **kwargs):
            results, buffer = {}, io.StringIO()
            held_rows, held_mode = entry.SELF_TEST_COLLECTED[:], os.environ.get(entry.STOP_AT_FIRST_FAILURE)
            entry.SELF_TEST_COLLECTED[:] = []
            if stop:
                os.environ[entry.STOP_AT_FIRST_FAILURE] = "1"
            else:
                os.environ.pop(entry.STOP_AT_FIRST_FAILURE, None)
            try:
                with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                    results["code"] = entry.guarded(miniature(results, **kwargs), stream=buffer)
                results["left"] = os.environ.get(entry.STOP_AT_FIRST_FAILURE)
            finally:
                entry.SELF_TEST_COLLECTED[:] = held_rows
                if held_mode is None:
                    os.environ.pop(entry.STOP_AT_FIRST_FAILURE, None)
                else:
                    os.environ[entry.STOP_AT_FIRST_FAILURE] = held_mode
            return results, buffer.getvalue()

        stopped, stopped_text = run_miniature(True)
        control("stop at the first failure: set, a suite leaves right after its first failure with a non-zero "
                "exit, that failure's line and no later one",
                stopped.get("code") == 1 and stopped.get("list") == "FailuresThatStop"
                and "a planted suite --self-test [FAIL] planted control 1:" in stopped_text
                and "planted control 2" not in stopped_text and "ran" not in stopped
                and "stopped at its first failure" in stopped_text and stopped.get("left") is None,
                f"{stopped} {stopped_text[:300]!r}")
        clean_run, clean_text = run_miniature(True, outcomes=(True, True, True, True), add="+=")
        control("stop at the first failure: set, a suite with no failure runs to its end with its OK line and "
                "count, though each control added an empty list",
                clean_run.get("code") == 0 and clean_run.get("ran") == 4
                and "a planted suite --self-test: OK (4 controls)" in clean_text and "stopped" not in clean_text,
                f"{clean_run} {clean_text[:300]!r}")
        full, full_text = run_miniature(False)
        control("stop at the first failure: unset, a suite with an early failure runs on and reports every failure",
                full.get("code") == 1 and full.get("ran") == 4 and full.get("list") == "list"
                and "[FAIL] planted control 1:" in full_text and "[FAIL] planted control 2:" in full_text
                and "stopped" not in full_text, f"{full} {full_text[:300]!r}")
        inner = {}
        outer, outer_text = run_miniature(True, nested=lambda: (miniature(inner)(), inner)[1])
        control("stop at the first failure: a suite started inside a stopping suite is not stopped, it runs in full",
                outer.get("code") == 1 and outer.get("list") == "FailuresThatStop" and inner.get("list") == "list"
                and inner.get("ran") == 4, f"outer={outer} inner={inner} {outer_text[:300]!r}")
        added, added_text = run_miniature(True, add="+=")
        control("stop at the first failure: set, a failure added with += stops the suite as an append does",
                added.get("code") == 1 and "[FAIL] planted control 1:" in added_text
                and "planted control 2" not in added_text and "ran" not in added, f"{added} {added_text[:300]!r}")
        printed = []
        own, own_text = run_miniature(True, publish=lambda failure: printed.append(failure))
        control("stop at the first failure: a suite outside the shared boundary is handed its first failure to "
                "print before it leaves",
                own.get("code") == 1 and printed == [("planted control 1", "planted to fail")],
                f"{own} printed={printed}")

    reporting.append("the report begins here")
    return report(failures, ran)


def report(failures, ran, label="distill --self-test"):
    """A self-test's own diagnostics, through the SAME printer every other line leaves by.

    A failure line carries whatever the control put in it — a path, a fixture's planted text — and it
    was printed directly, so a self-test could publish what every other route is checked for (R1#3).
    It goes to stderr because it is a diagnostic; the per-control listing stays on stdout."""
    if (label, failures) in entry.SELF_TEST_COLLECTED:
        entry.SELF_TEST_COLLECTED.remove((label, failures))
    for name, detail in failures:
        # Name and detail projected separately when the joined line would be withheld whole, so a
        # failing control cannot lose its own name (r4 R8).
        entry.emit(entry.failure_text(label, name, detail), sys.stderr)
    if failures:
        return 1
    for name in ran:
        say(f"  control {name}")
    say(f"{label}: OK ({len(ran)} controls)")
    return 0


if __name__ == "__main__":
    # Outside `main` there is still a boundary: an exception from `build_parser().parse_args` itself,
    # or a `BaseException` no handler above names, is described through the floor rather than by the
    # interpreter.
    sys.exit(entry.guarded(main, sys.argv[1:], HOME))
