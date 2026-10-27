#!/usr/bin/env python3
"""The dispatch supervisor (design §13.2, §13.3; plan WP-02): the one code path every live model
call takes, and the only module in the driver's import closure that starts a runner or a host
binary.

Every agent-backed dispatch is an episode (design §13.2). Before it starts, `reserve` takes the
call's calibrated cost from the stage's remaining budget in one critical section under the
supervisor's lock, so two requests can never both be admitted against one balance: the 95th
percentile of the measured cost of its class (stage, seat, case type), or — for a class with
fewer than CALIBRATION_MIN_SAMPLES measured calls — the nearest probe measurement (SEEDS) times
usage.SAFETY_FACTOR, marked `calibration: provisional` and admitted only in a calibration
tranche at concurrency one (S-15). The budget is the one run.json declares now, read through
records.declaration_state, so an amendment is recorded before anything is spent against it and a
hand edit is refused. A reservation that does not fit records the item `not_done`.

`call` then refuses, before anything is written, a call without its reservation or without both
caps, a call to a provider whose breaker is open or a reservation deferred when it opened (the
item recorded `deferred`), a call in a stopped run, a packet the linter rejects, a seat or
window outside its declaration, and a runner its realization does not admit: a fake or custom
runner runs only under realization `golden`, the pinned runner only under `live`. Admission is
decided under the breaker's lock and the supervisor's, held through the launch, so a provider
signal or a run stop recorded by any running call either precedes it (refused) or follows the
launch. It runs the runner with the packet on stdin and follows the call with the live monitor
(both caps at every stream event and transcript record; a structured provider signal opens the
breaker the moment it is read, and the provider's reserved work that has not started is
recorded deferred). At either cap it stops the call (stop.stop_tree: freeze until a fresh
listing shows the whole tree stopped, kill, verify; recorded `budget_stopped`); every reader of
the runner's pipes is drained to its end — never cut short by a per-reader timeout — before the stop is
recorded or anything is accounted, so a cap the monitor trips late still stops what is left of
the tree, and the outgoing-request boundary is checked against the verified freeze on the
drained ledger, its verdict one value on the stopped record (monitor.boundary_verdict). Once the
root has exited, a pipe still open past drain_deadline_s (DRAIN_DEADLINE_S) stops the remaining
tree as a cap would, and the drain waits at most another drain_deadline_s: the call is recorded
`drain_unfinished`, its usage unreconciled and its boundary STOP_BOUNDARY_UNVERIFIED, whoever held
the pipe, whether or not a cap tripped (the cap's evidence is kept as the record's `cap`) and
whatever violation was observed (kept in its problems). The runner is killed after every stop and
reaped only once every stop of the call is done, so its group id stays provably its own for each;
no wait on it or its pipes is unbounded. usage.json is written before the call's cell (its temporary homes) is deleted; the
receipt is written through the launcher's --emit-receipt with the evidence the gate recomputes;
the reservation is settled. A view-window call (S3 reading and its expansion windows, and only
those) whose observed input passes the bound stops the run (INPUT_BOUND_EXCEEDED; amendment
record 2026-10-21T0026--cc0498f--input-bound-amendment.md). `item` adds the gate and design
§3.2's one corrective retry, never after a provider signal: the item that met the signal is
recorded deferred with its attempts, as `<stage>:<item>`.

The runner contract (what WP-03's `claude-run --profile hermetic` and WP-04's `codex-run`
honour): the packet on stdin; the final result on stdout; REVIEW_CAPTURE_DIR is the call's
capture/ directory, where the runner writes host.json at exit (profile, flag-set hash, working
directory and its pre-call listing, session or thread id, effective context, and for Claude the
recorded requests and responses) and, for Claude, appends the stream-json events to
stream.jsonl as they arrive; DISTILL_CELL is the call's cell, `{home,config,cwd}`, which the
supervisor creates and deletes, so a runner never deletes it; codex-run's capture writes the
call's events.jsonl, frames.jsonl, host.json and usage.json through its helper (WP-04), which the
dispatcher never replaces, and passes the trace (RUST_LOG=CODEX_TRACE) on stderr, which the monitor
reads live for the caps and the boundary and reduces into capture/frames.jsonl only where the runner
wrote none. REVIEW_CALL_ID (and DISTILL_CALL_ID) name the call; the versioned host binary
seats.json pins reaches claude-run as --claude-bin with --host-version, and codex-run as
CODEX_RUN_BIN with CODEX_RUN_VERSION; claude-run's token comes from CLAUDE_RUN_TOKEN_FILE in the
caller's environment, a path never read here. Nothing of the runner's stderr is stored but an
adapter's named refusal on a nonzero exit (ADAPTER_CODES), recorded as the call's
`runner_refused` and the item's outcome. The dispatcher writes the call's receipt; a receipt the runner writes
for itself (REVIEW_RECEIPT_DIR points into capture/runner-receipts/) is evidence in the capture,
never the call's receipt (plan addendum 2026-10-21T0630--0e0d27e--plan-addendum-wp02.md).

Refused by name: RESERVATION_MISSING, CAP_MISSING, PROVIDER_DEFERRED, PACKET_REFUSED (with the
linter's codes), CALIBRATION_PROVISIONAL, CALIBRATION_SERIAL, BUDGET_UNDECLARED, BUDGET_EXHAUSTED
(the item recorded not_done), INPUT_BOUND_EXCEEDED and RUN_STOPPED, DRIVER_PART_UNCOUNTED,
DRIVER_PART_LENGTH_CONFLICT, APPENDED_PROMPT_PATH_FORM, APPENDED_PROMPT_UNDELIVERABLE,
CAP_UNDELIVERABLE, USAGE_INCOMPLETE, CAPACITY_UNDECLARED, CALL_EXISTS,
USAGE_UNCAPTURED, RECEIPT_MISSING, SEAT_UNPINNED, ALLOWANCE_UNMEASURED, ALLOWANCE_MISMATCH,
WINDOW_OVER_BOUND, RUNNER_REALIZATION_MISMATCH, USE_REFUSED, CAP_UNDECLARED. CONTRACT names the sections; the self-test
derives this set from the source and holds it, and this list, against its own cited copy. The
closure check (`closure_violations`) names DISPATCH_OUTSIDE_SUPERVISOR, DISPATCH_UNRESOLVED,
CLOSURE_IMPORTS_OUT_OF_SCOPE, DYNAMIC_LOAD_UNDECLARED and INVENTORY_STALE.

  dispatch.py --self-test
"""
import ast
import contextlib
import hashlib
import inspect
import json
import math
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time

if __package__ in (None, ""):  # run as a script: put session-distill/ on the import path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from runlib import breaker as breakers
from runlib import bound, gate, packet as packets, receipts, records, stagelock, stop
# Under a name of its own: `entry` is a LOCAL name in this file — the judge's own site rows — and the
# boundary is only read for the collected-failure publication an abort would otherwise swallow.
from runlib import entry as boundary
from runlib import monitor as monitors
from runlib import usage as usages
from runlib.records import Refused

REPO = pathlib.Path(__file__).resolve().parents[2]
RUNNERS = {"claude": REPO / "wrappers" / "claude-run.sh", "codex": REPO / "wrappers" / "codex-run.sh"}
USES = ("judge", "producing", "authoring")  # claude-run's call profiles (plan WP-03); producing is Claude's alone
# the refusals each adapter names on a nonzero exit: before anything is sent (codex-run's capture
# and its overrides; claude-run's pinned host, its cell and its read root), and claude-run's unreadable
# transcript (exit 70). The self-test derives each set from the adapter's own source and holds this to it.
ADAPTER_CODES = {"codex": ("HOST_VERSION_MISMATCH", "CONTEXT_EVIDENCE_MISSING", "CODEX_PROFILE_UNSUPPORTED",
                           "CODEX_INSTRUCTION_OVERRIDE_UNSUPPORTED", "CODEX_INSTRUCTION_OVERRIDE_REPEATED"),
                 "claude": ("HOST_VERSION_MISMATCH", "HOST_BINARY_UNPINNED", "CELL_UNDER_HOME", "CELL_OUTSIDE_ROOT",
                            "CELL_ROOT_OWNER", "CELL_ROOT_MODE", "CELL_ANCESTOR_SURFACE", "CELL_CWD_MISSING",
                            "READ_ROOT_MISMATCH", "TRANSCRIPT_UNREADABLE")}
ADAPTER_REFUSAL = {host: re.compile(rb"^" + host.encode() + rb"-run: (" + "|".join(codes).encode() + rb")\b[^\n]{0,400}")
                   for host, codes in ADAPTER_CODES.items()}
# the channels monitor.CodexFeed reads; the retry warnings are what HTTPS attempt coverage reconciles (design §3.2)
CODEX_TRACE = "tungstenite::protocol=trace,codex_otel.log_only=info,codex_core::responses_retry=warn"
CODEX_CHANNELS = ("frames", "otel", "responses_retry")
REALIZATIONS = ("live", "golden")  # what a supervisor may declare; a replay is the gate's, never a dispatch
CONTRACT = {"$comment": "design §13.2 (reservation, both caps, the breaker, the stop, not done) and §13.3 (usage), "
                        "plan WP-02 (dispatch.call's refusals, S-15), the amendment record "
                        "2026-10-21T0026--cc0498f--input-bound-amendment.md (the window bound): the Supervisor's "
                        "refusals and item outcomes", "predicate": "Supervisor"}
LOCK_WAIT_S = 30
# the stop's own wait on the declaration lock, read from the module at each stop so a control can
# shorten it; production never changes it (BC#0)
STOP_LOCK_WAIT_S = LOCK_WAIT_S
DRAIN_POLL_S = 0.05  # how often a drain still waiting on a reader looks for a cap the monitor tripped meanwhile
# How long readers may stay open once the runner's root has exited: a process holding its pipes past
# this escaped the tree, outside the stop guarantee (design §13.2) — recorded, never waited on.
DRAIN_DEADLINE_S = 30.0
CALIBRATION_MIN_SAMPLES = 5  # a reading: below five measured calls a 95th percentile is the maximum of too few
# The nearest probe measurement of one single-turn hermetic call per host (S-15); a provisional
# reservation is this times usage.SAFETY_FACTOR.
SEEDS = {
    "claude": {"tokens": 3216, "source": "distill-probes-20261020/claude-runner/captures/acc-clean-001 "
                                         "(replay fixture claude-runner/acc-clean-001/usage.json, all four token kinds)"},
    "codex": {"tokens": 25424, "source": "distill-probes-20261020/codex-runner/captures/acc-clean-002/capture.json "
                                        "usage.measured_totals.total_tokens"},
}
# Executors outside the redesign: the closure may import none of them (plan WP-02 done-when 6).
OUT_OF_SCOPE = (
    {"path": "session-distill/screen-codex.py", "reason": "the legacy screening pass, which starts codex-run itself",
     "retires": "deleted at the WP-22 cutover"},
    {"path": "benchmarks/tier/live.py", "reason": "tier experiments, outside the redesign",
     "retires": "when tier experiments move under this supervisor or are deleted"},
)
# Dynamic loads the closure may make, each with its reason; `trace` says whether the loaded file
# joins the closure. The launcher is shipped code whose host launches are its CLI's, and the only
# CLI use in the closure is dispatch.py's --emit-receipt (and receipts.py's self-test of it).
DYNAMIC_LOADS = (
    {"site": "session-distill/runlib/receipts.py", "path": "launch/agent-launch.py", "trace": False,
     "reason": "the receipt grammar (_raw_receipt_reason) has one owner, the launcher"},
    {"site": "session-distill/runlib/gate.py", "path": "wrappers/codex_frame_filter.py", "trace": False,
     "reason": "the Codex capture's one owner, loaded by its literal repo path (FRAME_OWNER) for its pure readers "
               "(gate.FRAME_READERS: responses, completions, join, attempts), held by the gate's self-test; read, not "
               "traced: its context command starts codex (app-server, debug prompt-input), which the gate never calls"},
    {"site": "session-distill/runlib/gate.py", "path": "wrappers/claude_hermetic_evidence.py", "trace": False,
     "reason": "the Claude observer's one owner, loaded by its literal repo path (OBSERVER_OWNER) for the one pure "
               "function the declared-instruction hash is computed with (gate.OBSERVER_READERS: norm_sha256), so the "
               "rendering rule is imported and never copied (BC#2); read, not traced: the rest of that file renders a "
               "capture and runs no host"},
    {"site": "session-distill/runlib/records.py", "path": "wrappers/jsonl_lines.py", "trace": True,
     "reason": "the one JSONL splitter, shipped, loaded by its literal repo path (_load_jsonl_lines) so runlib's "
               "readers use it, never a copy; it imports nothing and runs nothing"},
    {"site": "session-distill/runlib/inventory.py", "path": "compose/instructions_catalog.py", "trace": False,
     "reason": "the catalog's one owner, loaded by the path of the checkout being inventoried (catalog_carriers) so "
               "S2 splits the items the compiler would compile, never a second reading of them; read, not traced: "
               "the loader itself runs nothing, and the one module it imports (assemble.guide_members, a pure "
               "reader) keeps its executors in the installer's main() \u2014 the domain gate it runs as a script at "
               "compose/assemble.py:823 \u2014 which load_catalog never reaches"},
    {"site": "session-distill/runlib/inventory.py", "path": "compose/instructions_store.py", "trace": False,
     "reason": "the overlay resolver's one owner, loaded by the checkout's path (store_module) for the four readers "
               "the inventory calls over frozen copies of the owner's state (_runtime_state, _user_state, "
               "_effective_items, verify_snapshot), none of which locks, recovers or writes; read, not traced: the "
               "store runs no executor at all, and its plan, apply and install paths resolve an importer by a module "
               "name no trace can read, which the inventory never reaches"},
    {"site": "session-distill/runlib/inventory.py", "path": "compose/instructions_install.py", "trace": False,
     "reason": "the host configuration homes have one owner and it ships: `host_homes` loads the installer by the "
               "checkout's path (install_module) and reads `claude_root` and `codex_root` off a constructed "
               "`InstructionsInstaller`, so `CLAUDE_CONFIG_DIR` and `CODEX_HOME` are resolved by the code that owns "
               "that rule rather than by a second copy of it here (R2#1); read, not traced: constructing the "
               "installer resolves paths and nothing else, and the inventory calls no other member of it"},
    {"site": "session-distill/runlib/projection.py", "path": "learn/redact.py", "trace": True,
     "reason": "the secret floor's owner, loaded by its literal repo path (_load_floor) so its patterns are imported, "
               "never copied; it imports re and sys only and runs nothing"},
    {"site": "session-distill/runlib/ledger.py", "path": "session-distill/migrate-ledger.py", "trace": True,
     "reason": "the schema-1 migrator, loaded by its literal path beside the module (MIGRATOR) to compare a schema-1 "
               "base with a schema-2 head; its one executor is git ls-files"},
    {"site": "session-distill/runlib/ledger.py", "path": "gates/check-global-file.py", "trace": False,
     "reason": "design §13.1's author-side gate, loaded by its literal repo path (GATE_READERS) for its git readers, "
               "one implementation of reading a commit side; read, not traced: its executors are git (:50-:159, :396) "
               "and, in its own self-test, itself (:411), which the trace cannot name by __file__"},
    {"site": "session-distill/migrate-ledger.py", "path": "learn/build-promotions.py", "trace": True,
     "reason": "loaded by the migrator's self-test (build_promotions) by its literal repo path; it runs nothing"},
    {"site": "session-distill/migrate-ledger.py", "path": "compose/instructions-state.py", "trace": False,
     "reason": "loaded by the migrator's self-test (instructions_state) by its literal repo path for ledger_summary; "
               "read, not traced: its executors are git, compose/assemble.py (the installer's assembler) and itself "
               "(:81-:959), none of them a host"},
)
# Python scripts a closure site runs, each with its reason; a declared script joins the closure,
# so its own sites are judged like any module's.
SCRIPT_RUNS = (
    {"site": "session-distill/runlib/census.py", "path": "session-distill/census.py",
     "reason": "the self-test runs the legacy census on a fixture HOME (the runbook's census-to-digest handoff, "
               "retired at the WP-22 cutover); it reads history and transcript files"},
    {"site": "session-distill/runlib/census.py", "path": "session-distill/digest.py",
     "reason": "the same handoff's second step, run by the same self-test: it digests the census's sessions"},
    {"site": "session-distill/migrate-ledger.py", "path": "session-distill/merge-ledger.py",
     "reason": "the migrator's self-test runs the documented merge-ledger.py --window-end invocation on a fixture ledger"},
)
# Sites that run a closure file FROM A COPY of this checkout. The program is computed, so the trace
# cannot name it; what admits it is that the copy is this tree's own, made by
# `inventory.checkout_copy`, so the program is the file the trace already follows. Both halves are
# required of every entry: each value of the program must name the declared closure path, and the
# site must still carry the guards that make the copy this checkout's. A copy-run of any other
# script is refused like any undeclared one.
# Sites that run or load a closure file FROM A COPY of this checkout. The program is computed, so
# the trace cannot name it — and a file-wide guard string was not an answer: with the legitimate
# guard present, a `subprocess.run([sys.executable, os.environ['OTHER_SCRIPT']])` added to the same
# file was admitted, and so was an inline `runpy.run_path(sys.argv[1])` handed an unrelated script
# (R2#5).
#
# Admission is bound to THE CALL. Each entry names the one OWNER function that may produce such a
# path — `inventory.copied_member`, which returns a declared closure member inside a tree
# `checkout_copy` made in this process and refuses anything else — and a copy-run is admitted only
# where the program expression at that call site IS a call of it. For a `python -c` program, the
# argv element the inline load reads must be that same call, matched by index.
COPY_RUNS = (
    {"site": "session-distill/distill.py", "owner": "runlib.inventory.copied_member",
     "paths": ("session-distill/distill.py",),
     "reason": "the self-test's startup and checkout-protection controls run the COPY's own driver as a real "
               "process. Neither question can be asked of this checkout: the destination a protection rule is "
               "about has to be inside the checkout the rule protects, and an unreadable schema pin has to be "
               "unreadable in the tree that reads it (R1#2, R1#3)"},
    {"site": "session-distill/runlib/inventory.py", "owner": "copied_member",
     "paths": ("session-distill/distill.py", "session-distill/runlib/inventory.py"),
     "reason": "the bytecode control's child runs the COPY's driver as production does — "
               "`runpy.run_path(..., run_name=\'__main__\')` — to ask whether a real invocation leaves "
               "the tree it ran from unchanged, and its positive leg runs the same driver from a "
               "copy with the no-bytecode line taken out, which is what shows the comparison can "
               "fail. `learn/redact.py` was a member of this site while the control loaded the "
               "floor by path to make its own observer fire; the observer is gone, and so is that "
               "member. The copy's own `runlib/inventory.py` is run the same way by the "
               "boundary-bootstrap control, whose question — what this entry point prints when "
               "`runlib/entry.py` itself cannot be imported — can only be asked of a tree where "
               "that file is broken, never of this one (r3 #2)"},
)

# The ONE spelling each form-bearing file writes the admitted program forms with. A file that
# imports `pathlib` writes `pathlib.Path`; one that does `from pathlib import Path` writes `Path`.
# Exactly one spelling per file, declared here: admitting both would admit a spelling the file does
# not even have, and the point of an exact form is that there is nothing else to match (r3 #4).
FORM_SPELLINGS = (
    # The spellings are as the trace RESOLVES them: `mod.dotted` follows the file's own imports, so
    # the driver's `inventory.copied_member` reads as `runlib.inventory.copied_member`. Declaring
    # the resolved name is what makes one spelling per file decidable.
    {"site": "session-distill/distill.py", "str": "str", "path": "pathlib.Path",
     "member": "runlib.inventory.copied_member",
     "imports": {"pathlib": "pathlib", "inventory": "runlib"},
     "reason": "the driver imports pathlib as a module and inventory out of runlib"},
    {"site": "session-distill/runlib/inventory.py", "str": "str", "path": "pathlib.Path",
     "member": "copied_member", "imports": {"pathlib": "pathlib"}, "defines": ("copied_member",),
     "reason": "the inventory's sites call its own module-level `copied_member` by bare name, so "
               "the one binding of that name admitted here is the `def` that owns it"},
)

# The inline `python -c` programs the closure may run, as DATA. This judge does NOT read their
# insides. It asks three decidable things: the `-c` argument is this constant BY NAME, the
# constant's text still hashes to `sha256`, and the outer argv element at `loads` is an admitted
# program form. Judging the insides by shape was the hole: a direct `sys.argv[N]` rule still leaves
# `sys.argv` mutation before the load (`pop`, slice assignment, `setattr`, rebinding `sys`), and
# closing that means enumerating forms again, which is the defect being removed (r3 #5). The hash is
# what makes the reason below a review of the text that actually runs: change a character and the
# program is refused until the row is updated.
INLINE_PROGRAMS = (
    {"site": "session-distill/runlib/inventory.py", "name": "BYTECODE_PROBE",
     "sha256": "15107827053e49d63f6ee778cc97ed4cc02a258a99282ba7276d62a5f49951ae", "loads": 2,
     "reason": "the bytecode control's child: it runs the copy's own program, its own sys.argv[2], as "
               "`__main__`, which is how production runs it, and reports that run's exit code. It "
               "observes nothing — the audit hook and its table of mutating events were removed "
               "with the claim that rested on them, and the tree comparison answers instead"},
    {"site": "session-distill/distill.py", "name": "IGNORES_TERM",
     "sha256": "ec250f8f400ddb470e4d0da888652af25999b3720d3f7fc0dad39afbfe3524e0", "loads": None,
     "reason": "a TERM-ignoring descendant of a leader that exits on TERM, so the child bound is "
               "shown to end a tree rather than one process. It loads nothing, and both sleeps "
               "outlast the bound so only the kill can end them inside the control's window (r4 R2)"},
    {"site": "session-distill/distill.py", "name": "SLEEPS_BRIEFLY",
     "sha256": "60fa9b25b673777b30dd8b9ac67da767456dc61c9108978724e70b4d4f27317e", "loads": None,
     "reason": "a child that outlives its bound and does nothing else, for the control that asks "
               "what is signalled when its group cannot be established"},
    {"site": "session-distill/distill.py", "name": "LEADER_FIRST",
     "sha256": "6b0ac11a084dec4d37120418d5c887b9b97a62eef3ecc2122cf47962d214777e", "loads": None,
     "reason": "the ordinary shape, where the leader exits before its descendant: the bound must "
               "not fire and the leader's own result must come back"},
    # `runlib/stop.py`'s own fixtures: process trees the stop machinery is asked about. None of them
    # loads anything, and each ends on its own.
    {"site": "session-distill/runlib/stop.py", "name": "TREE",
     "sha256": "d0ae23fc14f7aa1bf9683d52d6fadd49cf22f81bcb697c81a8eba28283d06582", "loads": None,
     "reason": "a tree in its own session: a foreground child and an orphan that keeps the group, "
               "which is the shape only the group sweep can find"},
    {"site": "session-distill/runlib/stop.py", "name": "TREE_AWAY",
     "sha256": "5f29e9d79aa90d747810eb0050ebe43a7ca05c63c3ea62c5848ea501243635fc", "loads": None,
     "reason": "the same tree plus a child in a session of its own, so a member outside the group "
               "is shown to be left alone"},
    {"site": "session-distill/runlib/stop.py", "name": "TREE_EXITS",
     "sha256": "68b8667e5c4e1d288c1d3b215193a3f1010f1265aaca1f37dd87a722ceed1c5b", "loads": None,
     "reason": "a root that exits before the stop, for the control about a group id whose leader "
               "has already been reaped"},
    {"site": "session-distill/runlib/stop.py", "name": "SLEEPS_LONG",
     "sha256": "d9d34ec4f72b4a695978db51fbdd6fab3d048d36efad4c8260c8ef462e22b3b2", "loads": None,
     "reason": "one child outside the tree, for the two identity controls: it must be neither "
               "signalled nor counted"},
    {"site": "session-distill/runlib/stop.py", "name": "FORKING_ROOT",
     "sha256": "1d6df56c247670f3f2a5a8beac8f61f9de05c8a889098df7ff5fda8344d3a02c", "loads": None,
     "reason": "a root that forks a member between the listing that found it and its stop signal; "
               "the file it writes the new pid to arrives as its own argv"},
    # `runlib/ledger.py`'s hard-kill fixture: a writer killed before the rename.
    {"site": "session-distill/runlib/ledger.py", "name": "HARD_KILL",
     "sha256": "df7401e14372cf5eebd5e12ce0eee242d858ae9d1288d2c3a5d0ff6deaec75fc", "loads": None,
     "reason": "a real process that proposes a successor and dies before the rename, so bytes that "
               "are still the base afterwards say the rename had not happened (X#1). Its four "
               "values arrive as argv, since a declaration pins text and an f-string has none"},
)

# Sites whose program the trace cannot name, each admitted only while its guard — a literal line
# of the site's file that confines the program to one by name — is still there.
GUARDED_PROGRAMS = (
    {"site": "session-distill/runlib/sources.py",
     "guards": ('os.path.basename(os.path.realpath(zstd)) != "zstd"', '[checked_zstd(zstd), "-dcq", path]'),
     "reason": "read_lines decompresses with the zstd run.json declares (declare.py requires the source), through "
               "checked_zstd, the guard's one owner: it refuses any declared path whose resolved file is not named "
               "zstd, so the program is zstd by name, the standard the trace holds every named program to"},
    {"site": "session-distill/runlib/views.py",
     "guards": ('[sources.checked_zstd(zstd), "-q", "-f"',),
     "reason": "golden() compresses its fixture with the zstd the fixture run declares, through sources.checked_zstd "
               "(whose check the sources.py entry holds)"},
)
# interpreter options that take no value: they change how python runs, never what it runs
PY_FLAGS = ("-I", "-E", "-s", "-S", "-B", "-u", "-O", "-OO", "-q", "-b", "-bb", "-R")
CLOSURE_ROOTS = ("session-distill/distill.py", "session-distill/runlib")
IMPORT_DIRS = ("session-distill", "benchmarks")
HOST_NAMES = ("claude", "codex", "claude-run", "codex-run")
SHELLS = ("sh", "bash", "zsh", "dash", "env")
# A literal interpreter name, by any spelling. Production starts Python through `sys.executable`,
# which the trace reads as PYTHON and judges as a program; a literal `python3` is a different
# interpreter — whatever PATH answers with — and is refused wherever it is written (r4 R5).
INTERPRETER_NAME = re.compile(r"^python(\d+(\.\d+)?)?$|^py$|^pypy\d*$")
# r4 R5, default deny: the tail of `_judge_program` admitted ANY literal program with no problem at
# all, so `subprocess.Popen(['python3', '/fixture/other.py'])` and every other literal name were
# admitted in silence. These are the eight sites the fallthrough admitted at e011005, instrumented
# over the real tree and declared one by one; the program is matched by its basename, because the
# trace resolves `zstd` and `ps` to wherever this machine holds them.
LITERAL_PROGRAMS_DECLARED = (
    {"site": "session-distill/distill.py", "program": "git",
     "reason": "the driver reads the checkout's tracked paths and HEAD to record what it inventoried"},
    {"site": "session-distill/migrate-ledger.py", "program": "git",
     "reason": "the one-shot ledger migration records the commit it ran at"},
    {"site": "session-distill/runlib/inventory.py", "program": "git",
     "reason": "`tracked_paths` lists a source tree through git when the tree has a .git of its own"},
    {"site": "session-distill/runlib/ledger.py", "program": "git",
     "reason": "a ledger entry carries the commit it was recorded at"},
    {"site": "session-distill/runlib/census.py", "program": "zstd",
     "reason": "a compressed transcript is read through the zstd the run declares; `checked_zstd` "
               "refuses a declared path whose resolved file is not named zstd"},
    {"site": "session-distill/runlib/sources.py", "program": "zstd",
     "reason": "the same read, in the module that owns `checked_zstd`"},
    {"site": "session-distill/runlib/sources.py", "program": "cp",
     "reason": "the immutable copy of a transcript is made with /bin/cp, an absolute path"},
    {"site": "session-distill/runlib/stop.py", "program": "ps",
     "reason": "the process table is read with /bin/ps, an absolute path, to verify a stopped tree"},
)
EXEC_CALLS = {f"subprocess.{n}" for n in ("run", "Popen", "call", "check_call", "check_output", "getoutput",
                                          "getstatusoutput")} | \
             {f"os.{n}" for n in ("system", "popen", "execv", "execve", "execvp", "execvpe", "execl", "execle", "execlp",
                                  "execlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe", "spawnl", "spawnle", "spawnlp",
                                  "spawnlpe", "posix_spawn", "posix_spawnp")}
# os executors by argv shape: (index of the program, index of its argv list, or None, and the
# index where its loose arguments start — argv[0] included — and how many trail as the environment)
OS_ARGV = {**{f"os.{n}": (0, 1, None, 0) for n in ("execv", "execve", "execvp", "execvpe", "posix_spawn", "posix_spawnp")},
           **{f"os.{n}": (0, None, 1, 0) for n in ("execl", "execlp")}, **{f"os.{n}": (0, None, 1, 1) for n in ("execle", "execlpe")},
           **{f"os.{n}": (1, 2, None, 0) for n in ("spawnv", "spawnve", "spawnvp", "spawnvpe")},
           **{f"os.{n}": (1, None, 2, 0) for n in ("spawnl", "spawnlp")}, **{f"os.{n}": (1, None, 2, 1) for n in ("spawnle", "spawnlpe")}}
LOAD_CALLS = {"importlib.import_module": 0, "__import__": 0, "runpy.run_module": 0, "runpy.run_path": 0,
              "importlib.util.spec_from_file_location": 1, "importlib.machinery.SourceFileLoader": 1}
UNKNOWN, PYTHON = "<?>", "<python>"
UNREAD = ast.Name(id="<an argv the trace cannot read>", ctx=ast.Load())  # resolves to UNKNOWN wherever it is judged


# ---- the suites' only scratch, and the three ways a call hides from this judge ----------------
# A suite that asked `tempfile` for a parent of its own put every fixture it wrote inside whatever
# `TMPDIR` named, a protected root included (R1#5) — and observing that from outside took a child
# running the whole suite, which is what made the recursion of S7 possible. Every rule below is
# DEFAULT-DENY: it declares what is admitted, as data with reasons, and refuses the rest. A list of
# forbidden forms was the recurring defect (r3 #6) — `import subprocess as sp`, `make =
# tempfile.mkdtemp`, `cmd = [..., "--self-test"]` and `(spawn or subprocess.Popen)(...)` each passed
# a check that enumerated the shapes it knew.
TEMPFILE_SCOPE = ("session-distill/distill.py", "session-distill/runlib/inventory.py")
TEMPFILE_SITES = (
    {"file": "session-distill/runlib/inventory.py", "function": "self_test_scratch",
     "reason": "both suites' ONE scratch directory, created under the parent `scratch_parent` judged; "
               "the driver's suite calls this function rather than tempfile"},
    {"file": "session-distill/runlib/inventory.py", "function": "run",
     "reason": "production's frozen copies of the owner's state, made under `temp_root`, which the "
               "preflight has already judged against the protected set"},
)
# Modules whose names this judge reads: derived from EXEC_CALLS **and LOAD_CALLS**, so the set has one
# owner and a new executor or loader cannot be covered by the matcher and missed here. The loaders
# belong for the same reason as the executors: `from runpy import run_path` leaves a load this judge
# never recognises.
EXEC_MODULES = frozenset(name.split(".")[0] for name in set(EXEC_CALLS) | set(LOAD_CALLS))
# Modules that can start a process and that EXEC_CALLS does NOT describe. Importing one is refused
# unless it is declared here with the reason it is harmless where it stands.
PROCESS_MODULES = ("multiprocessing", "pty", "asyncio", "concurrent", "concurrent.futures",
                   "socketserver", "xmlrpc.server")
# The modules whose every reference this judge must be able to follow: the scratch module, the
# executors and the loaders, and the modules that can start a process (r4 R5).
WATCHED_MODULES = frozenset({"tempfile"} | set(EXEC_MODULES) | {name.split(".")[0] for name in PROCESS_MODULES})
PROCESS_IMPORTS_DECLARED = (
    {"module": "concurrent.futures", "file": "session-distill/runlib/census.py",
     "reason": "ThreadPoolExecutor over already-listed transcript files (census.py:309); threads, "
               "not processes, and no program name reaches it"},
)
# Names that may be taken OUT of an executor's or loader's module, each because it starts and loads
# nothing. EMPTY on purpose: this tree holds no `as` or `from` import of any such module — every one
# is a plain `import M` — so there is nothing to excuse, and an exception goes in with its reason
# when a real one appears rather than ahead of it.
EXEC_IMPORT_NAMES_DECLARED = ()
# Where the suite argv may be spelled. Everything else is refused: a constant in a list the trace
# cannot follow to its call is exactly how `cmd = [sys.executable, f, "--self-test"]` passed.
SUITE_ARGV = "--self-test"
SUITE_ARGV_CONTEXTS = (
    {"context": "add_argument", "reason": "the parser declaring the flag"},
    {"context": "comparison", "reason": "`argv == [\"--self-test\"]` and `in` tests: a read, not a run"},
    {"context": "in-process entry", "reason": "the suites are entered in this process, through main "
                                              "or the one boundary, never through a child"},
    {"context": "this judge's own declaration", "reason": "the constant this rule is about"},
)
IN_PROCESS_ENTRIES = ("main", "guarded_entry", "self_test")


def _parents(parsed):
    """`{id(child): parent}` for one tree: a context rule needs the node above, not only the node."""
    seen = {}
    for node in ast.walk(parsed):
        for child in ast.iter_child_nodes(node):
            seen[id(child)] = node
    return seen


def _enclosing(parsed, lineno):
    """The name of the function a line stands in, or None at module scope."""
    best = None
    for node in ast.walk(parsed):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= lineno <= (node.end_lineno or node.lineno) and (
                    best is None or node.lineno > best.lineno):
                best = node
    return best.name if best else None


def _suite_argv_admitted(node, parents):
    """Whether this `--self-test` constant stands in one of the declared contexts."""
    parent = parents.get(id(node))
    if isinstance(parent, ast.Call) and ast.unparse(parent.func).split(".")[-1] == "add_argument" \
            and parent.args and parent.args[0] is node:
        return True
    if isinstance(parent, ast.Compare):
        return True
    if isinstance(parent, ast.Assign) and len(parent.targets) == 1 \
            and ast.unparse(parent.targets[0]) == "SUITE_ARGV":
        return True
    # an element of a list/tuple: admitted only when that display IS the argument of a declared
    # in-process entry, or the right-hand side of a comparison
    if isinstance(parent, (ast.List, ast.Tuple)):
        above = parents.get(id(parent))
        if isinstance(above, ast.Compare):
            return True
        if isinstance(above, ast.Call) and ast.unparse(above.func).split(".")[-1] in IN_PROCESS_ENTRIES:
            return True
        return False
    if isinstance(parent, ast.Call) and ast.unparse(parent.func).split(".")[-1] in IN_PROCESS_ENTRIES:
        return True
    return False


def shape_violations(root=REPO, sites=TEMPFILE_SITES, scope=TEMPFILE_SCOPE, sources=None):
    """Default-deny judgements over the SOURCE of session-distill/: the scratch allow-list, the
    import forms a call can hide behind, an executor referenced as a value, and where the suite argv
    may be spelled.

    `sources` maps a relative path to source text, so a planted violation is judged in a copy of the
    text and never on disk — the recursion this guards against is exactly what must not be run."""
    root = pathlib.Path(root)
    held = dict(sources or {})

    def text_of(rel):
        if rel in held:
            return held[rel]
        path = root / rel
        return path.read_text(encoding="utf-8") if path.is_file() else None

    problems, counted = [], {}
    declared = {(entry["file"], entry["function"]) for entry in sites}
    # ---- the scratch allow-list: any REFERENCE to tempfile, not only a call of a listed name
    for rel in scope:
        source = text_of(rel)
        if source is None:
            problems.append(f"TEMPFILE_SCOPE_STALE {rel}: no such file")
            continue
        try:
            parsed = ast.parse(source)
        except SyntaxError as exc:
            problems.append(f"TEMPFILE_UNREADABLE {rel}: {exc}")
            continue
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "tempfile" and alias.asname:
                        problems.append(f"TEMPFILE_IMPORT_FORM {rel}:{node.lineno}: `import tempfile as "
                                        f"{alias.asname}` renames the module out of this judge's sight")
            if isinstance(node, ast.ImportFrom) and node.module == "tempfile":
                problems.append(f"TEMPFILE_IMPORT_FORM {rel}:{node.lineno}: `from tempfile import ...` "
                                f"leaves a reference this judge cannot recognise")
            if not (isinstance(node, ast.Attribute) and ast.unparse(node.value) == "tempfile"):
                continue
            where = _enclosing(parsed, node.lineno)
            if (rel, where) not in declared:
                problems.append(f"TEMPFILE_UNDECLARED {rel}:{node.lineno}: tempfile.{node.attr} in "
                                f"{where or '<module scope>'}, which no scratch site declares")
                continue
            counted[(rel, where)] = counted.get((rel, where), 0) + 1
    for entry in sites:
        made = counted.get((entry["file"], entry["function"]), 0)
        if made == 0:
            problems.append(f"INVENTORY_STALE tempfile site {entry['file']}:{entry['function']}: "
                            f"it refers to tempfile nowhere")
        elif made > 1:
            problems.append(f"TEMPFILE_SECOND_CALL {entry['file']}:{entry['function']}: {made} tempfile "
                            f"references where a declared site makes one")
    # ---- import forms, executors as values, and the suite argv, over every source of session-distill/
    names_declared = {(entry["module"], entry["name"]) for entry in EXEC_IMPORT_NAMES_DECLARED}
    process_declared = {(entry["module"], entry["file"]) for entry in PROCESS_IMPORTS_DECLARED}
    files = sorted(str(path.relative_to(root)) for path in (root / "session-distill").rglob("*.py")
                   if "__pycache__" not in str(path)) if (root / "session-distill").is_dir() else []
    for rel in sorted(set(files) | set(held)):
        source = text_of(rel)
        if source is None or not rel.startswith("session-distill/"):
            continue
        try:
            parsed = ast.parse(source)
        except SyntaxError:
            continue
        parents = _parents(parsed)
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    head = alias.name.split(".")[0]
                    if alias.name in EXEC_MODULES or head in EXEC_MODULES:
                        if alias.asname:
                            problems.append(f"DISPATCH_IMPORT_FORM {rel}:{node.lineno}: `import "
                                            f"{alias.name} as {alias.asname}` renames an executor's "
                                            f"module out of this judge's sight")
                    elif alias.name in PROCESS_MODULES or head in PROCESS_MODULES:
                        if (alias.name, rel) not in process_declared or alias.asname:
                            problems.append(f"DISPATCH_PROCESS_MODULE {rel}:{node.lineno}: `import "
                                            f"{alias.name}{' as ' + alias.asname if alias.asname else ''}` "
                                            f"can start a process and no declaration admits it here")
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                head = module.split(".")[0]
                for alias in node.names:
                    if module in EXEC_MODULES or head in EXEC_MODULES:
                        if (module, alias.name) not in names_declared:
                            problems.append(f"DISPATCH_IMPORT_FORM {rel}:{node.lineno}: `from {module} "
                                            f"import {alias.name}` takes a name out of an executor's "
                                            f"module; spell the call module-qualified")
                    elif module in PROCESS_MODULES or head in PROCESS_MODULES:
                        if (module, rel) not in process_declared:
                            problems.append(f"DISPATCH_PROCESS_MODULE {rel}:{node.lineno}: `from "
                                            f"{module} import {alias.name}` can start a process and no "
                                            f"declaration admits it here")
            # an executor may be the direct callee of a Call and nothing else: passed as a value,
            # stored, returned or inside a BoolOp/IfExp it is a program this judge never sees
            if isinstance(node, ast.Attribute):
                spelled = ast.unparse(node)
                if spelled in EXEC_CALLS:
                    parent = parents.get(id(node))
                    if not (isinstance(parent, ast.Call) and parent.func is node):
                        problems.append(f"DISPATCH_EXEC_AS_VALUE {rel}:{node.lineno}: {spelled} is "
                                        f"referenced without being called, so the program it would "
                                        f"start is judged nowhere")
            # r4 R5: a watched MODULE used as a value. The scratch check said it sees any REFERENCE
            # to tempfile and saw only `tempfile.<attr>` and import aliases, so `t = tempfile` and
            # then `t.TemporaryDirectory()` passed — and the same shape hides every executor and
            # process module. A module's name loaded anywhere but as the base of an attribute access
            # is a reference this judge cannot follow, so it is refused where it is written.
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in WATCHED_MODULES:
                parent = parents.get(id(node))
                if not (isinstance(parent, ast.Attribute) and parent.value is node):
                    problems.append(f"DISPATCH_MODULE_AS_VALUE {rel}:{node.lineno}: {node.id!r} is used as a "
                                    f"value rather than as the base of an attribute access, which takes "
                                    f"every call through it out of this judge's sight")
            if isinstance(node, ast.Constant) and node.value == SUITE_ARGV:
                if not _suite_argv_admitted(node, parents):
                    problems.append(f"DISPATCH_SELF_TEST_ARGV {rel}:{node.lineno}: {SUITE_ARGV!r} "
                                    f"stands in no declared context; a suite is entered in this "
                                    f"process, never handed to a child")
            if isinstance(node, (ast.JoinedStr, ast.BinOp)):
                parts = [part.value for part in ast.walk(node)
                         if isinstance(part, ast.Constant) and isinstance(part.value, str)]
                if "".join(parts) == SUITE_ARGV or SUITE_ARGV in parts:
                    problems.append(f"DISPATCH_SELF_TEST_ARGV {rel}:{node.lineno}: the suite argv is "
                                    f"spelled by composition, which no declared context admits")
    return problems




class Exhausted(Refused):
    """The stage's remaining budget cannot fit the reservation; the item is recorded not_done."""


def class_key(stage, seat, case_type):
    return f"{stage}|{seat}|{case_type}"


def p95(samples):
    """The nearest-rank 95th percentile."""
    ordered = sorted(samples)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def plain_tree(root):
    """True when `root` is a directory of regular files and directories only: what a producing call
    reads is copied into its cell, and a symlink could carry the read outside it."""
    root = pathlib.Path(root)
    return root.is_dir() and not root.is_symlink() and all(
        not p.is_symlink() and (p.is_file() or p.is_dir()) for p in root.rglob("*"))


def listing(cwd):
    """The working directory's files by relative path and sha256, as claude-run lists it before a call."""
    root = pathlib.Path(cwd)
    return [{"path": str(p.relative_to(root)), "sha256": packets.sha256_bytes(p.read_bytes())}
            for p in sorted(root.rglob("*")) if p.is_file()]


# What each adapter can actually DELIVER to its host, read off the runner interfaces in `wrappers/`:
# claude-run.sh takes `--max-output-tokens`, and under `--profile hermetic` an
# `--append-system-prompt-file` with the `--declared-sha256` it was declared at; codex-run.sh takes
# neither - Codex has no output cap (design §3.2) and no appending flag. A call that declares what its
# adapter cannot carry is refused rather than recorded: a reservation the host is never told is not a
# reservation, and a prompt that is recorded and not sent fails the gate's effective-context leg after
# the call is paid for (BB#2, BB#4). Each entry names the flag that carries it and the runner profile it
# needs, which is what the self-test holds against the wrapper scripts themselves.
ADAPTER_CONVEYS = {"claude": {"output_cap": ("--max-output-tokens", None),
                              "appended_prompts": ("--append-system-prompt-file", "hermetic")},
                   "codex": {}}


def adapter_conveys(host, runner_profile):
    """What `host`'s adapter can deliver for a call launched under `runner_profile`."""
    return {name for name, (_flag, needs) in (ADAPTER_CONVEYS.get(host) or {}).items()
            if needs is None or needs == runner_profile}


def runner_argv(host, spec):
    """The runner's argv for one call, in the adapters' interfaces: claude-run's as its --help states
    it ("A dispatcher calls one hermetic Claude call as", plan WP-03), the pinned host binary and
    version among the arguments; codex-run's (plan WP-04), whose host comes from CODEX_RUN_BIN and
    CODEX_RUN_VERSION in the environment. The use, the readable manifest directory and the
    output-token cap reach claude-run only: codex-run has no producing profile and no output cap
    (Codex has none, design §3.2), so a cap declared for a Codex call is recorded and not passed."""
    argv = [str(RUNNERS[host]), "--profile", spec["profile"], "--model", spec["model"], "--effort", spec["effort"]]
    conveys = adapter_conveys(host, spec["profile"])
    # the admission boundary has already refused such a call; this is the second place the same fact is kept,
    # so a spec that reached here with an undeliverable declaration cannot be launched without it. A cap on a
    # call that carries no view window is recorded and not passed, as it always was - the reservation of
    # check (d) is the only thing the host must be told.
    for code, name, declared in (("APPENDED_PROMPT_UNDELIVERABLE", "appended_prompts", bool(spec.get("appended_prompts"))),
                                 ("CAP_UNDELIVERABLE", "output_cap", bool(spec.get("view_window")))):
        if declared and name not in conveys:
            raise Refused(f"{code} {spec['call_id']}: {host}'s adapter under profile {spec['profile']!r} carries no "
                          f"{ADAPTER_CONVEYS.get(host, {}).get(name, ('flag for it',))[0]}")
    if host == "codex":
        return argv + ["--cd", spec["workdir"]] + (["--schema", spec["schema_path"]] if spec.get("schema_path") else []) + ["-"]
    argv += ["--cell-root", str(pathlib.Path(spec["cell"]).parent), "--call-id", spec["call_id"], "--cd", spec["workdir"],
             "--claude-bin", spec["host_bin"], "--host-version", spec["host_version"],
             "--max-output-tokens", str(spec["max_output_tokens"])]
    for prompt in spec.get("appended_prompts") or []:
        # the file holds the exact bytes admission counted, and the hash is the one the call record carries,
        # so the adapter's own check compares the delivered bytes with the declaration (BB#2)
        argv += ["--append-system-prompt-file", prompt["path"], "--declared-sha256", prompt["sha256"]]
    if spec.get("schema_path"):
        argv += ["--schema", spec["schema_path"]]
    if spec["use"] == "producing":
        argv += ["--use", "producing", "--tools", "Read", "--manifest", spec["read_root"]]
    elif spec["use"] != "judge":
        argv += ["--use", spec["use"]]
    return argv


def stop_detail(offered):
    """What a call reports when its own excess stopped it.

    The rule's own detail, plus the two things only this call knows: the stamp it could not avoid, and
    whether the run kept this stop or an earlier, stronger one stands. A stop that lost still says why it
    was made, which is how a stamping defect stays visible (BE#3)."""
    return (offered["detail"] + (f"; {offered['stamp']}" if offered.get("stamp") else "")
            + ("" if offered.get("kept", True) else "; an earlier stop stands in the run ledger"))


def reconcile_codex(call_dir, ledger, clock=time.time):
    """A Codex call's live ledger against the gate's strict join over its final capture (design
    §3.2, §13.3): what the live ledger measured from otel alone gives way — a row otel opened is
    dropped, a sent request otel measured before its frame arrived returns to what it was —; a
    completion no frame response joins is spent (frames_blind: unknown kind, usage from otel);
    every interrupted attempt, a failed post the retry warnings show among them, keeps a row.
    Returns whether everything reconciled — never while any thread's attempt coverage is unknown."""
    c = gate.Call(call_dir)
    unjoined, ambiguous, _leftover = gate.join_completions(c, gate.codex_responses(c))
    kept = []
    for r in ledger.requests:
        if r.get("otel_only"):
            continue
        if r.get("pre_otel") is not None and r.get("frame_usage") is None:
            r.update(r.pop("pre_otel"))
            r.pop("otel_usage", None)
        kept.append(r)
    ledger.requests[:] = kept
    for comp in unjoined + ambiguous:
        row = ledger.open(f"otel-{comp.get('ts')}", "unknown", comp.get("conversation.id"), clock())
        ledger.measure(row, monitors.codex_tokens(monitors.otel_usage(comp)))
    attempts = gate.codex_attempts(c)
    interrupted = sum(t["interrupted"] for t in attempts.values())
    unmeasured = sum(1 for r in ledger.requests if r["state"] != "measured")
    for n in range(max(0, interrupted - unmeasured)):
        ledger.open(f"interrupted-{n + 1}", "unknown", None, clock())
    return bool(ledger.requests) and all(r["state"] == "measured" for r in ledger.requests) \
        and not unjoined and not ambiguous and interrupted == 0 and all(t["coverage"] == "complete" for t in attempts.values())


class Supervisor:
    def __init__(self, run_dir, *, clock=time.time, runner=None, cell_root=None, env=None, realization="live",
                 seats_path=None, monitor=None):
        self.run_dir = pathlib.Path(run_dir)
        self.run_id = self.run_dir.resolve().name
        self.clock, self.runner, self.realization = clock, runner or runner_argv, realization
        self.monitor = monitor or monitors.Monitor  # the self-test's delayed-reader controls give a slower one
        self.drain_deadline_s = DRAIN_DEADLINE_S  # the self-test's held-pipe control gives a shorter one
        self.cell_root = pathlib.Path(cell_root) if cell_root else None
        self.env = dict(os.environ if env is None else env)
        self.breaker = breakers.Breaker(self.run_dir)
        self.seats_path = pathlib.Path(seats_path) if seats_path else gate.SEATS

    # --- the ledger and the calibration ------------------------------------------------------

    def _path(self, name):
        return self.run_dir / "supervisor" / name

    def ledger(self):
        path = self._path("ledger.json")
        held = records.read_json(path) if path.is_file() else {}
        return {"stages": held.get("stages", {}), "stopped": held.get("stopped")}

    @staticmethod
    def _stage(ledger, stage):
        return ledger["stages"].setdefault(stage, {"reservations": {}, "spent": {"measured": 0, "provisional": 0},
                                                   "not_done": [], "overshoot": []})

    def _write(self, ledger):
        records.write_json(self.run_dir, self._path("ledger.json"), ledger)

    def _lock(self):
        return stagelock.hold(self.run_dir, "supervisor", wait_s=LOCK_WAIT_S)

    def calibration(self):
        path = self._path("calibration.json")
        return records.read_json(path) if path.is_file() else {}

    def seed_from(self, samples):
        """The rehearsal's measured costs, {class: [tokens, ...]}, as this run's starting samples."""
        with self._lock():
            held = self.calibration()
            for klass, values in samples.items():
                held.setdefault(klass, {"samples": []})["samples"].extend(int(v) for v in values)
            records.write_json(self.run_dir, self._path("calibration.json"), held)

    def estimate(self, klass, host):
        samples = self.calibration().get(klass, {}).get("samples", [])
        if len(samples) >= CALIBRATION_MIN_SAMPLES:
            return p95(samples), "measured"
        return usages.SAFETY_FACTOR * max([SEEDS[host]["tokens"], *samples]), "provisional"

    def remaining(self, stage):
        run, _digest, _amendments = records.declaration_state(self.run_dir, who="dispatch")
        entry = self._stage(self.ledger(), stage)
        return run["budget"]["per_stage"].get(stage, 0) - self._committed(entry)

    @staticmethod
    def _committed(entry):
        held = sum(r["amount"] for r in entry["reservations"].values() if r["open"])
        return held + entry["spent"]["measured"] + entry["spent"]["provisional"]

    def reserve(self, stage, item, seat, case_type, *, tranche="broad", attempt=1, _between=None, _locked=True):
        """Check and reserve in one critical section. `_between` and `_locked` exist for the
        self-test's race control only: the unlocked variant is the check-then-reserve race."""
        host, klass = seat.partition(":")[0], class_key(stage, seat, case_type)
        with self._lock() if _locked else contextlib.nullcontext():
            ledger = self.ledger()
            if self._blocked(ledger):
                raise Refused(f"RUN_STOPPED {ledger['stopped']['code']} at {ledger['stopped']['call_id']}: "
                              f"nothing more is dispatched in this run")
            run, _digest, _amendments = records.declaration_state(self.run_dir, who="dispatch")
            budget = run["budget"]["per_stage"].get(stage)
            if budget is None:
                raise Refused(f"BUDGET_UNDECLARED {stage}: run.json declares no budget for the stage")
            amount, calibration = self.estimate(klass, host)
            if calibration == "provisional" and tranche != "calibration":
                raise Refused(f"CALIBRATION_PROVISIONAL {klass}: fewer than {CALIBRATION_MIN_SAMPLES} measured calls; "
                              f"only a calibration tranche dispatches it (S-15)")
            entry = self._stage(ledger, stage)
            if tranche == "calibration" and any(r["open"] and r["class"] == klass and r["tranche"] == "calibration"
                                                for r in entry["reservations"].values()):
                raise Refused(f"CALIBRATION_SERIAL {klass}: a calibration tranche runs at concurrency one")
            left = budget - self._committed(entry)
            if _between is not None:
                _between()
            if amount > left:
                entry["not_done"].append({"item": item, "class": klass, "at": self.clock(), "remaining": left,
                                          "reservation": amount})
                self._write(ledger)
                raise Exhausted(f"BUDGET_EXHAUSTED {stage}: the remaining {left} cannot fit the reservation {amount} "
                                f"of {klass}; {item} is recorded not_done")
            while f"{self.run_id}-{stage}-{item}-a{attempt}" in entry["reservations"]:
                attempt += 1  # a deferred or refused attempt keeps its id; the next one takes the next
            call_id = f"{self.run_id}-{stage}-{item}-a{attempt}"
            reservation = {"call_id": call_id, "stage": stage, "item": item, "seat": seat, "class": klass,
                           "amount": amount, "calibration": calibration, "tranche": tranche,
                           "declaration_seq": run["declaration_seq"], "at": self.clock(), "open": True, "outcome": None}
            entry["reservations"][call_id] = reservation
            self._write(ledger)
        return dict(reservation)

    def release(self, stage, call_id, outcome):
        """Close a reservation nothing was spent against (deferred, refused before dispatch)."""
        with self._lock():
            ledger = self.ledger()
            held = self._stage(ledger, stage)["reservations"][call_id]
            held.update(open=False, outcome=outcome)
            self._write(ledger)

    def charge(self, stage, call_id, totals, outcome, caps=None):
        """Settle a reservation with the call's spend in its three states; spend past the
        reservation or the cap is recorded as overshoot; a complete, unstopped call is a sample."""
        with self._lock():
            ledger = self.ledger()
            entry = self._stage(ledger, stage)
            held = entry["reservations"][call_id]
            held.update(open=False, outcome=outcome, spent=totals)
            entry["spent"]["measured"] += totals["measured"]
            entry["spent"]["provisional"] += totals["provisional"]
            spent = totals["measured"] + totals["provisional"]
            for past, limit in (("reservation", held["amount"]), ("cap", (caps or {}).get("tokens"))):
                if limit is not None and spent > limit:
                    entry["overshoot"].append({"call_id": call_id, "past": past, "limit": limit, "spent": spent,
                                               "state": "measured" if totals["complete"] else "estimated"})
            self._write(ledger)
            if totals["complete"] and outcome == "completed":
                cal = self.calibration()
                cal.setdefault(held["class"], {"samples": []})["samples"].append(totals["measured"])
                records.write_json(self.run_dir, self._path("calibration.json"), cal)

    def _stop_run(self, entry, into=None):  # noqa: C901 - one critical section

        """Stop the run, with the entry that records WHY - the one record of it.

        A bound excess is `bound.excess(...)`, stamped by `bound.committed` with the sequence the
        declaration has reached at this moment, because that is what the recovery rule compares against.
        There is no second file beside this:
        the stop is written here and read in `_stopped`, so the record a run recovers from is the record it
        stopped on (the seam record of 2026-10-22).

        **The lock order in this module is the declaration lock, then the supervisor's**, and a bound stop is
        the one place that takes both. It has to: the sequence the stop is stamped with must be the latest the
        declaration has reached, and that cannot be read from outside the lock `declare --amend` commits
        under. Read from outside it, an amendment that committed a moment earlier would stamp the stop with a
        sequence its own amendment then lifts, and an amendment caught between its log line and its run.json
        would make the read fail DECLARATION_DRIFT instead of waiting (BB#0). Every other site here only
        READS the declaration, under the supervisor's lock alone, and a read that lands mid-commit is refused
        by name rather than believed - so no site takes the two in the other order, and this one cannot
        deadlock against them.

        **An observed excess is never discarded.** The wait on the declaration lock is bounded, and the
        bound is the point: an unbounded wait would hang the dispatcher behind any holder, which is a
        worse failure than an unstamped stop. So when the lock cannot be taken, or the declaration it
        guards cannot be read, the stop is still written - under the ledger lock alone, with no
        `declaration_seq` and with `stamp` naming why. By the recovery rule an UNSTAMPED stop lifts for
        nothing (`bound.lifted` requires an integer sequence), so every later dispatch stays refused and
        recovery is a new run, not an amendment. The call itself fails by name either way (BC#0).

        **A stop never weakens.** The ledger holds one `stopped` entry and more than one call can settle an
        excess, so the entry kept is the stronger of the kept and the offered one (`bound.strongest`): an
        unstamped stop is terminal and nothing replaces it, and between stamped stops the higher sequence
        stays. Writing the newer entry over the older let a stamped stop from a call that was already
        running replace the unstamped stop of a lock timeout, and a `host_allowance` amendment then lifted
        a run that should have ended (BD#0). What this returns is this call's own record of the stop; what
        the ledger keeps is the stronger one."""
        bound_stop = entry.get("code") == bound.STOP_CODE
        with contextlib.ExitStack() as locks:
            unstamped = None
            if bound_stop:
                try:
                    locks.enter_context(stagelock.hold(self.run_dir, "declaration", wait_s=STOP_LOCK_WAIT_S))
                except stagelock.Locked as exc:
                    unstamped = f"lock-timeout: {exc}"
                except Exception as exc:         # noqa: BLE001 - ANY failure to TAKE the lock (BE#0): the
                    # lock file unreadable, linked out of the run, its directory gone. The ledger is still
                    # writable, so the overrun is recorded unstamped rather than lost with the exception.
                    unstamped = f"lock-unavailable: {exc!r}"
            with self._lock():
                ledger = self.ledger()
                if bound_stop and unstamped is None:
                    # BA#0: the sequence recovery is measured from is the latest the declaration has reached
                    # HERE, with the stop - not the one the call was reserved under. An amendment that landed
                    # while the call was still running was recorded before anybody knew the host had changed.
                    #
                    # The two steps are caught separately, because they fail for different reasons and a
                    # stop has to say which (BE#3): READING the declaration can fail on an unreadable file,
                    # a confinement violation, a decode error or the reader's own named refusal of a drifted
                    # declaration - all `declaration-unreadable`; STAMPING is this code's own arithmetic, so
                    # anything thrown there is a defect here and says so, under its own reason, rather than
                    # being reported as a filesystem problem.
                    try:
                        run, _digest, amendments = records.declaration_state(self.run_dir, who="dispatch")
                    except Exception as exc:     # noqa: BLE001 - see above
                        unstamped = f"declaration-unreadable: {exc!r}"
                    else:
                        try:
                            entry = bound.committed(entry, max([run["declaration_seq"]]
                                                               + [a["seq"] for a in amendments
                                                                  if isinstance(a.get("seq"), int)]))
                        except Exception as exc:  # noqa: BLE001 - see above
                            unstamped = f"stop-internal-error: {exc!r}"
                if unstamped is not None:
                    entry = {**entry, "stamp": unstamped}
                offered = dict(entry)             # the entry already carries its own `at` (HC#0)
                kept = bound.strongest(ledger.get("stopped"), offered)
                ledger["stopped"] = kept
                self._write(ledger)
                # what this returns is THIS call's own stop, whether or not the run kept it: the call
                # records it and names it in its refusal, so a stop that lost to an earlier terminal one
                # still leaves its reason somewhere a reader can find (BE#3)
                result = {**offered, "kept": kept is offered}
                if into is not None:
                    # HD#0: retained HERE, with the ledger written and the locks not yet released -
                    # releasing them can fail, and a failure after the write used to leave the caller
                    # without its own stop, so the failure path offered the same stop a second time
                    into["stop"] = result
                return result

    def _now(self):
        """`(at, note)` - the clock, with a fallback.

        A clock that raises must not block a stop that has already been decided (HC#0), so the
        fallback is taken and the entry says the timestamp did not come from the run's own clock."""
        try:
            return self.clock(), None
        except Exception as exc:                  # noqa: BLE001 - a timestamp decides nothing
            try:
                return time.time(), f"clock-unavailable: {exc!r}"
            except Exception as inner:            # noqa: BLE001
                return None, f"clock-unavailable: {inner!r}"

    @staticmethod
    def _rows_snapshot(mon):
        """The monitor's request rows, copied for the stop decision, raising on nothing.

        Taken under the monitor's own lock with a BOUNDED wait and copied either way: this runs on
        the failure path too, where the exception may have come from inside that lock in this very
        thread, and a stop must not deadlock waiting for a lock the failure still holds (HC#3)."""
        try:
            taken = mon.lock.acquire(timeout=STOP_LOCK_WAIT_S)
            try:
                return list(mon.ledger.requests)
            finally:
                if taken:
                    mon.lock.release()
        except Exception:                         # noqa: BLE001 - no monitor, no rows, no decision
            return []

    def _offer_stop(self, call, call_dir, rows, view_window):
        """THE stop decision, wherever settlement reaches it, and the only place it is made (HC#2).

        Three call sites: the moment `_follow` returns, the moment reconciliation has measured rows
        that were pending, and the way out of a failure. The first offer wins - the call's own record
        of it is the guard - so the later sites add nothing when the first already stopped the run.

        **Nothing here raises before the stop is persisted.** The reading, the rule's check, the entry
        and its timestamp are all total: a failure preparing any of them would be a failure with the
        excess already observed, which is the whole class this closes (HC#0). The call record is
        written with the offered stop where that is possible, and a record that cannot be written
        does not take the stop down with it - the ledger already has it."""
        if not view_window:
            return None
        if call.get("stop"):
            # already offered, possibly by a site that could not finish writing the record (HD#0):
            # complete the diagnostic, and never offer the same call's stop twice
            self._record_stop(call, call_dir)
            return call["stop"]
        try:
            observed, _unreadable = bound.observed_rows(rows)
            if not bound.check_observed(observed, view_window):
                return None
            at, note = self._now()
            entry = bound.excess(call["call_id"], observed, at)
            if note:
                entry = {**entry, "clock": note}
            try:
                json.dumps(entry)                 # a count past the interpreter's digit limit (HC#0) is
            except Exception as exc:              # still a count: the stop is written without it, saying so
                entry = {**{k: v for k, v in entry.items() if k != "observed"},
                         "stamp": f"observed-unrenderable: {exc!r}"}
        except Exception as exc:                  # noqa: BLE001 - a defect in the preparation stops the
            # run as a failed lock does (BE#0): fail closed, and say which half of this code failed
            entry = {"code": bound.STOP_CODE, "call_id": call.get("call_id"), "observed": 0, "at": None,
                     "detail": f"{bound.STOP_CODE} {call.get('call_id')}: the stop decision failed in this code",
                     "stamp": f"offer-internal-error: {exc!r}"}
        offered = self._stop_run(entry, into=call)
        call["stop"] = offered
        self._record_stop(call, call_dir)
        return offered

    def _record_stop(self, call, call_dir):
        """The call's own record of its stop, written wherever that is possible.

        A record that cannot be written does not take the stop down with it: the ledger already has
        it, and this is the diagnostic, not the decision."""
        try:
            records.write_json(self.run_dir, call_dir / "call.json", call)
        except Exception:                         # noqa: BLE001 - the stop is in the ledger already
            pass

    # --- one call ----------------------------------------------------------------------------

    def call(self, stage, seat, packet, schema, *, reservation, caps, view_window, host_version=None, manifest=None,
             child_seat=None, profile="hermetic", contract=None, use="judge", read_root=None, max_output_tokens=None):
        """Dispatch one model call and return its call directory (calls/<call_id>/). `use` is the
        call's profile of use (USES): a producing call is Claude's, reading only `read_root`, and
        its profile is recorded as `<profile>-producing` (the flag set it runs under, seats.json);
        `max_output_tokens` is the stage's output-token cap."""
        if not isinstance(reservation, dict) or not reservation.get("call_id"):
            raise Refused(f"RESERVATION_MISSING {stage}: no model call is dispatched without a reservation (design §13.2)")
        call_id, host = reservation["call_id"], seat.partition(":")[0]
        held = self._stage(self.ledger(), stage)["reservations"].get(call_id)
        if held and held["outcome"] == "deferred" and held["seat"] == seat:
            raise breakers.Deferred(f"PROVIDER_DEFERRED {host}: {call_id} was deferred when the breaker opened; "
                                    f"{stage}:{held['item']} waits for the provider")
        if not held or not held["open"] or held["amount"] != reservation.get("amount") or held["seat"] != seat:
            raise Refused(f"RESERVATION_MISSING {call_id}: no open reservation in the supervisor's ledger is this one")
        missing = [cap for cap in ("tokens", "compactions")
                   if not isinstance((caps or {}).get(cap), int) or isinstance((caps or {}).get(cap), bool)]
        if missing:
            self.release(stage, call_id, "refused")
            raise Refused(f"CAP_MISSING {call_id}: {', '.join(missing)}; no agent-backed dispatch starts without "
                          f"both caps (design §13.2)")
        # ... and a view-window call needs it on ANY host, because check (d) reserves exactly what this call
        # declared for its answer - there is no constant standing in for it (the ruling of 2026-10-22)
        if (max_output_tokens is not None or host == "claude" or view_window) and not (
                isinstance(max_output_tokens, int) and not isinstance(max_output_tokens, bool) and max_output_tokens > 0):
            self.release(stage, call_id, "refused")
            raise Refused(f"CAP_UNDECLARED {call_id}: output-token cap {max_output_tokens!r}; a Claude call and every "
                          f"view-window call declare the stage's output-token cap as a positive integer, apart from the "
                          f"episode's token and compaction caps")
        if use not in USES or (use == "producing") != (read_root is not None) or (use == "producing" and host != "claude") \
                or (use == "producing" and not plain_tree(read_root)):
            self.release(stage, call_id, "refused")
            raise Refused(f"USE_REFUSED {call_id}: use {use!r} on {host} with read root {read_root!r}; a producing call is "
                          f"Claude's and reads one declared directory of plain files, any other reads none (plan WP-03)")
        try:
            self.breaker.require_closed(host, self.clock())
        except breakers.Deferred:
            self._defer(stage, call_id, held["item"], host)
            raise
        schema_bytes = packets.schema_bytes(schema) if schema is not None else None
        runner_profile, profile = profile, f"{profile}-producing" if use == "producing" else profile
        problems = packets.check(packet, call_id, schema_bytes)
        host_version = host_version or gate.seats(self.seats_path)["hosts"][host]["version"]
        try:
            self._stopped(call_id)
            if problems:
                raise Refused(f"PACKET_REFUSED {call_id}: " + "; ".join(problems))
            admitted = self._admit_seat(stage, seat, call_id, host, host_version, profile, view_window, packet,
                                        schema_bytes, manifest, max_output_tokens, runner_profile)
            self._admit_runner(call_id, host)
        except Refused:
            self.release(stage, call_id, "refused")
            raise

        provider_model, _, effort = seat.partition(":")[2].rpartition("/")
        try:
            # admission, held through the launch: a breaker transition or a run stop recorded by any
            # running call either precedes this (refused) or follows the launch (design §13.2)
            with self.breaker.admitting(host, self.clock()), self._lock():
                ledger = self.ledger()
                held = self._stage(ledger, stage)["reservations"][call_id]
                self._stopped(call_id, ledger)
                if held["outcome"] == "deferred":
                    raise breakers.Deferred(f"PROVIDER_DEFERRED {host}: {call_id} was deferred when the breaker opened")
                call_dir = stagelock.confine(self.run_dir, self.run_dir / "calls" / call_id)
                if call_dir.exists():
                    raise Refused(f"CALL_EXISTS {call_dir}")
                held["dispatched_at"] = self.clock()
                self._write(ledger)
                capture = call_dir / "capture"
                capture.mkdir(parents=True)
                cell = pathlib.Path(tempfile.mkdtemp(prefix=f"{call_id}-", dir=self.cell_root))
                for part in ("home", "config", "cwd"):
                    (cell / part).mkdir()
                pinned = gate.seats(self.seats_path)["hosts"][host]
                # what the host loads by itself under the profile, declared per host version (seats.json `context`)
                builtin = (pinned.get("context") or {}).get(profile, {}) if pinned.get("version") == host_version else {}
                manifest = {"workdir_path": str(cell / "cwd"), "workdir_files": [], "instructions": [],
                            "appended_prompts": [], "skills": [], "agents": [], "hooks": [], "mcp_servers": [], **builtin,
                            **(admitted["declared"] or {})}
                if use == "producing":  # the read root is the cell's working directory, holding the declared files (claude-run bind)
                    shutil.copytree(read_root, cell / "cwd", dirs_exist_ok=True)
                    manifest.update(workdir_path=str(cell / "cwd"), workdir_files=listing(cell / "cwd"))
                (call_dir / "packet.md").write_bytes(packet)
                # the declared appended prompts, delivered: the bytes admission counted are written out of
                # the snapshot and handed to the adapter with the sha256 they were declared at, so what the
                # host receives, what the record carries and what was counted are the same bytes (BB#2)
                delivered = []
                for n, snapshot in enumerate(admitted["snapshots"].get("appended_prompts") or [], 1):
                    name = re.sub(r"[^A-Za-z0-9._-]", "_", snapshot.get("name") or f"prompt-{n}")
                    path = stagelock.confine(self.run_dir, call_dir / "appended" / f"{n:02d}-{name}")
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(snapshot["body"])
                    delivered.append({"name": snapshot.get("name") or f"prompt-{n}", "path": str(path),
                                      "sha256": snapshot["sha256"], "bytes": snapshot["bytes"]})
                if schema_bytes is not None:
                    (call_dir / "schema.json").write_bytes(schema_bytes)
                if contract is not None:
                    records.write_json(self.run_dir, call_dir / "contract.json", contract)
                call = {"schema": "DistillCall/v1", "call_id": call_id, "stage": stage, "item": held["item"],
                        "attempt": int(call_id.rpartition("-a")[2]), "host": host, "host_version": host_version,
                        "seat": seat, "child_seat": child_seat, "profile": profile, "manifest": manifest,
                        "schema_sha256": packets.sha256_bytes(schema_bytes) if schema_bytes is not None else None,
                        "view_window": bool(view_window), "realization": self.realization, "exit_status": None,
                        # what the boundary decided for this call, so the gate judges the bound from the
                        # call directory alone rather than reaching for the run (the seam record 2026-10-22)
                        "bound": {"limit": bound.INPUT_BOUND, "driver_bytes": admitted["driver_bytes"],
                                   "context_capacity": admitted.get("context_capacity"),
                                   "output_reservation": max_output_tokens if view_window else None,
                                   "stop_standing": bool(self._blocked(ledger))},
                        "wall_ms": None, "stopped": None, "contract": "required" if contract is not None else "none",
                        "provider_signals": [], "caps": caps, "use": use, "max_output_tokens": max_output_tokens,
                        "runner_refused": None,
                        "reservation": {k: held[k] for k in ("amount", "calibration", "tranche", "declaration_seq")}}
                records.write_json(self.run_dir, call_dir / "call.json", call)
                spec = {"call_id": call_id, "stage": stage, "seat": seat, "model": provider_model, "effort": effort,
                        "host_version": host_version, "profile": runner_profile, "call_profile": profile,
                        "host_bin": os.path.expanduser(pinned["path"]), "workdir": manifest["workdir_path"],
                        "schema_path": str(call_dir / "schema.json") if schema_bytes is not None else None,
                        "cell": str(cell), "capture": str(capture), "caps": caps, "use": use,
                        "read_root": manifest["workdir_path"] if use == "producing" else None, "max_output_tokens": max_output_tokens,
                        "view_window": bool(view_window), "appended_prompts": delivered,
                        "flags_sha256": gate.pinned_flags_sha256(host, host_version, profile)}
                env = self.runner_env(call_id, cell, capture, host, host_version, spec["host_bin"])
                began = time.monotonic()
                proc = subprocess.Popen(self.runner(host, spec), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, env=env, start_new_session=True)
        except breakers.Deferred:
            self._defer(stage, call_id, held["item"], host)
            raise
        except Refused as exc:
            if not str(exc).startswith("CALL_EXISTS"):
                self.release(stage, call_id, "refused")
            raise

        # HB#0/HC#2: THE STOP DECISION IS THE FIRST THING SETTLEMENT DOES, and `_offer_stop` is the one
        # place it is made. Three review rounds each found another statement between the process ending
        # and the stop that could fail and discard an observed excess; the fourth found two more places
        # the decision has to be reachable from - after reconciliation measures a row that was pending,
        # and on the way out of a failure. All three call sites are the same method, the first offer
        # wins, and nothing in it raises.
        monitor_held = {}
        try:
            exit_status, stdout, stderr, mon, stopped, wall_ms = self._follow(host, proc, began, packet, capture,
                                                                              cell, caps, max_output_tokens,
                                                                              monitor=monitor_held)
            excess = self._offer_stop(call, call_dir, self._rows_snapshot(mon), view_window)
            (call_dir / "result.json").write_bytes(stdout)
            # the runner's stderr is kept only as the refusal it names: its trace carries prompt and
            # output bodies, and the capture keeps none (design §3.2)
            refused = ADAPTER_REFUSAL[host].search(stderr) if exit_status not in (0, None) else None
            if host == "codex" and not (capture / "frames.jsonl").exists():  # codex-run's capture wrote its own: never replaced
                channels = {"dir": "info", "type": "channels", "channels": list(CODEX_CHANNELS)}
                (capture / "frames.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n"
                                                              for r in [channels, *mon.feed.records]), encoding="utf-8")
            projects = cell / "config" / "projects"
            if projects.is_dir():
                shutil.copytree(projects, capture / "transcripts")
            result = gate.Call(call_dir).result
            reconciled = self._reconcile(call_dir, call, mon, result if isinstance(result, dict) else {},
                                         stopped, exit_status)
            # HC#2: reconciliation can MEASURE a row that was still pending when the rows were first read -
            # a compaction measured from the aggregate - so the excess may exist only now. The offer is made
            # here, before the seat projection, the usage record and everything after them.
            excess = self._offer_stop(call, call_dir, self._rows_snapshot(mon), view_window) or excess
            usage = self._usage(call_dir, call, mon, reconciled, wall_ms)
            records.write_json(self.run_dir, call_dir / "usage.json", usage)
            self._delete_cell(cell, call_dir)  # only now: usage is captured before any temporary home goes (§13.3)

            if host == "claude":
                events = list(mon.ledger.events)
                if isinstance(result, dict) and result.get("type") == "result" and mon.ledger.result is None:
                    events.append(result)
                signals = breakers.claude_signals(events, max_output_tokens)
            else:
                signals = breakers.codex_signals(mon.feed.records, gate.Call(call_dir).events)
            if self.breaker.observe(host, signals, self.clock()) is not None:
                self._defer_outstanding(host)
            stopping = [sig for sig in signals if sig["kind"] in ("limit", "unrecognised")]
            if stopping:
                self.breaker.defer(host, f"{stage}:{held['item']}")  # the item that met the signal waits too
            call.update(exit_status=exit_status, wall_ms=wall_ms, stopped=stopped, provider_signals=breakers.report(host, signals),
                        runner_refused=refused.group(0).decode("utf-8", "replace").split(": ", 1)[1] if refused else None)
            if view_window:
                observed, missing = bound.observed_input(usage["requests"])
                call["input_observed"] = observed
                # there is no fourth decision here: the written record holds the same rows under the same
                # policy (HC#1), so a decision over it is the one made above, only later. A site no control
                # can tell apart from its absence is not a site.
                if missing:  # a usage record missing a component is not a smaller number (bound.observed_of)
                    # HA#0: and it is not a reason to forget an excess the COMPLETE rows already establish.
                    # `observed_input` answers both questions independently, so the stop above is written
                    # first and the call record carries it; this refusal is still what the call fails with.
                    records.write_json(self.run_dir, call_dir / "call.json", call)
                    raise Refused(f"USAGE_INCOMPLETE {call_id}: {', '.join(missing)}; the observed input of a call is "
                                  "input + cache creation + cache read, and a missing component is not a zero")
            records.write_json(self.run_dir, call_dir / "call.json", call)
            if exit_status is not None:  # a runner that never exited has no receipt (the gate refuses the call for it)
                self._receipt(call_dir, stage, call_id, seat, exit_status)
            outcome = "deferred" if stopping else stopped["outcome"] if stopped else "completed" if exit_status == 0 else "failed"
            self.charge(stage, call_id, usages.totals(usage), outcome, caps)
            if excess:
                raise Refused(stop_detail(excess))
            return call_dir
        except BaseException:
            # HC#3: an exception anywhere above, including out of `_follow` itself, leaves the monitor's
            # rows as evidence already in hand. The offer is made from them and the ORIGINAL failure is
            # what the caller gets - a stop that could not be offered never replaces it.
            held_monitor = monitor_held.get("mon")
            if held_monitor is not None:
                try:
                    self._offer_stop(call, call_dir, self._rows_snapshot(held_monitor), view_window)
                except Exception:                 # noqa: BLE001 - the original failure is the one that matters
                    pass
            raise

    def _stopped(self, call_id, ledger=None):
        """Refuse `call_id` while the run is stopped - unless the rule says the stop has lifted.

        A bound excess is the one stop a run can come back from, and only one way: the host allowance is
        re-measured and declared through `declare --amend` at a later sequence than the excess recorded
        (`bound.lifted`). Every other stop code stays as it was."""
        blocked = self._blocked(ledger)
        if blocked:
            raise Refused(f"{blocked}, {call_id} included")

    def _blocked(self, ledger=None):
        """The run's standing stop as the rule reads it, or None when dispatch may go on."""
        stopped = (ledger or self.ledger())["stopped"]
        if not stopped:
            return None
        _run, _digest, amendments = records.declaration_state(self.run_dir, who="dispatch")
        return bound.blocked(stopped, amendments)

    def _defer(self, stage, call_id, item, host):
        """A call refused at an open breaker: its reservation closes unspent, its item waits."""
        self.release(stage, call_id, "deferred")
        self.breaker.defer(host, f"{stage}:{item}")

    def _signal(self, host, signals):
        """A structured provider signal read while a call runs (design §13.2): the breaker opens
        at once, before the call returns, and the provider's reserved work is recorded deferred."""
        if self.breaker.observe(host, signals, self.clock()) is not None:
            self._defer_outstanding(host)

    def _defer_outstanding(self, host):
        """Every open reservation for `host` that has not started: closed unspent, its item deferred."""
        deferred = []
        with self._lock():
            ledger = self.ledger()
            for stage, entry in ledger["stages"].items():
                for held in entry["reservations"].values():
                    if held["open"] and held["seat"].partition(":")[0] == host and held.get("dispatched_at") is None:
                        held.update(open=False, outcome="deferred")
                        deferred.append(f"{stage}:{held['item']}")
            self._write(ledger)
        for item in deferred:
            self.breaker.defer(host, item)

    def _admit_runner(self, call_id, host):
        """The realization boundary (plan conventions): the pinned runner runs only a call declared
        live, and any other runner, a fake host above all, only a call declared golden."""
        pinned = self.runner is runner_argv
        if self.realization not in REALIZATIONS or (self.realization == "live") != pinned:
            raise Refused(f"RUNNER_REALIZATION_MISMATCH {call_id}: realization {self.realization!r} with "
                          f"{'the pinned runner ' + str(RUNNERS[host]) if pinned else 'a runner that is not the pinned one'}; "
                          f"a live call runs only the pinned runner, any other runner only under golden")

    def _admit_seat(self, stage, seat, call_id, host, host_version, profile, view_window, packet,
                    schema_bytes, manifest=None, max_output_tokens=None, runner_profile=None):
        """The seat must be one the run declares for the stage, or one seats.json pins for it
        (design §4). A view-window call also needs its host allowance: measured for this host
        version and profile in seats.json, declared for the seat in run.json with the same value,
        host version and flag set, and leaving room for the driver's part — the UTF-8 bytes of
        the packet, the schema and whatever the call's manifest declares it carries, each token
        covering at least one byte — under the bound `runlib/bound.py` owns (the input-bound
        amendment record, and the seam record of 2026-10-22).

        Every declared part is read once here, and what this call declares must be something its adapter
        can carry: an appended prompt the host cannot be sent, or an output cap it cannot be told, is
        refused by name rather than recorded (BB#1, BB#2, BB#4)."""
        run, _digest, _amendments = records.declaration_state(self.run_dir, who="dispatch")
        held = gate.seats(self.seats_path)
        declared = {v for k, v in run["seats"].items() if k == stage or k.startswith(f"{stage}.")}
        if seat not in declared | set(held.get("stage_seats", {}).get(stage, [])):
            raise Refused(f"SEAT_UNPINNED {call_id}: {seat} is neither declared in run.json nor pinned in seats.json for {stage}")
        # what the driver sends, counted by the rule's owner over everything this call SENDS: the packet
        # (its template, principles block and window payload are one object by now), the schema, and what
        # the call's own manifest declares it carries. The host's builtin context is not here - that is the
        # measured allowance, and counting it twice would charge the same tokens to both sides. Counted for
        # every call, window or not, because the record keeps it either way.
        # ... read ONCE: the count, the evidence the record carries and the bytes the adapter delivers are
        # three views of one snapshot, not three reads of a file that can move between them (BB#1)
        driver, evidence, snapshots, problems = bound.admitted_parts(packet, schema_bytes, manifest)
        if problems:
            raise Refused(f"{problems[0].split()[0]} {call_id}: " + "; ".join(problems))
        # BC#2: a declared instruction is compared with what the host REPORTS loading, and the Claude
        # observer reports its rendered form. The record keeps the raw sha256 and length the payload
        # count counted, and beside them the same bytes in the observer's form, computed by the
        # observer's own function (gate.observer_sha256) rather than by a copy of its rule here.
        for row, snapshot in zip(evidence.get("instructions") or [], snapshots.get("instructions") or []):
            row["observer_sha256"] = gate.observer_sha256(host, snapshot["body"])
        admitted = {"driver_bytes": driver, "declared": evidence, "snapshots": snapshots}
        # what this call declares must be something its adapter can carry. A declaration the host never
        # receives is not a declaration: it is a record of an intention, and the gate judges the call
        # against it afterwards (BB#2, BB#4).
        conveys = adapter_conveys(host, runner_profile)
        if snapshots.get("appended_prompts") and "appended_prompts" not in conveys:
            raise Refused(f"APPENDED_PROMPT_UNDELIVERABLE {call_id}: {len(snapshots['appended_prompts'])} appended "
                          f"system prompt(s) are declared, and {host}'s adapter under profile {runner_profile!r} has "
                          f"no way to send them; a prompt that is recorded and not sent fails the call's own "
                          f"effective-context check")
        if not view_window:
            return admitted
        # (d) reserves output tokens on the seat's context, so the host has to be TOLD the cap. An adapter
        # that cannot convey it leaves the reservation on the driver's side alone, which reserves nothing.
        if "output_cap" not in conveys:
            raise Refused(f"CAP_UNDELIVERABLE {call_id}: {host}'s adapter under profile {runner_profile!r} cannot "
                          f"convey an output-token cap, so the {max_output_tokens} tokens check (d) reserves would "
                          f"never be reserved at the host; no view-window call runs on it")
        slot = (((held["hosts"].get(host) or {}).get("host_allowance") or {}).get(profile)
                if (held["hosts"].get(host) or {}).get("version") == host_version else None)
        if not slot or slot.get("measured") is not True or not isinstance(slot.get("allowance_tokens"), int):
            raise Refused(f"ALLOWANCE_UNMEASURED {call_id}: seats.json has no measured host allowance for {host} "
                          f"{host_version} {profile}; preflight (WP-23) measures it, and no view-window call runs without it")
        declared_allowance = (run.get("host_allowance") or {}).get(seat) or {}
        want = {"allowance_tokens": slot["allowance_tokens"], "host_version": host_version,
                "flag_set_sha256": gate.pinned_flags_sha256(host, host_version, profile, path=self.seats_path)}
        if {k: declared_allowance.get(k) for k in want} != want:
            raise Refused(f"ALLOWANCE_MISMATCH {call_id}: run.json declares {declared_allowance or 'nothing'} for {seat}, "
                          f"the measured allowance is {want}")
        # (d) is about the seat's context, so its size is host-reported evidence seats.json declares. There
        # is no default: an invented capacity makes (d) a check about nothing (BA#1).
        capacity, basis = gate.seat_capacity(seat, host_version, path=self.seats_path)
        if capacity is None:
            raise Refused(f"CAPACITY_UNDECLARED {call_id}: {basis}; no view-window call runs against a capacity "
                          "nobody measured (the seat's context window is host-reported)")
        admitted["context_capacity"] = capacity
        # (d) reserves what THIS call declared for its answer. `call` has already refused a view-window
        # call without a positive cap, so this is the number the call will run under, not a stand-in.
        errors = bound.check_bound(driver, bound.limits(slot["allowance_tokens"], seat=seat, capacity=capacity,
                                                        reservation=max_output_tokens))
        if errors:
            # one code at the boundary, quoting which of the rule's two checks failed: (a) the bound less
            # the allowance, (d) the seat's capacity less the allowance and the reserved output
            raise Refused(f"WINDOW_OVER_BOUND {call_id}: " + "; ".join(errors)
                          + "; the window is split before dispatch")
        return admitted

    def runner_env(self, call_id, cell, capture, host, host_version, host_bin):
        """The environment one launched runner receives - the only place it is assembled.

        A receipt the runner writes for itself is capture evidence, never the call's receipt (plan
        addendum); REVIEW_CALL_ID is the adapters' name for the call, and claude-run reads
        DISTILL_CALL_ID. Codex takes its host through the environment where Claude takes it as
        arguments."""
        env = {k: v for k, v in self.env.items() if k != "REVIEW_CRITERION_SCHEMA"}
        env.update(REVIEW_CAPTURE_DIR=str(capture), DISTILL_CELL=str(cell), DISTILL_CALL_ID=call_id,
                   REVIEW_CALL_ID=call_id, REVIEW_RECEIPT_DIR=str(pathlib.Path(capture) / "runner-receipts"))
        if host == "codex":
            env.update(RUST_LOG=CODEX_TRACE, CODEX_RUN_BIN=host_bin, CODEX_RUN_VERSION=host_version)
        return env

    def _follow(self, host, proc, began, packet, capture, cell, caps, output_cap=None, monitor=None):
        """Follow a launched runner to its end: the monitor, the stop at either cap, the drain."""
        tripped = threading.Event()
        mon = self.monitor(host, caps, on_trip=lambda _why: tripped.set(), on_signal=lambda sigs: self._signal(host, sigs),
                           output_cap=output_cap)
        if monitor is not None:
            monitor["mon"] = mon                  # HC#3: the rows stay reachable if this never returns
        sampler = stop.TreeSampler(proc.pid, interval=0.05)
        sampler.start()
        out, err = [], []

        def feed():
            try:
                proc.stdin.write(packet)
                proc.stdin.close()
            except OSError:
                pass

        def read_out():
            out.append(proc.stdout.read())

        def read_err():  # nothing is kept but an adapter's named refusal
            for raw in iter(proc.stderr.readline, b""):
                if host == "codex":
                    mon.line(raw.decode("utf-8", "replace"))
                if ADAPTER_REFUSAL[host].match(raw):
                    err.append(raw)

        pipes = [threading.Thread(target=fn, daemon=True) for fn in (feed, read_out, read_err)]
        tails = [monitors.StreamTail(capture / "stream.jsonl", mon), monitors.TranscriptTail(cell / "config", mon)] \
            if host == "claude" else []
        for thread in pipes + tails:
            thread.start()
        # the runner is watched without being reaped until every stop of the call is done: while it
        # is unreaped, its pid and the id of the group it leads are provably its own (stop.anchored)
        while not stop.exited(proc) and not tripped.wait(0.01):
            pass
        record = stop.stop_tree(proc, sampler) if tripped.is_set() and not stop.exited(proc) else None
        until = time.monotonic() + self.drain_deadline_s  # one that outlives its stop is the record's survivor, never awaited
        while not stop.exited(proc) and time.monotonic() < until:
            time.sleep(0.01)
        # the readers are drained to their end: a line still in a pipe can trip a cap or carry a send
        # after the freeze, and both belong to this call's accounting and its boundary; meanwhile a
        # cap the monitor trips still stops whatever is left of the tree. The root has exited, so a
        # pipe still open past drain_deadline_s stops the remaining tree as a cap would, and the
        # drain then waits at most another drain_deadline_s: whoever still holds a pipe is outside
        # the stop guarantee (design §13.2), so the call is drain_unfinished, its usage incomplete
        # and its boundary unverified, without naming the holder
        deadline, expired = time.monotonic() + self.drain_deadline_s, False
        while any(thread.is_alive() for thread in pipes):
            for thread in pipes:
                thread.join(DRAIN_POLL_S)
            if record is None and mon.trip is not None:
                record = stop.stop_tree(proc, sampler)
                deadline = time.monotonic() + self.drain_deadline_s
            if time.monotonic() > deadline and any(thread.is_alive() for thread in pipes):
                expired = True
                if record is not None:
                    break
                record = stop.stop_tree(proc, sampler)
                deadline = time.monotonic() + self.drain_deadline_s
        for tail in tails:
            tail.halt.set()
            tail.join()
            tail.poll()
        mon.finish()
        # the monitor is drained: a cap it tripped after the root exited still stops what is left
        # of the tree, and the boundary is judged on every record the monitor read
        if record is None and mon.trip is not None:
            record = stop.stop_tree(proc, sampler)
        stopped = None
        if record is None:
            sampler.halt.set()
        else:
            problems, uncertain = monitors.boundary(mon.ledger, record["freeze_at"], record["kill_at"])
            unfinished = (f"DRAIN_UNFINISHED the runner's pipes were still open past the {self.drain_deadline_s} s drain "
                          f"deadline: the tree was stopped, and what still held a pipe is outside the stop guarantee")
            if expired:
                uncertain.append(unfinished)
            # an expired drain decides the outcome over any cap: what held the pipe is outside the stop
            # guarantee whatever tripped first; the cap's evidence stays beside it
            outcome, why = ("drain_unfinished", unfinished) if expired or mon.trip is None else ("budget_stopped", mon.trip["why"])
            stopped = {"outcome": outcome, "why": why,
                       "cap": {"why": mon.trip["why"], "at": mon.trip.get("at")} if mon.trip is not None else None,
                       "decided_at": record["decided_at"], "freeze_at": record["freeze_at"], "kill_at": record["kill_at"],
                       "tree": record["tree"], "survivors": record["survivors"],
                       "problems": record["problems"] + problems, "uncertain": uncertain,
                       # an expired drain is unverified by rule, whatever was observed: a violation stays in problems
                       "boundary": "STOP_BOUNDARY_UNVERIFIED" if expired
                       else monitors.boundary_verdict(record["problems"] + problems, uncertain)}
        proc.poll()  # every stop is done: the runner is reaped only now, if it has exited
        return proc.returncode, b"".join(out), b"".join(err), mon, stopped, int((time.monotonic() - began) * 1000)

    def _reconcile(self, call_dir, call, mon, result, stopped, exit_status):
        """The monitor's rows against the closing aggregates (design §13.3), and nothing else.

        Split from the usage record (HC#2) so the stop decision can be made the moment reconciliation
        has measured a row that was pending - before the seat projection, the record and the writes.

        Claude: the residual of result.modelUsage over every measured request is attributed to
        the call's one compaction only once every other request and attempt has reconciled — each
        measured and bound to its own transcript api-request record, the host's one record per
        HTTP attempt (design §13.3), so a response with no attempt record, or an attempt record no
        response answers, leaves the accounting incomplete; in any other case it stays unexplained
        — carried as a provisional `aggregate-residual` row for whatever the provisional estimates
        do not already cover — because aggregate agreement alone does not show completeness, and
        no request is made measured by it. Codex: reconcile_codex. `reconciled` holds only when
        every request is measured and nothing is left unexplained."""
        ledger = mon.ledger
        ended = not stopped and exit_status == 0
        if call["host"] == "claude":
            reconciled = False
            if ended and result.get("modelUsage"):
                keys = {"input": "inputTokens", "output": "outputTokens", "cache_read": "cacheReadInputTokens",
                        "cache_creation": "cacheCreationInputTokens"}
                aggregate = {k: sum((u or {}).get(v) or 0 for u in (result.get("modelUsage") or {}).values())
                             for k, v in keys.items()}
                measured = {k: sum(r[k] or 0 for r in ledger.requests if r["state"] == "measured") for k in keys}
                residual = {k: aggregate[k] - measured[k] for k in keys}
                attempts = [r for r in ledger.requests if r["role"] != "compaction"]
                settled = bool(attempts) and all(r["state"] == "measured" and r.get("send_seen") for r in attempts)
                compactions = [r for r in ledger.requests if r["role"] == "compaction" and r["state"] != "measured"]
                if all(v >= 0 for v in residual.values()) and any(residual.values()):
                    if settled and len(compactions) == 1:
                        ledger.measure(compactions[0], residual)  # aggregate-measured, design §13.3's table
                    else:
                        covered = sum(r["estimate"] or 0 for r in ledger.requests if r["state"] == "provisional")
                        if sum(residual.values()) > covered:
                            ledger.open("aggregate-residual", "unknown", None, self.clock(),
                                        estimate=sum(residual.values()) - covered)
                reconciled = settled and all(v >= 0 for v in residual.values()) \
                    and all(r["state"] == "measured" for r in ledger.requests)
        else:
            reconciled = reconcile_codex(call_dir, ledger, self.clock) and ended
        return reconciled

    def _usage(self, call_dir, call, mon, reconciled, wall_ms):
        """usage.json: the seat projection over the capture, and the monitor's own record of the call."""
        observed = gate.observed_seats(gate.Call(call_dir))
        return mon.ledger.record(call["call_id"], call["stage"], call["seat"], observed, wall_ms, reconciled)

    @staticmethod
    def _delete_cell(cell, call_dir):
        if not (pathlib.Path(call_dir) / "usage.json").is_file():
            raise Refused(f"USAGE_UNCAPTURED {call_dir}: the cell is kept until usage.json is written (design §13.3)")
        shutil.rmtree(cell, ignore_errors=True)

    def _receipt(self, call_dir, stage, call_id, seat, exit_status):
        """The call's ReviewReceipt/v1, written once after the runner exited and its capture was
        copied, through the launcher's own writer, so the receipt format keeps one owner (plan
        addendum 2026-10-21T0630--0e0d27e--plan-addendum-wp02.md). The gate recomputes every value."""
        evidence = gate.receipt_evidence(call_dir)
        argv = [sys.executable, str(receipts.LAUNCHER), "--emit-receipt", receipts.method_id(stage, call_id), seat,
                str(exit_status), str(call_dir / "packet.md"), str(call_dir / "result.json")]
        for key, value in evidence.items():
            argv += ["--evidence", f"{key}={'' if value is None else value}"]
        scratch = call_dir / "receipts"
        env = {k: v for k, v in self.env.items() if k != "REVIEW_CRITERION_SCHEMA"}
        env["REVIEW_RECEIPT_DIR"] = str(scratch)
        done = subprocess.run(argv, env=env, capture_output=True, text=True)
        written = sorted(scratch.glob("*.json"))
        if done.returncode != 0 or len(written) != 1:
            raise Refused(f"RECEIPT_MISSING {call_id}: the launcher wrote no receipt (rc {done.returncode}: "
                          f"{done.stderr.strip()[:300]})")
        written[0].replace(call_dir / "receipt.json")
        scratch.rmdir()

    # --- one item: the gate and the one corrective retry ---------------------------------------

    def item(self, stage, item, seat, payload, schema, *, case_type, caps, view_window, tranche="broad", **kwargs):
        """An item's attempts through reservation, dispatch and the gate (design §3.2): a failing
        output is retried once with the validation message; a provider signal or a stop is never
        retried here; every attempt is kept. Outcomes: accepted, failed, not_done, deferred,
        budget_stopped."""
        schema_bytes = packets.schema_bytes(schema) if schema is not None else None
        dirs, text, settled = [], payload, None
        for attempt in (1, 2):
            try:
                reservation = self.reserve(stage, item, seat, case_type, tranche=tranche, attempt=attempt)
            except Exhausted as exc:
                return {"item": item, "outcome": "not_done", "why": str(exc), "attempts": [str(d) for d in dirs]}
            packet = packets.build(reservation["call_id"], stage, seat, text, schema_bytes)
            try:
                call_dir = self.call(stage, seat, packet, schema, reservation=reservation, caps=caps,
                                     view_window=view_window, **kwargs)
            except breakers.Deferred as exc:
                return {"item": item, "outcome": "deferred", "why": str(exc), "attempts": [str(d) for d in dirs]}
            dirs.append(call_dir)
            call = records.read_json(call_dir / "call.json")
            if call["runner_refused"]:  # the adapter refused before sending: a retry meets the same host
                return {"item": item, "outcome": "failed", "why": call["runner_refused"],
                        "codes": [call["runner_refused"].split()[0]], "attempts": [str(d) for d in dirs]}
            if call["provider_signals"]:  # recorded deferred by call(), never retried here; a stop's boundary travels too
                return {"item": item, "outcome": "deferred", "why": "; ".join(call["provider_signals"]),
                        "boundary": (call["stopped"] or {}).get("boundary"), "attempts": [str(d) for d in dirs]}
            if call["stopped"]:  # the boundary verdict travels with the outcome (design §8.7's re-run reads it, WP-18)
                return {"item": item, "outcome": "budget_stopped" if call["stopped"]["outcome"] == "budget_stopped" else "failed",
                        "why": call["stopped"]["why"], "boundary": call["stopped"]["boundary"],
                        "attempts": [str(d) for d in dirs]}
            settled = gate.settle(dirs)
            if settled["ok"] or not settled["retry"]:
                break
            text = payload + "\n" + gate.correction(settled["attempts"][-1])
        return {"item": item, "outcome": "accepted" if settled["ok"] else "failed", "accepted": settled["accepted"],
                "codes": sorted(set(settled["codes"]) | {c for a in settled["attempts"] for c in a["codes"]}),
                "attempts": [str(d) for d in dirs]}


# --- dispatch edges: the import closure and its executor sites ----------------------------------

class _Module:
    """One parsed module: its aliases, its parents and the assignments a Name may resolve to."""

    def __init__(self, path, rel, source=None):
        self.path, self.rel = path, rel
        self.tree = ast.parse(source if source is not None else path.read_text(encoding="utf-8"), str(rel))
        self.parent, self.aliases = {}, {}
        for node in ast.walk(self.tree):
            for kid in ast.iter_child_nodes(node):
                self.parent[kid] = node
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.aliases[(a.asname or a.name).split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    self.aliases[a.asname or a.name] = f"{node.module}.{a.name}"

    def dotted(self, node):
        if isinstance(node, ast.Name):
            return self.aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = self.dotted(node.value)
            return f"{base}.{node.attr}" if base else None
        return None

    def assigned(self, name):
        """The values bound to `name` in its enclosing functions, then at module level."""
        scopes, node = [], name
        while node in self.parent:
            node = self.parent[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                scopes.append(node)
        found = []
        for scope in scopes:
            found += [n.value for n in ast.walk(scope) if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == name.id for t in n.targets)]
            if found:
                return found
        return [n.value for n in self.tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name.id for t in n.targets)]

    def values(self, node, depth=0):
        """The strings an expression can be, with UNKNOWN for what the trace cannot resolve."""
        if depth > 8:
            return [UNKNOWN]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.JoinedStr):
            return ["".join(v.value if isinstance(v, ast.Constant) else UNKNOWN for v in node.values)]
        name = self.dotted(node)
        if name == "sys.executable":
            return [PYTHON]
        if isinstance(node, ast.Name):
            found = self.assigned(node)
            return [v for f in found for v in self.values(f, depth + 1)] or [UNKNOWN]
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Add)):
            sep = "/" if isinstance(node.op, ast.Div) else ""
            return [a + sep + b for a in self.values(node.left, depth + 1) for b in self.values(node.right, depth + 1)]
        if isinstance(node, ast.Call):
            func = self.dotted(node.func)
            if func in ("str", "os.fspath", "pathlib.Path", "Path", "os.path.expanduser", "os.path.abspath",
                        "os.path.realpath") and node.args:
                return self.values(node.args[0], depth + 1)
            if func == "os.path.join" and node.args:
                parts = [self.values(a, depth + 1) for a in node.args]
                joined = [""]
                for options in parts:
                    joined = [f"{j}/{o}" if j else o for j in joined for o in options]
                return joined
            if isinstance(node.func, ast.Attribute) and node.func.attr in ("resolve", "expanduser", "absolute"):
                return self.values(node.func.value, depth + 1)
        return [UNKNOWN]

    def heads(self, node, depth=0):
        """[(argv[0] candidates, the remaining argument nodes)] of an argv expression; a string
        is a shell command line."""
        if depth > 8:
            return [([UNKNOWN], [])]
        if isinstance(node, ast.Name):
            found = self.assigned(node)
            return [h for f in found for h in self.heads(f, depth + 1)] or [([UNKNOWN], [])]
        if self._stringy(node):
            return [(["<shell>"], [node])]
        return [([UNKNOWN], []) if not argv or argv[0] is UNREAD else (self.values(argv[0]), argv[1:])
                for argv in self.argvs(node, depth)]

    def argvs(self, node, depth=0):
        """The argument lists an argv expression can be, each a list of element nodes: a list or
        tuple, a starred list inside it, a concatenation — both sides kept, in order — or a name
        bound to one of these; a part the trace cannot read is UNREAD, kept in its place."""
        if depth > 8:
            return [[UNREAD]]
        if isinstance(node, (ast.List, ast.Tuple)):
            out = [[]]
            for elt in node.elts:
                parts = self.argvs(elt.value, depth + 1) if isinstance(elt, ast.Starred) else [[elt]]
                out = [done + part for done in out for part in parts]
            return out
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) and not self._stringy(node):
            return [left + right for left in self.argvs(node.left, depth + 1) for right in self.argvs(node.right, depth + 1)]
        if isinstance(node, ast.Name):
            found = self.assigned(node)
            return [a for f in found for a in self.argvs(f, depth + 1)] or [[UNREAD]]
        return [[UNREAD]]

    def _stringy(self, node):
        return isinstance(node, (ast.Constant, ast.JoinedStr)) and not (isinstance(node, ast.Constant)
                                                                         and not isinstance(node.value, str)) \
            or (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
                and any(self._stringy(side) for side in (node.left, node.right)))


def _pinned(root):
    """The host binary paths seats.json pins, as written and expanded."""
    held = json.loads((root / "session-distill" / "seats.json").read_text(encoding="utf-8"))
    paths = {h["path"] for h in held["hosts"].values() if h.get("path")}
    return paths | {os.path.expanduser(p) for p in paths}


def _names(path, text):
    """True when a value the trace read can only name `path`: it is that path, or its unread head
    is followed by a known tail of whole path segments that `path` ends with."""
    if text.endswith(path):
        return True
    tail = text.rsplit(UNKNOWN, 1)[1] if UNKNOWN in text else ""
    return tail.startswith("/") and bool(tail.strip("/")) and path.endswith(tail)


def _spelling(mod, spellings=None):
    """The one spelling of the admitted forms this file declares, or None when it declares none.

    No declaration means no admitted form, which is the default-deny direction: a new file with a
    dispatch site is refused until its spelling is written down, rather than admitted because the
    judge happened to recognise a shape in it."""
    for row in (FORM_SPELLINGS if spellings is None else spellings):
        if row["site"] == str(mod.rel):
            return row
    return None


def _exact_call(mod, node, dotted, arity):
    """`node` is EXACTLY a call of `dotted` with `arity` positional arguments, no keywords and no
    starred argument.

    The arity is the whole point. The judge used to peel the first argument of whatever wrapper it
    recognised, so `pathlib.Path(__file__, "/fixture/other.py")` was admitted as "its own file"
    while the value it produces is the second argument (r3 #4)."""
    return (isinstance(node, ast.Call) and mod.dotted(node.func) == dotted
            and len(node.args) == arity and not node.keywords
            and not any(isinstance(arg, ast.Starred) for arg in node.args))


def _own_file(mod, node, spellings=None):
    """Whether this expression is EXACTLY `str(pathlib.Path(__file__).resolve())`, in this file's
    declared spelling: `str` of one argument, `.resolve()` of none, `pathlib.Path` of exactly one
    positional argument, and that argument the name `__file__`.

    A closure module running its own file runs a closure file — there is nothing to declare and
    nothing a declaration could add, because the identity IS the expression. The driver's and the
    inventory's self-tests both run their own entry point as a real process (R2#2, R2#3, R2#7), and
    the value is computed, so the trace cannot name it.

    Nothing else is admitted: not another wrapper, not an extra argument, not a keyword, not a
    join (`/`, `joinpath`), and not `.parent` — which names a DIRECTORY, and python runs a directory
    as its `__main__.py`, a different program entirely."""
    row = _spelling(mod, spellings)
    if row is None or not _exact_call(mod, node, row["str"], 1):
        return False
    resolved = node.args[0]
    if not (isinstance(resolved, ast.Call) and not resolved.args and not resolved.keywords
            and isinstance(resolved.func, ast.Attribute) and resolved.func.attr == "resolve"):
        return False
    path = resolved.func.value
    return (_exact_call(mod, path, row["path"], 1)
            and isinstance(path.args[0], ast.Name) and path.args[0].id == "__file__")


def _copy_member(mod, node, copies=None, spellings=None):
    """`(entry, member)` when this expression is EXACTLY
    `str(inventory.copied_member(<root>, "<literal>"))` and the literal is a member THIS SITE
    declares in `COPY_RUNS`; `(None, what was seen)` otherwise, and `(None, None)` when the
    expression is not of that shape at all.

    Two things the old admission did not ask. The arity: the owner's call was peeled out of any
    wrapper, so a join around it selected a different file. And WHICH member: every call of the
    owner was admitted as though it produced the one the site declared, so the driver-only site
    admitted `copied_member(copy, "learn/redact.py")` as well (r3 #4). The member is required to be
    a literal because an expression's value is not something this judge can read, and the admission
    has to be decidable here rather than at runtime.

    The `<root>` expression is deliberately unconstrained: which trees this process actually copied
    is a runtime fact, and `inventory.copied_member` refuses a root this process did not copy by
    name (`COPY_UNVERIFIED`), which is where that question belongs."""
    copies = COPY_RUNS if copies is None else copies
    row = _spelling(mod, spellings)
    if row is None or not _exact_call(mod, node, row["str"], 1):
        return None, None
    call = node.args[0]
    if not _exact_call(mod, call, row["member"], 2):
        # Anything composed around the owner's call is a FORM problem — `_reaches_for_a_form` names
        # it — because which member the site names is only readable once the form is the exact one.
        return None, None
    member = call.args[1]
    if not (isinstance(member, ast.Constant) and isinstance(member.value, str)):
        return None, "not a string literal"
    for entry in copies:
        if entry["site"] == str(mod.rel) and member.value in entry["paths"]:
            return entry, member.value
    return None, member.value


def _copy_run(mod, node, copies=None, spellings=None):
    """The `COPY_RUNS` entry that admits this program, or None."""
    return _copy_member(mod, node, copies, spellings)[0]


def _reaches_for_a_form(mod, node, spellings=None):
    """Which admitted form this expression reaches for without being it, or None.

    Only an expression that reaches for a form gets the form refusal; a program the trace simply
    could not read keeps the refusal it has always had, so this narrowing adds a name instead of
    renaming an existing failure."""
    row = _spelling(mod, spellings)
    if row is None or node is None:
        return None
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and inner.id == "__file__":
            return "its own file"
        if isinstance(inner, ast.Call) and mod.dotted(inner.func) == row["member"]:
            return "a copied member"
    return None


def _inline_constant(mod, name):
    """The text of a module-level string constant of this file, or None.

    Module level, because that is what a declaration can name and a hash can pin. Adjacent string
    literals are one constant by the time this reads them; anything computed is not a constant."""
    for node in mod.tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            return node.value.value
    return None


def _inline_row(mod, node, inlines=None):
    """The `INLINE_PROGRAMS` row this `-c` argument names, or None."""
    if not isinstance(node, ast.Name):
        return None
    for row in (INLINE_PROGRAMS if inlines is None else inlines):
        if row["site"] == str(mod.rel) and row["name"] == node.id:
            return row
    return None


def _unread(text):
    """Whether the trace read nothing of this value: it is the hole and the separators around it."""
    return bool(text) and UNKNOWN in text and not text.replace(UNKNOWN, "").strip("/.")


def _judge_program(mod, program, rest, line, pinned, problems, depth=0, runs=(), follow=None,
                   argv_node=None):
    """Append to `problems` the violations of one site whose program is `program`; a declared
    script it runs (`runs`, SCRIPT_RUNS) is appended to `follow`, to join the closure."""
    where = f"{mod.rel}:{line}"
    base = os.path.basename(program)
    base = base[:-3] if base.endswith(".sh") else base
    if program == "<shell>":
        for text in [v for node in rest[:1] for v in mod.values(node)]:
            if UNKNOWN in text:
                problems.append(f"DISPATCH_UNRESOLVED {where}: a shell command line the trace cannot resolve")
                continue
            _judge_words(mod, _shell_tokens(text), line, pinned, problems)
    elif base in HOST_NAMES or program in pinned:
        problems.append(f"DISPATCH_OUTSIDE_SUPERVISOR {where}: starts {program!r}, which only dispatch.py may start")
    elif UNKNOWN in program and not any(e["site"] == str(mod.rel) and all(g in mod.path.read_text(encoding="utf-8")
                                                                          for g in e["guards"]) for e in GUARDED_PROGRAMS):
        problems.append(f"DISPATCH_UNRESOLVED {where}: a program the trace cannot resolve ({program!r})")
    elif UNKNOWN in program:
        pass  # a guarded program (GUARDED_PROGRAMS)
    elif program == PYTHON:
        # The NODES travel beside the words: what admits a copy-run is the expression at this call,
        # so the words alone are not enough to judge it (R2#5).
        nodes = list(rest)
        words = [mod.values(node) for node in nodes]
        while words and len(words[0]) == 1 and words[0][0] in PY_FLAGS:
            words.pop(0)
            nodes.pop(0)
        flag = words[0] if words else [UNKNOWN]
        flag_node = nodes[0] if nodes else None
        nxt = words[1] if len(words) > 1 else [UNKNOWN]
        declared = [[e for e in runs if e["site"] == str(mod.rel) and _names(e["path"], s)] for s in flag]
        if flag == ["-c"]:
            # The program is admitted as DATA, by declaration, and its insides are not read. The
            # recursion that used to read them judged shapes, and a shape rule over a program that
            # can rewrite its own `sys.argv` before the load can always be worked around (r3 #5).
            row = _inline_row(mod, nodes[1] if len(nodes) > 1 else None)
            elements = list(getattr(argv_node, "elts", None) or [])
            if row is None:
                problems.append(f"DISPATCH_INLINE_UNDECLARED {where}: python -c with a program that is not "
                                f"a module-level constant of this file declared in INLINE_PROGRAMS")
            # The elements are read ONCE, defensively, because this rule is also what makes the
            # indexing below safe: with the refusal taken out, a non-literal argv made the judge die
            # with an AttributeError instead of admitting anything, so the rule could not be
            # reverted and nothing could watch it (r7 D6).
            elif not (isinstance(argv_node, ast.List)
                      and not any(isinstance(e, ast.Starred) for e in elements)):
                problems.append(f"DISPATCH_PROGRAM_FORM {where}: an inline program's argv must be a list "
                                f"literal at the call, or the element its declaration names is not this one")
            else:
                text = _inline_constant(mod, row["name"])
                digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
                if text is None or digest != row["sha256"]:
                    problems.append(f"DISPATCH_INLINE_CHANGED {where}: {row['name']}'s text is "
                                    f"{digest if text is not None else 'not a module-level constant'}, "
                                    f"not the declared {row['sha256']}")
                elif row["loads"] is not None:
                    # `loads` is the index the PROGRAM reads, in its own `sys.argv`. It used to be an
                    # index into the OUTER argv, which is only the same thing while exactly one flag
                    # precedes `-c`: with another flag, or none, admission inspected one element and
                    # the child loaded another (r4 R6). The element is computed from where `-c`
                    # actually sits — `elements[at_c + 1]` is the program text, and the program's
                    # `sys.argv[1]` is the element after it.
                    at_c = next((n for n, element in enumerate(elements) if element is nodes[0]), None)
                    at = None if at_c is None else at_c + 1 + row["loads"]
                    carried = elements[at] if at is not None and 0 <= at < len(elements) else None
                    entry, member = _copy_member(mod, carried) if carried is not None else (None, None)
                    if _own_file(mod, carried) if carried is not None else False:
                        pass            # the file this site is in: already in the closure
                    elif entry is not None:
                        if follow is not None:
                            follow.extend({"site": entry["site"], "path": path} for path in entry["paths"])
                    else:
                        problems.append(f"DISPATCH_INLINE_UNDECLARED {where}: {row['name']} loads "
                                        f"sys.argv[{row['loads']}], element {at} of this call's argv, "
                                        f"which this site does not produce as an admitted program form "
                                        f"({member or 'another expression'})")
        elif any(s.endswith("launch/agent-launch.py") for s in flag):
            if nxt != ["--emit-receipt"]:  # the receipt emitter dispatches nothing; the rest of the launcher does
                problems.append(f"DISPATCH_OUTSIDE_SUPERVISOR {where}: runs the launcher ({nxt!r}), which starts hosts")
        elif any(any(s.endswith(e["path"]) for e in OUT_OF_SCOPE) for s in flag):
            problems.append(f"CLOSURE_IMPORTS_OUT_OF_SCOPE {where}: runs {flag[0]!r}, an out-of-scope executor")
        elif follow is not None and declared and all(len(d) == 1 for d in declared):
            follow.extend(d[0] for d in declared)
        elif _own_file(mod, flag_node):
            if follow is not None:   # it is this file: already in the closure, and recorded as run
                follow.append({"site": str(mod.rel), "path": str(mod.rel)})
        elif _copy_member(mod, flag_node)[0] is not None:
            if follow is not None:   # already in the closure; the entry is what records it ran
                follow.extend({"site": entry["site"], "path": path}
                              for entry in [_copy_run(mod, flag_node)] for path in entry["paths"])
        elif _copy_member(mod, flag_node)[1] is not None:
            problems.append(f"DISPATCH_COPY_MEMBER_UNDECLARED {where}: a copy-run naming "
                            f"{_copy_member(mod, flag_node)[1]!r}, which is not a member this site "
                            f"declares in COPY_RUNS as an exact literal")
        elif _reaches_for_a_form(mod, flag_node) is not None:
            problems.append(f"DISPATCH_PROGRAM_FORM {where}: reaches for {_reaches_for_a_form(mod, flag_node)} "
                            f"without being the one admitted form for it")
        else:
            problems.append(f"DISPATCH_UNRESOLVED {where}: python runs {flag!r}, a script the trace does not follow")
    elif base in SHELLS:
        words = [v for node in rest for v in mod.values(node)]
        if any(UNKNOWN in w for w in words):
            problems.append(f"DISPATCH_UNRESOLVED {where}: {base} with arguments the trace cannot resolve")
        else:
            # The argv element after a `-c`-style flag is a shell LINE and is tokenized as one; every
            # other element stays a word of its own, because re-splitting an argument would change
            # the shape of a quoted one (r4 R5 addendum).
            tokens, previous = [], ""
            for word in words:
                tokens += (_shell_tokens(word) if previous in SHELL_LINE_FLAGS
                           else _plain_word_tokens(word))
                previous = word
            _judge_words(mod, tokens, line, pinned, problems)
    else:
        # r4 R5, the tail: a literal program nothing above answered for. It used to end here with no
        # problem appended at all.
        _judge_literal(mod, program, where, problems)


def _judge_literal(mod, program, where, problems, inside_shell=False):
    """Judge one LITERAL program name by declaration (r4 R5).

    Default deny. A literal interpreter is refused wherever it is written, and every other literal
    program must be declared for this site in `LITERAL_PROGRAMS_DECLARED`. The tail this replaces
    appended nothing, so a program that was not a host, a pinned path, a shell, `sys.executable` or
    unresolvable was admitted in silence — which is every spelling an author would reach for."""
    base = os.path.basename(program)
    base = base[:-3] if base.endswith(".sh") else base
    written = "a command line starts" if inside_shell else "starts"
    if INTERPRETER_NAME.match(base):
        problems.append(f"DISPATCH_INTERPRETER_LITERAL {where}: {written} {program!r}, a literal interpreter; "
                        f"production starts Python through sys.executable")
        return
    if not any(entry["site"] == str(mod.rel) and entry["program"] == base
               for entry in LITERAL_PROGRAMS_DECLARED):
        problems.append(f"DISPATCH_PROGRAM_UNDECLARED {where}: {written} {program!r} and no declaration "
                        f"admits that program at this site")


# The separators a shell line's commands are divided by: each command's FIRST word is a program, and
# only the first word of the whole line used to be looked at (r4 R5).
SHELL_SEPARATORS = (";", "&&", "||", "|", "|&", "&", "\n")
# Words that start no program of their own.
SHELL_BUILTINS = ("printf", "echo", "exit", "wait", "set", "cd", "export", "read", "test", "[", ":",
                  "true", "false", "shift", "trap", "unset")
# Builtins that run THE NEXT WORD as a program: skip the builtin and judge that word. `exec` sat in
# the builtin list, so `exec python3 x.py` was admitted (r4 R5 addendum).
SHELL_RUNS_NEXT = ("exec", "command", "nohup", "time", "nice", "xargs", "sudo", "doas", "env")
# A builtin that runs a line built at run time: refused by name, because what it runs is not here.
SHELL_EVALS = ("eval", "source", ".")
# The flags whose argv element is a shell LINE rather than a word.
SHELL_LINE_FLAGS = ("-c", "-ic", "-lc", "--command")
# A redirection operator; the word after it is a file, not a program.
SHELL_REDIRECTIONS = (">", ">>", "<", "<<", "<<<", "2>", "2>>", "&>", ">&", "<>")
# Command substitution: the program inside is built or run by the shell and is not judged here.
SHELL_SUBSTITUTIONS = ("$(", "`", "<(", ">(", "${")


def _shell_tokens(text):
    """Every token of one shell command LINE, with the separators as tokens of their own.

    `shlex.split` leaves `status;` whole, so a separator glued to the command before it was never a
    separator and every command after it went unjudged — `git status; python3 x.py` and
    `git status|codex exec -` were both admitted (r4 R5 addendum). `punctuation_chars` splits
    `;`, `&&`, `||`, `|`, `&`, `(` and `)` off however they are written, and a NEWLINE separates
    commands as `;` does, which `shlex` would otherwise read as whitespace."""
    tokens = []
    for n, physical in enumerate(text.split("\n")):
        if n:
            tokens.append("\n")
        lexer = shlex.shlex(physical, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            tokens += list(lexer)
        except ValueError:                   # an unbalanced quote: the words are what is readable
            tokens += physical.split()
    return tokens


def _plain_word_tokens(word):
    """One argv element that is NOT a shell line, split on whitespace alone — its punctuation is
    part of the argument and splitting it would change the argument's shape."""
    try:
        return shlex.split(word) if " " in word else [word]
    except ValueError:
        return word.split()


def _judge_words(mod, words, line, pinned, problems):
    """Judge a shell command LINE, command by command, from tokens one tokenizer produced.

    Host names were the only thing read here, and only until the first one was found, so a second
    command starting a host passed; and the words came pre-split, so a glued separator was no
    separator at all (r4 R5 and its addendum)."""
    where = f"{mod.rel}:{line}"
    if any(word == "--self-test" or word.endswith("=--self-test") for word in words):
        problems.append(f"DISPATCH_SELF_TEST_ARGV {where}: a shell command line carrying '--self-test'; "
                        f"a suite is entered in this process, never handed to a child")
    for n, word in enumerate(words):
        # The tokenizer splits `(` off as its own token, so `$(` arrives as `$` then `(`: the mark is
        # looked for in the word AND across the pair, or a substitution reads as an ordinary command.
        glued = word + (words[n + 1] if n + 1 < len(words) else "")
        for mark in SHELL_SUBSTITUTIONS:
            if mark in word or glued.startswith(mark):
                problems.append(f"DISPATCH_SHELL_SUBSTITUTION {where}: a shell line with {mark!r} in it; "
                                f"the program the shell builds there is judged nowhere")
                break
    commands, current = [], []
    for word in words:
        if word in SHELL_SEPARATORS or word in ("(", ")", "{", "}"):
            commands.append(current)
            current = []
        else:
            current.append(word)
    commands.append(current)
    for command in commands:
        skip_next = False
        for word in command:
            if skip_next:                      # a redirection's target is a file, not a program
                skip_next = False
                continue
            base = os.path.basename(word)
            base = base[:-3] if base.endswith(".sh") else base
            if word in SHELL_REDIRECTIONS:
                skip_next = True
                continue
            if "=" in word and not word.startswith("-") and word.split("=")[0].isidentifier():
                continue                       # a `VAR=value` prefix
            if base in SHELLS or word.startswith("-"):
                continue                       # the shell itself, or a flag of what was skipped
            if base in SHELL_EVALS:
                problems.append(f"DISPATCH_SHELL_EVAL {where}: a shell line running {base!r}, which "
                                f"runs a line built at run time; what it starts is judged nowhere")
                break
            if base in SHELL_RUNS_NEXT:
                continue                       # it runs the NEXT word: judge that one
            if base in SHELL_BUILTINS:
                break                          # a builtin starts no program of its own
            if base in HOST_NAMES or word in pinned or os.path.expanduser(word) in pinned:
                problems.append(f"DISPATCH_OUTSIDE_SUPERVISOR {where}: a command line starts {word!r}, "
                                f"which only dispatch.py may start")
            else:
                _judge_literal(mod, word, where, problems, inside_shell=True)
            break


def _sites(mod, pinned, depth=0, runs=(), follow=None):
    problems = []
    for node in ast.walk(mod.tree):
        if not isinstance(node, ast.Call):
            continue
        name = mod.dotted(node.func)
        if name not in EXEC_CALLS:
            continue
        args = list(node.args) + [k.value for k in node.keywords if k.arg in ("args", "path", "file", "cmd")]
        if not args or (name in OS_ARGV and len(args) <= OS_ARGV[name][0]):
            problems.append(f"DISPATCH_UNRESOLVED {mod.rel}:{node.lineno}: {name} with no command the trace can read")
            continue
        shell = any(k.arg == "shell" and not (isinstance(k.value, ast.Constant) and k.value.value is False)
                    for k in node.keywords) or name in ("os.system", "os.popen", "subprocess.getoutput",
                                                       "subprocess.getstatusoutput")
        executable = next((k.value for k in node.keywords if k.arg == "executable"), None)
        if name in OS_ARGV:
            # the program is its own argument; argv[0] is only a name, and the rest are the program's words
            at, listed, loose, trailing = OS_ARGV[name]
            if listed is not None:
                rest = [words if words or UNKNOWN not in argv0 else [UNREAD]
                        for argv0, words in mod.heads(args[listed])] if len(args) > listed else [[UNREAD]]
            else:
                rest = [args[loose + 1:len(args) - trailing]]
            heads = [(mod.values(args[at]), r) for r in rest]
        elif shell:
            heads = [(["<shell>"], [args[0]])]
            if executable is not None:  # the shell itself is overridden: judge what runs the line, too
                heads.append((mod.values(executable), []))
        elif executable is not None:
            # executable= replaces the program argv[0] names; the argv's other words are its arguments
            heads = [(mod.values(executable), words if words or UNKNOWN not in argv0 else [UNREAD])
                     for argv0, words in mod.heads(args[0])]
        else:
            heads = mod.heads(args[0])
        for programs, rest in heads:
            for program in programs:
                _judge_program(mod, program, rest, node.lineno, pinned, problems, depth, runs, follow,
                               argv_node=args[0] if args else None)
    return problems


def _module_file(root, name, here=None, level=0):
    parts = name.split(".") if name else []
    bases = [here] if level else [root / d for d in IMPORT_DIRS]
    for base in bases:
        if base is None:
            continue
        if level > 1:
            base = base.parents[level - 2]
        candidate = base.joinpath(*parts) if parts else base
        for path in (candidate.with_suffix(".py") if parts else None, candidate / "__init__.py"):
            if path is not None and path.is_file():
                return path
    return None


def name_rebindings(root=REPO, spellings=None):
    """Bindings of the names the admitted program forms are written with, other than the import
    that introduces each one.

    The forms are exact, so their MEANING rests on four names: `str`, `pathlib`, `__file__` and the
    module the member owner is reached through. A file that rebinds one of them writes the admitted
    form and runs something else, and no amount of exactness in the shape sees that.

    Default-deny, over every binding form Python's own grammar has rather than the ones that came to
    mind: a `Name` in `Store` or `Del` context (assignment, augmented assignment, `for`, `with ...
    as`, walrus, comprehension target), an import alias, a `def`/`class` name, any parameter name,
    an `except ... as` name, a `match` capture, and a `global`/`nonlocal` declaration. The declared
    import of the module names is the one binding admitted; `str` is a builtin and `__file__` is the
    interpreter's, so for those nothing is."""
    problems, scanned = [], 0
    for row in (FORM_SPELLINGS if spellings is None else spellings):
        path = pathlib.Path(root) / row["site"]
        if not path.is_file():
            problems.append(f"INVENTORY_STALE form spelling {row['site']}: no such file")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scanned += 1
        # The module names come from the spellings themselves, so a new form is covered by the name
        # it is written with rather than by a list someone has to remember to extend.
        watched = {"__file__", row["str"].split(".")[0], row["path"].split(".")[0],
                   row["member"].split(".")[0]}
        for node in ast.walk(tree):
            bound = []
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                bound = [node.id]
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                allowed = row.get("imports") or {}
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    if name in watched and allowed.get(name) != (
                            node.module if isinstance(node, ast.ImportFrom) else alias.name):
                        problems.append(f"DISPATCH_NAME_REBOUND {row['site']}:{node.lineno}: {name!r} is "
                                        f"imported in a way the spelling does not declare")
                continue
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                args = getattr(node, "args", None)
                bound = [node.name] + ([a.arg for a in (args.posonlyargs + args.args + args.kwonlyargs
                                                        + [a for a in (args.vararg, args.kwarg) if a])]
                                       if args is not None else [])
                # A bare-name member spelling names a function this file OWNS, so the `def` that
                # owns it is a binding the declaration admits — at module level, once, and nowhere
                # else. Any other binding of the same name is still refused below.
                if node.name in (row.get("defines") or ()) and node in tree.body:
                    bound = [name for name in bound if name != node.name]
            elif isinstance(node, ast.Lambda):
                bound = [a.arg for a in (node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                                         + [a for a in (node.args.vararg, node.args.kwarg) if a])]
            elif isinstance(node, ast.ExceptHandler) and node.name:
                bound = [node.name]
            elif isinstance(node, ast.MatchAs) and node.name:
                bound = [node.name]
            elif isinstance(node, ast.MatchStar) and node.name:
                bound = [node.name]
            elif isinstance(node, ast.MatchMapping) and node.rest:
                bound = [node.rest]
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                bound = list(node.names)
            for name in bound:
                if name in watched:
                    problems.append(f"DISPATCH_NAME_REBOUND {row['site']}:{node.lineno}: {name!r} is bound "
                                    f"here, so an admitted form in this file may not mean what it says")
    # A scan of nothing satisfies "no rebinding" and says nothing at all.
    if not scanned:
        problems.append("INVENTORY_STALE form spellings: no file was scanned, so this judges nothing")
    return problems


def closure_violations(root=REPO, out_of_scope=OUT_OF_SCOPE, dynamic=DYNAMIC_LOADS, scripts=SCRIPT_RUNS,
                       copies=None):
    """(problems, closure, sites inspected): the driver's import closure — its roots, every
    module they import from session-distill/ and benchmarks/, and the declared dynamic loads that
    join it — and every executor call site in it, judged by AST. dispatch.py's own sites are the
    supervisor's and are not judged; a textual mention outside the closure is not a site."""
    root = pathlib.Path(root)
    # `copies` is a SEAM for the controls: the default is resolved here rather than bound at import,
    # so the live tuple stays the production authority and a control can hand in rows of its own.
    copies = COPY_RUNS if copies is None else copies
    problems = []
    for entry in out_of_scope:
        if not (root / entry["path"]).is_file():
            problems.append(f"INVENTORY_STALE out-of-scope {entry['path']}: no such file")
    for entry in dynamic:
        if not (root / entry["site"]).is_file() or not (root / entry["path"]).is_file():
            problems.append(f"INVENTORY_STALE dynamic load {entry['site']} -> {entry['path']}: no such file")
    for entry in scripts:
        if not (root / entry["site"]).is_file() or not (root / entry["path"]).is_file():
            problems.append(f"INVENTORY_STALE script run {entry['site']} -> {entry['path']}: no such file")
    for entry in GUARDED_PROGRAMS:
        held = (root / entry["site"]).read_text(encoding="utf-8") if (root / entry["site"]).is_file() else ""
        for guard in entry["guards"]:
            if guard not in held:
                problems.append(f"INVENTORY_STALE guarded program {entry['site']}: its guard {guard!r} is gone")
    problems += name_rebindings(root)
    for entry in copies:
        missing = [name for name in entry["paths"] if not (root / name).is_file()]
        if not (root / entry["site"]).is_file() or missing:
            problems.append(f"INVENTORY_STALE copy run {entry['site']} -> {missing or entry['paths']}: no such file")
            continue
        # The owner is the admission, so the owner has to be there: an entry naming a function the
        # site cannot call admits nothing and must say so rather than sit quietly.
        held = (root / entry["site"]).read_text(encoding="utf-8")
        if f"{entry['owner'].split('.')[-1]}(" not in held:
            problems.append(f"INVENTORY_STALE copy run {entry['site']}: it calls no {entry['owner']}")
    excluded = {(root / e["path"]).resolve() for e in out_of_scope}
    queue = [root / CLOSURE_ROOTS[0]] + sorted((root / CLOSURE_ROOTS[1]).glob("*.py"))
    closure, seen, sites, used, ran = [], set(), 0, set(), set()
    pinned = _pinned(root)
    while queue:
        path = queue.pop(0).resolve()
        if path in seen:
            continue
        seen.add(path)
        rel = path.relative_to(root.resolve())
        mod = _Module(path, rel)
        closure.append(str(rel))
        for node in ast.walk(mod.tree):
            targets = []
            if isinstance(node, ast.Import):
                targets = [(a.name, 0) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                targets = [(f"{node.module}.{a.name}" if node.module else a.name, node.level) for a in node.names] + \
                          [(node.module, node.level)]
            for name, level in targets:
                found = _module_file(root, name, path.parent, level) if name or level else None
                if found is None:
                    continue
                if found.resolve() in excluded:
                    problems.append(f"CLOSURE_IMPORTS_OUT_OF_SCOPE {rel}:{node.lineno}: imports {found.relative_to(root)}")
                else:
                    queue.append(found)
            if isinstance(node, ast.Call) and mod.dotted(node.func) in LOAD_CALLS:
                at = LOAD_CALLS[mod.dotted(node.func)]
                arg = node.args[at] if len(node.args) > at else None
                candidates = mod.values(arg) if arg is not None else [UNKNOWN]
                for text in candidates:
                    as_path = text if text.endswith(".py") else text.replace(".", "/") + ".py"
                    hit = [e for e in out_of_scope if as_path.endswith(e["path"]) or as_path.endswith(
                        e["path"].split("/", 1)[1]) or text == pathlib.Path(e["path"]).stem]
                    declared = [e for e in dynamic if str(rel) == e["site"] and _names(e["path"], as_path)]
                    if hit:
                        problems.append(f"CLOSURE_IMPORTS_OUT_OF_SCOPE {rel}:{node.lineno}: loads {hit[0]['path']}")
                    elif declared:
                        used.add((declared[0]["site"], declared[0]["path"]))
                        if declared[0]["trace"]:
                            queue.append(root / declared[0]["path"])
                    elif UNKNOWN in text and not text.replace(UNKNOWN, "").strip("/."):
                        problems.append(f"DYNAMIC_LOAD_UNDECLARED {rel}:{node.lineno}: a load the trace cannot resolve")
                    else:
                        problems.append(f"DYNAMIC_LOAD_UNDECLARED {rel}:{node.lineno}: loads {text!r}, declared "
                                          f"nowhere in DYNAMIC_LOADS")
        if str(rel) != "session-distill/runlib/dispatch.py":
            follow = []
            found = _sites(mod, pinned, runs=scripts, follow=follow)
            for entry in follow:
                ran.add((entry["site"], entry["path"]))
                # A declaration naming a file that is not there is reported by the staleness leg
                # above; the walk must not die on it, or that report never gets printed.
                if (root / entry["path"]).is_file():
                    queue.append(root / entry["path"])
            sites += sum(1 for n in ast.walk(mod.tree) if isinstance(n, ast.Call) and mod.dotted(n.func) in EXEC_CALLS)
            problems.extend(found)
    for entry in dynamic:
        if (entry["site"], entry["path"]) not in used and (root / entry["site"]).is_file():
            problems.append(f"INVENTORY_STALE dynamic load {entry['site']} -> {entry['path']}: the site makes no such load")
    for entry in scripts:
        if (entry["site"], entry["path"]) not in ran and (root / entry["site"]).is_file():
            problems.append(f"INVENTORY_STALE script run {entry['site']} -> {entry['path']}: the site runs no such script")
    for entry in copies:
        for path in entry["paths"]:
            if (entry["site"], path) not in ran and (root / entry["site"]).is_file():
                problems.append(f"INVENTORY_STALE copy run {entry['site']} -> {path}: the site runs no such copy")
    return problems, closure, sites


def contract_branches(source):
    """({refusal code}, {item outcome}) the Supervisor implements, read from its source: the
    leading word of every message it raises as Refused, Exhausted or Deferred (a message bound
    to a name first is followed to that binding), and every outcome `item` returns."""
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == CONTRACT["predicate"])
    bound = {t.id: n.value for n in ast.walk(cls) if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}

    def head(node):
        while isinstance(node, ast.BinOp):
            node = node.left
        if isinstance(node, ast.Name) and node.id in bound:
            return head(bound[node.id])
        if isinstance(node, ast.JoinedStr) and node.values:
            node = node.values[0]
        return node.value.split()[0] if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.split() else None
    codes, outcomes = set(), set()
    for node in ast.walk(cls):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args and \
                ast.unparse(node.exc.func) in ("Refused", "Exhausted", "breakers.Deferred") and head(node.exc.args[0]):
            codes.add(head(node.exc.args[0]))
        if isinstance(node, ast.FunctionDef) and node.name == "item":
            for d in ast.walk(node):
                if isinstance(d, ast.Dict):
                    for k, v in zip(d.keys, d.values):
                        if isinstance(k, ast.Constant) and k.value == "outcome":
                            for x in (v.body, v.orelse) if isinstance(v, ast.IfExp) else (v,):
                                if isinstance(x, ast.Constant) and isinstance(x.value, str):
                                    outcomes.add(x.value)
    return codes, outcomes


# --- self-test ----------------------------------------------------------------------------------

FAKE_CLAUDE_BIN = r'''#!/usr/bin/env python3
"""A fake Claude host for the adapter controls (BC#6): it starts no model and records what it got.

The hermetic child's environment is scrubbed by the adapter, so there is nowhere to pass a path in:
this writes beside itself, which is the scratch directory the control made for it."""
import hashlib, json, os, pathlib, sys
here = pathlib.Path(__file__).resolve().parent
if "--version" in sys.argv[1:]:
    print((here / "version.txt").read_text().strip() + " (Claude Code)")
    sys.exit(0)
appended = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--append-system-prompt-file"]
(here / "received.json").write_text(json.dumps({
    # the hermetic child's environment is scrubbed to an allowlist, so the cell and the call id are NOT
    # readable here: what names the call on this side is the packet the adapter puts on stdin
    "argv": sys.argv[1:], "cap": os.environ.get("CLAUDE_CODE_MAX_OUTPUT_TOKENS"),
    "cwd": os.path.realpath(os.getcwd()), "packet_head": sys.stdin.readline().strip(),
    "appended": appended,
    "appended_bodies": [pathlib.Path(f).read_text() for f in appended],
    "appended_sha256": [hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest() for f in appended]}))
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": "fake",
                  "result": "", "stop_reason": "end_turn", "safety_stops": 0,
                  "terminal_reason": "completed", "modelUsage": {}}))
'''

FAKE_HOST = r'''
"""A golden host for dispatch.py --self-test: it plays a runner by the runner contract and
starts no model. argv: host mode spec-json."""
import hashlib, json, os, pathlib, sys, time, uuid, zlib
host, mode, spec = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
packet = sys.stdin.buffer.read().decode("utf-8")
call_id = packet.splitlines()[0].split(": ", 1)[1]
capture, cell = pathlib.Path(os.environ["REVIEW_CAPTURE_DIR"]), pathlib.Path(os.environ["DISTILL_CELL"])
schema = json.loads(pathlib.Path(spec["schema_path"]).read_text()) if spec.get("schema_path") else None
model, effort = spec["model"], spec["effort"]
# codex-cli 0.163.0 loads its four built-in skills under any profile, and its capture names them
context = {"instructions": [], "appended_prompts": [], "agents": [], "hooks": [],
           "skills": ["imagegen", "openai-docs", "skill-creator", "skill-installer"] if host == "codex" else []}
# the appended system prompts the adapter was handed: reported by the sha256 of the bytes THIS process
# read from the delivered file, which is what makes the gate's effective-context leg a delivery check
for n, prompt in enumerate(spec.get("appended_prompts") or [], 1):
    body = pathlib.Path(prompt["path"]).read_bytes()
    context["appended_prompts"].append({"name": prompt["name"], "sha256": hashlib.sha256(body).hexdigest(),
                                        "declared_sha256": prompt["sha256"], "source": "declared"})
if spec.get("env_seen"):  # the adapter calling convention, as the runner received it
    pathlib.Path(spec["env_seen"]).write_text(json.dumps({k: os.environ.get(k) for k in (
        "REVIEW_CALL_ID", "DISTILL_CALL_ID", "CODEX_RUN_BIN", "CODEX_RUN_VERSION")}))
def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".%06dZ" % int(t % 1 * 1e6)
def record(extra):
    (capture / "host.json").write_text(json.dumps({"host": host, "call_id": call_id, "profile": spec["call_profile"],
        "profile_flags_sha256": spec["flags_sha256"], "cwd": spec["workdir"], "context": context, "workdir_files": [
            {"path": str(p.relative_to(spec["workdir"])), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(pathlib.Path(spec["workdir"]).rglob("*")) if p.is_file()], **extra}))
if os.environ.get("REVIEW_RECEIPT_DIR"):  # a runner's own receipt: evidence in the capture, not the call's
    own = pathlib.Path(os.environ["REVIEW_RECEIPT_DIR"])
    own.mkdir(parents=True, exist_ok=True)
    (own / "runner.json").write_text(json.dumps({"schema": "ReviewReceipt/v1", "method_id": "runner/" + call_id}))
if mode == "adapter-refuses":  # an adapter's named refusal on a nonzero exit
    sys.stderr.write("trace before the refusal: BODY-CANARY-refusal\n" + spec["refusal"] + "\n")
    sys.exit(spec["exit"])
if mode == "stderr-canary":  # a body on the runner's stderr, as a host's trace carries one
    sys.stderr.write("BODY-CANARY-stderr the prompt and the answer\n")
    sys.stderr.flush()
def wait_for(path, limit=30.0):
    end = time.time() + limit
    while not pathlib.Path(path).exists() and time.time() < end:
        time.sleep(0.01)
if mode in ("late-cap", "late-send"):  # an orphan of the host's group, its stdio closed: the stop must still reach it
    import subprocess
    kid = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    start = subprocess.run(["/bin/ps", "-o", "lstart=", "-p", str(kid.pid)], capture_output=True, text=True).stdout
    pathlib.Path(spec["orphan"]).write_text(json.dumps({"pid": kid.pid, "start": " ".join(start.split())}))
if mode == "surviving-child":  # an ordinary child of the tree, holding the runner's stderr past the root's exit
    import subprocess
    kid = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    start = subprocess.run(["/bin/ps", "-o", "lstart=", "-p", str(kid.pid)], capture_output=True, text=True).stdout
    pathlib.Path(spec["orphan"]).write_text(json.dumps({"pid": kid.pid, "start": " ".join(start.split())}))
    time.sleep(0.3)  # long enough for the supervisor's tree sampler to see it
if mode in ("escaped-holder", "capped-escaped-holder", "held-late-send"):  # the runner's stderr handed to a process that was never in the tree
    import socket
    with socket.socket(socket.AF_UNIX) as sock:
        sock.connect(spec["holder_socket"])
        socket.send_fds(sock, [b"fd"], [2])
        sock.recv(1)
if host == "claude":
    sid = str(uuid.uuid4())
    stream = open(capture / "stream.jsonl", "a", buffering=1)
    log_path = cell / "config" / "projects" / "cell" / (sid + ".jsonl")
    log_path.parent.mkdir(parents=True)
    log = open(log_path, "a", buffering=1)
    emit = lambda obj: stream.write(json.dumps(obj) + "\n")
    usage = {"input_tokens": 2, "cache_read_input_tokens": 90000 if mode in ("big-first-request", "capped-escaped-holder") else 2800,
             "cache_creation_input_tokens": 350}
    if spec.get("replay"):  # a retained call's observed input, replayed: the number is evidence, not a choice
        row = json.loads(pathlib.Path(spec["replay"]).read_text())["requests"][-1]
        usage = {"input_tokens": row["input_tokens"] - row["cached_tokens"],
                 "cache_read_input_tokens": row["cached_tokens"], "cache_creation_input_tokens": 0}
    emit({"type": "system", "subtype": "status", "status": "requesting"})
    log.write(json.dumps({"type": "api-request", "timestamp": iso(time.time())}) + "\n")
    rid = "req_" + uuid.uuid4().hex[:12]
    if mode == "late-cap":  # the cap-crossing start, and the host gone before a slow reader reads it
        emit({"type": "stream_event", "event": {"type": "message_start", "message": {"id": "msg_1", "model": model,
                                                                                      "usage": {**usage, "cache_read_input_tokens": 90000}}}})
        sys.exit(0)
    if mode == "limit-then-hang":  # a rejected limit read live, the call kept alive while another dispatch is tried
        emit({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": spec["resets_at"],
                                                              "rateLimitType": "five_hour"}})
        wait_for(spec["release"])
        mode = "api-error-limit"
    if mode == "rate-limit-rejected":
        emit({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": spec["resets_at"],
                                                              "rateLimitType": "five_hour"}})
    emit({"type": "stream_event", "event": {"type": "message_start", "message": {"id": "msg_1", "model": model, "usage": usage}}})
    if mode in ("big-first-request", "capped-escaped-holder"):
        time.sleep(60)
    emit({"type": "stream_event", "event": {"type": "message_delta", "usage": {"output_tokens": 61}}})
    if mode == "compactions":
        for _ in range(3):
            emit({"type": "system", "subtype": "compact_boundary", "compact_metadata": {"trigger": "auto"}})
            time.sleep(0.05)
        time.sleep(60)
    base = {"type": "result", "session_id": sid, "safety_stops": 0, "stop_reason": "end_turn", "result": "",
            "modelUsage": {model: {"inputTokens": usage["input_tokens"], "outputTokens": 61,
                                   "cacheReadInputTokens": usage["cache_read_input_tokens"],
                                   "cacheCreationInputTokens": usage["cache_creation_input_tokens"]}}}
    if mode == "cap-overrun":  # Claude Code 2.1.304 past --max-output-tokens (WP-03v dw5, cap16)
        cap = spec.get("overrun_at", spec["max_output_tokens"])
        result = {**base, "subtype": "success", "is_error": True, "api_error": "max_output_tokens", "api_error_status": None,
                  "terminal_reason": "api_error", "stop_reason": "stop_sequence",
                  "result": f"API Error: Claude's response exceeded the {cap} output token maximum. To configure this "
                            f"behavior, set the CLAUDE_CODE_MAX_OUTPUT_TOKENS environment variable."}
        emit(result)
        record({"session_id": sid, "requests": [], "assistant": [], "structured_calls": []})
        print(json.dumps(result))
        sys.exit(1)
    if mode in ("usage-limit", "text-limit", "api-error-limit"):
        if mode in ("usage-limit", "api-error-limit"):
            if mode == "usage-limit":
                emit({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": spec["resets_at"],
                                                                      "rateLimitType": "five_hour"}})
            result = {**base, "subtype": "success", "is_error": True, "api_error": "usage_limit_reached",
                      "api_error_status": 429, "terminal_reason": "api_error"}
        else:
            result = {**base, "subtype": "success", "is_error": True, "api_error": None, "api_error_status": None,
                      "terminal_reason": "completed", "result": "You've hit your usage limit. Try again later."}
        emit(result)
        record({"session_id": sid, "requests": [], "assistant": [], "structured_calls": []})
        print(json.dumps(result))
        sys.exit(1)
    answer = {"verdict": "ABSENT", "why": "no section names it"}
    if mode == "invalid" or (mode == "invalid-then-valid" and "rejected by validation" not in packet):
        answer = {"verdict": "MAYBE"}
    structured = answer if schema is not None else None
    result = {**base, "subtype": "success", "is_error": False, "terminal_reason": "completed", "api_error": None,
              "api_error_status": None, "structured_output": structured}
    emit(result)
    record({"session_id": sid,
            "requests": [{"id": rid, "model": model, "role": "main", "packet_text": packet, "structured_output_schema": schema}],
            "assistant": [{"model": model, "request_id": rid, "role": "main", "stop_reason": "end_turn", "synthetic": False}],
            "structured_calls": [structured] if structured is not None else []})
    print(json.dumps(result))
else:
    root = str(uuid.uuid4())
    replay = json.loads(pathlib.Path(spec["replay"]).read_text())["requests"] if spec.get("replay") else [
        {"generate": False, "input_tokens": 11814, "cached_tokens": 1000, "output_tokens": 0},
        {"generate": None, "input_tokens": 13595, "cached_tokens": 1000, "output_tokens": 15}]
    def line(text):
        sys.stderr.write(text + "\n")
        sys.stderr.flush()
    def otel(fields):
        line(iso(time.time()) + "  INFO session_loop: codex_otel.log_only: " + fields)
    def received(obj):
        line(iso(time.time()) + " TRACE tungstenite::protocol: Received message " + json.dumps(obj))
    events = open(capture / "events.jsonl", "a", buffering=1)
    events.write(json.dumps({"type": "thread.started", "thread_id": root}) + "\n")
    line(iso(time.time()) + '  INFO codex.exec{thread.id="' + root + '"}: started')
    if mode == "stderr-canary":
        received({"type": "response.output_text.delta", "delta": "BODY-CANARY-delta"})
    if mode == "refusal-frame":  # the server refused, on the raw trace
        received({"type": "response.refusal.done", "refusal": "BODY-CANARY-refusal-text"})
    if mode == "helper-capture":  # codex-run's capture helper wrote the frames: a refusal and a warning stderr never showed
        (capture / "frames.jsonl").write_text("".join(json.dumps(r) + "\n" for r in (
            {"dir": "info", "type": "channels", "channels": ["frames", "otel", "responses_retry"]},
            {"dir": "info", "type": "root_thread", "thread": root},
            {"dir": "warn", "type": "responses_retry", "ts": iso(time.time())},
            {"dir": "recv", "type": "response.refusal.done", "ts": iso(time.time())})))
    deflate, prev = zlib.compressobj(wbits=-15), None
    def failed():
        events.write(json.dumps({"type": "turn.failed", "error": {"message": "usage limit"}}) + "\n")
        record({"session_id": root})
        sys.exit(1)
    if mode == "http-limit":  # an otel codex.api_request to /responses with status 429, nothing else
        otel('event.name="codex.api_request" http.response.status_code=429 attempt=0 endpoint=/responses')
        failed()
    if mode == "rate-limits-frame":  # a codex.rate_limits frame with limit_reached, nothing else
        received({"type": "codex.rate_limits", "rate_limits": {"allowed": False, "limit_reached": True}})
        failed()
    if mode in ("late-cap", "late-send", "late-truncated", "limit-late-send", "held-late-send"):
        replay = [{"generate": None, "input_tokens": 90000, "cached_tokens": 1000, "output_tokens": 15}]
    if mode == "https-fallback":  # probe 9's fallback shape: no frames; one stream dropped, then each request over HTTPS
        sse = 'event.name="codex.sse_event" event.kind=%s conversation.id=' + root
        otel(sse % "response.created")
        otel(sse % "response.completed")
        for r in replay:
            otel(sse % "response.created")
            otel(sse % "response.completed")
            otel('event.name="codex.sse_event" event.kind=response.completed input_token_count=%d output_token_count=%d '
                 "cached_token_count=%d cache_write_token_count=0 conversation.id=%s model=%s"
                 % (r["input_tokens"], r["output_tokens"], r.get("cached_tokens") or 0, root, model))
        replay = []
    for n, r in enumerate(replay):
        kind = "prewarm" if r.get("generate") is False else "turn"
        if mode == "mixed-fallback" and n > 0:  # the transport falls back to HTTPS after the first request
            sse = 'event.name="codex.sse_event" event.kind=%s conversation.id=' + root
            otel(sse % "response.created")
            otel(sse % "response.completed")
            otel('event.name="codex.sse_event" event.kind=response.completed input_token_count=%d output_token_count=%d '
                 "cached_token_count=%d cache_write_token_count=0 conversation.id=%s model=%s"
                 % (r["input_tokens"], r["output_tokens"], r.get("cached_tokens") or 0, root, model))
            continue
        meta = {"thread_id": root, "agent_name": "/root", "request_kind": kind, "parent_thread_id": None}
        create = {"type": "response.create", "model": model, "previous_response_id": prev, "prompt_cache_key": root,
                  "reasoning": {"effort": effort}, "client_metadata": {"x-codex-turn-metadata": json.dumps(meta)}}
        data = (deflate.compress(json.dumps(create).encode()) + deflate.flush(zlib.Z_SYNC_FLUSH))[:-4]
        otel('event.name="codex.websocket_request" conversation.id=%s model=%s' % (root, model))
        for text in (iso(time.time()) + " TRACE tungstenite::protocol::frame: writing frame", "opcode: TEXT",
                     "reserved: true false false", "payload: 0x" + data.hex()):
            line(text)
        if mode == "ws-limit" and kind == "turn":
            received({"type": "error", "status": 429, "error": {"type": "usage_limit_reached", "code": "usage_limit_reached"}})
            failed()
        resp = {"id": "resp_%d" % n, "model": model, "previous_response_id": prev, "prompt_cache_key": root,
                "reasoning": {"effort": effort}, "usage": None}
        received({"type": "response.created", "response": {**resp, "status": "in_progress"}})
        usage = {"input_tokens": r["input_tokens"], "input_tokens_details": {"cached_tokens": r.get("cached_tokens") or 0},
                 "output_tokens": r["output_tokens"], "total_tokens": r["input_tokens"] + r["output_tokens"]}
        received({"type": "response.completed", "response": {**resp, "status": "completed", "usage": usage}})
        line(iso(time.time()) + '  INFO session_loop: codex_otel.log_only: event.name="codex.sse_event" '
             "event.kind=response.completed input_token_count=%d output_token_count=%d cached_token_count=%d "
             "cache_write_token_count=0 conversation.id=%s model=%s"
             % (r["input_tokens"], r["output_tokens"], r.get("cached_tokens") or 0, root, model))
        prev = resp["id"]
        if mode == "late-truncated":  # a frame header stamped after any freeze whose payload never comes
            line(iso(time.time() + 30) + " TRACE tungstenite::protocol::frame: writing frame")
            line("opcode: TEXT")
            time.sleep(60)
        if mode == "limit-late-send":  # a usage limit read, and then the same late send
            received({"type": "error", "status": 429, "error": {"type": "usage_limit_reached", "code": "usage_limit_reached"}})
        if mode in ("late-send", "limit-late-send", "held-late-send"):  # a fault-injected send stamped after any freeze, then the host waits to be stopped
            later = (deflate.compress(json.dumps({**create, "previous_response_id": prev}).encode()) + deflate.flush(zlib.Z_SYNC_FLUSH))[:-4]
            for text in (iso(time.time() + 30) + " TRACE tungstenite::protocol::frame: writing frame", "opcode: TEXT",
                         "reserved: true false false", "payload: 0x" + later.hex()):
                line(text)
            time.sleep(60)
    if mode == "two-threads-retry":  # a retry warning in a call that also started a second thread
        line(iso(time.time()) + "  WARN codex_core::responses_retry: stream disconnected - retrying sampling request")
        otel('event.name="codex.websocket_request" conversation.id=%s model=%s' % (str(uuid.uuid4()), model))
    if mode == "second-send-retry":  # a retry warning, and a second thread's send that no otel row or response follows
        line(iso(time.time()) + "  WARN codex_core::responses_retry: stream disconnected - retrying sampling request")
        kid = str(uuid.uuid4())
        meta = {"thread_id": kid, "agent_name": "/root/kid", "request_kind": "turn", "parent_thread_id": root}
        create = {"type": "response.create", "model": model, "previous_response_id": None, "prompt_cache_key": kid,
                  "reasoning": {"effort": effort}, "client_metadata": {"x-codex-turn-metadata": json.dumps(meta)}}
        data = (deflate.compress(json.dumps(create).encode()) + deflate.flush(zlib.Z_SYNC_FLUSH))[:-4]
        for text in (iso(time.time()) + " TRACE tungstenite::protocol::frame: writing frame", "opcode: TEXT",
                     "reserved: true false false", "payload: 0x" + data.hex()):
            line(text)
    events.write(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 0, "output_tokens": 0}}) + "\n")
    record({"session_id": root})
    sys.stdout.write("OK")
'''


def self_test(scratch=None):
    """Registers its failure list with `boundary.SELF_TEST_COLLECTED` so an abort publishes what it
    had already collected; the report below removes it."""
    if scratch is None:
        scratch = pathlib.Path(tempfile.mkdtemp(prefix="dispatch-self-test-"))
        try:
            return self_test(scratch)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    from runlib import declare
    # Set where this suite begins publishing its report. Past that point a control is not in the
    # number the summary published, and the summary has already said OK — which is a conclusion
    # printed before the judging. The helpers below refuse past it rather than trusting placement.
    reporting = []
    failures, ran = [], []
    boundary.SELF_TEST_COLLECTED.append(("dispatch --self-test", failures))
    fake = scratch / "fake_host.py"
    fake.write_text(FAKE_HOST, encoding="utf-8")
    verdict_schema = {"type": "object", "additionalProperties": False, "required": ["verdict", "why"],
                      "properties": {"verdict": {"enum": ["PRESENT", "ABSENT", "UNCLEAR"]}, "why": {"type": "string"}}}
    judge, luna = "claude:claude-haiku-5-5/low", "codex:gpt-6-luna/low"
    caps = {"tokens": 50_000, "compactions": 2}

    def control(name, condition, detail):
        if reporting:
            raise RuntimeError(f"CONTROL_AFTER_SUMMARY {name}: this suite has begun publishing its "
                               f"report, so `control` is not in the count it published")
        # A boolean-style helper given a problem LIST passed on whatever its needle said, because a
        # non-empty list is truthy: three controls in this package read correctly and asked nothing
        # until S8a found them. The signature is enforced here rather than remembered.
        if not isinstance(condition, bool):
            raise TypeError(f"CONTROL_CONDITION_NOT_BOOL {name}: this file's `control` judges a "
                            f"boolean condition and was given {type(condition).__name__}")
        ran.append(name)
        if not condition:
            failures.append(f"{name}: {detail}")

    def type_refusal(call):
        """The message a self-test helper raises when it is given the wrong KIND of argument. The
        control below catches it here, so asking the guard does not fail the suite."""
        try:
            call()
        except TypeError as exc:
            return str(exc)
        return ""

    control("a boolean-style control given a problem list is refused by name",
            "CONTROL_CONDITION_NOT_BOOL" in type_refusal(
                lambda: control("a planted non-boolean", ["a problem"], "")),
            "the guard admitted a non-boolean condition, so a control in the other file's style would pass on a truthy list")

    def refusal(fn, *args, **kwargs):
        try:
            fn(*args, **kwargs)
        except (Refused, breakers.Deferred) as exc:
            return str(exc)
        return None

    astra = "codex:gpt-6-astra/xhigh"
    codex_flags = gate.pinned_flags_sha256("codex", "0.163.0", "hermetic")
    pinned_launcher = receipts.LAUNCHER        # one control points the receipt writer at a failing script
    # Every view-window control below runs on a CLAUDE seat, because a view-window call is admitted only on
    # a host whose adapter can convey the cap check (d) reserves, and codex-run conveys none (BB#4). S3's
    # seat is the one seats.json declares a host-reported capacity for; its allowance is read from the same
    # file the admission reads, never copied, so re-measuring preflight cannot leave this test behind.
    vseat, vstage = "claude:claude-sonnet-5-5/xhigh", "S3"
    claude_flags = gate.pinned_flags_sha256("claude", "2.1.304", "hermetic")
    claude_allowance = gate.seats()["hosts"]["claude"]["host_allowance"]["hermetic"]["allowance_tokens"]

    def run_dir(name, per_stage, allowance=None, window_allowance=None):
        directory = scratch / name
        directory.mkdir()
        run = declare.fixture()
        run["budget"]["per_stage"] = per_stage
        # the self-test's seats, declared as a run declares its seats (design §4 pins the others)
        run["seats"].update({"S6.judge": judge, "S6.luna": luna, "S7": judge, "S8": judge, "S9": judge})
        if allowance is not None:
            run["host_allowance"][astra] = {"allowance_tokens": allowance, "host_version": "0.163.0", "flag_set_sha256": codex_flags}
        run["host_allowance"][vseat] = {"allowance_tokens": claude_allowance if window_allowance is None else window_allowance,
                                        "host_version": "2.1.304", "flag_set_sha256": claude_flags}
        declare.create(directory, run)
        return directory

    clock = [1_800_000_000.0]
    measured_seats = scratch / "seats-measured.json"
    held = json.loads(gate.SEATS.read_text(encoding="utf-8"))
    held["hosts"]["codex"]["host_allowance"]["hermetic"].update(allowance_tokens=4000, measured=True)
    # BA#1: the self-test's own seat capacity for the Codex seat it dispatches view windows on. The
    # checkout's seats.json leaves every Codex seat undeclared because no capture reports one, which is
    # what `a-view-window-call-on-a-seat-with-no-declared-capacity-is-refused` reads against the real file.
    held["seat_capacity"] = {**(held.get("seat_capacity") or {}),
                             astra: {"context_capacity": 200_000, "host_version": "0.163.0",
                                     "basis": "the self-test's own declaration, not a measurement"}}
    measured_seats.write_text(json.dumps(held), encoding="utf-8")

    def supervisor(directory, mode="clean", seats_path=None, **spec_extra):
        """A golden supervisor; its Claude calls declare an output-token cap unless a call names one
        (the omitted-cap refusal is judged on the unwrapped method, Supervisor.call)."""
        sup = Supervisor(directory, clock=lambda: clock[0], cell_root=scratch, realization="golden", seats_path=seats_path)
        sup.runner = lambda host, spec: [sys.executable, str(fake), host, sup.mode, json.dumps({**spec, **sup.extra})]
        sup.mode, sup.extra = mode, spec_extra
        bound = sup.call
        sup.call = lambda stage, seat, *args, **kwargs: bound(stage, seat, *args, **(
            {"max_output_tokens": 4096, **kwargs} if seat.startswith("claude:") else kwargs))
        return sup

    calibrated = {class_key(s, judge, "judge"): [3000, 3100, 3213, 3300, 3400] for s in ("S6", "S7", "S8", "S9", "S10")}
    calibrated.update({class_key("S6", luna, "judge"): [24000, 25000, 25424, 25500, 26000]})

    # positive control first: a judge call reserved, dispatched, monitored, captured, receipted, accepted
    d = run_dir("run-a", {"S6": 200_000, "S7": 5100, "S8": 1000, "S9": 100_000})
    sup = supervisor(d)
    sup.seed_from(calibrated)
    r = sup.reserve("S6", "c1", judge, "judge")
    control("reservation-is-the-p95-of-the-class", (r["amount"], r["calibration"], r["call_id"]) == (3400, "measured", "run-a-S6-c1-a1"),
            f"{r}")
    packet = packets.build(r["call_id"], "S6", judge, "Is the rule present?\n", packets.schema_bytes(verdict_schema))
    call_dir = sup.call("S6", judge, packet, verdict_schema, reservation=r, caps=caps, view_window=False)
    verdict = gate.accept(call_dir)
    control("golden-judge-call-accepted-by-the-gate", verdict["ok"], f"{verdict['failures']}")
    usage = records.read_json(call_dir / "usage.json")
    control("usage-measured-and-reconciled", usages.call_state(usage) == "measured" and usages.totals(usage)["measured"] == 3213,
            f"{usage}")
    call = records.read_json(call_dir / "call.json")
    control("cell-deleted-after-usage-was-written", not pathlib.Path(call["manifest"]["workdir_path"]).exists()
            and (call_dir / "capture" / "transcripts").is_dir(), f"{call['manifest']['workdir_path']}")
    control("receipt-written-by-the-launcher", receipts.read(call_dir)[0] is not None
            and receipts.read(call_dir)[0]["method_id"] == "distill/S6/run-a-S6-c1-a1", f"{receipts.read(call_dir)}")
    left = sup.ledger()["stages"]["S6"]
    control("reservation-settled-with-the-spend", left["reservations"][r["call_id"]]["open"] is False
            and left["spent"] == {"measured": 3213, "provisional": 0}, f"{left}")
    control("usage-guard-keeps-a-cell-without-usage", (refusal(Supervisor._delete_cell, scratch, scratch / "nowhere") or "")
            .startswith("USAGE_UNCAPTURED"), "a cell was deleted before its usage was written")
    own = sorted((call_dir / "capture" / "runner-receipts").glob("*.json"))
    control("runner-receipt-kept-in-the-capture-never-the-calls", bool(own) and json.loads(own[0].read_text())["method_id"]
            .startswith("runner/") and receipts.read(call_dir)[0]["method_id"] == "distill/S6/run-a-S6-c1-a1", f"{own}")

    # the realization boundary (plan conventions): the identical fake runner is refused unless golden
    for label in ("live", "replay"):
        sx = Supervisor(d, clock=lambda: clock[0], cell_root=scratch, realization=label)
        sx.runner = sup.runner
        rx = sx.reserve("S6", f"realization-{label}", judge, "judge")
        got = refusal(sx.call, "S6", judge, packets.build(rx["call_id"], "S6", judge, "x\n", packets.schema_bytes(verdict_schema)),
                      verdict_schema, reservation=rx, caps=caps, view_window=False, max_output_tokens=4096)
        control(f"fake-runner-declared-{label}-refused", (got or "").startswith(f"RUNNER_REALIZATION_MISMATCH {rx['call_id']}")
                and not (d / "calls" / rx["call_id"]).exists(), f"{got}")
    pinned_golden = Supervisor(d, clock=lambda: clock[0], cell_root=scratch, realization="golden")  # judged, never launched
    control("pinned-runner-declared-golden-refused", (refusal(pinned_golden._admit_runner, "x", "claude") or "")
            .startswith("RUNNER_REALIZATION_MISMATCH x"), "the pinned runner was admitted under golden")
    control("pinned-runner-declared-live-admitted", refusal(Supervisor(d, realization="live")._admit_runner, "x", "claude") is None,
            "the pinned runner was refused under live")

    # refusals before anything starts, on a judge call (a non-actor call)
    r2 = sup.reserve("S6", "c2", judge, "judge")
    p2 = packets.build(r2["call_id"], "S6", judge, "x\n", packets.schema_bytes(verdict_schema))
    calls_before = sorted((d / "calls").iterdir())
    control("judge-call-without-a-reservation-refused", (refusal(sup.call, "S6", judge, p2, verdict_schema, reservation=None,
                                                                 caps=caps, view_window=False) or "").startswith("RESERVATION_MISSING S6"), "admitted")
    forged = {**r2, "amount": 1}
    control("forged-reservation-refused", (refusal(sup.call, "S6", judge, p2, verdict_schema, reservation=forged, caps=caps,
                                                   view_window=False) or "").startswith("RESERVATION_MISSING run-a-S6-c2-a1"), "admitted")
    for n, (missing, given) in enumerate((("compactions", {"tokens": 1000}), ("tokens", {"compactions": 2}),
                                          ("tokens, compactions", None))):
        r3 = sup.reserve("S6", f"cap-{n}", judge, "judge")
        p3 = packets.build(r3["call_id"], "S6", judge, "x\n", packets.schema_bytes(verdict_schema))
        got = refusal(sup.call, "S6", judge, p3, verdict_schema, reservation=r3, caps=given, view_window=False) or ""
        control(f"judge-call-without-the-{missing.replace(', ', '-and-')}-cap-refused", got.startswith(f"CAP_MISSING {r3['call_id']}: {missing}"), got)
    bare = p2.replace(packets.principles_block().encode(), b"")
    control("packet-without-the-principles-refused", "PRINCIPLES_MISSING" in (refusal(
        sup.call, "S6", judge, bare, verdict_schema, reservation=r2, caps=caps, view_window=False) or ""), "dispatched")
    r4 = sup.reserve("S6", "c4", judge, "judge")
    p4 = packets.build(r4["call_id"], "S6", judge, "x\n", None)
    control("packet-without-the-schema-reference-refused", "SCHEMA_REFERENCE_MISSING" in (refusal(
        sup.call, "S6", judge, p4, verdict_schema, reservation=r4, caps=caps, view_window=False) or ""), "dispatched")
    control("refused-calls-start-nothing", sorted((d / "calls").iterdir()) == calls_before, "a refused call left a call directory")
    r5 = sup.reserve("S6", "c5", judge, "judge")
    (d / "calls" / r5["call_id"]).mkdir()
    p5 = packets.build(r5["call_id"], "S6", judge, "x\n", packets.schema_bytes(verdict_schema))
    control("existing-call-directory-never-overwritten", (refusal(sup.call, "S6", judge, p5, verdict_schema, reservation=r5,
                                                                  caps=caps, view_window=False) or "").startswith("CALL_EXISTS"), "overwritten")
    copied = scratch / "receipt-copy"
    shutil.copytree(call_dir, copied)
    (copied / "receipt.json").unlink()
    control("receipt-the-launcher-refuses-is-named", (refusal(sup._receipt, copied, "S6", "run-a-S6-c1-a1", "not-a-seat", 0) or "")
            .startswith("RECEIPT_MISSING run-a-S6-c1-a1"), "a receipt was written for a malformed seat")

    # the corrective retry (design §3.2), through the gate
    sup.mode = "invalid-then-valid"
    out = sup.item("S6", "retry-ok", judge, "Is the rule present?\n", verdict_schema, case_type="judge", caps=caps, view_window=False)
    first = gate.accept(out["attempts"][0]) if out["attempts"] else {"codes": []}
    control("invalid-then-valid-accepted-with-both-attempts-kept", out["outcome"] == "accepted" and len(out["attempts"]) == 2
            and "SCHEMA_INVALID" in first["codes"] and out["accepted"] == out["attempts"][1], f"{out}")
    sup.mode = "invalid"
    out = sup.item("S6", "retry-no", judge, "Is the rule present?\n", verdict_schema, case_type="judge", caps=caps, view_window=False)
    control("two-invalid-attempts-retry-exhausted", out["outcome"] == "failed" and "RETRY_EXHAUSTED" in out["codes"]
            and len(out["attempts"]) == 2, f"{out}")

    # both caps stop a judge call mid-stream; the tree is killed and verified; usage stays provisional
    sup.mode = "big-first-request"
    began = time.monotonic()
    out = sup.item("S6", "capped", judge, "x\n", verdict_schema, case_type="judge", caps={"tokens": 50_000, "compactions": 2},
                   view_window=False)
    stopped_dir = pathlib.Path(out["attempts"][0]) if out["attempts"] else scratch
    stopped = (records.read_json(stopped_dir / "call.json") if (stopped_dir / "call.json").is_file() else {}).get("stopped") or {}
    control("token-cap-stops-the-call-mid-stream", out["outcome"] == "budget_stopped" and time.monotonic() - began < 20
            and stopped.get("why", "").startswith("token cap: measured and provisional 90352"), f"{out} {stopped.get('why')}")
    control("stopped-tree-verified-by-pid-and-start-time", stopped.get("freeze_at") is not None and not stopped.get("survivors")
            and not stopped.get("problems") and len(stopped.get("tree") or []) >= 1, f"{stopped}")
    stopped_usage = records.read_json(stopped_dir / "usage.json") if (stopped_dir / "usage.json").is_file() else {"requests": []}
    control("stopped-call-usage-provisional", usages.call_state(stopped_usage) == "provisional"
            and usages.totals(stopped_usage)["provisional"] == 90352, f"{stopped_usage}")
    control("stopped-call-refused-by-the-gate", "COMPLETION_INCOMPLETE" in gate.accept(stopped_dir)["codes"]
            and any("budget_stopped" in f for f in gate.accept(stopped_dir)["failures"]), f"{gate.accept(stopped_dir)['failures']}")
    sup.mode = "compactions"
    out = sup.item("S6", "compacting", judge, "x\n", verdict_schema, case_type="judge", caps={"tokens": 10 ** 9, "compactions": 2},
                   view_window=False)
    why = records.read_json(pathlib.Path(out["attempts"][0]) / "call.json")["stopped"]["why"] if out["attempts"] else None
    control("compaction-cap-stops-the-call", out["outcome"] == "budget_stopped" and why == "compaction cap: 3 compactions > 2", f"{out} {why}")

    # the breaker (design §13.2), once per signal kind, each from its own golden host and its own
    # run: a clean counterpart first; then the signal opens its provider, the item that met it and
    # the provider's reserved work are deferred as <stage>:<item>, nothing is retried, the next
    # item is refused before anything starts, the other provider keeps dispatching, and the work
    # resumes after resets_at — or, for a signal that names no reset, only at the operator's reset
    launches = []

    def counted(sup):
        inner = sup.runner
        sup.runner = lambda host, spec: launches.append(spec["call_id"]) or inner(host, spec)
        return sup

    def schema_for(seat):
        return (verdict_schema, "x\n") if seat == judge else (None, "Reply OK.\n")
    kinds = (("claude-result-api-error", judge, "api-error-limit", "result.api_error", False),
             ("claude-rate-limit-event", judge, "rate-limit-rejected", "rate_limit_event", True),
             ("codex-error-frame", luna, "ws-limit", "error frame", False),
             ("codex-otel-429", luna, "http-limit", "otel codex.api_request", False),
             ("codex-rate-limits", luna, "rate-limits-frame", "codex.rate_limits", False))
    # a Claude call past its own declared cap fails alone: the breaker stays closed and the next
    # call is admitted; the same sentence at a number the call did not declare stops the provider
    dc = run_dir("run-cap-overrun", {"S6": 400_000})
    sc = counted(supervisor(dc))
    sc.seed_from(calibrated)
    sc.mode, sc.extra = "cap-overrun", {}
    over = sc.item("S6", "over", judge, *schema_for(judge)[::-1], case_type="judge", caps=caps, view_window=False)
    sc.mode, sc.extra = "clean", {}
    after_over = sc.item("S6", "after", judge, *schema_for(judge)[::-1], case_type="judge", caps=caps, view_window=False)
    control("claude-cap-overrun-fails-the-call-and-leaves-the-breaker-closed",
            over["outcome"] == "failed" and over["attempts"] and all(
                any(line.startswith("COMPLETION_INCOMPLETE max_output_tokens: the response passed the call's declared cap of 4096")
                    for line in gate.accept(d)["failures"]) for d in over["attempts"])
            and not sc.breaker.is_open("claude", clock[0]) and sc.breaker.state()["claude"]["deferred_items"] == []
            and after_over["outcome"] == "accepted", f"{over} {after_over} {sc.breaker.state()['claude']}")
    dc2 = run_dir("run-cap-overrun-elsewhere", {"S6": 400_000})
    sc2 = counted(supervisor(dc2))
    sc2.seed_from(calibrated)
    sc2.mode, sc2.extra = "cap-overrun", {"overrun_at": 16}
    other_cap = sc2.item("S6", "over", judge, *schema_for(judge)[::-1], case_type="judge", caps=caps, view_window=False)
    control("claude-cap-overrun-at-an-undeclared-number-stops-the-provider",
            other_cap["outcome"] == "deferred" and sc2.breaker.is_open("claude", clock[0])
            and "PROVIDER_ERROR_UNRECOGNISED claude result.api_error" in other_cap["why"], f"{other_cap}")
    for name, seat, mode, source, resets in kinds:
        dk = run_dir(f"run-{name}", {"S6": 400_000})
        sk = counted(supervisor(dk))
        sk.seed_from(calibrated)
        host, other = seat.partition(":")[0], luna if seat == judge else judge
        schema, payload = schema_for(seat)
        out = sk.item("S6", "clean", seat, payload, schema, case_type="judge", caps=caps, view_window=False)
        control(f"{name}-clean-counterpart-accepted", out["outcome"] == "accepted" and not sk.breaker.is_open(host, clock[0]), f"{out}")
        parked = sk.reserve("S6", "reserved", seat, "judge")
        sk.mode, sk.extra = mode, {"resets_at": clock[0] + 3600}
        out = sk.item("S6", "hit", seat, payload, schema, case_type="judge", caps=caps, view_window=False)
        state = sk.breaker.state()[host]
        control(f"{name}-opens-its-provider-without-retry", out["outcome"] == "deferred" and len(out["attempts"]) == 1
                and sk.breaker.is_open(host, clock[0]) and (state["signal"] or {}).get("source") == source
                and f"PROVIDER_LIMIT {host} {source}" in out["why"], f"{out} {state}")
        sk.mode, before = "clean", list(launches)
        got = refusal(sk.call, "S6", seat, packets.build(parked["call_id"], "S6", seat, payload,
                                                         packets.schema_bytes(schema) if schema else None),
                      schema, reservation=parked, caps=caps, view_window=False)
        out = sk.item("S6", "next", seat, payload, schema, case_type="judge", caps=caps, view_window=False)
        control(f"{name}-reserved-and-next-work-refused-before-anything-starts", (got or "").startswith(f"PROVIDER_DEFERRED {host}")
                and out["outcome"] == "deferred" and out["why"].startswith(f"PROVIDER_DEFERRED {host}") and launches == before
                and not (dk / "calls" / parked["call_id"]).exists(), f"{got} {out} {launches[len(before):]}")
        control(f"{name}-deferred-items-are-stage-qualified", sorted(sk.breaker.state()[host]["deferred_items"])
                == ["S6:hit", "S6:next", "S6:reserved"], f"{sk.breaker.state()[host]}")
        other_schema, other_payload = schema_for(other)
        out = sk.item("S6", "other", other, other_payload, other_schema, case_type="judge", caps=caps, view_window=False)
        control(f"{name}-other-provider-keeps-dispatching", out["outcome"] == "accepted", f"{out}")
        if resets:
            early, items = sk.breaker.resume(host, clock[0] + 10), sk.breaker.resume(host, clock[0] + 3600)
        else:
            early, items = sk.breaker.resume(host, 10 ** 12), sk.breaker.reset(host)
        control(f"{name}-resumes-every-deferred-item", early == [] and sorted(items) == ["S6:hit", "S6:next", "S6:reserved"]
                and not sk.breaker.is_open(host, clock[0] + 3600), f"{early} {items}")
        out = sk.item("S6", "hit", seat, payload, schema, case_type="judge", caps=caps, view_window=False)
        control(f"{name}-resumed-item-dispatches-its-next-attempt", out["outcome"] == "accepted"
                and out["attempts"][0].endswith("-S6-hit-a2"), f"{out}")
    d2 = run_dir("run-b", {"S6": 200_000})
    sup2 = supervisor(d2, "text-limit")
    sup2.seed_from(calibrated)
    out = sup2.item("S6", "texty", judge, "x\n", verdict_schema, case_type="judge", caps=caps, view_window=False)
    control("usage-limit-text-without-a-field-is-unrecognised", out["outcome"] == "deferred"
            and "PROVIDER_ERROR_UNRECOGNISED claude result" in out["why"] and sup2.breaker.is_open("claude", 10 ** 12)
            and sup2.breaker.resume("claude", 10 ** 12) == [] and sup2.breaker.reset("claude") == ["S6:texty"], f"{out}")

    # a signal read mid-call closes admission at once: the limited call is still alive while a
    # second dispatch to the provider is tried, refused before it starts, and the other provider runs
    dl = run_dir("run-live-limit", {"S6": 400_000})
    hanging = counted(supervisor(dl, "limit-then-hang", resets_at=clock[0] + 3600, release=str(scratch / "release")))
    hanging.seed_from(calibrated)
    beside = counted(supervisor(dl))
    waiting = beside.reserve("S6", "reserved-earlier", judge, "judge")
    outcome = {}
    worker = threading.Thread(target=lambda: outcome.update(hanging.item("S6", "hanging", judge, "x\n", verdict_schema,
                                                                         case_type="judge", caps=caps, view_window=False)))
    worker.start()
    for _ in range(1000):
        if hanging.breaker.is_open("claude", clock[0]):
            break
        time.sleep(0.01)
    before = list(launches)
    out = beside.item("S6", "second", judge, "x\n", verdict_schema, case_type="judge", caps=caps, view_window=False)
    parked_live = beside.ledger()["stages"]["S6"]["reservations"][waiting["call_id"]]["outcome"]
    alive = worker.is_alive()
    other = beside.item("S6", "codex-meanwhile", luna, "Reply OK.\n", None, case_type="judge", caps=caps, view_window=False)
    (scratch / "release").write_text("")
    worker.join(30)
    control("limit-read-mid-call-closes-admission-at-once", alive and out["outcome"] == "deferred" and launches[len(before):]
            == [c for c in launches[len(before):] if "-codex-meanwhile-" in c] and other["outcome"] == "accepted", f"{alive} {out} {other}")
    control("work-reserved-before-the-signal-is-deferred-while-the-call-runs", alive and parked_live == "deferred"
            and outcome.get("outcome") == "deferred" and sorted(beside.breaker.state()["claude"]["deferred_items"])
            == ["S6:hanging", "S6:reserved-earlier", "S6:second"], f"{outcome} {beside.breaker.state()['claude']}")

    # admission is synchronized with the breaker: a transition in progress when a call passed its
    # early check (the lock held, the state written before release) still refuses that call
    dt = run_dir("run-transition", {"S6": 400_000})
    st = counted(supervisor(dt))
    st.seed_from(calibrated)
    rt = st.reserve("S6", "mid-transition", judge, "judge")
    held_lock, result = threading.Event(), {}

    def transition():
        with stagelock.hold(dt, "breaker"):
            held_lock.set()
            time.sleep(0.3)
            state = st.breaker.state()
            state["claude"].update(open=True, since=clock[0], resets_at=clock[0] + 3600,
                                   signal={"kind": "limit", "source": "rate_limit_event", "resets_at": clock[0] + 3600, "detail": "x"})
            st.breaker._write(state)
    opener = threading.Thread(target=transition)
    opener.start()
    held_lock.wait(5)
    before = list(launches)
    result["got"] = refusal(st.call, "S6", judge, packets.build(rt["call_id"], "S6", judge, "x\n", packets.schema_bytes(verdict_schema)),
                            verdict_schema, reservation=rt, caps=caps, view_window=False)
    opener.join(10)
    control("admission-waits-for-a-breaker-transition-in-progress", (result["got"] or "").startswith("PROVIDER_DEFERRED claude")
            and launches == before and not (dt / "calls" / rt["call_id"]).exists(), f"{result} {launches[len(before):]}")

    # late monitor input (a delayed reader): a cap read after the root exited still stops what is
    # left of the tree, and a send read after the stop still reaches the boundary verdict
    class SlowMonitor(monitors.Monitor):
        """Every line reaches the ledger `delay` seconds after it was read, `after` once a cap tripped."""
        delay, after = 0.3, 0.3

        def line(self, text, at=None):
            time.sleep(self.after if self.trip is not None else self.delay)
            super().line(text, at)

    def orphan_of(path):
        held = json.loads(pathlib.Path(path).read_text()) if pathlib.Path(path).is_file() else {}
        return held, bool(held) and stop.same(stop.ps_table(), held["pid"], held["start"])

    for host_seat, mode, delay, name in ((judge, "late-cap", (0.3, 0.3), "claude"), (luna, "late-send", (0.0, 0.5), "codex")):
        dlate = run_dir(f"run-late-{name}", {"S6": 400_000})
        sl = supervisor(dlate, mode, orphan=str(scratch / f"orphan-{name}"))
        sl.monitor = type("Slow", (SlowMonitor,), {"delay": delay[0], "after": delay[1]})
        sl.seed_from(calibrated)
        rl = sl.reserve("S6", "late", host_seat, "judge")
        schema, payload = schema_for(host_seat)
        late_dir = sl.call("S6", host_seat, packets.build(rl["call_id"], "S6", host_seat, payload,
                                                          packets.schema_bytes(schema) if schema else None),
                           schema, reservation=rl, caps={"tokens": 50_000, "compactions": 2}, view_window=False)
        late = records.read_json(late_dir / "call.json")["stopped"] or {}
        orphan, alive = orphan_of(scratch / f"orphan-{name}")
        if name == "claude":
            control("cap-read-after-the-root-exited-still-stops-the-tree", late.get("why", "").startswith("token cap")
                    and late.get("freeze_at") is not None and not late.get("survivors") and orphan
                    and orphan["pid"] in {m["pid"] for m in late.get("tree", [])} and not alive, f"{late} orphan {orphan} alive {alive}")
        else:
            control("send-read-after-the-stop-reaches-the-boundary", late.get("why", "").startswith("token cap")
                    and any(p.startswith("STOP_BOUNDARY_VIOLATED send#2") for p in late.get("problems", [])) and not alive
                    and late.get("boundary") == "STOP_BOUNDARY_VIOLATED", f"{late.get('problems')} {late.get('why')} {late.get('boundary')}")
        if alive:
            stop._signal(stop.ps_table(), {orphan["pid"]: orphan}, stop.signal.SIGKILL)

    # a reader still busy after the runner exited is drained to its end before anything is final:
    # every line it holds waits until the supervisor's final accounting begins, or 11 s — past the
    # 10 s a timed join once gave each reader —, so a drain that gives up on a reader accounts
    # before the cap its lines trip, and stops nothing
    class HeldMonitor(monitors.Monitor):
        release = None

        def line(self, text, at=None):
            self.release.wait(30)
            super().line(text, at)
    dh = run_dir("run-held-reader", {"S6": 400_000})
    sh = supervisor(dh)
    sh.seed_from(calibrated)
    release = threading.Event()
    sh.monitor = type("Held", (HeldMonitor,), {"release": release})
    accounting = sh._usage
    sh._usage = lambda *args: (release.set(), accounting(*args))[1]
    timer = threading.Timer(11.0, release.set)
    timer.start()
    rh = sh.reserve("S6", "held", luna, "judge")
    held_dir = sh.call("S6", luna, packets.build(rh["call_id"], "S6", luna, "Reply OK.\n", None), None, reservation=rh,
                       caps={"tokens": 20_000, "compactions": 2}, view_window=False)
    timer.cancel()
    held_stop = records.read_json(held_dir / "call.json")["stopped"] or {}
    held_rows = [(r["role"], r["state"]) for r in records.read_json(held_dir / "usage.json")["requests"]]
    control("reader-outliving-the-runner-is-drained-before-final-accounting", held_stop.get("why", "")
            .startswith("token cap: measured and provisional 23628 >= 20000") and held_stop.get("freeze_at") is not None
            and held_rows == [("warmup", "measured"), ("main", "measured")], f"{held_stop} {held_rows}")

    control("held-reader-call-boundary-is-clean", held_stop.get("boundary") == "clean" and not held_stop.get("uncertain")
, f"{held_stop}")
    # an uncertain boundary is never read as clean: a frame header stamped after the freeze whose
    # payload never comes (the host killed first) leaves the stored record and the item UNVERIFIED
    du = run_dir("run-uncertain-boundary", {"S6": 400_000})
    su = supervisor(du, "late-truncated")
    su.seed_from(calibrated)
    item_out = su.item("S6", "uncertain", luna, "Reply OK.\n", None, case_type="judge", caps=caps, view_window=False)
    uncertain_stop = records.read_json(pathlib.Path(item_out["attempts"][0]) / "call.json")["stopped"] or {} if item_out["attempts"] else {}
    control("uncertain-boundary-is-unverified-on-the-record-and-the-item", item_out["outcome"] == "budget_stopped"
            and uncertain_stop.get("boundary") == "STOP_BOUNDARY_UNVERIFIED" and item_out.get("boundary") == "STOP_BOUNDARY_UNVERIFIED"
            and any(u.startswith("truncated#1:") for u in uncertain_stop.get("uncertain", [])) and not uncertain_stop.get("problems"),
            f"{item_out} {uncertain_stop}")

    # a pipe still open after the root exited: the tree is stopped, swept and verified as at a cap,
    # which kills an ordinary child holding it; the drain then waits at most one more deadline, so a
    # holder that was never in the tree (handed the pipe) cannot hold the call. Either way the call
    # is drain_unfinished, usage incomplete, boundary unverified — no holder is identified. The
    # positive counterpart is the held reader above, drained in full under the default deadline.
    def drain_expired(name, mode, **spec):
        directory = run_dir(f"run-drain-{name}", {"S6": 400_000})
        sx = supervisor(directory, mode, **spec)
        sx.seed_from(calibrated)
        sx.drain_deadline_s = 1.0
        reserved = sx.reserve("S6", name, luna, "judge")
        began = time.monotonic()
        held_dir = sx.call("S6", luna, packets.build(reserved["call_id"], "S6", luna, "Reply OK.\n", None), None,
                           reservation=reserved, caps=caps, view_window=False)
        record = records.read_json(held_dir / "call.json")["stopped"] or {}
        return time.monotonic() - began, record, held_dir

    def unfinished(record, held_dir):
        return record.get("outcome") == "drain_unfinished" and record.get("boundary") == "STOP_BOUNDARY_UNVERIFIED" \
            and record.get("why", "").startswith("DRAIN_UNFINISHED") and "holders" not in record \
            and records.read_json(held_dir / "usage.json")["reconciled"] is False and "COMPLETION_INCOMPLETE" in gate.accept(held_dir)["codes"]
    took, child_stop, child_dir = drain_expired("child", "surviving-child", orphan=str(scratch / "orphan-child"))
    kid, kid_alive = orphan_of(scratch / "orphan-child")
    control("surviving-child-holding-a-pipe-is-stopped-and-killed", took < 1.0 + 6.0 and bool(kid) and not kid_alive
            and kid["pid"] in {m["pid"] for m in child_stop.get("tree", [])} and not child_stop.get("survivors")
            and unfinished(child_stop, child_dir), f"took {took:.1f} s, {child_stop}, alive {kid_alive}")
    if kid_alive:
        stop._signal(stop.ps_table(), {kid["pid"]: kid}, stop.signal.SIGKILL)
    socket_path = str(scratch / "hs")
    holder_proc = subprocess.Popen([sys.executable, "-c", "import socket, sys, time\ns = socket.socket(socket.AF_UNIX)\n"
                                    "s.bind(sys.argv[1])\ns.listen(8)\nheld = []\nwhile True:\n    c, _ = s.accept()\n"
                                    "    held.append((c, socket.recv_fds(c, 16, 4)))\n    c.send(b'k')", socket_path],
                                   start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(500):
            if pathlib.Path(socket_path).exists():
                break
            time.sleep(0.01)
        took, escaped_stop, escaped_dir = drain_expired("escaped", "escaped-holder", holder_socket=socket_path)
        control("escaped-holder-of-a-pipe-returns-unfinished-in-bounded-time", took < 2 * 1.0 + 6.0 and holder_proc.poll() is None
                and unfinished(escaped_stop, escaped_dir), f"took {took:.1f} s, {escaped_stop}")
    finally:  # the holder outlives no failure of the control above
        holder_proc.kill()
        holder_proc.wait()

    # a retry warning in a call of two threads is attributed to neither: the gate fails the call
    # USAGE_ATTRIBUTION_UNKNOWN, its usage stays unreconciled, and the item's outcome names it
    dw = run_dir("run-two-threads-retry", {"S6": 400_000})
    sw = supervisor(dw, "two-threads-retry")
    sw.seed_from(calibrated)
    out = sw.item("S6", "two-threads", luna, "Reply OK.\n", None, case_type="judge", caps=caps, view_window=False)
    first_usage = records.read_json(pathlib.Path(out["attempts"][0]) / "usage.json") if out["attempts"] else {}
    control("warning-over-two-threads-fails-attribution-in-the-gate-and-the-item", out["outcome"] == "failed"
            and "USAGE_ATTRIBUTION_UNKNOWN" in out.get("codes", []) and first_usage.get("reconciled") is False
            and "USAGE_ATTRIBUTION_UNKNOWN" in gate.accept(out["attempts"][0])["codes"], f"{out} {first_usage.get('reconciled')}")
    control("warning-over-two-threads-keeps-the-corrective-retry", len(out["attempts"]) == 2, f"{out}")
    # a retry warning beside a second thread's send that nothing answers: only the sent frame names
    # that thread, and it is enough — attribution unknown in the gate and the item, usage
    # unreconciled, the corrective retry kept
    ds = run_dir("run-second-send-retry", {"S6": 400_000})
    ss = supervisor(ds, "second-send-retry")
    ss.seed_from(calibrated)
    out = ss.item("S6", "second-send", luna, "Reply OK.\n", None, case_type="judge", caps=caps, view_window=False)
    first_usage = records.read_json(pathlib.Path(out["attempts"][0]) / "usage.json") if out["attempts"] else {}
    control("warning-beside-a-second-thread-only-a-send-names-fails-attribution-and-retries", out["outcome"] == "failed"
            and "USAGE_ATTRIBUTION_UNKNOWN" in out.get("codes", []) and first_usage.get("reconciled") is False
            and len(out["attempts"]) == 2 and "USAGE_ATTRIBUTION_UNKNOWN" in gate.accept(out["attempts"][0])["codes"],
            f"{out} {first_usage.get('reconciled')}")

    # a cap that trips while a holder outside the tree keeps a pipe open: the drain expiry decides,
    # so the call is drain_unfinished with the cap kept beside it, usage incomplete, boundary
    # unverified, refused by the gate, and the item failed (the escaped holder above is the
    # uncapped counterpart, the token cap the unheld one)
    socket_path = str(scratch / "hc")
    holder_proc = subprocess.Popen([sys.executable, "-c", "import socket, sys, time\ns = socket.socket(socket.AF_UNIX)\n"
                                    "s.bind(sys.argv[1])\ns.listen(8)\nheld = []\nwhile True:\n    c, _ = s.accept()\n"
                                    "    held.append((c, socket.recv_fds(c, 16, 4)))\n    c.send(b'k')", socket_path],
                                   start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(500):
            if pathlib.Path(socket_path).exists():
                break
            time.sleep(0.01)
        dc = run_dir("run-capped-and-held", {"S6": 400_000})
        sc = supervisor(dc, "capped-escaped-holder", holder_socket=socket_path)
        sc.seed_from(calibrated)
        sc.drain_deadline_s = 1.0
        out = sc.item("S6", "capped-held", judge, "x\n", verdict_schema, case_type="judge", caps=caps, view_window=False)
        held_dir = pathlib.Path(out["attempts"][0]) if out["attempts"] else scratch
        record = (records.read_json(held_dir / "call.json") if (held_dir / "call.json").is_file() else {}).get("stopped") or {}
        control("drain-expiry-decides-over-a-cap", unfinished(record, held_dir) and out["outcome"] == "failed"
                and out.get("boundary") == "STOP_BOUNDARY_UNVERIFIED" and len(out["attempts"]) == 1
                and (record.get("cap") or {}).get("why", "").startswith("token cap: measured and provisional 90352")
                and not any(f.startswith("RECORD_INTEGRITY call.json") for f in gate.accept(held_dir)["failures"]),
                f"{out} {record} {gate.accept(held_dir)['failures']}")
    finally:
        holder_proc.kill()
        holder_proc.wait()

    # a stop after the root exited still finds the runner unreaped, so its group id is provably its
    # own; the surviving child above is that path (the ordinary call's stop is the positive one)
    anchors, real_stop = [], stop.stop_tree

    def stop_watched(proc, sampler, **kwargs):
        anchors.append((stop.exited(proc), stop.anchored(proc)))
        return real_stop(proc, sampler, **kwargs)
    stop.stop_tree = stop_watched
    try:
        took, late_stop, late_dir = drain_expired("late-anchor", "surviving-child", orphan=str(scratch / "orphan-late"))
    finally:
        stop.stop_tree = real_stop
    kid, kid_alive = orphan_of(scratch / "orphan-late")
    control("stop-after-the-root-exited-finds-the-runner-unreaped", anchors == [(True, True)] and not kid_alive
            and not any("was reaped before the stop" in p for p in late_stop.get("problems", [])), f"{anchors} {late_stop}")
    if kid_alive:
        stop._signal(stop.ps_table(), {kid["pid"]: kid}, stop.signal.SIGKILL)

    # an expired drain is unverified by rule even where a send after the freeze was observed: the
    # violation stays in the problems, the verdict on the call and the item is UNVERIFIED, usage
    # incomplete, the gate refuses it (the late send alone, above, is VIOLATED)
    socket_path = str(scratch / "hv")
    holder_proc = subprocess.Popen([sys.executable, "-c", "import socket, sys, time\ns = socket.socket(socket.AF_UNIX)\n"
                                    "s.bind(sys.argv[1])\ns.listen(8)\nheld = []\nwhile True:\n    c, _ = s.accept()\n"
                                    "    held.append((c, socket.recv_fds(c, 16, 4)))\n    c.send(b'k')", socket_path],
                                   start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(500):
            if pathlib.Path(socket_path).exists():
                break
            time.sleep(0.01)
        dv = run_dir("run-held-late-send", {"S6": 400_000})
        sv = supervisor(dv, "held-late-send", holder_socket=socket_path)
        sv.seed_from(calibrated)
        sv.drain_deadline_s = 1.0
        out = sv.item("S6", "held-late-send", luna, "Reply OK.\n", None, case_type="judge", caps=caps, view_window=False)
        held_dir = pathlib.Path(out["attempts"][0]) if out["attempts"] else scratch
        record = (records.read_json(held_dir / "call.json") if (held_dir / "call.json").is_file() else {}).get("stopped") or {}
        control("drain-expiry-is-unverified-over-an-observed-violation", unfinished(record, held_dir) and out["outcome"] == "failed"
                and out.get("boundary") == "STOP_BOUNDARY_UNVERIFIED"
                and monitors.boundary_verdict(record.get("problems", []), []) == "STOP_BOUNDARY_VIOLATED",
                f"{out} {record}")
    finally:
        holder_proc.kill()
        holder_proc.wait()

    # the first stop-time listing fails and the later ones recover: the runner dies through its
    # handle, the call returns in bounded time, and its stop is named unverified (the token cap
    # above is the positive counterpart, every listing sound)
    def bounded(fn, limit=30.0):
        got = []
        worker = threading.Thread(target=lambda: got.append(fn()), daemon=True)
        worker.start()
        worker.join(limit)
        return (got[0] if got else None), worker.is_alive()
    listed, real_stop, armed = stop.ps_table, stop.stop_tree, []

    def stop_armed(*args, **kwargs):
        armed.append(True)
        return real_stop(*args, **kwargs)

    def fails_once():
        if armed == [True] and not isinstance(threading.current_thread(), stop.TreeSampler):
            armed.append(False)
            raise stop.ListingFailed("planted: the first stop-time listing")
        return listed()
    dr = run_dir("run-listing-recovers", {"S6": 400_000})
    sr = supervisor(dr, "big-first-request")
    sr.seed_from(calibrated)
    sr.drain_deadline_s = 1.0
    stop.stop_tree, stop.ps_table = stop_armed, fails_once
    try:
        out, hung = bounded(lambda: sr.item("S6", "recovers", judge, "x\n", verdict_schema, case_type="judge",
                                            caps=caps, view_window=False))
    finally:
        stop.stop_tree, stop.ps_table = real_stop, listed
    record = records.read_json(pathlib.Path(out["attempts"][0]) / "call.json")["stopped"] or {} if out and out["attempts"] else {}
    rows = stop.ps_table()
    left = [m["pid"] for m in record.get("tree", []) if stop.same(rows, m["pid"], m["start"])]
    control("first-stop-listing-failing-then-recovering-returns-unverified-with-the-runner-dead", not hung
            and out["outcome"] == "budget_stopped" and record.get("boundary") == "STOP_BOUNDARY_UNVERIFIED"
            and any(p.startswith("STOP_FREEZE_UNVERIFIED the process listing failed (planted") for p in record.get("problems", []))
            and record.get("tree") and not left and not record.get("survivors"), f"hung {hung}, {out}, {record}, left {left}")
    stop._signal(rows, {m["pid"]: m for m in record.get("tree", [])}, stop.signal.SIGKILL)

    # a runner that outlives its stop is never awaited without bound: the stop named it, and the
    # call still returns
    survived = []

    def stop_nothing(proc, sampler, **kwargs):
        sampler.halt.set()
        survived.append(proc)
        now = time.time()
        return {"decided_at": now, "freeze_at": None, "kill_at": now, "tree": [], "survivors": [proc.pid],
                "problems": [f"STOP_SURVIVORS pids [{proc.pid}] outlived the kill (planted)"]}
    dn = run_dir("run-runner-survives", {"S6": 400_000})
    sn = supervisor(dn, "big-first-request")
    sn.seed_from(calibrated)
    sn.drain_deadline_s = 1.0
    stop.stop_tree = stop_nothing
    try:
        out, hung = bounded(lambda: sn.item("S6", "survives", judge, "x\n", verdict_schema, case_type="judge",
                                            caps=caps, view_window=False))
    finally:
        stop.stop_tree = real_stop
        for proc in survived:
            proc.kill()
    control("runner-outliving-its-stop-is-not-awaited-without-bound", not hung and out is not None
            and out["outcome"] == "failed" and out.get("boundary") == "STOP_BOUNDARY_UNVERIFIED" and out["attempts"]
            and not (pathlib.Path(out["attempts"][0]) / "receipt.json").exists()
            and "COMPLETION_INCOMPLETE" in gate.accept(out["attempts"][0])["codes"], f"hung {hung}, {out}")

    # a provider signal and a stop together: the item is deferred, and the stop's boundary verdict
    # travels with it beside the signal
    dl2 = run_dir("run-limit-and-stop", {"S6": 400_000})
    sl2 = supervisor(dl2, "limit-late-send")
    sl2.seed_from(calibrated)
    out = sl2.item("S6", "limit-and-stop", luna, "Reply OK.\n", None, case_type="judge", caps=caps, view_window=False)
    both = records.read_json(pathlib.Path(out["attempts"][0]) / "call.json") if out["attempts"] else {}
    control("provider-deferral-and-stop-boundary-travel-together", out["outcome"] == "deferred"
            and "PROVIDER_LIMIT codex" in out["why"] and out.get("boundary") == "STOP_BOUNDARY_VIOLATED"
            and (both.get("stopped") or {}).get("boundary") == "STOP_BOUNDARY_VIOLATED"
            and "COMPLETION_INCOMPLETE" in gate.accept(out["attempts"][0])["codes"], f"{out} {both.get('stopped')}")

    # a frames-blind (HTTPS fallback) call: its usage comes from the otel ledger, its dropped stream is an attempt
    df = run_dir("run-f", {"S6": 200_000})
    sf = supervisor(df, "https-fallback")
    sf.seed_from(calibrated)
    rf = sf.reserve("S6", "fallback", luna, "judge")
    blind_dir = sf.call("S6", luna, packets.build(rf["call_id"], "S6", luna, "Reply OK.\n", None), None, reservation=rf,
                        caps=caps, view_window=False)
    blind = gate.accept(blind_dir)
    control("frames-blind-call-usage-from-otel-and-its-interrupted-attempt",
            "frames_blind" in blind["codes"] and blind["usage"] == {"measured": 25424, "provisional": 0, "unresolved": 1,
                                                                    "complete": False}
            and [t["interrupted"] for t in (blind["attempts"] or {}).values()] == [1], f"{blind['usage']} {blind['attempts']}")

    # mixed coverage (golden): one request over websocket, the next over HTTPS; the otel-only
    # request is charged, and the live monitor counts it toward the token cap
    dm = run_dir("run-mixed", {"S6": 400_000})
    sm = supervisor(dm, "mixed-fallback")
    sm.seed_from(calibrated)
    rm = sm.reserve("S6", "mixed", luna, "judge")
    mixed_dir = sm.call("S6", luna, packets.build(rm["call_id"], "S6", luna, "Reply OK.\n", None), None, reservation=rm,
                        caps=caps, view_window=False)
    mixed = gate.accept(mixed_dir)
    control("mixed-coverage-call-charges-its-otel-only-request", "frames_blind" in mixed["codes"]
            and (mixed["usage"] or {}).get("measured") == 25424
            and sm.ledger()["stages"]["S6"]["reservations"][rm["call_id"]]["spent"]["measured"] == 25424, f"{mixed['usage']}")
    rm = sm.reserve("S6", "mixed-capped", luna, "judge")
    capped_dir = sm.call("S6", luna, packets.build(rm["call_id"], "S6", luna, "Reply OK.\n", None), None, reservation=rm,
                         caps={"tokens": 25424, "compactions": 2}, view_window=False)
    capped = records.read_json(capped_dir / "call.json")["stopped"] or {}
    control("otel-only-usage-reaches-the-token-cap-through-the-supervisor", capped.get("why", "")
            .startswith("token cap: measured and provisional 25424"), f"{capped.get('why')}")

    # the closing reconciliation of a Claude call (design §13.3): the residual of result.modelUsage
    # is the one compaction's only when every other request reconciled — measured, and bound to its
    # own transcript api-request record (one per HTTP attempt) —; otherwise it stays unexplained.
    # Each case is fed through the monitor as the host emits it: the stream's requesting status,
    # message_start and message_delta, the transcript's api-request record, the compaction marker.
    main_tokens = {"input": 2, "output": 61, "cache_read": 2800, "cache_creation": 350}
    fed = {"status": ("line", {"type": "system", "subtype": "status", "status": "requesting"}),
           "attempt": ("transcript", {"type": "api-request", "timestamp": "2026-10-21T00:00:01.000Z"}),
           "start": ("line", {"type": "stream_event", "event": {"type": "message_start", "message": {
               "id": "msg_1", "model": "claude-haiku-5-5", "usage": {"input_tokens": 2, "cache_read_input_tokens": 2800,
                                                                     "cache_creation_input_tokens": 350}}}}),
           "delta": ("line", {"type": "stream_event", "event": {"type": "message_delta", "usage": {"output_tokens": 61}}}),
           "compaction": ("line", {"type": "system", "subtype": "compact_boundary", "compact_metadata": {"trigger": "auto"}})}
    request = ("status", "attempt", "start", "delta")

    def residual_case(steps, extra):
        m = monitors.Monitor("claude", {"tokens": 10 ** 9, "compactions": 9})
        for step in steps:
            how, obj = fed[step]
            m.line(json.dumps(obj), 1.0) if how == "line" else m.transcript("main", "main", obj, 1.0)
        total = {k: main_tokens[k] + extra.get(k, 0) for k in main_tokens}
        model_usage = {"claude-haiku-5-5": {"inputTokens": total["input"], "outputTokens": total["output"],
                                            "cacheReadInputTokens": total["cache_read"], "cacheCreationInputTokens": total["cache_creation"]}}
        subject = {"host": "claude", "call_id": "x", "stage": "S6", "seat": judge}
        # the two halves are called in the order settlement calls them, with the stop decision between
        # them in production (HC#2): reconciliation first, then the record the projection completes
        reconciled = sup._reconcile(call_dir, subject, m, {"modelUsage": model_usage}, None, 0)
        rec = sup._usage(call_dir, subject, m, reconciled, 10)
        return rec, [(r["id"], r["state"], r["estimate"], usages.request_total(r) if r["state"] == "measured" else None)
                     for r in rec["requests"]], usages.check(rec)
    extra = {"output": 1000, "cache_read": 9000}
    rec, rows, problems = residual_case(request + ("compaction",), extra)
    control("residual-is-the-one-compaction-once-every-other-request-reconciled", rows == [
        ("main#1", "measured", None, 3213), ("compaction#1", "measured", None, 10000)] and rec["reconciled"] and not problems,
        f"{rows} {rec['reconciled']}")
    rec, rows, problems = residual_case(tuple(s for s in request if s != "attempt") + ("compaction",), extra)
    control("residual-beside-a-response-without-its-attempt-record-stays-unexplained", rows == [
        ("main#1", "measured", None, 3213), ("compaction#1", "provisional", 6426, None), ("aggregate-residual", "provisional", 3574, None)]
            and not rec["reconciled"] and not problems, f"{rows} {rec['reconciled']}")
    rec, rows, problems = residual_case(request + ("attempt",), {"cache_read": 5000})
    control("residual-beside-an-attempt-record-no-response-answers-stays-unexplained", rows == [
        ("main#1", "measured", None, 3213), ("main#2", "provisional", 3213, None), ("aggregate-residual", "provisional", 1787, None)]
            and not rec["reconciled"] and not problems, f"{rows} {rec['reconciled']}")
    rec, rows, problems = residual_case(request, {"cache_read": 400})
    control("residual-without-a-compaction-is-not-made-measured", rows == [
        ("main#1", "measured", None, 3213), ("aggregate-residual", "provisional", 400, None)] and not rec["reconciled"]
            and not problems, f"{rows} {rec['reconciled']}")
    rec, rows, problems = residual_case(request + ("compaction", "compaction"), {"cache_read": 9000})
    control("residual-over-two-compactions-stays-at-their-estimates", rows == [
        ("main#1", "measured", None, 3213), ("compaction#1", "provisional", 6426, None), ("compaction#2", "provisional", 6426, None)]
            and not rec["reconciled"] and not problems, f"{rows} {rec['reconciled']}")
    rec, rows, problems = residual_case(request, {})
    control("a-call-whose-every-request-reconciled-and-no-residual-is-reconciled", rows == [("main#1", "measured", None, 3213)]
            and rec["reconciled"] and not problems, f"{rows} {rec['reconciled']}")

    # reservations: atomic against a race, not_done below one reservation, amendment before spend
    def race(locked):
        directory = run_dir(f"race-{'locked' if locked else 'unlocked'}", {"S7": 5100})
        racer = supervisor(directory)
        racer.seed_from(calibrated)
        barrier, results = threading.Barrier(2, timeout=1.0), []

        def between():
            with contextlib.suppress(threading.BrokenBarrierError):
                barrier.wait()

        def one(n):
            try:
                results.append(racer.reserve("S7", f"r{n}", judge, "judge", _between=between, _locked=locked)["call_id"])
            except Exhausted as exc:
                results.append(str(exc).split(":")[0])
        threads = [threading.Thread(target=one, args=(n,)) for n in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        return sorted(results), racer.remaining("S7")
    got, remaining = race(True)
    control("reservation-race-admits-exactly-one", len(got) == 2 and got.count("BUDGET_EXHAUSTED S7") == 1 and remaining == 5100 - 3400,
            f"{got} remaining {remaining}")
    got, _remaining = race(False)
    control("check-then-reserve-variant-admits-both", len(got) == 2 and "BUDGET_EXHAUSTED S7" not in got, f"{got}")
    nothing = sorted((d / "calls").iterdir())
    out = sup.item("S8", "starved", judge, "x\n", verdict_schema, case_type="judge", caps=caps, view_window=False)
    control("budget-below-one-reservation-not-done", out["outcome"] == "not_done" and sorted((d / "calls").iterdir()) == nothing
            and sup.ledger()["stages"]["S8"]["not_done"][0]["item"] == "starved", f"{out}")
    declare.amend(d, [("budget.per_stage.S8", 10_000)], "fund the S8 item", scope=["S8"])
    r8 = sup.reserve("S8", "starved", judge, "judge")
    control("budget-amendment-recorded-before-spend", r8["declaration_seq"] == 1 and sup.remaining("S8") == 10_000 - 3400, f"{r8}")
    run_json = records.run_json_path(d)
    edited = json.loads(run_json.read_text(encoding="utf-8"))
    edited["budget"]["per_stage"]["S9"] = 10 ** 9
    run_json.write_text(json.dumps(edited), encoding="utf-8")
    control("hand-edited-budget-refused", (refusal(sup.reserve, "S9", "x", judge, "judge") or "").startswith("DECLARATION_DRIFT"),
            "spent against an unrecorded budget")

    # the calibration tranche (S-15)
    d3 = run_dir("run-c", {"S6": 200_000, "S7": 10})
    sup3 = supervisor(d3)
    control("provisional-class-refused-broad-dispatch", (refusal(sup3.reserve, "S6", "b1", judge, "judge") or "")
            .startswith("CALIBRATION_PROVISIONAL S6|claude:claude-haiku-5-5/low|judge"), "dispatched broadly")
    rc = sup3.reserve("S6", "k1", judge, "judge", tranche="calibration")
    control("calibration-reserves-the-seed-times-the-factor", (rc["amount"], rc["calibration"]) == (2 * SEEDS["claude"]["tokens"], "provisional"),
            f"{rc}")
    control("calibration-runs-at-concurrency-one", (refusal(sup3.reserve, "S6", "k2", judge, "judge", tranche="calibration") or "")
            .startswith("CALIBRATION_SERIAL"), "a second calibration call was admitted")
    control("undeclared-stage-budget-refused", (refusal(sup3.reserve, "S9", "x", judge, "judge", tranche="calibration") or "")
            .startswith("BUDGET_UNDECLARED S9"), "reserved")
    sup3.release("S6", rc["call_id"], "refused")
    for n in range(CALIBRATION_MIN_SAMPLES):
        rk = sup3.reserve("S6", f"k{n + 10}", judge, "judge", tranche="calibration")
        sup3.charge("S6", rk["call_id"], {"measured": 3000 + n, "provisional": 0, "unresolved": 0, "complete": True}, "completed")
    control("measured-class-admitted-broadly", sup3.reserve("S6", "b1", judge, "judge")["calibration"] == "measured", "still provisional")
    seed = usages.totals(json.loads((gate.FIXTURES / "claude-runner" / "acc-clean-001" / "usage.json").read_text()))["measured"]
    control("claude-seed-is-the-replayed-probe-call", seed == SEEDS["claude"]["tokens"], f"{seed}")

    # window scope: probe 7's R-authoring call (about 136k input) replayed through the dispatcher. The
    # non-window half stays on the Codex seat it was captured from; the window half runs on the Claude seat,
    # the only kind a view-window call is admitted on, with the same retained observation replayed.
    replay = str(gate.FIXTURES / "reconstruction" / "author-full-astra" / "requests.json")
    authoring = {class_key("S7b", astra, "authoring"): [170_000, 175_000, 178_134, 180_000, 182_000],
                 class_key(vstage, vseat, "authoring"): [170_000, 175_000, 178_134, 180_000, 182_000]}
    for view, name in ((False, "run-r"), (True, "run-s3")):
        stage, seat = (vstage, vseat) if view else ("S7b", astra)
        dv = run_dir(name, {stage: 2_000_000}, allowance=4000)
        sv = counted(supervisor(dv, "clean", seats_path=measured_seats, replay=replay))
        sv.seed_from(authoring)
        later = sv.reserve(stage, "reserved-before", seat, "authoring")  # reserved before the run stops
        rv = sv.reserve(stage, "author", seat, "authoring")
        pv = packets.build(rv["call_id"], stage, seat, "Author the record.\n", None)
        got = refusal(sv.call, stage, seat, pv, None, reservation=rv, caps={"tokens": 400_000, "compactions": 2},
                      view_window=view, max_output_tokens=32_000)
        if not view:
            verdict = gate.accept(dv / "calls" / rv["call_id"])
            control("authoring-call-without-a-view-window-accepted", got is None and verdict["ok"], f"{got} {verdict['failures']}")
        else:
            control("view-window-call-past-the-bound-stops-the-run", (got or "").startswith(f"INPUT_BOUND_EXCEEDED {rv['call_id']}: "
                    "a view-window call read 135796"), f"{got}")
            control("stopped-run-dispatches-nothing", (refusal(sv.reserve, stage, "next", seat, "authoring") or "")
                    .startswith("RUN_STOPPED INPUT_BOUND_EXCEEDED"), "dispatched after the run stopped")
            before = list(launches)
            got = refusal(sv.call, stage, seat, packets.build(later["call_id"], stage, seat, "Author the record.\n", None), None,
                          reservation=later, caps={"tokens": 400_000, "compactions": 2}, view_window=False)
            control("call-reserved-before-the-run-stopped-dispatches-nothing", (got or "").startswith("RUN_STOPPED INPUT_BOUND_EXCEEDED")
                    and launches == before and not (dv / "calls" / later["call_id"]).exists(), f"{got} {launches[len(before):]}")

    # seats are pinned per stage (design §4 in seats.json, or run.json); a view-window call needs its measured allowance
    design_4 = {  # design §4's stage table, "Seat (default)" column, copied by hand
        "S3": ["claude:claude-sonnet-5-5/xhigh"], "S4": ["claude:claude-opus-5-5/high"],
        "S6": ["claude:claude-opus-5-5/high", "codex:gpt-6-astra/xhigh", "claude:claude-sonnet-5-5/medium", "codex:gpt-6-luna/medium"],
        "S7": ["claude:claude-opus-5-5/high"], "S7b": ["codex:gpt-6-astra/xhigh"], "S9b": ["codex:gpt-6-astra/high"]}
    pinned = {k: v for k, v in gate.seats().get("stage_seats", {}).items() if not k.startswith("$")}
    control("stage-seats-are-design-section-4", pinned == design_4, f"{pinned}")
    # a slot is unmeasured (no number) or measured (a positive count and the measurement it came from);
    # the negative rows build their own slots, so the control keeps testing when every live slot is measured
    def allowance_slot_problem(slot):
        if slot.get("measured") is False:
            return None if slot.get("allowance_tokens") is None else "ALLOWANCE_SLOT_SHAPE unmeasured slot carries a number"
        if slot.get("measured") is not True:
            return "ALLOWANCE_SLOT_SHAPE measured is neither true nor false"
        tokens = slot.get("allowance_tokens")
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0:
            return "ALLOWANCE_SLOT_SHAPE measured slot without a positive token count"
        if not str(slot.get("basis") or "").strip():
            return "ALLOWANCE_SLOT_SHAPE measured slot without its basis"
        return None
    live_slots = {f"{h}.{p}": allowance_slot_problem(slot) for h, entry in gate.seats()["hosts"].items()
                  for p, slot in entry["host_allowance"].items()}
    control("host-allowance-slots-are-unmeasured-or-measured-with-basis", live_slots and not any(live_slots.values()),
            f"{live_slots}")
    for row, slot in (("measured-with-null-tokens", {"allowance_tokens": None, "measured": True, "basis": "b"}),
                      ("unmeasured-with-a-number", {"allowance_tokens": 4000, "measured": False, "basis": "b"}),
                      ("measured-with-zero", {"allowance_tokens": 0, "measured": True, "basis": "b"}),
                      ("measured-with-empty-basis", {"allowance_tokens": 4000, "measured": True, "basis": " "})):
        problem = allowance_slot_problem(slot)
        control(f"allowance-slot-{row}-refused", (problem or "").startswith("ALLOWANCE_SLOT_SHAPE"), f"{problem}")
    da = run_dir("run-seats", {"S6": 400_000, "S3": 2_000_000, "S7b": 2_000_000}, allowance=4000)
    # the Claude host's allowance, unmeasured and measured-with-a-number, as seats fixtures: the checkout's
    # file carries a measured one, so the two refusals need declarations of their own
    claude_unmeasured, claude_numbered = scratch / "seats-claude-unmeasured.json", scratch / "seats-claude-numbered.json"
    for path, slot in ((claude_unmeasured, {"allowance_tokens": None, "measured": False, "basis": "unmeasured"}),
                       (claude_numbered, {"allowance_tokens": claude_allowance, "measured": False, "basis": "a number nobody measured"})):
        fixture_seats = json.loads(gate.SEATS.read_text(encoding="utf-8"))
        fixture_seats["hosts"]["claude"]["host_allowance"]["hermetic"] = slot
        path.write_text(json.dumps(fixture_seats), encoding="utf-8")

    def admitted(sup, stage, seat, view_window, size=None):
        r = sup.reserve(stage, f"seat-{len(ran)}", seat, "judge", tranche="calibration")
        before = sorted((da / "calls").iterdir()) if (da / "calls").is_dir() else []
        payload = "v" * (size - len(packets.build(r["call_id"], stage, seat, "", None))) if size else "x\n"
        cap = {"max_output_tokens": 32_000} if view_window else {}
        got = refusal(sup.call, stage, seat, packets.build(r["call_id"], stage, seat, payload, None), None, reservation=r,
                      caps=caps, view_window=view_window, **cap)
        after = sorted((da / "calls").iterdir()) if (da / "calls").is_dir() else []
        return got, after == before
    plain, measured = supervisor(da), supervisor(da, seats_path=measured_seats)
    got, untouched = admitted(plain, "S6", "claude:claude-opus-5-5/max", False)
    control("seat-neither-declared-nor-pinned-refused", (got or "").startswith("SEAT_UNPINNED") and untouched, f"{got}")
    got, _untouched = admitted(plain, "S6", "codex:gpt-6-luna/medium", False)
    control("seat-pinned-by-design-section-4-admitted", got is None, f"{got}")
    got, untouched = admitted(supervisor(da, seats_path=claude_unmeasured), vstage, vseat, True)
    control("view-window-call-without-a-measured-allowance-refused", (got or "").startswith("ALLOWANCE_UNMEASURED") and untouched,
            f"{got}")
    got, untouched = admitted(supervisor(da, seats_path=claude_numbered), vstage, vseat, True)
    control("allowance-with-a-number-but-not-measured-refused", (got or "").startswith("ALLOWANCE_UNMEASURED") and untouched,
            f"{got}")
    mismatched = run_dir("run-allowance-mismatch", {vstage: 2_000_000}, window_allowance=claude_allowance - 1)
    sm = supervisor(mismatched)
    rm = sm.reserve(vstage, "w", vseat, "judge", tranche="calibration")
    got = refusal(sm.call, vstage, vseat, packets.build(rm["call_id"], vstage, vseat, "x\n", None), None, reservation=rm,
                  caps=caps, view_window=True, max_output_tokens=32_000)
    control("declared-allowance-not-the-measured-one-refused", (got or "").startswith("ALLOWANCE_MISMATCH"), f"{got}")
    got, _untouched = admitted(plain, vstage, vseat, True, size=bound.INPUT_BOUND - claude_allowance)
    control("window-at-the-bound-less-the-allowance-admitted", got is None, f"{got}")
    got, untouched = admitted(plain, vstage, vseat, True, size=bound.INPUT_BOUND - claude_allowance + 1)
    control("window-past-the-bound-less-the-allowance-refused", (got or "").startswith("WINDOW_OVER_BOUND") and untouched, f"{got}")
    # BB#4: and the same call on a host whose adapter cannot convey the cap is refused for that, whatever
    # else is declared - the check sits before the allowance and the capacity, because a reservation the
    # host is never told is not a reservation at all
    got, untouched = admitted(measured, "S7b", astra, True)
    control("a-view-window-call-on-a-host-whose-adapter-cannot-convey-the-cap-is-refused",
            (got or "").startswith("CAP_UNDELIVERABLE") and "codex-run" not in (got or "") and untouched, f"{got}")
    got, _untouched = admitted(measured, "S7b", astra, False)
    control("a-non-window-call-on-the-same-host-is-still-admitted", got is None, f"{got}")
    got, _untouched = admitted(plain, vstage, vseat, True)
    control("window-inside-the-bound-with-a-measured-allowance-admitted", got is None, f"{got}")

    # dispatch edges (N#5): the real closure is clean, and each planted edge is named by file and line
    violations, closure, sites = closure_violations()
    control("closure-clean-over-real-subjects", not violations and "session-distill/distill.py" in closure
            and {f"session-distill/runlib/{p.name}" for p in (REPO / "session-distill" / "runlib").glob("*.py")} <= set(closure)
            and sites >= 3, f"{violations} closure {closure} sites {sites}")
    control("closure-imports-no-out-of-scope-executor", not set(closure) & {e["path"] for e in OUT_OF_SCOPE}, f"{closure}")
    tree = scratch / "tree"
    for rel in ["session-distill/distill.py", "session-distill/seats.json", "session-distill/screen-codex.py", "launch/agent-launch.py"] \
            + [str(p.relative_to(REPO)) for p in (REPO / "session-distill" / "runlib").glob("*.py")] \
            + [str(p.relative_to(REPO)) for p in (REPO / "benchmarks").rglob("*.py")] \
            + sorted({e[k] for e in DYNAMIC_LOADS + SCRIPT_RUNS for k in ("site", "path")}):
        (tree / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, tree / rel)

    def plant(rel, code, **kwargs):
        """The closure check's violations over the copied tree with `code` appended to `rel`,
        and the line the appended code starts on."""
        path = tree / rel
        original = path.read_text(encoding="utf-8")
        path.write_text(original + "\n" + code + "\n", encoding="utf-8")
        try:
            return closure_violations(tree, **kwargs)[0], original.count("\n") + 2
        finally:
            path.write_text(original, encoding="utf-8")

    def planted(name, rel, code, needle, offset=0, **kwargs):
        found, at = plant(rel, code, **kwargs)
        want = needle.format(at=f"{rel}:{at + offset}")
        control(f"planted-{name}", any(v.startswith(want) for v in found), f"expected {want!r} in {found}")

    # The one refusal every undeclared inline program gets, spelled once: six controls below name it,
    # and a needle copied six times drifts.
    UNDECLARED_INLINE = ("DISPATCH_INLINE_UNDECLARED {at}: python -c with a program that is not a "
                         "module-level constant of this file declared in INLINE_PROGRAMS")
    control("copied-tree-is-clean", not closure_violations(tree)[0], f"{closure_violations(tree)[0]}")
    # ---- the source-shape judgements, and the six ways they are broken. Each plant is judged in a
    # COPY OF THE TEXT: the violation these guard against is a suite running a suite, and running one
    # to prove the check is the incident itself (S4).
    control("source-shape-clean-over-the-real-tree", not shape_violations(), f"{shape_violations()}")
    inventory_rel, driver_rel = "session-distill/runlib/inventory.py", "session-distill/distill.py"
    live_inventory = (REPO / inventory_rel).read_text(encoding="utf-8")
    live_driver = (REPO / driver_rel).read_text(encoding="utf-8")
    for name, planted_sources, needle in (
            ("a-second-scratch-inside-a-suite",
             {driver_rel: live_driver + "\n\ndef _planted_scratch():\n"
                                        "    return tempfile.TemporaryDirectory()\n"},
             f"TEMPFILE_UNDECLARED {driver_rel}:"),
            ("a-scratch-import-form",
             {driver_rel: live_driver.replace("import tempfile", "from tempfile import mkdtemp", 1)},
             f"TEMPFILE_IMPORT_FORM {driver_rel}:"),
            ("a-scratch-module-alias",
             {driver_rel: live_driver.replace("import tempfile", "import tempfile as tf", 1)},
             f"TEMPFILE_IMPORT_FORM {driver_rel}:"),
            ("a-second-call-at-a-declared-scratch-site",
             {inventory_rel: live_inventory.replace(
                 "    parent = scratch_parent(environ)",
                 "    tempfile.gettempdir()\n    parent = scratch_parent(environ)", 1)},
             f"TEMPFILE_SECOND_CALL {inventory_rel}:self_test_scratch"),
            ("an-exec-import-form",
             {driver_rel: live_driver.replace("import subprocess", "from subprocess import run", 1)},
             f"DISPATCH_IMPORT_FORM {driver_rel}:"),
            ("a-child-handed-the-suite",
             {driver_rel: live_driver + "\n\ndef _planted_child():\n"
                                        "    subprocess.run([sys.executable, __file__, '--self-test'])\n"},
             f"DISPATCH_SELF_TEST_ARGV {driver_rel}:"),
            # G3: the constant in a list the trace cannot follow to its call, in a tuple built
            # elsewhere, and spelled by composition — each ordinary code, none of them adversarial.
            ("a-suite-argv-through-a-variable",
             {driver_rel: live_driver + "\n\ndef _planted_variable():\n"
                                        "    cmd = [sys.executable, __file__, '--self-test']\n"
                                        "    subprocess.run(cmd)\n"},
             f"DISPATCH_SELF_TEST_ARGV {driver_rel}:"),
            ("a-suite-argv-in-a-tuple-built-elsewhere",
             {driver_rel: live_driver + "\n\nPLANTED_ARGV = (sys.executable, '--self-test')\n"},
             f"DISPATCH_SELF_TEST_ARGV {driver_rel}:"),
            ("a-suite-argv-spelled-by-composition",
             {driver_rel: live_driver + "\n\ndef _planted_join():\n"
                                        "    flag = '--self' + '-test'\n"
                                        "    return flag\n"},
             f"DISPATCH_SELF_TEST_ARGV {driver_rel}:"),
            # G2: an executor's module renamed, a name taken out of it, and a process module nobody
            # declared. The first two hid every call behind an alias this judge does not read.
            ("an-executor-module-renamed",
             {driver_rel: live_driver.replace("import subprocess", "import subprocess as sp", 1)},
             f"DISPATCH_IMPORT_FORM {driver_rel}:"),
            ("an-os-module-renamed",
             {driver_rel: live_driver.replace("import os\n", "import os as o\n", 1)},
             f"DISPATCH_IMPORT_FORM {driver_rel}:"),
            ("a-loader-name-taken-out-of-its-module",
             {driver_rel: live_driver + "\n\nfrom runpy import run_path\n"},
             f"DISPATCH_IMPORT_FORM {driver_rel}:"),
            ("an-undeclared-process-module",
             {driver_rel: live_driver + "\n\nimport multiprocessing\n"},
             f"DISPATCH_PROCESS_MODULE {driver_rel}:"),
            # G4: a tempfile reference that is not a call of a name any list knows.
            ("a-scratch-function-taken-as-a-value",
             {driver_rel: live_driver + "\n\ndef _planted_alias():\n"
                                        "    make = tempfile.mkdtemp\n"
                                        "    return make()\n"},
             f"TEMPFILE_UNDECLARED {driver_rel}:"),
            # G5: the executor passed as a value, which is the shape I introduced myself.
            ("an-executor-referenced-as-a-value",
             {driver_rel: live_driver + "\n\ndef _planted_value(spawn=None):\n"
                                        "    return (spawn or subprocess.Popen)(['git'])\n"},
             f"DISPATCH_EXEC_AS_VALUE {driver_rel}:"),
            # r4 R5: the MODULE taken as a value. The scratch rule claimed it sees any reference to
            # tempfile and saw only `tempfile.<attr>`, so these two spellings passed every judge.
            ("the-scratch-module-taken-as-a-value",
             {driver_rel: live_driver + "\n\ndef _planted_module_value():\n"
                                        "    t = tempfile\n"
                                        "    return t.TemporaryDirectory()\n"},
             f"DISPATCH_MODULE_AS_VALUE {driver_rel}:"),
            ("an-executors-module-taken-as-a-value",
             {driver_rel: live_driver + "\n\ndef _planted_executor_module():\n"
                                        "    sp = subprocess\n"
                                        "    return sp.run(['git', 'status'])\n"},
             f"DISPATCH_MODULE_AS_VALUE {driver_rel}:"),
            ("a-watched-module-handed-to-a-function",
             {driver_rel: live_driver + "\n\ndef _planted_module_argument(run=None):\n"
                                        "    return (run or getattr)(subprocess, 'run')\n"},
             f"DISPATCH_MODULE_AS_VALUE {driver_rel}:")):
        seen = shape_violations(sources=planted_sources)
        control(f"planted-{name}", any(row.startswith(needle) for row in seen),
                f"expected {needle!r} in {seen}")
    # ---- audit 480/485/551: the scratch allow-list reads FILES, so an entry naming no file and an
    # entry whose file does not parse are refusals of their own rather than a quiet `continue`. Each
    # plant is this control's own scope tuple; indexing the live one would stop testing the day that
    # tuple changes.
    gone_rel = "session-distill/a-control-names-no-file.py"
    gone = shape_violations(scope=(gone_rel,))
    control("a-scratch-scope-entry-naming-no-file",
            any(row == f"TEMPFILE_SCOPE_STALE {gone_rel}: no such file" for row in gone), f"{gone}")
    unreadable_rel = "session-distill/a-control-that-does-not-parse.py"
    unreadable = shape_violations(scope=(unreadable_rel,), sources={unreadable_rel: "def (\n"})
    control("a-scratch-scope-entry-whose-file-does-not-parse",
            any(row.startswith(f"TEMPFILE_UNREADABLE {unreadable_rel}: ") for row in unreadable),
            f"{unreadable}")
    # `import multiprocessing` is the other branch; this is the spelling that takes a NAME out of an
    # undeclared process module, which that branch never sees.
    from_process = shape_violations(sources={driver_rel: live_driver + "\n\nfrom multiprocessing import Pool\n"})
    control("a-name-taken-out-of-an-undeclared-process-module",
            any(row.startswith(f"DISPATCH_PROCESS_MODULE {driver_rel}:")
                and "`from multiprocessing import Pool`" in row for row in from_process),
            f"{from_process}")
    # A declared site that stops making its call admits nothing and must say so rather than sit there.
    stale = shape_violations(sources={inventory_rel: live_inventory.replace(
        "        with tempfile.TemporaryDirectory(prefix=prefix, dir=str(parent)) as td:\n"
        "            yield pathlib.Path(td)",
        "        yield pathlib.Path(parent)", 1)})
    control("planted-a-declared-scratch-site-that-makes-no-call",
            any(row.startswith(f"INVENTORY_STALE tempfile site {inventory_rel}:self_test_scratch")
                for row in stale), f"{stale}")
    planted("direct-dispatch-in-a-closure-module", "session-distill/runlib/records.py",
            "import subprocess\ndef _planted():\n    subprocess.run(['codex', 'exec', '-'])", "DISPATCH_OUTSIDE_SUPERVISOR {at}:", 2)
    planted("screen-codex-loaded-by-the-driver", "session-distill/distill.py",
            "import importlib.util\nSC = importlib.util.spec_from_file_location('sc', REPO / 'session-distill' / 'screen-codex.py')",
            "CLOSURE_IMPORTS_OUT_OF_SCOPE {at}: loads session-distill/screen-codex.py", 1)
    planted("shell-command-line", "session-distill/runlib/claims.py", "import os\nos.system('claude -p hello')",
            "DISPATCH_OUTSIDE_SUPERVISOR {at}: a command line starts 'claude'", 1)
    # ---- r4 R5: the tail of the program judge is DEFAULT DENY, and every command of a shell line is
    # judged by the same rules. Each plant is source-only, in the copied tree, and never run.
    planted("a-literal-interpreter-as-the-program", "session-distill/runlib/claims.py",
            "import subprocess\nsubprocess.run(['python3', '/fixture/other.py'])",
            "DISPATCH_INTERPRETER_LITERAL {at}: starts 'python3', a literal interpreter", 1)
    planted("a-literal-program-no-declaration-admits", "session-distill/runlib/claims.py",
            "import subprocess\nsubprocess.run(['curl', 'https://example.invalid/'])",
            "DISPATCH_PROGRAM_UNDECLARED {at}: starts 'curl'", 1)
    # A declaration is per SITE: `git` is declared for four files, and the same program written
    # anywhere else is refused exactly as an undeclared one is.
    planted("a-declared-program-written-at-another-site", "session-distill/runlib/claims.py",
            "import subprocess\nsubprocess.run(['git', 'status'])",
            "DISPATCH_PROGRAM_UNDECLARED {at}: starts 'git'", 1)
    planted("a-shell-line-carrying-the-suite-flag", "session-distill/runlib/claims.py",
            "import os\nos.system('/bin/ls x.py --self-test')",
            "DISPATCH_SELF_TEST_ARGV {at}: a shell command line carrying '--self-test'", 1)
    planted("a-shell-lines-second-command-starting-a-host", "session-distill/runlib/claims.py",
            "import os\nos.system('/bin/ls -l && codex exec -')",
            "DISPATCH_OUTSIDE_SUPERVISOR {at}: a command line starts 'codex'", 1)
    planted("a-shell-lines-second-command-running-an-interpreter", "session-distill/runlib/claims.py",
            "import os\nos.system('/bin/ls -l | python3 -')",
            "DISPATCH_INTERPRETER_LITERAL {at}: a command line starts 'python3'", 1)
    # ---- r4 R5 addendum: the spellings a word-at-a-time reading let through. The first command of
    # each line is `git`, which inventory.py declares, so what is judged is the SECOND command —
    # glued to its separator, written after a newline, or run by a builtin. Source-only plants.
    for name, spelled, needle in (
            ("a-separator-glued-to-the-command-before-it", "git status;python3 x.py",
             "DISPATCH_INTERPRETER_LITERAL {at}: a command line starts 'python3'"),
            ("a-semicolon-with-a-space-after-it", "git status; python3 x.py",
             "DISPATCH_INTERPRETER_LITERAL {at}: a command line starts 'python3'"),
            ("a-glued-and-and", "git status&&python3 x.py",
             "DISPATCH_INTERPRETER_LITERAL {at}: a command line starts 'python3'"),
            ("a-glued-pipe-into-a-host", "git status|codex exec -",
             "DISPATCH_OUTSIDE_SUPERVISOR {at}: a command line starts 'codex'"),
            ("a-second-command-on-the-next-line", "git status\\npython3 x.py",
             "DISPATCH_INTERPRETER_LITERAL {at}: a command line starts 'python3'"),
            ("a-program-run-by-exec", "exec python3 x.py",
             "DISPATCH_INTERPRETER_LITERAL {at}: a command line starts 'python3'"),
            ("a-program-run-by-command", "command python3 x.py",
             "DISPATCH_INTERPRETER_LITERAL {at}: a command line starts 'python3'"),
            ("a-line-run-by-eval", "eval 'python3 x.py'",
             "DISPATCH_SHELL_EVAL {at}: a shell line running 'eval'"),
            ("a-command-substitution-in-dollar-parens", "git $(python3 x.py)",
             "DISPATCH_SHELL_SUBSTITUTION {at}: a shell line with '$(' in it"),
            ("a-command-substitution-in-backticks", "git `python3 x.py`",
             "DISPATCH_SHELL_SUBSTITUTION {at}: a shell line with '`' in it"),
            ("a-process-substitution", "git <(python3 x.py)",
             "DISPATCH_SHELL_SUBSTITUTION {at}: a shell line with '<(' in it"),
            ("a-subshell-around-the-program", "(python3 x.py)",
             "DISPATCH_INTERPRETER_LITERAL {at}: a command line starts 'python3'")):
        planted(f"shell-{name}", "session-distill/runlib/inventory.py",
                f'import os\nos.system("{spelled}")', needle, 1)
    # And a shell line of admitted commands only stays admitted: `git` is declared for this site.
    clean_shell, clean_at = plant("session-distill/runlib/inventory.py",
                                  'import os\nos.system("git status && git log -1")')
    control("a-shell-line-of-declared-commands-only-is-admitted",
            not [row for row in clean_shell if f"session-distill/runlib/inventory.py:{clean_at + 1}" in row],
            f"{[row for row in clean_shell if str(clean_at + 1) in row]}")
    planted("pinned-binary-path", "session-distill/runlib/validate.py",
            "import os, subprocess\nsubprocess.Popen([os.path.expanduser('~/.local/share/claude/versions/2.1.304'), '-p'])",
            "DISPATCH_OUTSIDE_SUPERVISOR {at}: starts '~/.local/share/claude/versions/2.1.304'", 1)
    planted("unresolved-program", "session-distill/runlib/stagelock.py", "def _run(binary):\n    subprocess.run([binary, '-p'])",
            "DISPATCH_UNRESOLVED {at}: a program the trace cannot resolve", 1)
    # An inline program that starts a host: refused because it is not declared, which is the
    # answer before anything reads it. The declaration's hash is what holds its text afterwards.
    planted("dispatch-inside-python-c", "session-distill/runlib/usage.py",
            "import subprocess\nsubprocess.run([sys.executable, '-c', \"import subprocess; subprocess.run(['claude', '-p'])\"])",
            UNDECLARED_INLINE, 1)
    planted("launcher-run-beyond-its-receipt-emitter", "session-distill/runlib/receipts.py",
            "import subprocess\nsubprocess.run([sys.executable, str(LAUNCHER), 'claude', '--model', 'x'])",
            "DISPATCH_OUTSIDE_SUPERVISOR {at}: runs the launcher", 1)
    found, _at = plant("session-distill/distill.py", "sys.path.insert(0, str(REPO / 'benchmarks'))\nimport dispatch")
    control("planted-benchmarks-module-imported-by-the-driver-is-traced",
            any(v.startswith("DISPATCH_UNRESOLVED benchmarks/dispatch.py:") for v in found), f"{found}")
    planted("tier-experiments-imported", "session-distill/runlib/claims.py", "from tier import live",
            "CLOSURE_IMPORTS_OUT_OF_SCOPE {at}: imports benchmarks/tier/live.py")
    planted("unresolved-dynamic-load", "session-distill/runlib/claims.py", "import importlib\nM = importlib.import_module(NAME)",
            "DYNAMIC_LOAD_UNDECLARED {at}: a load the trace cannot resolve", 1)
    planted("stale-out-of-scope-entry", "session-distill/runlib/claims.py", "",
            "INVENTORY_STALE out-of-scope session-distill/retired.py",
            out_of_scope=OUT_OF_SCOPE + ({"path": "session-distill/retired.py", "reason": "x", "retires": "x"},))
    planted("declared-load-with-no-site", "session-distill/runlib/claims.py", "",
            "INVENTORY_STALE dynamic load session-distill/runlib/claims.py -> launch/agent-launch.py: the site makes no such load",
            dynamic=DYNAMIC_LOADS + ({"site": "session-distill/runlib/claims.py", "path": "launch/agent-launch.py",
                                      "trace": False, "reason": "x"},))
    planted("load-declared-nowhere", "session-distill/runlib/claims.py", "import importlib\nM = importlib.import_module('json')",
            "DYNAMIC_LOAD_UNDECLARED {at}: loads 'json', declared nowhere", 1)
    planted("dynamic-load-entry-naming-no-file", "session-distill/runlib/claims.py", "",
            "INVENTORY_STALE dynamic load session-distill/runlib/claims.py -> launch/gone.py: no such file",
            dynamic=DYNAMIC_LOADS + ({"site": "session-distill/runlib/claims.py", "path": "launch/gone.py",
                                      "trace": False, "reason": "x"},))
    planted("unresolved-shell-line", "session-distill/runlib/claims.py", "import os\nos.system(f'{CMD} -p')",
            "DISPATCH_UNRESOLVED {at}: a shell command line the trace cannot resolve", 1)
    planted("unresolved-python-c", "session-distill/runlib/claims.py", "import subprocess\nsubprocess.run([sys.executable, '-c', CODE])",
            UNDECLARED_INLINE, 1)
    planted("python-runs-an-out-of-scope-executor", "session-distill/runlib/claims.py",
            "import subprocess\nsubprocess.run([sys.executable, 'session-distill/screen-codex.py'])",
            "CLOSURE_IMPORTS_OUT_OF_SCOPE {at}: runs 'session-distill/screen-codex.py'", 1)
    planted("python-runs-a-script-not-followed", "session-distill/runlib/claims.py",
            "import subprocess\nsubprocess.run([sys.executable, 'tool.py'])", "DISPATCH_UNRESOLVED {at}: python runs ['tool.py']", 1)
    planted("shell-starts-a-host", "session-distill/runlib/claims.py", "import subprocess\nsubprocess.run(['bash', '-c', 'codex exec -'])",
            "DISPATCH_OUTSIDE_SUPERVISOR {at}: a command line starts 'codex'", 1)
    planted("shell-with-unresolved-arguments", "session-distill/runlib/claims.py", "import subprocess\nsubprocess.run(['sh', '-c', CMD])",
            "DISPATCH_UNRESOLVED {at}: sh with arguments the trace cannot resolve", 1)
    planted("executor-without-a-command", "session-distill/runlib/claims.py", "import subprocess\nsubprocess.run()",
            "DISPATCH_UNRESOLVED {at}: subprocess.run with no command", 1)
    # every executor form keeps its own argv semantics, and executable= overrides the program
    for form, code, needle in (
            ("shell-through-execv", "os.execv('/bin/sh', ['sh', '-c', 'codex exec -'])", "a command line starts 'codex'"),
            ("shell-through-execve", "os.execve('/bin/sh', ['sh', '-c', 'codex exec -'], {})", "a command line starts 'codex'"),
            ("shell-through-execl", "os.execl('/bin/sh', 'sh', '-c', 'claude -p hi')", "a command line starts 'claude'"),
            ("shell-through-execle", "os.execle('/bin/sh', 'sh', '-c', 'claude -p hi', {})", "a command line starts 'claude'"),
            ("shell-through-spawnv", "os.spawnv(os.P_WAIT, '/bin/bash', ['bash', '-c', 'codex exec -'])", "a command line starts 'codex'"),
            ("shell-through-spawnl", "os.spawnl(os.P_WAIT, '/bin/sh', 'sh', '-c', 'codex exec -')", "a command line starts 'codex'"),
            ("shell-through-posix-spawn", "os.posix_spawn('/bin/sh', ['sh', '-c', 'codex exec -'], {})", "a command line starts 'codex'"),
            ("host-through-execvp", "os.execvp('codex', ['codex', 'exec'])", "starts 'codex'"),
            ("shell-through-execv-with-an-unread-argv", "os.execv('/bin/sh', ARGV)", "sh with arguments the trace cannot resolve"),
            ("executable-override-names-a-host", "subprocess.run(['harmless'], executable='codex')", "starts 'codex'"),
            ("executable-override-runs-a-shell", "subprocess.run(['x', '-c', 'claude -p'], executable='/bin/sh')",
             "a command line starts 'claude'"),
            # a concatenated argv keeps both sides, and a side the trace cannot read is refused, not dropped
            ("argv-concatenation-through-subprocess", "subprocess.run(['/bin/sh'] + ['-c', 'codex exec -'])",
             "a command line starts 'codex'"),
            ("argv-concatenation-through-execv", "os.execv('/bin/sh', ['sh'] + ['-c', 'codex exec -'])", "a command line starts 'codex'"),
            ("argv-starred-list-through-subprocess", "subprocess.run([*['/bin/sh', '-c'], 'claude -p hi'])",
             "a command line starts 'claude'"),
            ("argv-concatenation-with-an-unread-side", "subprocess.run(['sh'] + ARGS)", "sh with arguments the trace cannot resolve"),
            ("argv-concatenation-with-an-unread-side-through-execv", "os.execv('/bin/sh', ['sh'] + ARGS)",
             "sh with arguments the trace cannot resolve")):
        code_at = "DISPATCH_UNRESOLVED {at}: " if "cannot resolve" in needle else "DISPATCH_OUTSIDE_SUPERVISOR {at}: "
        planted(form, "session-distill/runlib/claims.py", f"import os, subprocess\n{code}", code_at + needle, 1)
    planted("argv-concatenation-through-a-bound-name", "session-distill/runlib/claims.py",
            "import subprocess\nTAIL = ['-c', 'claude -p hi']\nsubprocess.run(['bash'] + TAIL)",
            "DISPATCH_OUTSIDE_SUPERVISOR {at}: a command line starts 'claude'", 2)
    # what the declarations admit stays bound to its site, its path and its guard: an undeclared
    # site of each kind still fails, a declared script is traced, and a stale entry is named
    planted("python-flags-then-an-undeclared-script", "session-distill/runlib/census.py",
            "import subprocess\nsubprocess.run([sys.executable, '-I', str(HERE / 'other.py')])",
            "DISPATCH_UNRESOLVED {at}: python runs ['<?>/other.py']", 1)
    planted("a-declared-script-run-from-another-site", "session-distill/runlib/claims.py",
            "import subprocess\nsubprocess.run([sys.executable, '-I', str(HERE / 'census.py')])",
            "DISPATCH_UNRESOLVED {at}: python runs ['<?>/census.py']", 1)
    planted("a-declared-script-is-traced", "session-distill/digest.py",
            "import subprocess\nsubprocess.run(['claude', '-p'])", "DISPATCH_OUTSIDE_SUPERVISOR {at}: starts 'claude'", 1)
    # A copy-run is admitted by THE CALL: the program expression has to be a call of the entry's
    # owner, which is a function that refuses every root this process did not copy and every member
    # the declaration does not name. Each row below is a program at a DECLARED site, with the
    # legitimate calls still in that file, and each one is refused because it is not that call
    # (R2#5 — every one of these was admitted while the rule was about guard text in the file).
    for name, code, needle in (
            ("a-copy-run-of-a-script-that-is-not-the-driver",
             "subprocess.run([sys.executable, str(COPY / 'session-distill' / 'digest.py')])",
             "python runs ['<?>/session-distill/digest.py']"),
            ("a-program-the-environment-selects",
             "subprocess.run([sys.executable, os.environ['OTHER_SCRIPT']])",
             "python runs ['<?>']"),
            ("a-path-into-a-copy-that-no-owner-produced",
             "subprocess.run([sys.executable, str(COPY / 'session-distill' / 'distill.py')])",
             "python runs ['<?>/session-distill/distill.py']"),
            ("a-foreign-absolute-path-that-ends-in-the-drivers-name",
             "subprocess.run([sys.executable, '/elsewhere/session-distill/distill.py'])",
             "python runs ['/elsewhere/session-distill/distill.py']")):
        planted(name, "session-distill/distill.py", f"import os, subprocess\n{code}",
                "DISPATCH_UNRESOLVED {at}: " + needle, 1)
    # A bare name is not this file either. The identity is the EXPRESSION, and `__file__` is the only
    # name that is this file; a name the trace cannot read is a program the trace cannot resolve, and
    # nothing in the `_own_file` admission had a control standing on that half of it.
    planted("a-bare-name-is-not-this-file", "session-distill/distill.py",
            "import os, subprocess\nPROGRAM = os.environ['OTHER_SCRIPT']\n"
            "subprocess.run([sys.executable, PROGRAM])",
            "DISPATCH_UNRESOLVED {at}: python runs ['<?>']", 2)
    # And a PARENT of this file is not this file: python runs a directory as that directory's
    # `__main__.py`, which is another program. The peel used to follow `.parent`, so both of these
    # were admitted as the site running itself.
    planted("the-parent-of-this-file-is-not-this-file", "session-distill/distill.py",
            "import pathlib, subprocess\nsubprocess.run([sys.executable, str(pathlib.Path(__file__).parent)])",
            "DISPATCH_PROGRAM_FORM {at}: reaches for its own file", 1)
    planted("a-grandparent-of-this-file-is-not-this-file", "session-distill/distill.py",
            "import pathlib, subprocess\n"
            "subprocess.run([sys.executable, str(pathlib.Path(__file__).parent.parent)])",
            "DISPATCH_PROGRAM_FORM {at}: reaches for its own file", 1)
    # The same for a load inside a `python -c` program: what answers for it is the expression the
    # site passed at the argv index the program reads. `runpy.run_path(sys.argv[1])` with an
    # unrelated script in argv was admitted and recorded as following the driver.
    planted("an-inline-load-of-an-argv-the-site-does-not-produce", "session-distill/distill.py",
            "import subprocess\nsubprocess.run([sys.executable, '-c', "
            "'import runpy, sys\\nscript = sys.argv[1]\\nrunpy.run_path(script)', OTHER])",
            UNDECLARED_INLINE, 1)
    planted("script-entry-the-site-never-runs", "session-distill/runlib/claims.py", "",
            "INVENTORY_STALE script run session-distill/runlib/claims.py -> session-distill/census.py: the site runs no such script",
            scripts=SCRIPT_RUNS + ({"site": "session-distill/runlib/claims.py", "path": "session-distill/census.py", "reason": "x"},))
    planted("script-entry-naming-no-file", "session-distill/runlib/claims.py", "",
            "INVENTORY_STALE script run session-distill/runlib/claims.py -> session-distill/gone.py: no such file",
            scripts=SCRIPT_RUNS + ({"site": "session-distill/runlib/claims.py", "path": "session-distill/gone.py", "reason": "x"},))
    planted("an-undeclared-load-beside-a-declared-one", "session-distill/runlib/ledger.py",
            "import importlib.util\nX = importlib.util.spec_from_file_location('x', HERE / 'other.py')",
            "DYNAMIC_LOAD_UNDECLARED {at}: loads '<?>/other.py', declared nowhere", 1)
    planted("python-c-with-an-unread-callee", "session-distill/runlib/claims.py",
            "import subprocess\nsubprocess.run([sys.executable, '-c', f'{MOD}.run([1])'])",
            UNDECLARED_INLINE, 1)
    planted("python-c-with-unread-data-is-still-judged", "session-distill/runlib/claims.py",
            "import subprocess\nsubprocess.run([sys.executable, '-c', f\"import subprocess; subprocess.run(['claude', {ARG!r}])\"])",
            UNDECLARED_INLINE, 1)
    def without(rel, old, new):
        """The closure check's violations over the copied tree with `old` replaced by `new` in `rel`."""
        path = tree / rel
        kept = path.read_text(encoding="utf-8")
        path.write_text(kept.replace(old, new), encoding="utf-8")
        try:
            return closure_violations(tree)[0]
        finally:
            path.write_text(kept, encoding="utf-8")

    def unguarded_and_stale(found, site):
        return any(v.startswith(f"DISPATCH_UNRESOLVED {site}:") for v in found) \
            and any(v.startswith(f"INVENTORY_STALE guarded program {site}") for v in found)
    by_site = {e["site"]: e for e in GUARDED_PROGRAMS}
    sources_entry = by_site.get("session-distill/runlib/sources.py", {"site": "session-distill/runlib/sources.py", "guards": ("?",)})
    unguarded = without(sources_entry["site"], sources_entry["guards"][0], "False")
    control("a-guarded-program-without-its-guard-is-unresolved-and-stale", unguarded_and_stale(unguarded, sources_entry["site"]),
            f"{unguarded}")
    # the guard has one owner: a site that runs the declared zstd without calling it fails by name
    for site in ("session-distill/runlib/sources.py", "session-distill/runlib/views.py"):
        control(f"guarded-program-declared-{pathlib.Path(site).stem}", site in by_site, f"{sorted(by_site)}")
        if site not in by_site:
            continue
        entry = by_site[site]
        unchecked = without(entry["site"], entry["guards"][-1], entry["guards"][-1].replace("sources.checked_zstd(zstd)", "zstd")
                            .replace("checked_zstd(zstd)", "zstd"))
        control(f"a-guarded-program-without-its-checked-call-is-unresolved-and-stale-{pathlib.Path(entry['site']).stem}",
                unguarded_and_stale(unchecked, entry["site"]), f"{unchecked}")
    # a load inside a `-c` program is judged by the same declaration: an undeclared one is named,
    # and the bytecode control's own site is refused the moment its construction guard is gone
    planted("a-load-inside-python-c-is-judged", "session-distill/runlib/claims.py",
            "import subprocess\nsubprocess.run([sys.executable, '-c', \"import runpy; runpy.run_path('other.py')\"])",
            UNDECLARED_INLINE, 1)
    # The driver and the inventory each run their OWN file as a real process (their self-tests do),
    # which is closure-equivalent by construction — and nothing else is: a sibling named by the same
    # kind of expression is still refused.
    planted("a-sibling-of-this-file-is-not-this-file", "session-distill/runlib/claims.py",
            "import pathlib, subprocess\n"
            "subprocess.run([sys.executable, str(pathlib.Path(__file__).parent / 'other.py')])",
            "DISPATCH_UNRESOLVED {at}: python runs ['<?>/other.py']", 1)
    probe_entry = [e for e in COPY_RUNS if e["site"] == "session-distill/runlib/inventory.py"]
    control("copy-run-declared-for-the-bytecode-probe",
            {p for e in probe_entry for p in e["paths"]} == {"session-distill/distill.py",
                                                              "session-distill/runlib/inventory.py"},
            f"{[e['paths'] for e in probe_entry]}")
    if probe_entry:
        unowned_probe = without(probe_entry[0]["site"], "copied_member(", "a_copy_of(")
        # The staleness half asks for the "it calls no" text, not the prefix: the closure walk reports
        # `INVENTORY_STALE copy run {site} -> {path}: the site runs no such copy` for the same fixture,
        # and a control matching a prefix two refusals share cannot tell which of them fired (S8i).
        control("the-bytecode-probes-load-without-its-owner-is-unresolved-and-stale",
                any(v.startswith("DISPATCH_UNRESOLVED session-distill/runlib/inventory.py:") for v in unowned_probe)
                and any(v.startswith("INVENTORY_STALE copy run session-distill/runlib/inventory.py")
                        and "it calls no " in v for v in unowned_probe),
                f"{unowned_probe}")
    # What the owner may produce is declared as `paths`, and the declaration is held against the
    # tree: an entry naming a file that is not there admits a member nobody can check.
    held_copies = globals()["COPY_RUNS"]
    try:
        globals()["COPY_RUNS"] = (dict(held_copies[0], paths=("session-distill/gone.py",)),)
        stale_paths = closure_violations(tree)[0]
    finally:
        globals()["COPY_RUNS"] = held_copies
    control("copy-run-entry-naming-no-file",
            any("INVENTORY_STALE copy run" in row and "no such file" in row for row in stale_paths),
            f"{stale_paths}")
    copy_entry = {e["site"]: e for e in COPY_RUNS}.get(
        "session-distill/distill.py", {"site": "session-distill/distill.py", "owner": "?"})
    # The owner is the admission, so a site that stops calling it loses every copy-run it had, and
    # the entry is reported stale in the same run rather than sitting there admitting nothing.
    unowned = without(copy_entry["site"], f"{copy_entry['owner'].split('.')[-1]}(", "a_copy_of(")
    control("a-copy-run-whose-site-no-longer-calls-its-owner-is-unresolved-and-stale",
            any(v.startswith(f"DISPATCH_UNRESOLVED {copy_entry['site']}:") for v in unowned)
            and any(v.startswith(f"INVENTORY_STALE copy run {copy_entry['site']}")
                    and f"it calls no {copy_entry['owner']}" in v for v in unowned),
            f"{unowned}")
    control("copy-run-declared-for-the-driver", copy_entry.get("paths") == ("session-distill/distill.py",),
            f"{COPY_RUNS}")
    # ---- r3 S3: the admitted program forms are EXACT, and an expression that reaches for one
    # without being it is refused by its own name. Every plant is source-only, in the copied tree.
    for name, source, needle, offset in (
            ("a-path-join-around-its-own-file",
             "import pathlib, subprocess, sys\n"
             "subprocess.run([sys.executable, str(pathlib.Path(__file__, '/fixture/other.py'))])",
             "DISPATCH_PROGRAM_FORM {at}: reaches for its own file", 1),
            ("a-path-join-around-a-copied-member",
             "import pathlib, subprocess, sys\n"
             "subprocess.run([sys.executable, str(pathlib.Path(inventory.copied_member("
             "startup_copy, 'session-distill/distill.py'), '/fixture/other.py'))])",
             "DISPATCH_PROGRAM_FORM {at}: reaches for a copied member", 1),
            ("the-parent-of-its-own-file-joined",
             "import pathlib, subprocess, sys\n"
             "subprocess.run([sys.executable, str(pathlib.Path(__file__).parent / 'other.py')])",
             "DISPATCH_PROGRAM_FORM {at}: reaches for its own file", 1),
            ("a-keyword-in-the-own-file-form",
             "import pathlib, subprocess, sys\n"
             "subprocess.run([sys.executable, str(pathlib.Path(__file__, strict=False).resolve())])",
             "DISPATCH_PROGRAM_FORM {at}: reaches for its own file", 1),
            ("a-member-this-site-does-not-declare",
             "import subprocess, sys\n"
             "subprocess.run([sys.executable, str(inventory.copied_member(startup_copy, 'learn/redact.py'))])",
             "DISPATCH_COPY_MEMBER_UNDECLARED {at}: a copy-run naming 'learn/redact.py'", 1),
            ("a-member-that-is-not-a-literal",
             "import subprocess, sys\n"
             "subprocess.run([sys.executable, str(inventory.copied_member(startup_copy, member))])",
             "DISPATCH_COPY_MEMBER_UNDECLARED {at}: a copy-run naming 'not a string literal'", 1),
            # r7 found the ARITY clause of `_exact_call` unguarded: the plant above has no
            # `.resolve()`, so `_own_file` already refuses it at that clause and removing the arity
            # test changed nothing any control could see. These two are the arity test's own
            # subjects — the form is otherwise exactly the admitted one.
            ("an-extra-argument-inside-the-own-file-form",
             "import pathlib, subprocess, sys\n"
             "subprocess.run([sys.executable, str(pathlib.Path(__file__, '/fixture/other.py').resolve())])",
             "DISPATCH_PROGRAM_FORM {at}: reaches for its own file", 1),
            ("a-third-argument-to-the-member-owner",
             "import subprocess, sys\n"
             "subprocess.run([sys.executable, str(inventory.copied_member("
             "startup_copy, 'session-distill/distill.py', 'extra'))])",
             "DISPATCH_PROGRAM_FORM {at}: reaches for a copied member", 1),
    ):
        planted(name, driver_rel, source, needle, offset)
    # The three inline shapes the review found — a reassignment, a tuple reassignment and a binding
    # inside `if` — now share ONE refusal, and that is the point: the judge no longer reads a `-c`
    # program's insides, so there is no shape left for a rebinding to get past. Each is still
    # planted, because what must be shown is that each of the three is refused, not that the judge
    # has a branch for it.
    for name, inline_source in (
            ("an-inline-program-that-reassigns-its-argv",
             "p = sys.argv[1]\np = sys.argv[2]\nimport runpy; runpy.run_path(p)"),
            ("an-inline-program-that-reassigns-a-tuple",
             "p, q = sys.argv[1], sys.argv[2]\np, q = sys.argv[2], sys.argv[1]\nimport runpy; runpy.run_path(p)"),
            ("an-inline-program-bound-inside-an-if",
             "import sys, runpy\nif len(sys.argv) > 2:\n    p = sys.argv[2]\nelse:\n    p = sys.argv[1]\nrunpy.run_path(p)"),
    ):
        planted(name, driver_rel,
                "import subprocess, sys\nsubprocess.run([sys.executable, '-c', " + repr(inline_source)
                + ", str(inventory.copied_member(startup_copy, 'session-distill/distill.py'))])",
                "DISPATCH_INLINE_UNDECLARED {at}: python -c with a program that is not a module-level "
                "constant of this file declared in INLINE_PROGRAMS", 1)
    planted("an-inline-constant-nobody-declared", driver_rel,
            "PLANTED_PROGRAM = 'import time; time.sleep(1)\\n'\n"
            "import subprocess, sys\nsubprocess.run([sys.executable, '-c', PLANTED_PROGRAM])",
            "DISPATCH_INLINE_UNDECLARED {at}: python -c with a program that is not a module-level "
            "constant of this file declared in INLINE_PROGRAMS", 2)
    # A declared constant whose TEXT changed: the declaration's hash is what makes its reason a
    # review of the program that actually runs, so a changed character is refused until the row
    # moves with it. The edit is made in the copy, never in this checkout.
    changed_probe = tree / inventory_rel
    held_probe_text = changed_probe.read_text(encoding="utf-8")
    try:
        edited = held_probe_text.replace("print(json.dumps({'code': code}))",
                                         "print(json.dumps({'code': code, 'changed': True}))", 1)
        # The edit has to land, or this control judges an unchanged file and passes for the wrong
        # reason — which is what a needle copied from an older version of the probe did.
        control("the text-change control really changed the declared program",
                edited != held_probe_text, f"changed={edited != held_probe_text}")
        changed_probe.write_text(edited, encoding="utf-8")
        changed_rows = closure_violations(tree)[0]
    finally:
        changed_probe.write_text(held_probe_text, encoding="utf-8")
    control("a-declared-inline-program-whose-text-changed",
            any(row.startswith(f"DISPATCH_INLINE_CHANGED {inventory_rel}:") for row in changed_rows),
            f"{changed_rows}")
    control("and-the-copied-tree-is-clean-again-after-that-edit", not closure_violations(tree)[0],
            f"{closure_violations(tree)[0]}")
    # ---- audit 1911: the declared element is read, and an element the site does not produce as an
    # admitted program form is refused BY NAME. The plants above reach 1884's branch (a program that
    # is not a declared constant); this one declares the row and moves its index, which with the
    # refusal removed is admitted in silence — the child loads a path nothing in the closure follows.
    held_inlines = globals()["INLINE_PROGRAMS"]
    probe_row = [r for r in held_inlines if r["name"] == "BYTECODE_PROBE"]
    control("the-bytecode-probe-row-is-the-one-that-declares-a-loaded-element",
            len(probe_row) == 1 and probe_row[0]["loads"] is not None, f"{probe_row}")
    try:    # the program's own sys.argv[1] is this call's destination, not a program form
        globals()["INLINE_PROGRAMS"] = tuple(dict(r, loads=1) if r["name"] == "BYTECODE_PROBE" else r
                                             for r in held_inlines)
        moved = closure_violations(tree)[0]
    finally:
        globals()["INLINE_PROGRAMS"] = held_inlines
    control("a-declared-inline-program-loading-an-element-the-site-does-not-produce",
            any(row.startswith(f"DISPATCH_INLINE_UNDECLARED {inventory_rel}:")
                and "BYTECODE_PROBE loads sys.argv[1]" in row
                and "which this site does not produce as an admitted program form" in row
                for row in moved), f"{moved}")
    control("and-the-copied-tree-is-clean-again-after-the-index-move",
            not closure_violations(tree)[0], f"{closure_violations(tree)[0]}")
    # ---- r4 R6: `loads` is the index the PROGRAM reads, so the element admission inspects is
    # computed from where `-c` sits. Declared as an OUTER index it was right only while exactly one
    # flag preceded `-c`: this plant writes NO flag, so the old reading inspected the copied member
    # while the child loads its own sys.argv[2], which here is a literal path instead.
    no_flag = plant("session-distill/runlib/inventory.py",
                    "import subprocess, sys\n"
                    "subprocess.Popen([sys.executable, '-c', BYTECODE_PROBE, 'out', '/fixture/other.py',\n"
                    "                  copied_member(startup_copy, 'session-distill/distill.py')])")[0]
    control("an-inline-program-whose-flagless-argv-moves-the-element-it-loads",
            any(row.startswith(f"DISPATCH_INLINE_UNDECLARED {inventory_rel}:")
                and "BYTECODE_PROBE loads sys.argv[2]" in row for row in no_flag),
            f"{no_flag}")
    control("and-the-real-call-with-its-one-flag-is-still-admitted",
            not any("BYTECODE_PROBE loads" in row for row in closure_violations(tree)[0]),
            f"{[row for row in closure_violations(tree)[0] if 'BYTECODE_PROBE' in row]}")
    # r7 found this requirement unguarded. The declared index names an element of the argv AT THE
    # CALL, so an argv that is not a list literal there means the declaration points at nothing
    # decidable — and no control saw it removed.
    argv_probe = tree / inventory_rel
    held_argv_text = argv_probe.read_text(encoding="utf-8")
    spliced = held_argv_text.replace(
        '                [sys.executable, "-I", "-c", BYTECODE_PROBE, str(destination),\n'
        '                 str(copied_member(from_copy, "session-distill/distill.py"))],',
        '                [sys.executable, "-I", "-c", BYTECODE_PROBE] + [str(destination),\n'
        '                 str(copied_member(from_copy, "session-distill/distill.py"))],', 1)
    control("the argv-literal control really changed the declared site",
            spliced != held_argv_text, f"changed={spliced != held_argv_text}")
    try:
        argv_probe.write_text(spliced, encoding="utf-8")
        spliced_rows = closure_violations(tree)[0]
    finally:
        argv_probe.write_text(held_argv_text, encoding="utf-8")
    control("an inline program whose argv is not a list literal at the call",
            any(row.startswith(f"DISPATCH_PROGRAM_FORM {inventory_rel}:")
                and "an inline program's argv must be a list literal at the call" in row
                for row in spliced_rows),
            f"{spliced_rows}")
    control("and-the-copied-tree-is-clean-again-after-the-argv-edit", not closure_violations(tree)[0],
            f"{closure_violations(tree)[0]}")

    # ---- r3 S3: the names the forms are WRITTEN with. An exact shape means nothing in a file that
    # rebinds `str`, `pathlib` or `__file__`, so one row per name, each planted on its own.
    for name, source in (("__file__", "__file__ = '/fixture/other.py'\n"),
                       ("str", "def str(x):\n    return '/fixture/other.py'\n"),
                       ("pathlib", "for pathlib in ():\n    pass\n")):
        found, at = plant(driver_rel, source)
        control(f"planted-a-rebinding-of-{name}",
                any(row.startswith("DISPATCH_NAME_REBOUND") and repr(name) in row for row in found),
                f"expected a rebinding of {name!r} in {found}")
    control("name-rebindings-judges-at-least-one-file", bool(FORM_SPELLINGS), "no spelling is declared")
    control("name-rebindings-over-no-file-refuses-rather-than-passing",
            any(row.startswith("INVENTORY_STALE form spellings") for row in name_rebindings(spellings=())),
            f"{name_rebindings(spellings=())}")
    # ---- audit 2030: a spelling whose FILE is gone. The row above covers an empty list, which is a
    # different refusal ("no file was scanned"), so this one keeps a present row beside the missing
    # one: one file is scanned, and the missing row still has to be named.
    gone_spelling = "session-distill/a-control-spells-no-file.py"
    mixed = name_rebindings(spellings=(FORM_SPELLINGS[0],
                                       {"site": gone_spelling, "str": "str", "path": "pathlib.Path",
                                        "member": "copied_member", "imports": {},
                                        "reason": "a control's own row: a spelling naming no file"}))
    control("a-form-spelling-naming-no-file",
            any(row == f"INVENTORY_STALE form spelling {gone_spelling}: no such file" for row in mixed),
            f"{mixed}")
    # ---- audit 2048: an import ALIAS that binds a watched name. The three plants above are an
    # assignment, a `def` and a `for`; an import takes the `continue` branch and is judged by what
    # the spelling declares the name to be imported as, not by being bound at all.
    aliased, _ = plant(driver_rel, "import os as pathlib\n")
    control("planted-a-watched-name-bound-by-an-import-alias",
            any(row.startswith("DISPATCH_NAME_REBOUND") and "'pathlib'" in row
                and "is imported in a way the spelling does not declare" in row for row in aliased),
            f"{aliased}")

    # ---- audit 1797: the copy-run staleness leg, over rows this control BUILDS. Indexing the live
    # tuple would make the control stop testing the day that tuple changes, which is the trap this
    # repo has already paid for once.
    own_rows = ({"site": "session-distill/distill.py", "owner": "runlib.inventory.copied_member",
                 "paths": ("session-distill/runlib/census.py",),
                 "reason": "a control's own row: an existing site and an existing file the site never "
                           "runs as a copy"},)
    unrun = closure_violations(tree, copies=own_rows)[0]
    control("a-declared-copy-run-the-site-never-runs",
            any(row.startswith("INVENTORY_STALE copy run session-distill/distill.py -> "
                               "session-distill/runlib/census.py") and "runs no such copy" in row
                for row in unrun), f"{unrun}")
    control("and-that-rows-site-and-file-both-exist-so-it-is-the-run-that-is-missing",
            (REPO / own_rows[0]["site"]).is_file() and (REPO / own_rows[0]["paths"][0]).is_file(),
            f"{own_rows}")

    # ---- audit 344: `runner_argv`'s own refusals, asked of the function DIRECTLY. The admission
    # boundary refuses such a call first, which is why removing either of these left every suite
    # green: this is the second place the same fact is kept.
    for refusal_code, host, spec in (
            ("APPENDED_PROMPT_UNDELIVERABLE", "codex",
             {"call_id": "c-appended", "profile": "hermetic", "model": "m", "effort": "medium",
              "workdir": "/fixture/work", "use": "judging",
              "appended_prompts": [{"path": "/fixture/p.md", "sha256": "0" * 64}]}),
            ("CAP_UNDELIVERABLE", "codex",
             {"call_id": "c-capped", "profile": "hermetic", "model": "m", "effort": "medium",
              "workdir": "/fixture/work", "use": "judging", "view_window": {"lines": 10},
              "output_cap": 1000}),
    ):
        runner_refusal = ""
        try:
            runner_argv(host, spec)
        except Exception as exc:
            runner_refusal = f"{type(exc).__name__}: {exc}"
        control(f"runner-argv-refuses-{refusal_code.lower().replace('_', '-')}",
                refusal_code in runner_refusal, f"{runner_refusal!r}")
    control("and-the-adapter-that-refused-really-conveys-neither",
            not adapter_conveys("codex", "hermetic"), f"{adapter_conveys('codex', 'hermetic')}")

    found, _at = plant("session-distill/runlib/dispatch.py", "import subprocess\nsubprocess.run(['claude', '-p'])")
    control("supervisor-own-sites-are-not-failures", not found, f"{found}")
    found, _at = plant("session-distill/screen-codex.py", "import subprocess\nsubprocess.run(['codex', 'exec'])")
    control("a-mention-outside-the-closure-is-not-a-failure", not found, f"{found}")

    # the adapters' own sources, as they ship (the tree's file, and only once it states the final
    # interface): what their bind check and refusal inventory are judged against, never a copy
    # made here
    def adapter_source(rel, marker):
        path = REPO / rel
        if path.is_file() and marker in path.read_text(encoding="utf-8", errors="replace"):
            return path.read_text(encoding="utf-8", errors="replace")
        return None
    claude_marker = "A dispatcher calls one hermetic Claude call as"
    sources = {"claude": [adapter_source("wrappers/claude-run.sh", claude_marker),
                          adapter_source("wrappers/claude_hermetic_evidence.py", "def bind_problems")],
               "codex": [adapter_source("wrappers/codex-run.sh", "CODEX_RUN_VERSION"),
                         adapter_source("wrappers/codex_frame_filter.py", "CONTEXT_EVIDENCE_MISSING")]}
    control("adapter-sources-are-readable", all(all(texts) for texts in sources.values()),
            f"ADAPTER_SOURCE_ABSENT {[(h, [t is not None for t in texts]) for h, texts in sources.items()]}")

    def adapter_codes(host):
        """The codes an adapter names: its `<host>-run: CODE` lines and its helper's problem codes
        outside the helper's self-test, less environment names and the gate's own evidence codes."""
        text = "".join((t or "").split("\ndef self_test", 1)[0] for t in sources[host])
        found = set(re.findall(host + r"-run: ([A-Z][A-Z0-9]*_[A-Z0-9_]*[A-Z0-9])\b", text)) \
            | set(re.findall(r'f"([A-Z][A-Z0-9]*_[A-Z0-9_]*[A-Z0-9]) ', text))
        return found - set(re.findall(r"\$\{?([A-Z][A-Z0-9_]+)", text)) - set(gate.CODES)
    derived = {host: adapter_codes(host) for host in sources}
    control("adapter-refusal-inventory-is-the-adapters-own", all(derived[h] == set(ADAPTER_CODES[h]) for h in derived),
            f"{ {h: sorted(derived[h] ^ set(ADAPTER_CODES[h])) for h in derived} }")

    # the runner's argv in the adapters' interfaces (claude-run's --help, plan WP-03; codex-run, WP-04),
    # golden: a judge call with the stage's output-token cap, a producing call whose read root is its
    # working directory, and a Codex call, which takes neither (no producing profile, no output cap)
    # and whose host is named in the environment
    base = {"profile": "hermetic", "model": "claude-haiku-5-5", "effort": "low", "cell": "/cells/c1", "call_id": "c1",
            "workdir": "/cells/c1/cwd", "schema_path": "/calls/c1/schema.json", "use": "judge", "read_root": None,
            "max_output_tokens": 16, "host_bin": "/hosts/claude/2.1.304", "host_version": "2.1.304"}
    claude_head = [str(RUNNERS["claude"]), "--profile", "hermetic", "--model", "claude-haiku-5-5", "--effort", "low",
                   "--cell-root", "/cells", "--call-id", "c1", "--cd", "/cells/c1/cwd",
                   "--claude-bin", "/hosts/claude/2.1.304", "--host-version", "2.1.304", "--max-output-tokens", "16"]
    control("runner-argv-of-a-judge-call", runner_argv("claude", base) == claude_head + ["--schema", "/calls/c1/schema.json"],
            f"{runner_argv('claude', base)}")
    producing = dict(base, use="producing", read_root="/cells/c1/cwd")
    control("runner-argv-of-a-producing-call", runner_argv("claude", producing) == claude_head + [
        "--schema", "/calls/c1/schema.json", "--use", "producing", "--tools", "Read", "--manifest", "/cells/c1/cwd"],
        f"{runner_argv('claude', producing)}")
    control("runner-argv-of-a-codex-call", runner_argv("codex", dict(base, model="gpt-6-luna")) == [
        str(RUNNERS["codex"]), "--profile", "hermetic", "--model", "gpt-6-luna", "--effort", "low", "--cd", "/cells/c1/cwd",
        "--schema", "/calls/c1/schema.json", "-"], f"{runner_argv('codex', dict(base, model='gpt-6-luna'))}")
    # through the supervisor: the argv recorded for each call, the real adapter's bind check over the
    # paths that argv names, the calling convention the runner received, and the producing call
    # recorded under its profile with the declared files in its working directory
    helper = scratch / "claude_hermetic_evidence.py"
    helper.write_text(sources["claude"][1] or "", encoding="utf-8")
    da = run_dir("run-argv", {"S6": 400_000})
    sa = supervisor(da)
    sa.seed_from(calibrated)
    recorded, binds, fake_runner = [], [], sa.runner

    def bind(spec, manifest):
        done = subprocess.run([sys.executable, "-I", str(helper), "bind", "--root", str(pathlib.Path(spec["cell"]).parent),
                               "--cell", spec["cell"], "--cwd", spec["workdir"]] + (["--manifest", manifest] if manifest else []),
                              capture_output=True, text=True)
        return done.returncode, done.stderr.strip()

    def recording(host, spec):
        recorded.append(runner_argv(host, spec))
        if host == "claude":
            binds.append((bind(spec, spec["read_root"]), bind(spec, str(readable)) if spec["read_root"] else None))
        return fake_runner(host, spec)
    sa.runner = recording
    readable = scratch / "manifest-dir"
    (readable / "notes").mkdir(parents=True)
    (readable / "a.md").write_text("declared file\n")
    (readable / "notes" / "b.md").write_text("another\n")
    pinned = gate.seats()["hosts"]
    seen, argv_dirs = {}, {}
    for name, seat, kwargs in (("judge", judge, {"max_output_tokens": 16}), ("producing", judge, {"use": "producing",
                               "read_root": readable, "max_output_tokens": 16}), ("codex", luna, {"max_output_tokens": 16})):
        sa.extra = {"env_seen": str(scratch / f"env-{name}.json")}
        r = sa.reserve("S6", f"argv-{name}", seat, "judge")
        argv_dirs[name] = sa.call("S6", seat, packets.build(r["call_id"], "S6", seat, "Reply OK.\n", None), None, reservation=r,
                                  caps=caps, view_window=False, **kwargs)
        seen[name] = (json.loads((scratch / f"env-{name}.json").read_text()), r["call_id"])
    claude_pin = ["--claude-bin", os.path.expanduser(pinned["claude"]["path"]), "--host-version", pinned["claude"]["version"],
                  "--max-output-tokens", "16"]
    producing_argv = recorded[1] if len(recorded) > 1 else []
    cd = producing_argv[producing_argv.index("--cd") + 1] if "--cd" in producing_argv else None
    control("supervisor-passes-host-use-manifest-and-cap-to-claude-only",
            len(recorded) == 3 and recorded[0][-6:] == claude_pin
            and producing_argv[-12:] == claude_pin + ["--use", "producing", "--tools", "Read", "--manifest", cd]
            and not {"--max-output-tokens", "--use", "--claude-bin"} & set(recorded[2]), f"{recorded}")
    control("the-real-adapter-binds-the-producing-paths", len(binds) == 2 and binds[0][0] == (0, "") and binds[1][0] == (0, ""),
            f"{binds}")
    control("the-real-adapter-refuses-a-read-root-that-is-not-the-working-directory",
            len(binds) == 2 and binds[1][1] is not None and binds[1][1][0] == 3 and "READ_ROOT_MISMATCH" in binds[1][1][1],
            f"{binds}")
    producing_call = records.read_json(argv_dirs["producing"] / "call.json")
    control("producing-call-recorded-under-its-profile-and-accepted", producing_call["profile"] == "hermetic-producing"
            and producing_call["use"] == "producing" and gate.accept(argv_dirs["producing"])["ok"]
            and [f["path"] for f in producing_call["manifest"]["workdir_files"]] == ["a.md", "notes/b.md"],
            f"{producing_call['profile']} {producing_call['manifest']['workdir_files']} {gate.accept(argv_dirs['producing'])['failures']}")
    control("runner-environment-names-the-call-and-the-codex-host",
            all(env["REVIEW_CALL_ID"] == env["DISTILL_CALL_ID"] == cid for env, cid in seen.values())
            and seen["judge"][0]["CODEX_RUN_BIN"] is None
            and seen["codex"][0]["CODEX_RUN_BIN"] == os.path.expanduser(pinned["codex"]["path"])
            and seen["codex"][0]["CODEX_RUN_VERSION"] == pinned["codex"]["version"], f"{seen}")
    # the stage's output-token cap: a capped Claude call runs (above); an omitted, zero or non-integer
    # cap is refused before anything starts, and so is a malformed cap on a Codex call
    caps_refused = []
    for n, (seat, cap) in enumerate(((judge, None), (judge, 0), (judge, "16"), (judge, True), (luna, -1))):
        r = sa.reserve("S6", f"output-cap-{n}", seat, "judge")
        caps_refused.append(refusal(Supervisor.call, sa, "S6", seat, packets.build(r["call_id"], "S6", seat, "x\n", None), None,
                                    reservation=r, caps=caps, view_window=False, max_output_tokens=cap) or "")
        caps_refused[-1] = (caps_refused[-1], (da / "calls" / r["call_id"]).exists())
    control("an-undeclared-output-token-cap-is-refused-before-launch",
            all(text.startswith("CAP_UNDECLARED") and not started for text, started in caps_refused), f"{caps_refused}")
    # a producing read root with a symlink is refused: its target could lie outside the cell
    linked, outside = scratch / "linked-dir", scratch / "outside-the-cell"
    linked.mkdir()
    outside.mkdir()
    (outside / "secret.md").write_text("not declared\n")
    (linked / "out").symlink_to(outside)
    r = sa.reserve("S6", "use-linked", judge, "judge")
    linked_refusal = refusal(sa.call, "S6", judge, packets.build(r["call_id"], "S6", judge, "x\n", None), None, reservation=r,
                             caps=caps, view_window=False, use="producing", read_root=linked) or ""
    control("a-read-root-holding-a-symlink-is-refused", linked_refusal.startswith("USE_REFUSED"), linked_refusal)
    # plan P2: a pinned host binary is the versioned file, never a symlink an update moves (judged where it exists)
    control("pinned-host-binaries-are-not-symlinks", not [h["path"] for h in pinned.values()
                                                           if os.path.islink(os.path.expanduser(h["path"]))], f"{pinned}")
    # a use the adapters cannot serve is refused before anything starts
    refusals = []
    for seat, use, root in ((luna, "producing", readable), (judge, "producing", None), (judge, "judge", readable),
                            (judge, "browsing", None)):
        r = sa.reserve("S6", f"use-{len(refusals)}", seat, "judge")
        refusals.append(refusal(sa.call, "S6", seat, packets.build(r["call_id"], "S6", seat, "x\n", None), None,
                                reservation=r, caps=caps, view_window=False, use=use, read_root=root) or "")
    control("a-use-the-adapters-cannot-serve-is-refused", all(x.startswith("USE_REFUSED") for x in refusals), f"{refusals}")

    # an adapter's named refusal on a nonzero exit is the call's runner_refused and the item's
    # outcome, never retried; nothing else the runner printed is kept (a clean call is the positive).
    # Every code the adapters' own sources name is driven, READ_ROOT_MISMATCH among them.
    refusing = [(judge if host == "claude" else luna, 70 if code == "TRANSCRIPT_UNREADABLE" else 3 if host == "codex" else 2,
                 f"{host}-run: {code} named by the adapter") for host in sorted(derived) for code in sorted(derived[host])]
    wrong = []
    for n, (seat, status, line) in enumerate(refusing):
        code = line.split(": ", 1)[1].split()[0]
        dr_ = run_dir(f"run-adapter-{n}", {"S6": 400_000})
        sr_ = supervisor(dr_, "adapter-refuses", refusal=line, exit=status)
        sr_.seed_from(calibrated)
        out = sr_.item("S6", "refused", seat, "Reply OK.\n", None, case_type="judge", caps=caps, view_window=False)
        refused_call = records.read_json(pathlib.Path(out["attempts"][0]) / "call.json") if out["attempts"] else {}
        if not (out["outcome"] == "failed" and out.get("codes") == [code] and out.get("why") == line.split(": ", 1)[1]
                and len(out["attempts"]) == 1 and refused_call.get("runner_refused") == line.split(": ", 1)[1]):
            wrong.append((code, out, refused_call.get("runner_refused")))
    control("every-adapter-refusal-is-the-item-outcome", refusing and not wrong
            and "claude-run: READ_ROOT_MISMATCH named by the adapter" in [line for _, _, line in refusing], f"{wrong}")
    # the same named line from the other adapter, or on a zero exit, is no refusal
    dr_ = run_dir("run-adapter-not-ours", {"S6": 400_000})
    sr_ = supervisor(dr_, "adapter-refuses", refusal="claude-run: CONTEXT_EVIDENCE_MISSING x", exit=3)
    sr_.seed_from(calibrated)
    out = sr_.item("S6", "not-ours", luna, "Reply OK.\n", None, case_type="judge", caps=caps, view_window=False)
    control("another-adapters-code-is-no-refusal", "CONTEXT_EVIDENCE_MISSING" not in out.get("codes", [])
            and records.read_json(pathlib.Path(out["attempts"][0]) / "call.json")["runner_refused"] is None, f"{out}")

    # a refusal frame read from the raw trace reaches the gate through the dispatcher's own capture:
    # the clean call is accepted, the refusing one rejected by its completion code and retried once
    dg_ = run_dir("run-refusal-frame", {"S6": 400_000})
    sg_ = supervisor(dg_)
    sg_.seed_from(calibrated)
    clean = sg_.item("S6", "clean", luna, "Reply OK.\n", None, case_type="judge", caps=caps, view_window=False)
    sg_.mode = "refusal-frame"
    refused_item = sg_.item("S6", "refused", luna, "Reply OK.\n", None, case_type="judge", caps=caps, view_window=False)
    first = gate.accept(refused_item["attempts"][0]) if refused_item["attempts"] else {"failures": []}
    control("refusal-frame-from-the-trace-is-rejected-through-the-dispatcher", clean["outcome"] == "accepted"
            and refused_item["outcome"] == "failed" and len(refused_item["attempts"]) == 2
            and "RETRY_EXHAUSTED" in refused_item["codes"]
            and any(f.startswith("COMPLETION_INCOMPLETE response.refusal.done frame") for f in first["failures"]),
            f"{clean['outcome']} {refused_item} {first['failures']}")

    # no body the runner prints reaches the call directory: a canary on each host's stderr (and on a
    # Codex output frame) is in no file under it, while the call itself is accepted
    for host_seat in (judge, luna):
        dc_ = run_dir(f"run-canary-{host_seat.partition(':')[0]}", {"S6": 400_000})
        sc_ = supervisor(dc_, "stderr-canary")
        sc_.seed_from(calibrated)
        r = sc_.reserve("S6", "canary", host_seat, "judge")
        canary_dir = sc_.call("S6", host_seat, packets.build(r["call_id"], "S6", host_seat, "Reply OK.\n", None), None,
                              reservation=r, caps=caps, view_window=False)
        leaked = [str(f.relative_to(canary_dir)) for f in canary_dir.rglob("*") if f.is_file() and b"BODY-CANARY" in f.read_bytes()]
        control(f"no-runner-body-reaches-the-call-directory-{host_seat.partition(':')[0]}", not leaked
                and gate.accept(canary_dir)["ok"], f"leaked into {leaked}, {gate.accept(canary_dir)['failures']}")

    # codex-run's capture is never replaced: the frames its helper wrote — here a refusal frame and a
    # retry warning stderr never showed — reach the gate intact
    dh_ = run_dir("run-helper-capture", {"S6": 400_000})
    sh_ = supervisor(dh_, "helper-capture")
    sh_.seed_from(calibrated)
    r = sh_.reserve("S6", "helper", luna, "judge")
    helper_dir = sh_.call("S6", luna, packets.build(r["call_id"], "S6", luna, "Reply OK.\n", None), None, reservation=r,
                          caps=caps, view_window=False)
    kept = gate.Call(helper_dir).frames
    control("codex-run-capture-reaches-the-gate-intact", any(f.get("type") == "response.refusal.done" for f in kept)
            and any(f.get("type") == "responses_retry" for f in kept)
            and any("response.refusal.done frame" in f for f in gate.accept(helper_dir)["failures"]), f"{kept}")

    # the host's own built-in skills are declared from seats.json per host version: a Codex call whose
    # manifest declares none of them fails the gate by name (every clean Codex call above is the positive)
    db_ = run_dir("run-builtin-skills", {"S6": 400_000})
    sb_ = supervisor(db_)
    sb_.seed_from(calibrated)
    r = sb_.reserve("S6", "builtin", luna, "judge")
    bare_dir = sb_.call("S6", luna, packets.build(r["call_id"], "S6", luna, "Reply OK.\n", None), None, reservation=r,
                        caps=caps, view_window=False, manifest={"skills": []})
    control("codex-built-in-skills-undeclared-fail-the-gate", any(f.startswith("CONTEXT_UNDECLARED skills ['imagegen'")
                                                                    for f in gate.accept(bare_dir)["failures"]),
            f"{gate.accept(bare_dir)['failures']}")




    # ---- BA#1: the seat's capacity is declared, not invented -------------------------------------
    plain_capacity = run_dir("run-seam-no-capacity", {vstage: 2_000_000})
    only_allowance = scratch / "seats-allowance-no-capacity.json"
    allow_held = json.loads(measured_seats.read_text(encoding="utf-8"))
    allow_held.pop("seat_capacity")
    only_allowance.write_text(json.dumps(allow_held), encoding="utf-8")
    sc = supervisor(plain_capacity, seats_path=only_allowance)
    rc = sc.reserve(vstage, "no-capacity", vseat, "judge", tranche="calibration")
    got = refusal(sc.call, vstage, vseat, packets.build(rc["call_id"], vstage, vseat, "x\n", None), None,
                  reservation=rc, caps=caps, view_window=True, max_output_tokens=32_000)
    control("a-view-window-call-on-a-seat-with-no-declared-capacity-is-refused",
            (got or "").startswith("CAPACITY_UNDECLARED") and not (plain_capacity / "calls").exists(), f"{got}")
    rc2 = sc.reserve(vstage, "no-capacity-non-window", vseat, "judge", tranche="calibration")
    got = refusal(sc.call, vstage, vseat, packets.build(rc2["call_id"], vstage, vseat, "x\n", None), None,
                  reservation=rc2, caps=caps, view_window=False)
    control("a-non-window-call-on-the-same-seat-needs-no-capacity", got is None, f"{got}")
    for row, entry, why in (
            ("without a basis", {"context_capacity": 1_000_000, "host_version": "0.163.0"}, "no basis"),
            ("with a blank basis", {"context_capacity": 1_000_000, "host_version": "0.163.0", "basis": "  "},
             "no basis"),
            ("that is not a number", {"context_capacity": "big", "host_version": "0.163.0", "basis": "b"},
             "not a positive integer"),
            ("at another host version", {"context_capacity": 1_000_000, "host_version": "0.1.0", "basis": "b"},
             "not '0.163.0'")):
        bad = scratch / f"seats-capacity-{row.replace(' ', '-')}.json"
        bad_held = json.loads(measured_seats.read_text(encoding="utf-8"))
        bad_held["seat_capacity"][astra] = entry
        bad.write_text(json.dumps(bad_held), encoding="utf-8")
        found, reason = gate.seat_capacity(astra, "0.163.0", path=bad)
        control(f"a-seat-capacity-{row.replace(' ', '-')}-is-no-capacity", found is None and why in (reason or ""),
                f"{found} {reason}")
    found, basis = gate.seat_capacity("claude:claude-sonnet-5-5/xhigh", "2.1.304")
    control("the-checkout-declares-the-S3-seat-s-host-reported-capacity",
            found == 1_000_000 and "modelUsage.contextWindow" in (basis or ""), f"{found} {basis}")
    control("the-checkout-leaves-every-codex-seat-undeclared",
            all(not str(k).startswith("codex:") for k in (gate.seats().get("seat_capacity") or {})),
            "a Codex seat carries a capacity no capture reports")

    # ---- BA#2: a non-empty appended prompt, through dispatch and through the gate ----------------
    prompted = run_dir("run-seam-prompt", {"S6": 400_000}, allowance=4000)
    sp = supervisor(prompted)
    rp = sp.reserve("S6", "prompted", judge, "judge", tranche="calibration")
    prompt_text = "An appended system prompt the driver really sends.\n"
    pd = sp.call("S6", judge, packets.build(rp["call_id"], "S6", judge, "Reply OK.\n", None), None, reservation=rp,
                 caps=caps, view_window=False, max_output_tokens=4096,
                 manifest={"appended_prompts": [{"name": "stage.md", "text": prompt_text}]})
    recorded = json.loads((pd / "call.json").read_text(encoding="utf-8"))
    control("an-appended-prompt-is-recorded-as-its-hash-and-the-length-counted",
            recorded["manifest"]["appended_prompts"] ==
            [{"name": "stage.md", "sha256": packets.sha256_bytes(prompt_text.encode("utf-8")),
              "bytes": len(prompt_text.encode("utf-8"))}],
            f"{recorded['manifest']['appended_prompts']}")
    # BB#2: the prompt is DELIVERED, not only recorded. The bytes admission counted are written out of the
    # snapshot, handed to the adapter with their declared sha256, read back by the host, and the gate's
    # effective-context leg is what compares the two - so a prompt that never arrived cannot pass.
    delivered_files = sorted((pd / "appended").glob("*"))
    control("BB#2-the-counted-snapshot-is-what-the-adapter-is-handed",
            [f.read_bytes() for f in delivered_files] == [prompt_text.encode("utf-8")]
            and [packets.sha256_bytes(f.read_bytes()) for f in delivered_files]
            == [r["sha256"] for r in recorded["manifest"]["appended_prompts"]],
            f"{[f.name for f in delivered_files]}")
    observed_prompts = json.loads((pd / "capture" / "host.json").read_text(encoding="utf-8"))["context"]["appended_prompts"]
    control("BB#2-the-host-reports-the-delivered-bytes-under-the-declared-hash",
            [o["sha256"] for o in observed_prompts] == [r["sha256"] for r in recorded["manifest"]["appended_prompts"]]
            and [o["declared_sha256"] for o in observed_prompts] == [o["sha256"] for o in observed_prompts],
            f"{observed_prompts}")
    argv = runner_argv("claude", {"profile": "hermetic", "model": "m", "effort": "high", "cell": str(pd / "cell"),
                                  "call_id": recorded["call_id"], "workdir": str(pd), "host_bin": "/bin/true",
                                  "host_version": "2.1.304", "max_output_tokens": 4096, "use": "judge",
                                  "view_window": False,
                                  "appended_prompts": [{"name": "stage.md", "path": str(delivered_files[0]),
                                                        "sha256": recorded["manifest"]["appended_prompts"][0]["sha256"]}]})
    control("BB#2-the-pinned-adapter-argv-carries-the-file-and-the-hash-it-was-declared-at",
            ["--append-system-prompt-file", str(delivered_files[0]), "--declared-sha256",
             recorded["manifest"]["appended_prompts"][0]["sha256"]]
            == argv[argv.index("--append-system-prompt-file"):argv.index("--append-system-prompt-file") + 4]
            if "--append-system-prompt-file" in argv else False, f"{argv}")
    # BC#6: the declaration is held against what the adapter DOES, not against what its text mentions.
    # The wrapper is run for real against a fake host binary that starts no model and records what it
    # received; then the two forwarding behaviours are removed from a copy of the wrapper, one at a time,
    # and the same run must lose exactly that. A grep for the flag passed with the parser deleted.
    def adapter_dispatch(label):
        """Dispatch one real `claude-run.sh` call and return what the host received.

        BD#3: the invocation is the production one. The argv is `runner_argv` over the spec the Supervisor
        builds, the environment is `runner_env` for that call, and the cell, the working directory and the
        delivered prompt file are the ones the dispatcher made - the fixtures are the host binary, which
        starts no model and records what it was given, and the homes, which are inside the scratch
        directory so the adapter's own dispatch log is written there and nowhere near the owner's."""
        # the cell root may not lie under HOME - claude-run refuses one that does, because such a cell's
        # ancestry holds the owner's instruction files - so the fake HOME is a directory of its own here
        home = scratch / f"adapter-{label}"
        (home / "config").mkdir(parents=True, exist_ok=True)
        (home / "home").mkdir(parents=True, exist_ok=True)
        cells, host_bin = home / "cells", home / "fake-claude"
        cells.mkdir(exist_ok=True)
        cells.chmod(0o700)                            # claude-run refuses a cell root any other mode
        host_bin.write_text(FAKE_CLAUDE_BIN, encoding="utf-8")
        host_bin.chmod(0o700)
        (home / "version.txt").write_text(gate.seats()["hosts"]["claude"]["version"], encoding="utf-8")
        (home / "token").write_text("CLAUDE_CODE_OAUTH_TOKEN=a-fixture-not-a-token\n", encoding="utf-8")
        adapter_run_dir = run_dir(f"run-adapter-{label}", {"S6": 400_000})
        sup_a = Supervisor(adapter_run_dir, clock=lambda: clock[0], cell_root=cells, realization="golden",
                           env={**os.environ, "HOME": str(home / "home"),
                                "CLAUDE_CONFIG_DIR": str(home / "config"),
                                "CLAUDE_RUN_TOKEN_FILE": str(home / "token")})
        # the production builder, with the pinned host binary replaced by the fixture
        sup_a.runner = lambda host, spec: runner_argv(host, {**spec, "host_bin": str(host_bin)})
        ra = sup_a.reserve("S6", f"adapter-{label}", judge, "judge", tranche="calibration")
        try:
            sup_a.call("S6", judge, packets.build(ra["call_id"], "S6", judge, "Reply OK.\n", None), None,
                       reservation=ra, caps=caps, view_window=False, max_output_tokens=4096,
                       manifest={"appended_prompts": [{"name": "stage.md", "text": "Follow these rules.\n"}]})
        except Exception:                             # noqa: BLE001 - the fake host returns no usable
            pass                                      # capture; what this control reads is what it received
        received = home / "received.json"
        call_record = adapter_run_dir / "calls" / ra["call_id"] / "call.json"
        return ((json.loads(received.read_text(encoding="utf-8")) if received.is_file() else None),
                ra["call_id"], json.loads(call_record.read_text(encoding="utf-8")) if call_record.is_file() else {})
    # the positive control first: the adapter the dispatcher really launches, launched the way it does
    got_real, real_call_id, real_record = adapter_dispatch("real")
    control("BC#6-the-claude-adapter-passes-the-declared-output-cap-to-the-host",
            (got_real or {}).get("cap") == "4096", f"{got_real}")
    control("BC#6-the-claude-adapter-appends-the-declared-prompt-with-its-bytes",
            len((got_real or {}).get("appended") or []) == 1
            and (got_real or {}).get("appended_bodies") == ["Follow these rules.\n"],
            f"{got_real}")
    # the production invocation, as the host saw it: the adapter ENTERS the cell's working directory
    # rather than passing it on, the prompt it appends is the copy inside the cell, and the call id the
    # dispatcher assigned is the one the runner was given
    declared_cell = str(pathlib.Path(((real_record.get("manifest") or {}).get("workdir_path") or "/nowhere")).parent)
    control("BD#3-the-host-was-started-in-the-working-directory-of-the-cell-the-dispatcher-made",
            (got_real or {}).get("cwd") == os.path.realpath((real_record.get("manifest") or {})
                                                            .get("workdir_path") or "/nowhere"),
            f"{(got_real or {}).get('cwd')} / {(real_record.get('manifest') or {}).get('workdir_path')}")
    control("BD#3-the-appended-prompt-the-host-read-is-the-copy-inside-that-cell",
            bool((got_real or {}).get("appended"))
            and all(os.path.realpath(a).startswith(os.path.realpath(declared_cell)) and "/declared/" in a
                    and a.endswith("01-stage.md") for a in (got_real or {}).get("appended") or []),
            f"{(got_real or {}).get('appended')} under {declared_cell}")
    control("BD#3-the-packet-the-host-received-names-the-call-the-dispatcher-reserved",
            (got_real or {}).get("packet_head") == f"CALL-ID: {real_call_id}",
            f"{(got_real or {}).get('packet_head')} / {real_call_id}")
    # ... and one mutation per forwarding behaviour, on a copy of the adapter the launcher is pointed at
    adapter_copy = scratch / "adapter-mutations"
    adapter_copy.mkdir(exist_ok=True)
    shutil.copy(RUNNERS["claude"].parent / "claude_hermetic_evidence.py", adapter_copy)
    pinned_adapter = RUNNERS["claude"]
    for label, (old_text, new_text), lost in (
            ("no-cap-export", ('export CLAUDE_CODE_MAX_OUTPUT_TOKENS="$max_output"', 'true'), "cap"),
            ("no-append-arg", ('args+=(--append-system-prompt-file "$snap")', 'true'), "appended")):
        mutated = adapter_copy / f"claude-run-{label}.sh"
        mutated.write_text(pinned_adapter.read_text(encoding="utf-8").replace(old_text, new_text), encoding="utf-8")
        mutated.chmod(0o700)                          # the launcher execs the script path it is given
        control(f"BC#6-the-{label}-mutation-really-changed-the-adapter",
                mutated.read_text(encoding="utf-8") != pinned_adapter.read_text(encoding="utf-8"),
                f"{old_text} is not in the adapter any more")
        RUNNERS["claude"] = mutated                   # the launcher builds the same argv for the copy
        try:
            got_mutated = adapter_dispatch(label)[0]
        finally:
            RUNNERS["claude"] = pinned_adapter
        # the mutated adapter must still REACH the host - otherwise this control would pass on any
        # breakage, and prove nothing about the forwarding it names
        control(f"BC#6-control-removing-{lost}-forwarding-is-detected",
                got_mutated is not None and not (got_mutated.get(lost) or None), f"{got_mutated}")
    control("BC#6-the-pinned-adapter-is-back-after-the-mutations", RUNNERS["claude"] == pinned_adapter,
            f"{RUNNERS['claude']}")
    codex_script = RUNNERS["codex"].read_text(encoding="utf-8") if RUNNERS["codex"].is_file() else ""
    control("the-codex-adapter-takes-neither-the-cap-nor-an-appending-flag",
            "--max-output-tokens" not in codex_script and "--append-system-prompt" not in codex_script,
            f"{RUNNERS['codex']}")
    control("the-recorded-length-is-inside-the-counted-driver-payload",
            recorded["bound"]["driver_bytes"] >= len(prompt_text.encode("utf-8")) + len(
                packets.build(rp["call_id"], "S6", judge, "Reply OK.\n", None)),
            f"{recorded['bound']['driver_bytes']}")
    # ... and the whole call passes the gate, context leg included: BA#2 could only show that the record's
    # shape passed every OTHER leg, because nothing delivered the prompt and the context leg failed by design
    control("BB#2-a-call-carrying-a-delivered-appended-prompt-is-accepted-by-the-gate",
            gate.accept(pd)["ok"], f"{gate.accept(pd)['failures']}")
    # BC#2: ... and a declared INSTRUCTION is recorded in both forms - the raw sha256 and length the
    # payload count counted, and the same bytes in the form the host's observer reports, which is the one
    # the gate compares. The gate's own leg runs the real normalisation; this holds the producer to it.
    instruction_body = b"# Rules\n\n<!-- a comment the host strips -->\nFollow these rules.\n"
    (scratch / "declared-instruction.md").write_bytes(instruction_body)
    ri = sp.reserve("S6", "instructed", judge, "judge", tranche="calibration")
    pid = sp.call("S6", judge, packets.build(ri["call_id"], "S6", judge, "Reply OK.\n", None), None, reservation=ri,
                  caps=caps, view_window=False, max_output_tokens=4096,
                  manifest={"instructions": [{"path": str(scratch / "declared-instruction.md")}]})
    instructed = json.loads((pid / "call.json").read_text(encoding="utf-8"))["manifest"]["instructions"]
    # the subject's presence and keys are checked FIRST (BD#4): without that, a record missing
    # `observer_sha256` made the next control raise a KeyError, and the suite died before printing the
    # named failure it had already recorded
    control("BC#2-a-declared-instruction-is-recorded-with-both-hashes-and-its-length",
            len(instructed) == 1 and sorted(instructed[0]) == ["bytes", "observer_sha256", "path", "sha256"],
            f"{instructed}")
    control("BC#2-a-declared-instruction-is-recorded-raw-and-in-the-observer-s-form",
            instructed == [{"path": str(scratch / "declared-instruction.md"),
                            "sha256": packets.sha256_bytes(instruction_body), "bytes": len(instruction_body),
                            "observer_sha256": gate.observer_sha256("claude", instruction_body)}],
            f"{instructed}")
    control("BC#2-the-two-forms-of-that-instruction-really-differ",
            instructed[0].get("sha256") != instructed[0].get("observer_sha256"),
            "the fixture renders to its own bytes, so the control above tests no translation")
    so = supervisor(run_dir("run-seam-prompt-oversized", {vstage: 2_000_000}))
    ro = so.reserve(vstage, "oversized", vseat, "judge", tranche="calibration")
    got = refusal(so.call, vstage, vseat, packets.build(ro["call_id"], vstage, vseat, "x\n", None), None,
                  reservation=ro, caps=caps, view_window=True, max_output_tokens=32_000,
                  manifest={"appended_prompts": [{"name": "huge.md", "text": "P" * (bound.INPUT_BOUND - claude_allowance)}]})
    control("an-oversized-appended-prompt-is-refused-before-dispatch",
            (got or "").startswith("WINDOW_OVER_BOUND") and "WINDOW_BOUND_EXCEEDED (a)" in (got or ""), f"{got}")
    # BB#1: a prompt whose asserted length contradicts its content is refused by name, so no call is
    # admitted on one length and recorded with another
    rl = so.reserve(vstage, "conflicting-length", vseat, "judge", tranche="calibration")
    got = refusal(so.call, vstage, vseat, packets.build(rl["call_id"], vstage, vseat, "x\n", None), None,
                  reservation=rl, caps=caps, view_window=True, max_output_tokens=32_000,
                  manifest={"appended_prompts": [{"name": "lying.md", "text": "P" * 130_000, "bytes": 1}]})
    control("a-prompt-asserting-a-length-its-content-contradicts-is-refused",
            (got or "").startswith("DRIVER_PART_LENGTH_CONFLICT") and "130000" in (got or ""), f"{got}")
    # BB#3: and the path form is gone - an appended prompt is declared by content
    rpp = so.reserve(vstage, "path-form", vseat, "judge", tranche="calibration")
    (scratch / "path-form-prompt.md").write_text("declared by a path", encoding="utf-8")
    got = refusal(so.call, vstage, vseat, packets.build(rpp["call_id"], vstage, vseat, "x\n", None), None,
                  reservation=rpp, caps=caps, view_window=True, max_output_tokens=32_000,
                  manifest={"appended_prompts": [{"name": "stage.md", "path": str(scratch / "path-form-prompt.md")}]})
    control("an-appended-prompt-declared-by-path-is-refused-at-declaration",
            (got or "").startswith("APPENDED_PROMPT_PATH_FORM"), f"{got}")
    # BB#2: a host whose adapter cannot send it refuses by name rather than recording it
    sq = supervisor(run_dir("run-seam-prompt-undeliverable", {"S7b": 2_000_000}, allowance=4000),
                    seats_path=measured_seats)
    rq = sq.reserve("S7b", "undeliverable", astra, "judge", tranche="calibration")
    got = refusal(sq.call, "S7b", astra, packets.build(rq["call_id"], "S7b", astra, "x\n", None), None,
                  reservation=rq, caps=caps, view_window=False,
                  manifest={"appended_prompts": [{"name": "stage.md", "text": prompt_text}]})
    control("an-appended-prompt-on-a-host-whose-adapter-cannot-send-it-is-refused",
            (got or "").startswith("APPENDED_PROMPT_UNDELIVERABLE"), f"{got}")
    control("the-undeliverable-prompt-left-no-call-record-to-judge-later",
            not (sq.run_dir / "calls" / rq["call_id"]).exists(), "a call record was written for a prompt nobody sent")

    # ---- BA#5: the producer's guarantee, asserted on calls it just made --------------------------
    for label, call_dir, window in (("non-window", pd, False),):
        rec = json.loads((call_dir / "call.json").read_text(encoding="utf-8"))
        control(f"a-new-{label}-call-records-the-complete-bound-block",
                sorted(rec.get("bound") or {}) == ["context_capacity", "driver_bytes", "limit",
                                                   "output_reservation", "stop_standing"]
                and rec["bound"]["limit"] == bound.INPUT_BOUND
                and isinstance(rec["bound"]["driver_bytes"], int) and rec["bound"]["driver_bytes"] > 0
                and rec["bound"]["context_capacity"] is None and rec["bound"]["output_reservation"] is None
                and rec["bound"]["stop_standing"] is False,
                f"{rec.get('bound')}")
    sw = counted(supervisor(run_dir("run-seam-window-record", {vstage: 2_000_000}), "clean"))
    rw = sw.reserve(vstage, "window-record", vseat, "judge", tranche="calibration")
    wd = sw.call(vstage, vseat, packets.build(rw["call_id"], vstage, vseat, "x\n", None), None, reservation=rw,
                 caps=caps, view_window=True, max_output_tokens=32_000)
    wrec = json.loads((wd / "call.json").read_text(encoding="utf-8"))
    control("a-new-window-call-records-the-complete-bound-block",
            sorted(wrec.get("bound") or {}) == ["context_capacity", "driver_bytes", "limit",
                                                "output_reservation", "stop_standing"]
            and wrec["bound"]["context_capacity"] == gate.seat_capacity(vseat, "2.1.304")[0]
            and wrec["bound"]["output_reservation"] == 32_000
            and wrec["bound"]["driver_bytes"] == len(packets.build(rw["call_id"], vstage, vseat, "x\n", None)),
            f"{wrec.get('bound')}")
    control("a-call-record-with-the-bound-block-omitted-fails-the-producer-control",
            sorted({k: v for k, v in (wrec.get("bound") or {}).items() if k != "driver_bytes"})
            != ["context_capacity", "driver_bytes", "limit", "output_reservation", "stop_standing"],
            "omitting a field still satisfies the producer control")
    # BC#4: the legacy envelope is BUILT, from the record the dispatcher just wrote over a retained
    # capture, by removing what the seam added. The old control read a fixture file that does not exist
    # and then judged `{}` under `if legacy else True`, so it passed without validating anything; this one
    # fails if its subject is missing, and the mandatory-bound variant below shows it can fail at all.
    legacy = {k: v for k, v in wrec.items() if k != "bound"}
    legacy_problems = gate.validate.validate_instance(gate.CALL_VALIDATOR, legacy)
    control("a-legacy-call-record-without-a-bound-block-is-still-schema-valid",
            "bound" in wrec and "bound" not in legacy and not legacy_problems,
            f"subject bound={('bound' in wrec)!r}, problems {legacy_problems[:1]}")
    required_bound = gate.validate.compile_schema(
        {**gate.CALL_SCHEMA, "required": sorted(set(gate.CALL_SCHEMA["required"]) | {"bound"})})
    control("the-legacy-control-fails-the-moment-the-bound-block-is-made-mandatory",
            bool(gate.validate.validate_instance(required_bound, legacy))
            and not gate.validate.validate_instance(required_bound, wrec),
            f"{gate.validate.validate_instance(required_bound, legacy)[:1]} / "
            f"{gate.validate.validate_instance(required_bound, wrec)[:1]}")

    # ---- M3 and M4: one excess record, and the one way back --------------------------------------
    #
    # The stop a bound excess leaves is the ONLY stop a run can recover from, and only one way: the host
    # allowance is re-measured and declared later than the excess recorded. The run below really overruns -
    # probe 7's R-authoring capture (about 136k observed input) replayed as a VIEW-WINDOW call - so the
    # record under test is one the dispatcher wrote, not one a control built.
    rec = run_dir("run-seam-recovery", {vstage: 2_000_000})
    sr = counted(supervisor(rec, "clean", replay=replay))
    sr.seed_from(authoring)
    # an EARLIER host_allowance amendment: recorded before the excess, so it is not the way back (M4 v)
    declare.amend(rec, [(f"host_allowance.{vseat}.allowance_tokens", claude_allowance)],
                  "the allowance is re-declared before anything overruns", scope=(vstage,))
    before = sr.reserve(vstage, "reserved-before", vseat, "authoring")
    rr = sr.reserve(vstage, "overrun", vseat, "authoring")
    # ... and one that lands between this call's reservation and its stop (BA#0)
    declare.amend(rec, [(f"host_allowance.{vseat}.allowance_tokens", claude_allowance)],
                  "the allowance is re-declared while the call is in flight", scope=(vstage,))
    over = refusal(sr.call, vstage, vseat, packets.build(rr["call_id"], vstage, vseat, "Author the record.\n", None), None,
                   reservation=rr, caps={"tokens": 400_000, "compactions": 2}, view_window=True,
                   max_output_tokens=32_000)
    control("the-replayed-overrun-stops-the-run-at-the-real-boundary",
            (over or "").startswith(f"INPUT_BOUND_EXCEEDED {rr['call_id']}"), f"{over}")
    stopped = json.loads((rec / "supervisor" / "ledger.json").read_text(encoding="utf-8"))["stopped"]
    control("the-excess-record-is-the-run-s-stop-entry",
            (stopped or {}).get("code") == bound.STOP_CODE and stopped.get("call_id") == rr["call_id"],
            f"{stopped}")
    control("the-excess-record-carries-the-observation-and-the-sequence-recovery-is-measured-from",
            isinstance(stopped.get("observed"), int) and stopped["observed"] > bound.INPUT_BOUND
            and isinstance(stopped.get("declaration_seq"), int), f"{stopped}")
    control("there-is-no-second-excess-file-beside-the-stop-entry",
            not (rec / "input_bound.jsonl").exists() and not list(rec.glob("**/input_bound*")),
            "a second record of the excess was written")
    # M4, the five steps. (i) a window call, (ii) a non-window call - both refused while the stop stands
    def seam_dispatch(label, view_window=True, reservation=None):
        held_r = reservation or sr.reserve(vstage, f"after-{label}", vseat, "authoring")
        if isinstance(held_r, str):
            return held_r
        return refusal(sr.call, vstage, vseat,
                       packets.build(held_r["call_id"], vstage, vseat, "Author the record.\n", None), None,
                       reservation=held_r, caps={"tokens": 400_000, "compactions": 2}, view_window=view_window)

    control("M4-i-a-window-call-is-refused-while-the-stop-stands",
            (refusal(sr.reserve, vstage, "after-window", vseat, "authoring") or "")
            .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), "a window call was reserved after the stop")
    control("M4-ii-a-non-window-call-reserved-before-the-stop-is-refused-too",
            (seam_dispatch("non-window", view_window=False, reservation=before) or "")
            .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), "a non-window call dispatched after the stop")
    # (iii) an amendment of another key is not the way back
    declare.amend(rec, [(f"budget.per_stage.{vstage}", 2_100_000)], "an unrelated amendment", scope=(vstage,))
    control("M4-iii-an-amendment-of-another-key-does-not-lift-the-stop",
            (refusal(sr.reserve, vstage, "after-unrelated", vseat, "authoring") or "")
            .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), "an unrelated amendment lifted the stop")
    # (v) ... and neither does the host_allowance amendment that was recorded BEFORE the excess: it is
    # still in the log, and the rule compares sequences, not spellings
    # BA#0: the sequence the stop is stamped with is the one the COMMIT read. This amendment lands AFTER
    # the call was reserved and BEFORE the stop was committed - which is the case that distinguishes the
    # two readings, and the one the earlier code got wrong.
    control("BA#0-the-stop-is-stamped-with-the-sequence-the-commit-read-not-the-call-s",
            stopped["declaration_seq"] > rr["declaration_seq"], f"{stopped['declaration_seq']} {rr['declaration_seq']}")
    control("BA#0-an-amendment-between-the-reservation-and-the-stop-does-not-lift-it",
            any(a["seq"] > rr["declaration_seq"] and a["seq"] <= stopped["declaration_seq"]
                and any(str(k).startswith("host_allowance") for k in a.get("diff") or {})
                for a in records.declaration_state(rec, who="dispatch")[2])
            and (refusal(sr.reserve, vstage, "after-between", vseat, "authoring") or "")
            .startswith(f"RUN_STOPPED {bound.STOP_CODE}"),
            "no host_allowance amendment landed between the reservation and the stop, or it lifted the stop")
    control("M4-v-the-host_allowance-amendment-recorded-before-the-excess-does-not-lift-it",
            any(a["seq"] <= stopped["declaration_seq"] and any(str(k).startswith("host_allowance")
                                                               for k in a.get("diff") or {})
                for a in records.declaration_state(rec, who="dispatch")[2])
            and (refusal(sr.reserve, vstage, "after-earlier", vseat, "authoring") or "")
            .startswith(f"RUN_STOPPED {bound.STOP_CODE}"),
            "the earlier host_allowance amendment is missing, or it lifted the stop")
    # (iv) the way back: the allowance re-measured and declared after the excess
    declare.amend(rec, [(f"host_allowance.{vseat}.allowance_tokens", 6_000)],
                  "the host allowance was re-measured after the excess", scope=(vstage,))
    after = sr.reserve(vstage, "after-amendment", vseat, "authoring")
    control("M4-iv-a-later-host_allowance-amendment-lets-the-run-go-on",
            isinstance(after, dict) and bool(after.get("call_id")), f"{after}")
    # ... and the recovered call really runs: the same retained capture, as the NON-window call design §8.6
    # says an R-authoring call is, launched through the fake runner and accepted by the gate
    launched_before = list(launches)
    recovered = sr.call(vstage, vseat, packets.build(after["call_id"], vstage, vseat, "Author the record.\n", None),
                        None, reservation=after, caps={"tokens": 400_000, "compactions": 2}, view_window=False)
    verdict = gate.accept(recovered)
    control("BA#4-the-recovered-call-is-launched-and-accepted",
            len(launches) == len(launched_before) + 1 and recovered.is_dir() and verdict["ok"],
            f"{len(launches) - len(launched_before)} launches, {verdict['failures']}")
    control("BA#4-the-recovered-call-records-the-bound-block-with-the-stop-no-longer-standing",
            json.loads((recovered / "call.json").read_text(encoding="utf-8"))["bound"]["stop_standing"] is False,
            "the recovered call records a standing stop")
    control("M4-recovery-does-not-forget-the-excess",
            json.loads((rec / "supervisor" / "ledger.json").read_text(encoding="utf-8"))["stopped"] == stopped,
            "the excess record was cleared instead of being left where it happened")

    # ---- BB#0 and BC#0: the stop and the amendments are serialized by one lock, in one order ------
    #
    # The stop is stamped with the latest sequence the declaration has reached, and BA#0 read that from
    # outside the lock `declare --amend` commits under. The first control below is the interleaving that
    # reading could not survive: an amendment that starts BEFORE the stop and is caught between its log
    # line and its run.json. Nothing here sleeps for a window - the amendment and the stop hand each other
    # the turn through events, so the control does not depend on how the machine schedules them.
    def ledger_stop(directory):
        """The run's one `stopped` entry, or `{}`: read as a file, because a reverted stop writes none and
        a control must then report its own name rather than die on a missing ledger."""
        path = pathlib.Path(directory) / "supervisor" / "ledger.json"
        return (json.loads(path.read_text(encoding="utf-8")).get("stopped") or {}) if path.is_file() else {}

    bb0 = run_dir("run-bb0-lock-order", {vstage: 2_000_000})
    sb = supervisor(bb0)
    mid_commit, stop_attempted = threading.Event(), threading.Event()
    committed_at, failed_in_thread = [], []

    def amend_mid_commit(run_dir_path, wait_for_stop=True):
        """An amendment paused between its two writes, as `declare --amend` would be if it were
        interrupted there: the log line is on disk and run.json still answers the previous sequence."""
        try:
            with stagelock.hold(run_dir_path, "declaration"):
                run, _digest, _amendments = records.declaration_state(run_dir_path, who="declare")
                seq = run["declaration_seq"] + 1
                allowance = {**run["host_allowance"][vseat], "allowance_tokens": claude_allowance}
                new_run = {**run, "declaration_seq": seq, "host_allowance": {**run["host_allowance"], vseat: allowance}}
                records.append_amendment(run_dir_path, {"seq": seq, "at": records.now(), "scope": [vstage],
                                                        "invalidates": [],
                                                        "reason": "the allowance is re-measured while a call is in flight",
                                                        "diff": {f"host_allowance.{vseat}.allowance_tokens": claude_allowance},
                                                        "run_json_sha256": records.bound_digest(new_run)})
                mid_commit.set()                      # the log line is written, run.json is not
                if wait_for_stop:
                    # BE#2: this waits for the stop's acquisition to find THIS lock held - the hook fires
                    # inside `stagelock.hold`, after the real flock attempt failed - and the lock is
                    # released only by the write below. Signalling before the attempt (BD#2's first shape)
                    # left a schedule in which the amendment finished first and a regression that reads
                    # outside the lock still passed.
                    stop_attempted.wait(30)
                records.write_json(run_dir_path, records.run_json_path(run_dir_path), new_run)
                committed_at.append(time.monotonic())
        except Exception as exc:                      # noqa: BLE001 - reported as this control's failure
            failed_in_thread.append(repr(exc))

    amender = threading.Thread(target=amend_mid_commit, args=(bb0,), daemon=True)
    amender.start()
    control("BB#0-the-amendment-reached-its-mid-commit-state", mid_commit.wait(30), "the amendment never started")
    stop_failed, contended = None, []

    def on_contention(name):
        contended.append(name)
        stop_attempted.set()

    stagelock.CONTENDED = on_contention
    try:
        stopped_bb0 = sb._stop_run(bound.excess("run-bb0-S3-x-a1", 135_796, clock[0]))
    except Exception as exc:                          # noqa: BLE001 - this control's own failure, by name
        stopped_bb0, stop_failed = {}, repr(exc)
    finally:
        stagelock.CONTENDED = None
    returned_at = time.monotonic()
    amender.join(60)
    control("BE#2-the-amendment-was-released-by-real-contention-on-the-declaration-lock",
            contended[:1] == ["declaration"] and bool(committed_at), f"{contended} {committed_at}")
    control("BB#0-the-mid-commit-amendment-committed-without-error", not failed_in_thread, f"{failed_in_thread}")
    # reading the sequence outside the declaration lock does not see a tidy earlier state: it sees the log
    # line without the run.json that answers it, and that is what DECLARATION_DRIFT names
    control("BB#0-the-stop-is-committed-across-the-amendment-rather-than-between-its-two-writes",
            stop_failed is None, f"{stop_failed}")
    control("BB#0-the-stop-waited-for-the-amendment-s-commit-instead-of-reading-across-it",
            bool(committed_at) and returned_at >= committed_at[0], f"{committed_at} {returned_at}")
    log_bb0 = records.declaration_state(bb0, who="dispatch")[2]
    control("BB#0-the-stop-is-stamped-with-the-sequence-that-amendment-reached",
            stopped_bb0.get("declaration_seq") == max(a["seq"] for a in log_bb0), f"{stopped_bb0} {log_bb0}")
    control("BB#0-an-amendment-started-before-the-stop-cannot-lift-it",
            (sb._blocked() or "").startswith(f"RUN_STOPPED {bound.STOP_CODE}"), f"{sb._blocked()}")
    declare.amend(bb0, [(f"host_allowance.{vseat}.allowance_tokens", claude_allowance)],
                  "the allowance is re-measured after the excess", scope=(vstage,))
    control("BB#0-an-amendment-committed-after-the-stop-lifts-it", sb._blocked() is None, f"{sb._blocked()}")
    stop_source = inspect.getsource(Supervisor._stop_run)
    control("BB#0-the-stop-takes-the-declaration-lock-first-and-the-supervisor-s-inside-it",
            '"declaration"' in stop_source
            and stop_source.index('"declaration"') < stop_source.index("with self._lock():")
            and stop_source.index("with self._lock():") < stop_source.index('ledger["stopped"]'),
            "the stop does not hold the declaration lock around the supervisor's")

    # BC#0: ... and when that lock cannot be taken at all, the excess is still recorded. The wait is
    # bounded on purpose - an unbounded one would hang the dispatcher behind whoever holds the lock - so
    # the failure mode this closes is the one that discards an observed overrun: the stop is written
    # unstamped, nothing lifts it, and the run is over.
    bc0 = run_dir("run-bc0-lock-timeout", {vstage: 2_000_000})
    st = counted(supervisor(bc0, "clean", replay=replay))
    st.seed_from(authoring)
    mid_commit, stop_attempted = threading.Event(), threading.Event()
    committed_at, failed_in_thread = [], []
    holder_release = threading.Event()

    def hold_declaration_past_the_timeout():
        try:
            with stagelock.hold(bc0, "declaration"):
                mid_commit.set()
                holder_release.wait(60)
        except Exception as exc:                      # noqa: BLE001
            failed_in_thread.append(repr(exc))

    holder = threading.Thread(target=hold_declaration_past_the_timeout, daemon=True)
    holder.start()
    control("BC#0-the-declaration-lock-is-held-by-another-writer", mid_commit.wait(30), "the holder never started")
    held_wait, globals()["STOP_LOCK_WAIT_S"] = STOP_LOCK_WAIT_S, 0.2
    over, rt, timeout_error = None, {"call_id": "unreserved"}, None
    try:
        rt = st.reserve(vstage, "overrun-while-locked", vseat, "authoring")
        over = refusal(st.call, vstage, vseat,
                       packets.build(rt["call_id"], vstage, vseat, "Author the record.\n", None), None,
                       reservation=rt, caps={"tokens": 400_000, "compactions": 2}, view_window=True,
                       max_output_tokens=32_000)
    except Exception as exc:                          # noqa: BLE001 - a lock error that escapes IS the defect
        timeout_error = repr(exc)
    finally:
        globals()["STOP_LOCK_WAIT_S"] = held_wait
        holder_release.set()
        holder.join(60)
    control("BC#0-a-lock-timeout-does-not-escape-the-call-unhandled", timeout_error is None, f"{timeout_error}")
    control("BC#0-the-call-whose-stop-could-not-be-stamped-still-fails-by-name",
            (over or "").startswith(f"{bound.STOP_CODE} {rt['call_id']}"), f"{over}")
    timed_out = ledger_stop(bc0)
    control("BC#0-the-excess-is-recorded-even-though-the-declaration-lock-timed-out",
            (timed_out or {}).get("code") == bound.STOP_CODE and timed_out.get("observed") == 135_796
            and timed_out.get("call_id") == rt["call_id"], f"{timed_out}")
    control("BC#0-that-stop-is-unstamped-and-says-why",
            bool(timed_out) and "declaration_seq" not in timed_out
            and "lock-timeout" in (timed_out.get("stamp") or ""), f"{timed_out}")
    control("BC#0-dispatch-stays-refused-after-an-unstamped-stop",
            (refusal(st.reserve, vstage, "after-timeout", vseat, "authoring") or "")
            .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), "a call was reserved after an unstamped stop")
    declare.amend(bc0, [(f"host_allowance.{vseat}.allowance_tokens", claude_allowance + 1)],
                  "the allowance is re-measured after an unstamped stop", scope=(vstage,))
    control("BC#0-and-no-later-amendment-lifts-it-so-recovery-is-a-new-run",
            (refusal(st.reserve, vstage, "after-amendment", vseat, "authoring") or "")
            .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), "an amendment lifted an unstamped stop")
    control("BC#0-the-holder-thread-raised-nothing", not failed_in_thread, f"{failed_in_thread}")

    # BD#0: ... and a stop never weakens. A call that was ALREADY RUNNING when that timeout happened
    # settles its own excess afterwards, with the lock free, so it stamps a sequence - and writing that
    # entry over the unstamped one handed the run a sequence a later amendment could pass. The ledger keeps
    # the stronger entry; the settling call still reports its own stop in its own record.
    settled_later = st._stop_run(bound.excess("run-bc0-S3-already-running-a1", 136_002, clock[0]))
    kept_bd0 = ledger_stop(bc0)
    control("BD#0-the-already-running-call-stamps-its-own-stop",
            isinstance(settled_later.get("declaration_seq"), int)
            and settled_later.get("call_id") == "run-bc0-S3-already-running-a1", f"{settled_later}")
    control("BD#0-a-later-stamped-stop-does-not-replace-the-unstamped-one",
            kept_bd0.get("call_id") == timed_out.get("call_id") and "declaration_seq" not in kept_bd0
            and "lock-timeout" in (kept_bd0.get("stamp") or ""), f"{kept_bd0}")
    declare.amend(bc0, [(f"host_allowance.{vseat}.allowance_tokens", claude_allowance + 2)],
                  "the allowance is re-measured after the second stop", scope=(vstage,))
    control("BD#0-an-amendment-later-than-that-stamped-stop-still-does-not-lift-the-run",
            (st._blocked() or "").startswith(f"RUN_STOPPED {bound.STOP_CODE}"), f"{st._blocked()}")
    # ... and between two STAMPED stops the higher sequence is the one kept, so recovery must pass the
    # latest excess rather than an earlier one
    bd0 = run_dir("run-bd0-two-stamped", {vstage: 2_000_000})
    sd0 = supervisor(bd0)
    first_stop = sd0._stop_run(bound.excess("run-bd0-S3-first-a1", 130_001, clock[0]))
    for n in (1, 2):
        declare.amend(bd0, [(f"host_allowance.{vseat}.allowance_tokens", claude_allowance + n)],
                      f"the allowance is re-measured, amendment {n}", scope=(vstage,))
    second_stop = sd0._stop_run(bound.excess("run-bd0-S3-second-a1", 130_002, clock[0]))
    kept_two = ledger_stop(bd0)
    control("BD#0-between-two-stamped-stops-the-higher-sequence-is-kept",
            kept_two.get("declaration_seq") == second_stop["declaration_seq"] > first_stop["declaration_seq"],
            f"{kept_two} {first_stop.get('declaration_seq')} {second_stop.get('declaration_seq')}")
    control("BD#0-an-amendment-between-the-two-sequences-does-not-lift-the-run",
            any(first_stop["declaration_seq"] < a["seq"] <= second_stop["declaration_seq"]
                and any(str(k).startswith("host_allowance") for k in a.get("diff") or {})
                for a in records.declaration_state(bd0, who="dispatch")[2])
            and (sd0._blocked() or "").startswith(f"RUN_STOPPED {bound.STOP_CODE}"),
            f"{sd0._blocked()}")

    # BD#1: an unreadable declaration is an unstamped stop too, not a discarded excess. The reader refuses
    # a DRIFTED declaration by name, and that was the only failure handled here; a file this process cannot
    # read, or one linked out of the run, arrives as PermissionError or Escaped and used to escape the stop
    # entirely - leaving the ledger with no stop at all and admission open once the file was readable again.
    for label, break_it, mend_it, needle in (
            ("unreadable", lambda path: path.chmod(0o000), lambda path: path.chmod(0o600), "PermissionError"),
            ("linked out of the run", lambda path: (path.unlink(), path.symlink_to(scratch / "outside-log.jsonl")),
             lambda path: (path.unlink(), path.write_text("", encoding="utf-8")), "Escaped")):
        bd1 = run_dir(f"run-bd1-{label.replace(' ', '-')}", {vstage: 2_000_000})
        s1 = supervisor(bd1)
        log_path = records.amendments_path(bd1)
        kept_log = log_path.read_text(encoding="utf-8")
        (scratch / "outside-log.jsonl").write_text("", encoding="utf-8")
        stop_error = None
        break_it(log_path)
        try:
            unreadable_stop = s1._stop_run(bound.excess(f"run-bd1-S3-{label[:4]}-a1", 136_003, clock[0]))
        except Exception as exc:                      # noqa: BLE001 - escaping IS the defect this closes
            unreadable_stop, stop_error = {}, repr(exc)
        finally:
            mend_it(log_path)
            log_path.write_text(kept_log, encoding="utf-8")
        control(f"BD#1-a-declaration-{label.replace(' ', '-')}-does-not-escape-the-stop",
                stop_error is None, f"{stop_error}")
        kept_bd1 = ledger_stop(bd1)
        control(f"BD#1-the-excess-is-recorded-unstamped-when-the-declaration-is-{label.replace(' ', '-')}",
                kept_bd1.get("code") == bound.STOP_CODE and "declaration_seq" not in kept_bd1
                and "declaration-unreadable" in (kept_bd1.get("stamp") or ""), f"{kept_bd1}")
        control(f"BD#1-the-stamp-names-what-went-wrong-({label.replace(' ', '-')})",
                needle in (kept_bd1.get("stamp") or ""), f"{kept_bd1.get('stamp')}")
        # the declaration is readable again here, and that does not reopen the run
        control(f"BD#1-restoring-the-declaration-does-not-reopen-admission-({label.replace(' ', '-')})",
                (s1._blocked() or "").startswith(f"RUN_STOPPED {bound.STOP_CODE}")
                and (refusal(s1.reserve, vstage, "after-unreadable", vseat, "judge", tranche="calibration") or "")
                .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), f"{s1._blocked()}")
        declare.amend(bd1, [(f"host_allowance.{vseat}.allowance_tokens", claude_allowance + 3)],
                      "the allowance is re-measured after an unreadable declaration", scope=(vstage,))
        control(f"BD#1-and-no-amendment-lifts-that-stop-({label.replace(' ', '-')})",
                (s1._blocked() or "").startswith(f"RUN_STOPPED {bound.STOP_CODE}"), f"{s1._blocked()}")

    # ---- F-19: the stop is persisted FIRST, and no later failure can discard it -------------------
    #
    # Round 5 found two ways an observed excess ended with no stop in the ledger: a declaration-lock
    # acquisition that failed as anything other than Locked, and a failure anywhere in the settlement that
    # used to run before the stop was written - the call record, the receipt the launcher writes, the
    # charge's calibration read. Each case below breaks exactly one of those through the real code, with
    # the supervisor ledger left writable, and asks the same three questions: is the overrun recorded, is
    # the next dispatch refused, and did the call itself report the failure.
    def overrun_under(label, arrange=None, restore=None, adjust=None):
        """One replayed 136k view-window call, with `arrange` having broken one thing first.

        `adjust` gets the supervisor before the call, for the one case whose fixture is the
        measurement itself rather than the filesystem (HA#0)."""
        directory = run_dir(f"run-f19-{label}", {vstage: 2_000_000})
        sup_f = counted(supervisor(directory, "clean", replay=replay))
        sup_f.seed_from(authoring)
        held_r = sup_f.reserve(vstage, label, vseat, "authoring")
        if adjust:                                # after the reservation: a case may break the clock
            adjust(sup_f)                         # or the measurement the call itself runs on
        if arrange:
            arrange(directory)
        reported = None
        try:
            sup_f.call(vstage, vseat, packets.build(held_r["call_id"], vstage, vseat, "Author the record.\n", None),
                       None, reservation=held_r, caps={"tokens": 400_000, "compactions": 2}, view_window=True,
                       max_output_tokens=32_000)
        except Exception as exc:                      # noqa: BLE001 - the failure IS what each case reads
            reported = f"{type(exc).__name__}: {exc}"
        finally:
            if restore:
                restore(directory)
        return directory, sup_f, held_r, reported

    def lock_path(directory):
        path = pathlib.Path(directory) / "locks" / "declaration.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def break_lock_mode(directory):
        path = lock_path(directory)
        path.touch()
        path.chmod(0o000)

    def break_lock_link(directory):
        path = lock_path(directory)
        path.unlink(missing_ok=True)
        (scratch / "outside.lock").touch()
        path.symlink_to(scratch / "outside.lock")

    def mend_lock(directory):
        path = lock_path(directory)
        if path.is_symlink():
            path.unlink()
        else:
            path.chmod(0o600)

    def break_calibration(directory, text=None):
        path = pathlib.Path(directory) / "supervisor" / "calibration.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if text is None:                              # unreadable: charge reads it after its ledger write
            path.write_text("{}", encoding="utf-8")
            path.chmod(0o000)
        else:                                         # or readable and not JSON at all
            path.write_text(text, encoding="utf-8")

    def mend_calibration(directory):
        path = pathlib.Path(directory) / "supervisor" / "calibration.json"
        if path.exists():
            path.chmod(0o600)

    def break_launcher(_directory):
        failing = scratch / "no-launcher.py"
        failing.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
        receipts.LAUNCHER = failing

    for label, arrange, restore, wanted, stamped in (
            ("lock-mode-000", break_lock_mode, mend_lock, "INPUT_BOUND_EXCEEDED", "lock-unavailable"),
            ("lock-linked-out", break_lock_link, mend_lock, "INPUT_BOUND_EXCEEDED", "lock-unavailable"),
            ("receipt-missing", break_launcher, lambda _d: setattr(receipts, "LAUNCHER", pinned_launcher),
             "RECEIPT_MISSING", None),
            ("calibration-unreadable", break_calibration, mend_calibration, "RECORD_UNREADABLE", None),
            ("calibration-malformed", lambda d: break_calibration(d, "not json at all"), mend_calibration,
             "RECORD_UNREADABLE", None)):
        f19, sup_f, rf, reported = overrun_under(label, arrange, restore)
        kept_f19 = ledger_stop(f19)
        control(f"F-19-{label}-the-observed-excess-is-in-the-ledger",
                kept_f19.get("code") == bound.STOP_CODE and kept_f19.get("observed") == 135_796
                and kept_f19.get("call_id") == rf["call_id"], f"{kept_f19}")
        control(f"F-19-{label}-the-next-dispatch-is-refused",
                (refusal(sup_f.reserve, vstage, f"after-{label}", vseat, "authoring") or "")
                .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), f"a call was reserved after {label}")
        control(f"F-19-{label}-the-call-itself-reported-the-failure",
                wanted in (reported or ""), f"{reported}")
        if stamped:
            control(f"F-19-{label}-that-stop-is-unstamped-and-names-the-lock-failure",
                    "declaration_seq" not in kept_f19 and stamped in (kept_f19.get("stamp") or ""),
                    f"{kept_f19}")
            control(f"F-19-{label}-and-no-amendment-lifts-it",
                    bool(declare.amend(f19, [(f"host_allowance.{vseat}.allowance_tokens", claude_allowance + 4)],
                                       "the allowance is re-measured", scope=(vstage,)))
                    and (sup_f._blocked() or "").startswith(f"RUN_STOPPED {bound.STOP_CODE}"),
                    f"{sup_f._blocked()}")
        else:
            control(f"F-19-{label}-the-stop-is-stamped-because-the-declaration-was-readable",
                    isinstance(kept_f19.get("declaration_seq"), int) and "stamp" not in kept_f19, f"{kept_f19}")

    # HA#0: an incomplete usage row does not discard an excess the COMPLETE rows already establish.
    # `bound.observed_input` answers the two questions independently, and the refusal for the second used
    # to be raised before the stop for the first was written. The fixture here is the measurement itself -
    # one real replayed 136k request, plus a measured row whose input is a float, which `bound.observed_of`
    # reads as a missing component - and everything after it is the production settlement.
    def add_an_incomplete_row(sup):
        inner = sup._usage

        def measured(*args, **kwargs):
            usage = inner(*args, **kwargs)
            complete = usage["requests"][0]
            usage["requests"] = list(usage["requests"]) + [
                {**complete, "input_tokens": 1.0, "input": 1.0}]       # both spellings: neither is an int
            return usage

        sup._usage = measured

    f19u, sup_u, ru, reported_u = overrun_under("usage-incomplete", adjust=add_an_incomplete_row)
    kept_u = ledger_stop(f19u)
    recorded_u = json.loads((f19u / "calls" / ru["call_id"] / "call.json").read_text(encoding="utf-8"))
    control("HA#0-the-excess-the-complete-rows-establish-is-in-the-ledger",
            kept_u.get("code") == bound.STOP_CODE and kept_u.get("observed") == 135_796
            and kept_u.get("call_id") == ru["call_id"], f"{kept_u}")
    control("HA#0-the-next-dispatch-is-refused-although-the-usage-was-incomplete",
            (refusal(sup_u.reserve, vstage, "after-usage-incomplete", vseat, "authoring") or "")
            .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), "a call was reserved after an incomplete usage record")
    control("HA#0-the-call-still-fails-with-the-incomplete-usage-refusal",
            "USAGE_INCOMPLETE" in (reported_u or "") and "input_tokens" in (reported_u or ""), f"{reported_u}")
    control("HA#0-and-that-call-s-record-carries-the-stop-it-offered",
            (recorded_u.get("stop") or {}).get("call_id") == ru["call_id"]
            and (recorded_u.get("stop") or {}).get("observed") == 135_796, f"{recorded_u.get('stop')}")

    # F-20: and each call records its own stop, whether or not the run kept it. A stamping defect - this
    # code's own arithmetic, not the filesystem's - says so under its own reason, and says it even when an
    # earlier terminal stop is the one the ledger keeps.
    f20, sup_20, r20, reported_20 = overrun_under("records-its-own-stop")
    recorded_20 = json.loads((f20 / "calls" / r20["call_id"] / "call.json").read_text(encoding="utf-8"))
    control("F-20-the-call-record-carries-this-call-s-own-stop",
            (recorded_20.get("stop") or {}).get("call_id") == r20["call_id"]
            and (recorded_20["stop"]).get("observed") == 135_796 and recorded_20["stop"].get("kept") is True
            and isinstance(recorded_20["stop"].get("declaration_seq"), int), f"{recorded_20.get('stop')}")
    control("F-20-the-call-record-with-a-stop-is-still-schema-valid",
            not gate.validate.validate_instance(gate.CALL_VALIDATOR, recorded_20),
            f"{gate.validate.validate_instance(gate.CALL_VALIDATOR, recorded_20)[:1]}")
    # a stamping defect, with an earlier terminal stop already standing: the ledger keeps the earlier one
    # and the defect is still reported - in this call's own stop and in its refusal
    f20b = run_dir("run-f20-stamping-defect", {vstage: 2_000_000})
    sup_20b = supervisor(f20b)
    break_lock_mode(f20b)                             # the earlier stop is unstamped, and so terminal
    try:                                              # guard the subject: a stop that ESCAPES is named by
        first_terminal = sup_20b._stop_run(           # this control rather than aborting the suite (BD#4)
            bound.excess("run-f20-S3-earlier-a1", 136_000, clock[0]))
    except Exception as exc:                          # noqa: BLE001 - the escape IS the finding
        first_terminal = {"stamp": f"escaped: {exc!r}"}
    finally:
        mend_lock(f20b)
    control("F-20-the-planted-earlier-stop-is-terminal",
            bound.terminal(first_terminal) and "lock-unavailable" in (first_terminal.get("stamp") or ""),
            f"{first_terminal}")
    held_committed, bound.committed = bound.committed, None     # not callable: a defect in this code
    try:
        defective = sup_20b._stop_run(bound.excess("run-f20-S3-defective-a1", 136_001, clock[0]))
    except Exception as exc:                          # noqa: BLE001 - an escaped defect is a failure here
        defective = {"stamp": f"escaped: {exc!r}"}
    finally:
        bound.committed = held_committed
    control("F-20-a-stamping-defect-is-named-as-such-not-as-an-unreadable-declaration",
            "stop-internal-error" in (defective.get("stamp") or "")
            and "declaration-unreadable" not in (defective.get("stamp") or ""), f"{defective.get('stamp')}")
    control("F-20-a-stamping-defect-carries-the-exception-it-came-from",
            "TypeError" in (defective.get("stamp") or ""), f"{defective.get('stamp')}")
    control("F-20-the-earlier-terminal-stop-is-still-the-one-the-run-keeps",
            ledger_stop(f20b).get("call_id") == first_terminal.get("call_id") is not None
            and defective.get("kept") is False,
            f"{ledger_stop(f20b)} {defective.get('kept')}")

    # HA#1: and the losing stop says so through the REAL settlement, not only in the helper's return
    # value. The earlier terminal stop lands while this call is in flight - so the call was admitted and
    # is already running - and this call's own stamping is broken, so the stop it offers loses. Its
    # reason has to survive in its own call record and in the refusal the call fails with.
    planted_earlier = []
    held_stamping = bound.committed

    def plant_a_terminal_stop_and_break_stamping(sup):
        """The plant runs where `_follow` returns - the host has answered, nothing has been written,
        no lock of this supervisor's is held, and this call's own stop has not been decided yet. It
        has to be the LAST point before that decision, or the planted stop is not the earlier one."""
        inner = sup._follow

        def follow(*args, **kwargs):
            outcome = inner(*args, **kwargs)
            break_lock_mode(sup.run_dir)              # the planted stop is unstamped, and so terminal
            try:
                planted_earlier.append(sup._stop_run(
                    bound.excess("run-f19-defect-behind-a-stop-S3-earlier-a1", 136_000, clock[0])))
            finally:
                mend_lock(sup.run_dir)
            bound.committed = None                    # not callable: a defect in THIS call's stamping
            return outcome

        sup._follow = follow

    f19d, sup_d, rd, reported_d = overrun_under(
        "defect-behind-a-stop", adjust=plant_a_terminal_stop_and_break_stamping,
        restore=lambda _directory: setattr(bound, "committed", held_stamping))
    recorded_d = json.loads((f19d / "calls" / rd["call_id"] / "call.json").read_text(encoding="utf-8"))
    earlier_id = (planted_earlier[0] if planted_earlier else {}).get("call_id")
    control("HA#1-the-losing-call-s-record-carries-its-own-stamping-defect",
            "stop-internal-error" in ((recorded_d.get("stop") or {}).get("stamp") or "")
            and (recorded_d.get("stop") or {}).get("kept") is False, f"{recorded_d.get('stop')}")
    control("HA#1-the-earlier-terminal-stop-is-still-the-one-the-ledger-keeps",
            earlier_id is not None and ledger_stop(f19d).get("call_id") == earlier_id
            and earlier_id != rd["call_id"], f"{ledger_stop(f19d)} {earlier_id}")
    control("HA#1-and-the-refusal-carries-that-defect-beside-the-earlier-stop",
            "stop-internal-error" in (reported_d or "")
            and "an earlier stop stands in the run ledger" in (reported_d or ""), f"{reported_d}")

    # HB#0: and the stop decision is the FIRST thing settlement does after the process ends. Each case
    # below breaks ONE statement that used to run before it - the result write, the reconciliation, the
    # seat projection, the usage write, and a row that used to abort the reading itself - over a replayed
    # call whose complete row is already 135796 tokens. Every one asks the same two questions: is the
    # overrun in the ledger, and is the next dispatch refused. The fixtures are planted where `_follow`
    # returns, which is the moment the host has answered and nothing has been written yet.
    held_observed_seats = gate.observed_seats

    def after_follow(sup, then):
        inner = sup._follow

        def follow(*args, **kwargs):
            return then(inner(*args, **kwargs))

        sup._follow = follow

    def seal_the_call_directories(directory, mode):
        for entry in sorted((pathlib.Path(directory) / "calls").iterdir()):
            entry.chmod(mode)

    def corrupt_the_aggregate(sup):
        def then(outcome):                            # result.modelUsage is not a mapping: _usage raises
            status, stdout, stderr, mon, stopped, wall = outcome
            payload = json.loads(stdout.decode("utf-8"))
            payload["modelUsage"] = "not a mapping"
            return status, json.dumps(payload).encode("utf-8"), stderr, mon, stopped, wall

        after_follow(sup, then)

    def break_the_seat_projection(_sup):              # the host projection the usage record carries
        def raising(*_args, **_kwargs):
            raise RuntimeError("the seat projection failed")

        gate.observed_seats = raising

    def break_a_monitor_row(sup):
        def then(outcome):                            # a row whose output is not a number: _usage sums it
            rows = outcome[3].ledger.requests
            rows.append({**rows[0], "output": "not a number"})
            return outcome

        after_follow(sup, then)

    def plant_an_unreadable_row(sup):
        def then(outcome):                            # a row that is not a mapping at all
            outcome[3].ledger.requests.append(None)
            return outcome

        after_follow(sup, then)

    def break_the_usage_write(sup):
        inner = sup._usage

        def measured(*args, **kwargs):
            usage = inner(*args, **kwargs)            # computed, and then nothing can be written
            seal_the_call_directories(sup.run_dir, 0o500)
            return usage

        sup._usage = measured

    def break_the_first_post_process_write(sup):
        def then(outcome):                            # nothing has been written yet, and now nothing can
            seal_the_call_directories(sup.run_dir, 0o500)
            return outcome

        after_follow(sup, then)

    def unseal(directory):
        seal_the_call_directories(directory, 0o700)

    for label, adjust, restore_case, recorded in (
            ("aggregate-malformed", corrupt_the_aggregate, None, True),
            ("projection-failed", break_the_seat_projection,
             lambda _d: setattr(gate, "observed_seats", held_observed_seats), True),
            ("monitor-row-shape", break_a_monitor_row, None, True),
            ("row-unreadable", plant_an_unreadable_row, None, True),
            # the call directory goes read-only in the last two, so `recorded` says whether the call
            # record could be written at all: the usage case seals it AFTER the stop block has written
            # call.json, the first-write case before, which is the point of that case
            ("usage-unwritable", break_the_usage_write, unseal, True),
            ("first-write-unwritable", break_the_first_post_process_write, unseal, False)):
        hb, sup_hb, rhb, reported_hb = overrun_under(f"hb0-{label}", restore=restore_case, adjust=adjust)
        kept_hb = ledger_stop(hb)
        control(f"HB#0-{label}-the-observed-excess-is-in-the-ledger",
                kept_hb.get("code") == bound.STOP_CODE and kept_hb.get("observed") == 135_796
                and kept_hb.get("call_id") == rhb["call_id"], f"{kept_hb}")
        control(f"HB#0-{label}-the-next-dispatch-is-refused",
                (refusal(sup_hb.reserve, vstage, f"after-{label}", vseat, "authoring") or "")
                .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), f"a call was reserved after {label}")
        control(f"HB#0-{label}-the-call-itself-reported-the-failure", bool(reported_hb), f"{reported_hb}")
        if recorded:                                  # the call directory is still writable in this case
            saved = json.loads((hb / "calls" / rhb["call_id"] / "call.json").read_text(encoding="utf-8"))
            control(f"HB#0-{label}-and-the-call-record-carries-the-stop-it-offered",
                    (saved.get("stop") or {}).get("call_id") == rhb["call_id"]
                    and (saved.get("stop") or {}).get("observed") == 135_796, f"{saved.get('stop')}")

    # HC#0: nothing in the preparation can fail with an excess already observed - not the container the
    # rows arrive in, not a count too large for the interpreter to render, not the clock.
    def replace_rows(sup, make_rows, aggregate=None):
        inner = sup._follow

        def follow(*args, **kwargs):
            status, stdout, stderr, mon, stopped, wall = inner(*args, **kwargs)
            mon.ledger.requests[:] = make_rows(list(mon.ledger.requests))
            if aggregate is not None:
                payload = json.loads(stdout.decode("utf-8"))
                payload["modelUsage"] = aggregate
                stdout = json.dumps(payload).encode("utf-8")
            return status, stdout, stderr, mon, stopped, wall

        sup._follow = follow

    def unrenderable_count(sup):
        replace_rows(sup, lambda rows: [{**rows[0], "state": "measured", "input": 10 ** 4400,
                                         "cache_creation": 0, "cache_read": 0}])

    def break_the_clock(sup):
        """The clock fails the moment the host has answered - the call was launched on a working one,
        and the stop decision is the first thing that needs it afterwards."""
        inner = sup._follow

        def raising():
            raise RuntimeError("the run clock failed")

        def follow(*args, **kwargs):
            outcome = inner(*args, **kwargs)
            sup.clock = raising
            return outcome

        sup._follow = follow

    def restore_clock(_directory):
        pass                                          # the clock lives on the case's own supervisor

    f_big, sup_big, r_big, reported_big = overrun_under("hc0-unrenderable-count", adjust=unrenderable_count)
    kept_big = ledger_stop(f_big)
    control("HC#0-a-count-too-large-to-render-still-stops-the-run",
            kept_big.get("code") == bound.STOP_CODE and kept_big.get("call_id") == r_big["call_id"]
            and "observed-unrenderable" in (kept_big.get("stamp") or ""), f"{kept_big}")
    control("HC#0-and-the-next-dispatch-is-refused-after-it",
            (refusal(sup_big.reserve, vstage, "after-unrenderable", vseat, "authoring") or "")
            .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), "a call was reserved after an unrenderable count")

    f_clk, sup_clk, r_clk, reported_clk = overrun_under("hc0-clock-unavailable", adjust=break_the_clock,
                                                        restore=restore_clock)
    kept_clk = ledger_stop(f_clk)
    control("HC#0-a-clock-that-raises-does-not-block-the-stop",
            kept_clk.get("code") == bound.STOP_CODE and kept_clk.get("observed") == 135_796
            and "clock-unavailable" in (kept_clk.get("clock") or ""), f"{kept_clk}")
    control("HC#0-and-the-next-dispatch-is-refused-after-a-failed-clock",
            (refusal(sup_clk.reserve, vstage, "after-clock", vseat, "authoring") or "")
            .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), "a call was reserved after a failed clock")

    def rows_are_not_a_container(sup):
        inner = sup._follow

        def follow(*args, **kwargs):
            status, stdout, stderr, mon, stopped, wall = inner(*args, **kwargs)
            mon.ledger.requests = 7                   # not a sequence at all
            return status, stdout, stderr, mon, stopped, wall

        sup._follow = follow

    f_box, _sup_box, _r_box, reported_box = overrun_under("hc0-rows-not-a-container", adjust=rows_are_not_a_container)
    control("HC#0-a-rows-container-that-cannot-be-walked-is-reported-not-raised",
            bool(reported_box) and "observed_rows" not in (reported_box or "")
            and ledger_stop(f_box) == {}, f"{reported_box}")

    # HC#2: an excess that exists only AFTER reconciliation - one measured request of a token, one
    # pending compaction, and an aggregate that makes that compaction 135796 - is stopped at the second
    # call site, before the seat projection and before the usage record is written.
    def reconciled_into_an_excess(sup):
        def rows(existing):
            first = existing[0]
            return [{**first, "state": "measured", "role": "turn", "send_seen": True,
                     "input": 1, "output": 1, "cache_read": 0, "cache_creation": 0, "estimate": None},
                    {**first, "state": "provisional", "role": "compaction", "send_seen": True, "estimate": 1,
                     "input": None, "output": None, "cache_read": None, "cache_creation": None}]

        replace_rows(sup, rows, aggregate={"m": {"inputTokens": 135_797, "outputTokens": 2,
                                                 "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0}})

    def reconciled_then_projection_fails(sup):
        reconciled_into_an_excess(sup)
        break_the_seat_projection(sup)

    def reconciled_then_usage_unwritable(sup):
        reconciled_into_an_excess(sup)
        break_the_usage_write(sup)

    # the first of these is the one that ISOLATES the second decision site: settlement after it succeeds
    # from end to end, so no exception path can stand in for it, and with the site gone the call returns
    # the overrun unreported. The other two show the same stop standing when a later step does fail.
    for label, adjust, restore_case in (
            ("settles-cleanly", reconciled_into_an_excess, None),
            ("projection-failed", reconciled_then_projection_fails,
             lambda _d: setattr(gate, "observed_seats", held_observed_seats)),
            ("usage-unwritable", reconciled_then_usage_unwritable, unseal)):
        fr, sup_r, rr, reported_r = overrun_under(f"hc2-reconciled-{label}", adjust=adjust, restore=restore_case)
        kept_r = ledger_stop(fr)
        control(f"HC#2-an-excess-only-reconciliation-establishes-is-in-the-ledger-({label})",
                kept_r.get("code") == bound.STOP_CODE and kept_r.get("observed") == 135_796
                and kept_r.get("call_id") == rr["call_id"], f"{kept_r}")
        control(f"HC#2-the-next-dispatch-is-refused-({label})",
                (refusal(sup_r.reserve, vstage, f"after-reconciled-{label}", vseat, "authoring") or "")
                .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), f"a call was reserved after reconciled-{label}")
        control(f"HC#2-the-call-itself-reported-the-failure-({label})", bool(reported_r), f"{reported_r}")
        if label == "settles-cleanly":            # nothing else failed, so nothing else could have stopped it
            control("HC#2-a-clean-settlement-still-fails-by-name-on-the-reconciled-excess",
                    f"{bound.STOP_CODE} {rr['call_id']}" in (reported_r or ""), f"{reported_r}")
            saved_r = json.loads((fr / "calls" / rr["call_id"] / "call.json").read_text(encoding="utf-8"))
            control("HC#2-and-that-call-s-record-carries-the-stop-it-offered",
                    (saved_r.get("stop") or {}).get("observed") == 135_796
                    and (saved_r.get("stop") or {}).get("kept") is True, f"{saved_r.get('stop')}")

    # HC#3: and an exception out of `_follow` itself, with the rows already in the monitor, stops the
    # run on the way out - and the caller still gets the original failure.
    def fail_out_of_follow(sup):
        inner = sup._follow

        def follow(*args, **kwargs):
            inner(*args, **kwargs)                    # the monitor exists, its rows hold the overrun
            raise RuntimeError("the monitor could not be finished")

        sup._follow = follow

    f_exc, sup_exc, r_exc, reported_exc = overrun_under("hc3-follow-raised", adjust=fail_out_of_follow)
    kept_exc = ledger_stop(f_exc)
    control("HC#3-an-exception-out-of-the-follow-still-stops-the-run",
            kept_exc.get("code") == bound.STOP_CODE and kept_exc.get("observed") == 135_796
            and kept_exc.get("call_id") == r_exc["call_id"], f"{kept_exc}")
    control("HC#3-and-the-caller-gets-the-original-failure-unchanged",
            "RuntimeError" in (reported_exc or "") and "could not be finished" in (reported_exc or ""),
            f"{reported_exc}")
    control("HC#3-and-the-next-dispatch-is-refused",
            (refusal(sup_exc.reserve, vstage, "after-follow-raised", vseat, "authoring") or "")
            .startswith(f"RUN_STOPPED {bound.STOP_CODE}"), "a call was reserved after the follow raised")

    # HD#0: the ledger write succeeds and RELEASING the locks then fails. The call's own stop is
    # retained before that release, so the failure path finishes the diagnostic instead of offering
    # the same stop a second time.
    offers = []
    held_hold = stagelock.hold

    def break_lock_cleanup(sup):
        inner = sup._stop_run

        def counted_stop(entry, into=None):
            offers.append(entry.get("call_id"))
            return inner(entry, into=into)

        sup._stop_run = counted_stop

        @contextlib.contextmanager
        def failing(run_dir_path, name, *args, **kwargs):
            with held_hold(run_dir_path, name, *args, **kwargs):
                yield
            if name == "declaration":             # the descriptor is gone by the time it is closed
                raise OSError(9, "bad file descriptor on release")

        stagelock.hold = failing

    f_cln, sup_cln, r_cln, reported_cln = overrun_under(
        "hd0-lock-cleanup-failed", adjust=break_lock_cleanup,
        restore=lambda _d: setattr(stagelock, "hold", held_hold))
    kept_cln = ledger_stop(f_cln)
    control("HD#0-a-lock-cleanup-failure-after-the-write-leaves-the-excess-in-the-ledger",
            kept_cln.get("code") == bound.STOP_CODE and kept_cln.get("observed") == 135_796
            and kept_cln.get("call_id") == r_cln["call_id"], f"{kept_cln}")
    control("HD#0-and-the-stop-is-offered-once-not-once-per-failure",
            offers == [r_cln["call_id"]], f"{offers}")
    control("HD#0-and-the-call-record-still-carries-the-diagnostic",
            (json.loads((f_cln / "calls" / r_cln["call_id"] / "call.json").read_text(encoding="utf-8"))
             .get("stop") or {}).get("observed") == 135_796,
            f"{json.loads((f_cln / 'calls' / r_cln['call_id'] / 'call.json').read_text(encoding='utf-8')).get('stop')}")

    # HD#1: and the snapshot the decision reads from is judged directly, not through a case whose
    # failure another guard would also explain
    class _Rows:                                  # a monitor shape the snapshot must survive
        class _Ledger:
            def __init__(self, requests):
                self.requests = requests

        def __init__(self, requests):
            self.lock, self.ledger = threading.Lock(), self._Ledger(requests)

    def snapshot(rows_held):
        """What the snapshot answered, or what it RAISED - a helper that must not raise is judged by a
        control that can say it did, rather than ending the suite with it (BD#4)."""
        try:
            return globals()[CONTRACT["predicate"]]._rows_snapshot(rows_held)
        except Exception as exc:                  # noqa: BLE001 - the raise IS the finding
            return f"raised: {exc!r}"

    control("HD#1-the-rows-snapshot-answers-a-list-whatever-the-monitor-holds",
            (snapshot(_Rows(7)), snapshot(_Rows(None)), snapshot(None),
             snapshot(_Rows([{"state": "measured"}]))) == ([], [], [], [{"state": "measured"}]),
            f"{(snapshot(_Rows(7)), snapshot(_Rows(None)), snapshot(None))}")
    held_rows = [{"state": "measured"}]
    control("HD#1-and-it-copies-the-rows-rather-than-handing-the-monitor-s-own-list",
            snapshot(_Rows(held_rows)) == held_rows and snapshot(_Rows(held_rows)) is not held_rows,
            "the snapshot is the live list, or is not the rows at all")

    # and the reading the decision rests on cannot raise, whatever shape the rows are in
    complete_row = {"state": "measured", "input": 135_796, "cache_creation": 0, "cache_read": 0}
    control("HB#0-a-complete-row-establishes-its-excess-beside-rows-that-cannot-be-read",
            bound.observed_rows([None, "not a row", {"state": "measured"}, complete_row])
            == (135_796, [bound.ROW_UNREADABLE, "input_tokens", "cache_creation_input_tokens",
                          "cache_read_input_tokens"]),
            f"{bound.observed_rows([None, 'not a row', {'state': 'measured'}, complete_row])}")
    control("HC#1-a-partial-row-s-valid-components-are-the-lower-bound-the-boundary-decides-on",
            bound.observed_rows([{"state": "measured", "input": 135_796, "cache_read": 0}])
            == (135_796, ["cache_creation_input_tokens"]),
            f"{bound.observed_rows([{'state': 'measured', 'input': 135_796, 'cache_read': 0}])}")
    control("HB#0-the-extraction-raises-on-nothing-it-is-given",
            all(bound.observed_rows(rows) is not None
                for rows in (None, [], [None], [{"state": "sent"}], [{"state": "measured", "input": "x"}])),
            "the extraction raised on a row shape")

    # ---- the seam: the bound has ONE owner, and the dispatcher is its boundary (seam record 2026-10-22)
    #
    # M1. The rule used to exist twice - this module admitted against its own copy while views.py cut
    # windows against another. These two controls are what keeps that from coming back: the module must
    # reach the owner, and the owner's answer must be the one the boundary gives.
    seam_source = pathlib.Path(__file__).read_text(encoding="utf-8")

    def delegated(src):
        """Every `bound.<name>` the SUPERVISOR CLASS calls - production call sites, from the AST.

        Read from the class rather than from the file, because the self-test below calls the rule
        directly: a text scan of this module is satisfied by its own controls (BA#3)."""
        cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == CONTRACT["predicate"])
        return {node.func.attr for node in ast.walk(cls)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "bound"}

    owed = {"check_bound", "admitted_parts", "check_observed", "excess", "committed", "blocked", "limits",
            "strongest"}
    control("the-bound-helpers-have-a-caller-in-the-supervisor", delegated(seam_source) >= owed,
            f"the Supervisor delegates none of {sorted(owed - delegated(seam_source))} to the rule's owner")
    for gone in sorted(owed):
        without = re.sub(rf"bound\.{gone}\(", f"_inlined_{gone}(", seam_source)
        control(f"removing-the-delegation-of-{gone}-is-detected",
                without != seam_source and not (delegated(without) >= owed),
                f"the ownership check still passes with bound.{gone} inlined")
    control("the-bound-is-not-spelled-twice-here",
            not re.search(r"^\s*INPUT_BOUND\s*=", seam_source, re.M)
            and f"{bound.INPUT_BOUND:_}" not in seam_source.replace("bound.INPUT_BOUND:_", ""),
            "this module carries a second copy of the bound")
    seam_limits = bound.limits(4000, seat=astra, capacity=200_000, reservation=32_000)
    seam_rows = [(bound.INPUT_BOUND - 4000 - 1, False), (bound.INPUT_BOUND - 4000, False),
                 (bound.INPUT_BOUND - 4000 + 1, True)]
    control("the-boundary-and-the-rule-agree-at-the-exact-bound",
            [(n, bool(bound.check_bound(n, seam_limits))) for n, _ in seam_rows] == seam_rows,
            f"{[(n, bool(bound.check_bound(n, seam_limits))) for n, _ in seam_rows]}")

    # M5. The driver's part is what the call SENDS. The planted parts are non-zero on purpose: an equality
    # between two empty counts proves nothing, and today's hermetic profile declares no instructions at all.
    seam_packet = packets.build("r1/S3/t1/0a", "S3", astra, "a window of blocks\n" * 20, None)
    seam_schema = b'{"type":"object"}'
    seam_manifest = {"instructions": [{"path": str(scratch / "planted-instruction.md")}],
                     "appended_prompts": [{"text": "an appended system prompt"}],
                     "skills": [{"bytes": 50_000}], "workdir_files": [{"bytes": 50_000}]}
    (scratch / "planted-instruction.md").write_text("I" * 3000, encoding="utf-8")
    seam_plain = bound.driver_bytes(seam_packet, seam_schema)[0]
    seam_carried, seam_uncounted = bound.driver_bytes(seam_packet, seam_schema, seam_manifest)
    control("the-driver-payload-counts-the-instructions-and-prompts-the-call-carries",
            (seam_carried - seam_plain, seam_uncounted) == (3000 + len("an appended system prompt"), []),
            f"{seam_carried - seam_plain} {seam_uncounted}")
    control("the-planted-driver-parts-are-not-zero-bytes", 3000 + len("an appended system prompt") > 0, "planted nothing")
    control("the-host-s-own-context-is-not-charged-to-the-driver",
            bound.driver_bytes(seam_packet, seam_schema,
                               {k: v for k, v in seam_manifest.items() if k in ("skills", "workdir_files")})[0]
            == seam_plain, "a builtin part was counted on the driver's side")
    sd = run_dir("run-seam-count", {vstage: 2_000_000})
    ss = supervisor(sd)
    rs = ss.reserve(vstage, "count", vseat, "judge", tranche="calibration")
    fat = {"instructions": [{"path": str(scratch / "fat-instruction.md")}]}
    (scratch / "fat-instruction.md").write_text("F" * (bound.INPUT_BOUND - claude_allowance), encoding="utf-8")
    small = packets.build(rs["call_id"], vstage, vseat, "x\n", None)
    got = refusal(ss.call, vstage, vseat, small, None, reservation=rs, caps=caps, view_window=True, max_output_tokens=32_000, manifest=fat)
    control("a-window-inside-the-bound-whose-declared-instructions-pass-it-is-refused",
            (got or "").startswith("WINDOW_OVER_BOUND") and "WINDOW_BOUND_EXCEEDED (a)" in (got or ""), f"{got}")
    rs2 = ss.reserve(vstage, "uncounted", vseat, "judge", tranche="calibration")
    got = refusal(ss.call, vstage, vseat, packets.build(rs2["call_id"], vstage, vseat, "x\n", None), None, reservation=rs2,
                  caps=caps, view_window=True, max_output_tokens=32_000,
                  manifest={"appended_prompts": [{"name": "no bytes, no text, no path"}]})
    control("a-declared-driver-part-that-cannot-be-counted-is-refused-not-read-as-zero",
            (got or "").startswith("DRIVER_PART_UNCOUNTED"), f"{got}")

    # M2. Check (d) existed on the view side alone, so a window that fits (a) and leaves no room for the
    # answer was dispatched. The clean case is the same call one byte under the capacity.
    narrow_seats = scratch / "seats-narrow-capacity.json"
    narrow_held = json.loads(measured_seats.read_text(encoding="utf-8"))
    narrow_held["seat_capacity"][vseat] = {**narrow_held["seat_capacity"][vseat], "context_capacity": 60_000}
    narrow_seats.write_text(json.dumps(narrow_held), encoding="utf-8")
    narrow = run_dir("run-seam-capacity", {vstage: 2_000_000, "S7b": 2_000_000}, allowance=4000)
    sn = supervisor(narrow, seats_path=narrow_seats)
    # (d) with a narrow declared capacity, and with the cap this call reserved. The window is the same in
    # both rows and the capacity is the same; the only thing that moves is the cap - which is the point of
    # the ruling of 2026-10-22: the reservation is what the call declared, not a constant.
    for cap, want in ((20_000, None), (40_000, "WINDOW_CAPACITY_EXCEEDED (d)")):
        rn = sn.reserve(vstage, f"cap-{cap}", vseat, "judge", tranche="calibration")
        base = len(packets.build(rn["call_id"], vstage, vseat, "", None))
        got = refusal(sn.call, vstage, vseat,
                      packets.build(rn["call_id"], vstage, vseat, "d" * max(20_000 - base, 1), None), None,
                      reservation=rn, caps=caps, view_window=True, max_output_tokens=cap)
        if want is None:
            control("a-window-with-a-cap-that-leaves-room-for-the-answer-is-admitted", got is None, f"{got}")
        else:
            control("the-same-window-with-a-cap-that-leaves-none-is-refused",
                    (got or "").startswith("WINDOW_OVER_BOUND") and want in (got or ""), f"{got}")
    # ... and a view-window call that declares no cap at all is refused before admission, on any host
    rn = sn.reserve("S7b", "no-cap", astra, "judge", tranche="calibration")
    got = refusal(sn.call, "S7b", astra, packets.build(rn["call_id"], "S7b", astra, "x\n", None), None,
                  reservation=rn, caps=caps, view_window=True)
    control("a-view-window-call-without-a-declared-output-cap-is-refused-on-any-host",
            (got or "").startswith("CAP_UNDECLARED"), f"{got}")

    # contract fidelity: the Supervisor's refusals and item outcomes, read from the source, equal
    # this copy, made once and cited; the module docstring's list is held to the same set
    design = {
        # plan WP-02, dispatch.call's interface
        "RESERVATION_MISSING", "CAP_MISSING", "PROVIDER_DEFERRED", "PACKET_REFUSED",
        # BB#1-BB#4: what a declared part may not be, and what an adapter cannot carry
        "DRIVER_PART_LENGTH_CONFLICT", "APPENDED_PROMPT_PATH_FORM", "APPENDED_PROMPT_UNDELIVERABLE",
        "CAP_UNDELIVERABLE",
        # design §13.2: a reservation that cannot fit records the remaining work not done; plan WP-02, S-15
        "BUDGET_EXHAUSTED", "CALIBRATION_PROVISIONAL",
        # the amendment record 2026-10-21T0026--cc0498f--input-bound-amendment.md: the window bound, the run stop
        "INPUT_BOUND_EXCEEDED", "RUN_STOPPED", "ALLOWANCE_UNMEASURED", "ALLOWANCE_MISMATCH", "WINDOW_OVER_BOUND",
        "DRIVER_PART_UNCOUNTED", "USAGE_INCOMPLETE", "CAPACITY_UNDECLARED",
        # the implementation's own, each closing a gap the contract leaves open: S-15's concurrency one, a stage
        # with no declared budget, a call directory never overwritten, usage before the cell goes (§13.3), the
        # receipt (§3.2), the seat table (§4), the realization boundary (plan conventions)
        "CALIBRATION_SERIAL", "BUDGET_UNDECLARED", "CALL_EXISTS", "USAGE_UNCAPTURED", "RECEIPT_MISSING", "SEAT_UNPINNED",
        "RUNNER_REALIZATION_MISMATCH",
        # plan WP-03's adapter interface: the producing profile is Claude's and reads one declared directory;
        # every Claude call carries its stage's output-token cap (lead decision, WP-02 review round 9)
        "USE_REFUSED", "CAP_UNDECLARED"}
    # design §3.2 (accepted, failed with every attempt kept) and §13.2 (deferred, not done, budget_stopped)
    outcomes = {"accepted", "failed", "deferred", "not_done", "budget_stopped"}
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    listed = set(re.findall(r"\b[A-Z][A-Z_]{4,}\b", __doc__.split("Refused by name:", 1)[1].split("CONTRACT names", 1)[0]))
    control("contract-cites-its-sections", CONTRACT["$comment"].startswith("design §13.2"), CONTRACT["$comment"])
    # The bound's stop is raised through the record its owner writes (`bound.excess`), so the leading word
    # of that message is not a literal here and `contract_branches` cannot see it - it reads literals. The
    # scan is told where the code comes from, and told to lose it the moment that raise goes.
    # the token is assembled rather than written, so this control's own source does not contain the thing it
    # looks for - a scan that matches itself can never go quiet
    raise_site = "Refused(stop_detail" + "(excess))"
    # the same for a declared part's refusal: the dispatcher computes the code from the problem the rule
    # reports, so the inventory reads the rule's own PART_CODES and loses them when that raise goes
    parts_site = 'Refused(f"{problems[0].' + 'split()[0]} {call_id}: "'

    def raised_codes(src):
        return (contract_branches(src)[0] | ({bound.STOP_CODE} if raise_site in src else set())
                | (set(bound.PART_CODES) if parts_site in src else set()))

    control("supervisor-refusals-are-the-cited-set", raised_codes(source) == design, f"{raised_codes(source) ^ design}")
    control("the-bound-stop-is-raised-where-the-rule-says-it-is",
            "self._stop_run(bound.excess(" in source and raise_site in source,
            "the dispatcher does not stop the run on the rule's own excess record")
    # the call record is written twice - once inside the launch, once in settlement - so this reads the
    # settlement tail alone, from where the excess is established to the end of `call`
    # HC#5: the boundary is STRUCTURAL, not a list of strings somebody remembered to add. Between the
    # `_follow` call and the first offer, in the AST of `call`, there may be nothing at all - which is
    # the only form of the property that survives the next statement somebody writes there.
    def boundary_gap(src):
        """The statements between the follow call and the first stop offer, or None if unreadable."""
        try:
            tree = ast.parse(src)
            cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == CONTRACT["predicate"])
            fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "call")
        except Exception:                             # noqa: BLE001 - an unreadable subject fails by name
            return None
        for parent in ast.walk(fn):
            body = getattr(parent, "body", None)
            if not isinstance(body, list):
                continue
            follows = [i for i, st in enumerate(body) if "self._follow(" in ast.unparse(st)]
            offers = [i for i, st in enumerate(body) if "self._offer_stop(" in ast.unparse(st)]
            if follows and offers and offers[0] > follows[0]:
                return [ast.unparse(st).splitlines()[0] for st in body[follows[0] + 1:offers[0]]]
        return None
    control("nothing-stands-between-the-end-of-the-process-and-the-stop-decision",
            boundary_gap(source) == [], f"{boundary_gap(source)}")
    planted_before = source.replace("            excess = self._offer_stop(call, call_dir, self._rows_snapshot(mon)",
                                    "            self.clock()\n            excess = self._offer_stop(call, call_dir, "
                                    "self._rows_snapshot(mon)", 1)
    control("control-an-unrelated-statement-before-the-stop-decision-is-detected",
            planted_before != source and boundary_gap(planted_before) == ["self.clock()"],
            f"{boundary_gap(planted_before)}")
    control("control-the-boundary-is-unreadable-when-the-subject-is-gone",
            boundary_gap(source.replace("def call(", "def renamed_call(", 1)) is None, "the boundary read a subject that is not there")
    # and the old-order regression: the offer must still precede every statement settlement makes
    settlement_from = source.find("        monitor_held = {}")
    settlement_to = source.find("    def _stopped(")
    settlement = source[settlement_from:settlement_to] if 0 <= settlement_from < settlement_to else ""
    persisted = settlement.find("self._offer_stop(")
    later = [settlement.find(site) for site in (
        '(call_dir / "result.json").write_bytes(stdout)',
        "result = gate.Call(call_dir).result",
        "reconciled = self._reconcile(",
        'records.write_json(self.run_dir, call_dir / "usage.json", usage)',
        "self._delete_cell(cell, call_dir)",
        "self.breaker.observe(host, signals, self.clock())",
        "self._receipt(call_dir, stage, call_id, seat, exit_status)",
        "self.charge(stage, call_id, usages.totals(usage), outcome, caps)")]
    control("the-stop-is-persisted-before-every-statement-settlement-makes-after-the-process-ends",
            bool(settlement) and persisted >= 0 and all(site >= 0 for site in later) and persisted < min(later),
            f"settlement work that can fail runs before the stop is written (F-19/HB#0): {persisted} {later}")
    control("module-docstring-lists-the-same-refusals", listed == design, f"{listed ^ design}")
    control("item-outcomes-are-the-cited-set", contract_branches(source)[1] == outcomes, f"{contract_branches(source)[1]}")
    anchor = '                    raise Refused(f"CALL_EXISTS {call_dir}")\n'
    added = source.replace(anchor, anchor + '                    raise Refused(f"PLANTED_REFUSAL {call_dir}")\n', 1)
    removed = source.replace('raise Refused(f"CAP_MISSING', 'raise ValueError(f"CAP_MISSING', 1)
    control("an-added-refusal-is-detected", added != source and raised_codes(added) - design == {"PLANTED_REFUSAL"},
            f"{contract_branches(added)[0] - design}")
    dropped = source.replace("raise " + raise_site, "pass", 1)
    control("a-removed-bound-stop-is-detected", dropped != source and bound.STOP_CODE not in raised_codes(dropped),
            "the scan still reports the bound stop after its raise is gone")
    control("a-removed-refusal-is-detected", removed != source and design - raised_codes(removed) == {"CAP_MISSING"},
            f"{design - raised_codes(removed)}")
    unparted = source.replace("raise " + parts_site, "pass  #", 1)
    control("a-removed-driver-part-refusal-is-detected",
            unparted != source and not (set(bound.PART_CODES) & raised_codes(unparted)),
            "the scan still reports the part refusals after their raise is gone")

    # ---- r4 R1: this runner's own `__main__` boundary, DRIVEN. It was a `try` inside the
    # `if __name__` block, so the claim that it publishes what the suite collected was read out of
    # the source in inventory's suite — satisfied by any handler of this file reaching the call.
    # `main_boundary` is that block as a function; the real handler runs here.
    boundary_published = []
    planted_row = ("a planted suite --self-test", ["a failure an abort must not swallow"])
    boundary.SELF_TEST_COLLECTED.append(planted_row)
    aborted_with = ""
    try:
        main_boundary(run=lambda: (_ for _ in ()).throw(RuntimeError("a planted abort")),
                      publish=boundary_published.append)
    except RuntimeError as exc:
        aborted_with = str(exc)
    finally:
        boundary.SELF_TEST_COLLECTED.remove(planted_row)
    control("the main boundary publishes what the suite collected before an abort leaves",
            "a planted suite --self-test [FAIL] a failure an abort must not swallow" in boundary_published
            and aborted_with == "a planted abort",
            f"{boundary_published} raised={aborted_with!r}")
    clean_published = []
    boundary.SELF_TEST_COLLECTED.append(planted_row)
    try:
        returned_code = main_boundary(run=lambda: 0, publish=clean_published.append)
    finally:
        boundary.SELF_TEST_COLLECTED.remove(planted_row)
    control("and a run that returns normally through it publishes nothing and keeps its code",
            clean_published == [] and returned_code == 0, f"{clean_published} code={returned_code}")

    reporting.append("the report begins here")
    boundary.SELF_TEST_COLLECTED.remove(("dispatch --self-test", failures))
    for failure in failures:
        print(f"dispatch --self-test [FAIL] {failure}")
    if failures:
        return 1
    print(f"dispatch --self-test: OK ({len(ran)} controls: " + ", ".join(ran) + ")")
    return 0


def main_boundary(run=None, publish=print):
    """This module's `__main__` boundary, as a FUNCTION so a control can drive it.

    It was a `try` inside the `if __name__` block, which no control can enter: the claim "every
    abort path of this package publishes what the suite collected" was read out of the SOURCE
    instead, and a check satisfied by any `except` handler in a file cannot see the handler that
    does not publish (r4 R1). Here the real handler runs."""
    try:
        return (run or self_test)()
    except BaseException:
        # What the suite had collected, before the abort leaves with its own non-zero exit.
        boundary.publish_collected(publish)
        raise


if __name__ == "__main__":
    if "--self-test" not in sys.argv[1:]:
        sys.exit("usage: dispatch.py --self-test")
    sys.exit(main_boundary())
