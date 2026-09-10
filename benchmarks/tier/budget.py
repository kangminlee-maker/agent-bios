"""The spawn-trigger experiment's budget ledger — the design's stop rule made durable
(design §Budget and stop rules: "a stage starts only if the remaining budget covers its
ceiling"; "any extension past R or $165 needs the owner"; build review round 1, F1).

Spend is never stored: it is re-derived from the records under the tier run root every
time it is asked, so no counter can drift from the artifacts. A run in flight is not
counted until its record exists, which is why the dispatch gate is asked before EVERY
dispatch and not once per stage. The groups and ceilings are the design's table."""
from __future__ import annotations

import contextlib
import fcntl
import json
import math
import os
import pathlib

TOTAL_CEILING = 165.0
# A dispatch is refused unless its bounded charge fits inside both remaining ceilings
# (round 2, F1): the reserve is the most a unit of that kind has been seen to cost, with
# room — a run at small M was projected under $2 and a card call measured $0.16.
RESERVE = {"run": 2.0, "call": 0.25}
ATTEMPTS = "attempts.jsonl"   # append-only, at the root: every dispatch opens a line, every end closes it
ACK_UNIT = "breaker-ack"      # the unit a person's acknowledgement is filed under (`<prefix>breaker-ack`)
LOCK = "budget.lock"          # held across check + cap + open: two runners never see the same remaining dollars (round 4, F2)
# The reserve is a bound, not an estimate, because every dispatch carries it to the host
# as `--max-budget-usd` (`cap_for`): the process stops itself at the cap (round 3, F7).
CEILINGS = {"A": 25.0, "B-discovery": 60.0, "B-sweep": 15.0, "B-same": 5.0,
            "B-conditional": 25.0, "C": 35.0}
ROOT_FILE = "experiment.json"


def ceilings(root: pathlib.Path | None) -> dict:
    """The group ceilings in force under `root`: the design's table, with every group the
    owner extended on `experiment.json` (`extend_ceiling`) at its extended figure. The
    total ceiling is not extended here — $165 is the owner's, and a group's extension
    fits inside it or the total refuses the dispatch."""
    out = dict(CEILINGS)
    p = pathlib.Path(root) / ROOT_FILE if root is not None else None
    if p is not None and p.is_file():
        try:
            ident = json.loads(p.read_text())
        except ValueError:
            return out
        import math
        for g, v in (ident.get("ceilings") or {}).items():
            if g in out and isinstance(v, (int, float)) and math.isfinite(float(v)):
                out[g] = float(v)
    return out


def extend_ceiling(root: pathlib.Path, group: str, usd: float, decision: str, why: str) -> dict:
    """The owner raises one group's ceiling: refused without a decision id and a reason,
    for a group outside the table, or for a figure not above the one in force. The row
    (group, from, to, decision, why, time) stays on `experiment.json`."""
    root = pathlib.Path(root)
    if group not in CEILINGS:
        raise BudgetError(f"no group {group!r} in the design's table")
    if not (decision or "").strip() or not (why or "").strip():
        raise BudgetError("a ceiling extension names its decision and its reason")
    with locked(root):
        p = root / ROOT_FILE
        if not p.is_file():
            raise BudgetError(f"{p} does not exist — the experiment root is created by the first Stage B declaration")
        ident = json.loads(p.read_text())
        now = ceilings(root)[group]
        import math
        if not math.isfinite(float(usd)) or float(usd) <= now:
            raise BudgetError(f"group {group} is at ${now:.2f}; an extension raises it to a finite figure")
        ident.setdefault("ceilings", {})[group] = float(usd)
        import time
        ident.setdefault("ceiling_decisions", []).append(
            {"group": group, "from": now, "to": float(usd), "decision": decision.strip(), "why": why.strip(),
             "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        p.write_text(json.dumps(ident, indent=1))
    return ident
# where each group's records live under the root, and which arm (for a stage) or pass
# (for the cards) belongs to it
STAGE_GROUPS = {"trigger-b": {"inline": "B-discovery", "delegated-workhorse": "B-discovery",
                              "delegated-sweep": "B-sweep", "delegated-same": "B-same"},
                "trigger-cell3": {"inline": "B-conditional", "delegated-workhorse": "B-conditional"},
                "trigger-cell7": {"inline": "B-conditional", "delegated-workhorse": "B-conditional"},
                "trigger-c": {"inline": "C", "delegated-workhorse": "C"}}
PASS_GROUPS = {"A": "A", "A1": "A", "A2": "A", "C": "C", "probe": "A"}
CARDS_DIR = "trigger-cards"


class BudgetError(RuntimeError):
    pass


def group_of_run(stage: str, arm: str) -> str:
    try:
        return STAGE_GROUPS[stage][arm]
    except KeyError:
        raise BudgetError(f"no budget group for stage {stage!r} arm {arm!r} — a run outside the design's table is not dispatched")


def group_of_pass(pass_name: str) -> str:
    try:
        return PASS_GROUPS[pass_name]
    except KeyError:
        raise BudgetError(f"no budget group for cards pass {pass_name!r}")


def task_cost(rec: dict) -> float | None:
    """What a run's task process spent, from the first figure the record carries: its
    cost to parity; else what its ledger shows (a run that never reached); else what the
    host's wrapper measured (a ledger that could not close — a cut transcript; fix review
    3, F1). None when the record carries none of them: an UNKNOWN cost is never read as
    zero (fix review 4, F5) — the attempt is closed at the reserve and the record is
    uncosted, which stops every dispatch until a person prices or parks it."""
    r = rec.get("result") or {}
    c = r.get("cost_to_parity")
    if c is None:
        c = ((r.get("ledger") or {}).get("usd")) if isinstance(r.get("ledger"), dict) else None
    if c is None:
        c = rec.get("measured_total_usd")
    # each source field is a figure on its own, before any aggregation: a negative task
    # cost hidden under a positive priming charge, a boolean, or a numeric string is
    # unknown, never coerced (fix review 6, F5)
    return _figure(c)


def _figure(x) -> float | None:
    """A monetary field as read from a record: a finite, non-negative number, or None."""
    if x is None or isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x) if math.isfinite(float(x)) and float(x) >= 0 else None


def priming_cost(rec: dict) -> float | None:
    """What a run's priming processes spent — excluded from the experiment's estimand by
    design, never from the money (round 4, F1). None when any priming process carries no
    finite charge: an unknown part makes the whole unknown (fix review 5, F5)."""
    total = 0.0
    for p_ in rec.get("priming") or []:
        c = _figure(p_.get("cost_usd")) if isinstance(p_, dict) else None
        if c is None:
            return None
        total += c
    return total


def run_cost(rec: dict) -> float | None:
    """What a run spent in all: task plus priming, or None while either is unknown."""
    c, pr = task_cost(rec), priming_cost(rec)
    return None if c is None or pr is None else c + pr


def close_run(root: pathlib.Path, attempt: str, rec: dict, status: str = "ok") -> dict:
    """Close a run's attempt at what its record shows; a record with an unknown task or
    priming cost closes at the reserve plus whatever part IS known, basis `reserve` (fix
    review 4 F5, fix review 5 F5) — bounded, never a guess of zero."""
    c, pr = task_cost(rec), priming_cost(rec)
    if c is None or pr is None:
        return close_attempt(root, attempt, None, status, priming=(pr or 0.0) + (c or 0.0))
    return close_attempt(root, attempt, c + pr, status)


def open_attempt(root: pathlib.Path, group: str, kind: str, ref: str, pid: int | None = None) -> str:
    """Append the opening line of an attempt before its dispatch; returns the attempt id.
    `ref` is stage-qualified (`trigger-b/M1-b1-inline`, `A1/abcd1234/c01-r1`), and the
    record the attempt produces carries the id back, so a retry at the same path never
    erases an earlier charge (round 3, F6). The line names the dispatching pid: while that
    process lives the attempt is in flight and reserved; once it is dead and still open,
    the attempt is stale and stops every dispatch until a person closes it (round 2 F2,
    round 3 F12)."""
    if group not in CEILINGS or kind not in RESERVE:
        raise BudgetError(f"attempt outside the table: group {group!r} kind {kind!r}")
    if "/" not in ref:
        raise BudgetError(f"attempt ref {ref!r} is not stage-qualified (<stage or pass>/<unit>)")
    root = pathlib.Path(root); root.mkdir(parents=True, exist_ok=True)
    import secrets, time
    aid = secrets.token_hex(6)
    with open(root / ATTEMPTS, "a") as fh:
        fh.write(json.dumps({"attempt": aid, "open": True, "group": group, "kind": kind, "ref": ref,
                             "pid": int(pid if pid is not None else os.getpid()),
                             "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}) + "\n")
    return aid


def _alive(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (TypeError, ValueError, OSError):
        return False


def _money(x, what: str) -> float:
    """A charge is a finite, non-negative figure — NaN or a negative one would silently
    disable both ceiling comparisons (fix review 4, F7)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise BudgetError(f"{what} {x!r} is not a figure")
    if isinstance(x, bool) or not math.isfinite(v) or v < 0:
        raise BudgetError(f"{what} {x!r} is not a finite, non-negative figure")
    return v


def close_attempt(root: pathlib.Path, attempt: str, cost_usd: float | None, status: str,
                  priming: float = 0.0) -> dict:
    """Append the closing line: the attempt's cost when known, else the reserve for its
    kind plus whatever priming is known, charged as a bounded cost with its basis named.
    Check and append happen under the root lock, so two closers cannot both find the
    attempt open (fix review 4, F8)."""
    root = pathlib.Path(root)
    cost = None if cost_usd is None else _money(cost_usd, "a close's charge")
    prime = _money(priming, "a close's priming charge")
    if status.startswith("corrected"):
        raise BudgetError("a correction is written by `correct`, never as a close")
    with locked(root):
        rows = attempts(root)
        opened = [a for a in rows if a["attempt"] == attempt and a.get("open")]
        if not opened:
            raise BudgetError(f"attempt {attempt} was never opened at {root}")
        if any(a["attempt"] == attempt and not a.get("open") for a in rows):
            # an attempt has exactly one terminal row; a second would let the breaker read a
            # success it never had, or a failure twice (fix review 2, F3)
            raise BudgetError(f"attempt {attempt} is already closed at {root} — a correction is `correct`, with its reason")
        kind = opened[0]["kind"]
        line = {"attempt": attempt, "open": False, "status": status,
                "cost_usd": cost if cost is not None else RESERVE[kind] + prime,
                "cost_basis": "measured" if cost is not None else "reserve"}
        import time
        line["at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with open(root / ATTEMPTS, "a") as fh:
            fh.write(json.dumps(line) + "\n")
    return line


def correct_attempt(root: pathlib.Path, attempt: str, cost_usd: float, why: str) -> dict:
    """A person raises a closed attempt's charge to a figure the artifacts show (fix
    review 3, F1: an unpriced run's wrapper charge was left out of its close). Refused
    without a reason, for an open or unknown attempt, or for a figure that is not a raise;
    the row's status is `corrected: <why>` and the breaker ignores it."""
    root = pathlib.Path(root)
    if not (why or "").strip():
        raise BudgetError("a correction names its reason")
    cost_usd = _money(cost_usd, "a correction")
    with locked(root):
        st = attempt_state(root).get(attempt)
        if not st or not st.get("open"):
            raise BudgetError(f"attempt {attempt} was never opened at {root}")
        if st.get("close") is None:
            raise BudgetError(f"attempt {attempt} is still open — close it, do not correct it")
        now = charge_of(st)
        if float(cost_usd) <= now:
            raise BudgetError(f"attempt {attempt} is charged ${now:.4f}; a correction raises it")
        import time
        line = {"attempt": attempt, "open": False, "status": f"corrected: {why.strip()}", "cost_usd": float(cost_usd),
                "cost_basis": "measured", "corrected_from": now, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        with open(root / ATTEMPTS, "a") as fh:
            fh.write(json.dumps(line) + "\n")
    return line


def attempts(root: pathlib.Path) -> list[dict]:
    p = pathlib.Path(root) / ATTEMPTS
    if not p.is_file():
        return []
    out = []
    terminal = {}   # attempt id -> the line of its one terminal row
    for i, raw in enumerate(p.read_text().splitlines(), 1):
        if not raw.strip():
            continue
        try:
            a = json.loads(raw)
        except ValueError:
            raise BudgetError(f"{p}:{i} is not a JSON line — the attempts ledger is unreadable, and an unreadable ledger stops every dispatch")
        if not isinstance(a, dict) or not a.get("attempt"):
            raise BudgetError(f"{p}:{i} names no attempt — the attempts ledger is unreadable, and an unreadable ledger stops every dispatch")
        if a.get("cost_usd") is not None:
            try:
                _money(a["cost_usd"], f"{p}:{i} charge")
            except BudgetError as exc:
                raise BudgetError(f"{exc} — the attempts ledger is unreadable, and an unreadable ledger stops every dispatch")
        if not a.get("open") and not str(a.get("status") or "").startswith("corrected: "):
            # an attempt has exactly one terminal row (fix review 4, F8): a second one
            # planted by hand or by a race would let the breaker read a success it never
            # had, so the ledger refuses to be read at all
            if a["attempt"] in terminal:
                raise BudgetError(f"{p}:{i} is a second terminal row for attempt {a['attempt']} (the first is line "
                                  f"{terminal[a['attempt']]}) — the attempts ledger is unreadable, and an unreadable ledger stops every dispatch")
            terminal[a["attempt"]] = i
        out.append(a)
    return out


def attempt_state(root: pathlib.Path) -> dict:
    """Per attempt: its opening line, its one closing line when present, and every
    correction a person wrote afterwards (`corrected: <why>` rows, in ledger order)."""
    st = {}
    for a in attempts(root):
        aid = a["attempt"]
        entry = st.setdefault(aid, {"open": None, "close": None, "corrections": []})
        if a.get("open"):
            entry["open"] = a
        elif str(a.get("status") or "").startswith("corrected: "):
            entry["corrections"].append(a)
        else:
            entry["close"] = a
    return st


def charge_of(st: dict) -> float:
    """The charge an attempt's ledger rows put on it: its close, raised by any
    correction (a correction only ever raises — `correct_attempt`)."""
    cl = st.get("close") or {}
    figures = [float(cl.get("cost_usd") or 0.0)] + [float(c.get("cost_usd") or 0.0) for c in st.get("corrections") or []]
    return max(figures)


def spend(root: pathlib.Path) -> dict:
    """Dollars spent per group, re-derived from every record under the root, plus the
    attempts ledger: a closed attempt whose ref has no costed record is charged at its
    closing line (measured, or the reserve); open attempts and uncosted records are
    listed — and either one refuses the next dispatch."""
    root = pathlib.Path(root)
    out = {g: 0.0 for g in CEILINGS}
    ceil = ceilings(root)
    uncosted = []
    record_cost = {}   # attempt id -> the measured cost its own record carries
    for stage, arms in STAGE_GROUPS.items():
        for rec_path in sorted((root / stage / "runs").glob("*/record.json")) if (root / stage / "runs").is_dir() else []:
            try:
                rec = json.loads(rec_path.read_text())
            except (OSError, ValueError):
                uncosted.append(str(rec_path)); continue
            arm = rec.get("arm")
            if arm not in arms:
                continue
            try:
                c = run_cost(rec)
            except (TypeError, ValueError):
                c = None
            if c is None or isinstance(c, bool) or not math.isfinite(float(c)) or float(c) <= 0:
                # unknown, NaN, negative or zero: none is a spend that can be read (fix
                # review 4 F5, fix review 5 F6)
                uncosted.append(str(rec_path))
                continue
            if rec.get("attempt"):
                record_cost[rec["attempt"]] = c
            out[arms[arm]] += c
    passes = root / CARDS_DIR / "passes"
    if passes.is_dir():
        for pass_dir in sorted(p for p in passes.iterdir() if p.is_dir()):
            g = PASS_GROUPS.get(pass_dir.name)
            if g is None:
                continue
            for rec_path in sorted(pass_dir.glob("*/*.json")):
                if rec_path.name in ("manifest.json", "score.json", "state.json"):
                    continue
                try:
                    rec = json.loads(rec_path.read_text())
                except (OSError, ValueError):
                    uncosted.append(str(rec_path)); continue
                c = rec.get("cost_usd")
                if c is None or isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(float(c)) or float(c) < 0:
                    uncosted.append(str(rec_path)); continue
                if rec.get("attempt"):
                    record_cost[rec["attempt"]] = float(c)
                out[g] += float(c)
    open_attempts, in_flight, reserve_charged, corrected = [], [], [], []
    for aid, st in attempt_state(root).items():
        op, cl = st["open"], st["close"]
        if op is None:
            uncosted.append(f"attempt {aid}: closed without an opening line")
            continue
        if cl is None:
            entry = {"attempt": aid, "group": op["group"], "kind": op["kind"], "ref": op["ref"], "at": op["at"], "pid": op.get("pid")}
            if op.get("pid") is not None and _alive(op["pid"]):
                # in flight: another runner's live dispatch — reserved, not stale
                out[op["group"]] += RESERVE[op["kind"]]
                in_flight.append(entry)
            else:
                open_attempts.append(entry)
            continue
        charge = charge_of(st)
        if aid in record_cost:
            # its own record carries the measured cost already; a person's correction
            # above that figure is charged on top, never dropped (fix review 4, F6)
            extra = charge - record_cost[aid]
            if extra > 1e-9:
                out[op["group"]] += extra
                corrected.append({"attempt": aid, "ref": op["ref"], "record_usd": record_cost[aid], "charged_usd": charge})
            continue
        out[op["group"]] += charge
        if st["corrections"]:
            corrected.append({"attempt": aid, "ref": op["ref"], "close_usd": float(cl.get("cost_usd") or 0.0), "charged_usd": charge})
        elif cl.get("cost_basis") == "reserve":
            reserve_charged.append({"attempt": aid, "ref": op["ref"], "usd": cl["cost_usd"]})
    return {"groups": {g: round(v, 6) for g, v in out.items()}, "total": round(sum(out.values()), 6), "ceilings": ceil,
            "uncosted": uncosted, "open_attempts": open_attempts, "in_flight": in_flight, "reserve_charged": reserve_charged,
            "corrected": corrected}


def can_start(root: pathlib.Path, group: str) -> tuple[bool, str]:
    """A stage (or pass) starts only if the remaining total budget covers what its
    group's ceiling still allows."""
    if group not in CEILINGS:
        return False, f"unknown budget group {group!r}"
    s = spend(root)
    ceil = ceilings(root)
    remaining_total = TOTAL_CEILING - s["total"]
    remaining_group = ceil[group] - s["groups"][group]
    if remaining_group <= 0:
        return False, f"group {group} has spent ${s['groups'][group]:.2f} of its ${ceil[group]:.0f} ceiling — nothing left to start"
    if remaining_total < remaining_group:
        return False, (f"remaining budget ${remaining_total:.2f} does not cover group {group}'s remaining ceiling "
                       f"${remaining_group:.2f} (total spent ${s['total']:.2f} of ${TOTAL_CEILING:.0f}) — the owner decides")
    return True, f"group {group}: ${s['groups'][group]:.2f} spent of ${ceil[group]:.0f}; total ${s['total']:.2f} of ${TOTAL_CEILING:.0f}"


def dispatch_allowed(root: pathlib.Path, group: str, kind: str = "run") -> tuple[bool, str]:
    """Asked before every dispatch: the unit's reserve must fit inside the group's and the
    total's remaining ceiling, no attempt may be open, and no record may be uncosted. A
    dispatch that could cross is not made (round 2, F1, F2)."""
    if group not in CEILINGS:
        return False, f"unknown budget group {group!r}"
    if kind not in RESERVE:
        return False, f"unknown dispatch kind {kind!r}"
    s = spend(root)
    if s["open_attempts"]:
        a = s["open_attempts"][0]
        return False, (f"stale attempt {a['attempt']} ({a['kind']} {a['ref']}, {a['at']}, pid {a.get('pid')} gone) has no closing line — "
                       f"its cost is unknown; a person closes it with `budget.py close` before anything else is dispatched")
    if s["uncosted"]:
        return False, f"uncosted record {s['uncosted'][0]} — a spend that cannot be read stops every dispatch"
    reserve = RESERVE[kind]
    ceil = ceilings(root)
    if s["groups"][group] + reserve > ceil[group] + 1e-9:
        return False, (f"ceiling: group {group} has spent ${s['groups'][group]:.2f} of ${ceil[group]:.0f}; "
                       f"a {kind} reserves ${reserve:.2f} and does not fit")
    if s["total"] + reserve > TOTAL_CEILING + 1e-9:
        return False, f"ceiling: total spent ${s['total']:.2f} of ${TOTAL_CEILING:.0f}; a {kind} reserves ${reserve:.2f} and does not fit"
    return True, f"group {group}: ${s['groups'][group]:.2f} of ${ceil[group]:.0f}; total ${s['total']:.2f}"


def trailing_failures(root: pathlib.Path, prefix: str) -> int:
    """How many of the latest closed attempts under `prefix` (a stage or pass name plus
    "/") failed in a row with no success after them — the breaker's streak, rebuilt from
    the ledger so a resume cannot reset it (round 3, F8)."""
    opened = {}
    closes = []   # in ledger order — the file's append order is the sequence, never a timestamp
    for a in attempts(pathlib.Path(root)):
        if a.get("open"):
            opened[a["attempt"]] = a
        elif a["attempt"] in opened and opened[a["attempt"]]["ref"].startswith(prefix):
            closes.append((a.get("status", ""), opened[a["attempt"]]["ref"]))
    n = 0
    for status, ref in reversed(closes):
        if status.startswith("corrected: "):
            continue
        if ref.endswith("/" + ACK_UNIT):
            # a person's acknowledgement clears the streak only as the row it writes;
            # any other close of that attempt (a crash closed by hand, a status of its
            # own) is neither a failure nor a success (fix review, F3)
            if status.startswith("acknowledged: "):
                break
            continue
        if status.startswith("failed"):
            n += 1
        else:
            break
    return n


def ack_streak(root: pathlib.Path, prefix: str, why: str) -> dict:
    """A person closes the breaker's streak on the ledger: one attempt under `prefix`,
    opened and closed at zero measured cost with the status `acknowledged: <why>`, so
    `trailing_failures` sees a non-failed close after the failures and a resume may
    dispatch again. Refused when there is no streak to close or no reason given — the
    row is the record of who decided the cause was gone (a host usage limit restored, a
    fixture repaired), and an empty reason records nothing. The resume itself is still
    the stage's own command; this touches no run and no record."""
    root = pathlib.Path(root)
    why = (why or "").strip()
    if not why:
        raise BudgetError("an acknowledgement names its reason")
    if "/" not in prefix:
        raise BudgetError(f"prefix {prefix!r} is not a stage or pass prefix (<stage or pass>/)")
    import secrets, time
    with locked(root):
        # the streak is read, judged, and closed under one lock: two acknowledgements
        # cannot both see the same tail (fix review, F4)
        n = trailing_failures(root, prefix)
        if n == 0:
            raise BudgetError(f"no failure streak under {prefix!r} to acknowledge")
        last = [a for a in attempts(root) if a.get("open") and a["ref"].startswith(prefix)][-1]
        aid = secrets.token_hex(6)
        at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        opening = {"attempt": aid, "open": True, "group": last["group"], "kind": last["kind"],
                   "ref": f"{prefix}{ACK_UNIT}", "pid": os.getpid(), "at": at}
        line = {"attempt": aid, "open": False, "status": f"acknowledged: {why}", "cost_usd": 0.0,
                "cost_basis": "measured", "at": at}
        # one write for both rows: an acknowledgement is never half on the ledger (F3)
        with open(root / ATTEMPTS, "a") as fh:
            fh.write(json.dumps(opening) + "\n" + json.dumps(line) + "\n")
    return {"attempt": aid, "streak_closed": n, "group": last["group"], **line}


@contextlib.contextmanager
def locked(root: pathlib.Path):
    """An exclusive lock on the root's ledger for the span of a check-and-reserve."""
    root = pathlib.Path(root); root.mkdir(parents=True, exist_ok=True)
    with open(root / LOCK, "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def reserve(root: pathlib.Path, group: str, kind: str, ref: str, prefix: str | None = None,
            max_failures: int | None = None) -> tuple[str | None, float, str]:
    """The one way to take a dispatch: under the root lock, ask `dispatch_allowed`, compute
    the cap, and open the attempt — so a parallel runner cannot read the same remaining
    dollars (round 4, F2). Returns (attempt id, cap, why); attempt None means refused."""
    with locked(root):
        if prefix is not None and max_failures is not None:
            # the breaker is judged under the same lock as the reservation: two dispatchers
            # cannot both pass a one-time entry check and then both reserve (fix review 4, F9)
            n = trailing_failures(root, prefix)
            if n >= max_failures:
                return None, 0.0, (f"breaker: {n} consecutive failed dispatches under {prefix!r} stand on the ledger — a person "
                                   f"closes the streak with its reason (`budget.py ack <root> {prefix} <why>`) once the cause is gone")
            if n >= 1:
                # a failure stands: until a success clears it, dispatches under the prefix
                # are serial, so a second runner cannot pass the breaker on a streak the
                # first is about to lengthen (fix review 5, F7)
                flying = [a for a in spend(root)["in_flight"] if str(a.get("ref", "")).startswith(prefix)]
                if flying:
                    return None, 0.0, (f"breaker: a failure stands under {prefix!r} and attempt {flying[0]['attempt']} "
                                       f"({flying[0]['ref']}) is in flight — the next dispatch waits for it")
        allowed, why = dispatch_allowed(root, group, kind)
        if not allowed:
            return None, 0.0, why
        cap = cap_for(root, group, kind)
        if cap <= 0:
            return None, 0.0, f"cap {cap} for a {kind} in {group}: nothing left to spend"
        return open_attempt(root, group, kind, ref), cap, why


def cap_for(root: pathlib.Path, group: str, kind: str) -> float:
    """The most this dispatch may spend, carried to the host as its own cap: the reserve,
    or less when a ceiling is nearer. Zero or negative means the dispatch is not made."""
    s = spend(root)
    return round(min(RESERVE[kind], ceilings(root)[group] - s["groups"][group], TOTAL_CEILING - s["total"]), 4)


def self_test() -> int:
    import tempfile, shutil
    ok, bad = [], []
    d = pathlib.Path(tempfile.mkdtemp(prefix="tier-budget-"))
    try:
        def run(stage, name, arm, cost):
            p = d / stage / "runs" / name
            p.mkdir(parents=True, exist_ok=True)
            (p / "record.json").write_text(json.dumps({"arm": arm, "result": {"cost_to_parity": cost}}))
        def card(pass_name, name, cost):
            p = d / CARDS_DIR / "passes" / pass_name / "abcd1234"
            p.mkdir(parents=True, exist_ok=True)
            (p / name).write_text(json.dumps({"cost_usd": cost}))
        s = spend(d)
        (ok if s["total"] == 0 and all(v == 0 for v in s["groups"].values()) else bad).append("empty root spends nothing")
        allowed, why = can_start(d, "B-discovery")
        (ok if allowed else bad).append(f"a fresh root can start B-discovery ({why[:40]})")
        run("trigger-b", "M1-b1-inline", "inline", 1.5); run("trigger-b", "M1-b1-delegated-sweep", "delegated-sweep", 0.5)
        run("trigger-b", "M1-b1-delegated-same", "delegated-same", 0.25); card("A", "c01-r1.json", 0.1)
        s = spend(d)
        (ok if s["groups"] == {"A": 0.1, "B-discovery": 1.5, "B-sweep": 0.5, "B-same": 0.25, "B-conditional": 0.0, "C": 0.0} and s["total"] == 2.35
         else bad).append(f"spend is re-derived per group from the records: {s['groups']}")
        # positive control: a group at its ceiling refuses the next dispatch, by name
        for i in range(20):
            run("trigger-b", f"M1-b{i+2}-delegated-same", "delegated-same", 0.25)
        allowed, why = dispatch_allowed(d, "B-same")
        (ok if not allowed and "ceiling: group B-same" in why else bad).append(f"a group at its ceiling refuses dispatch: {why[:60]}")
        # the reserve: a group $0.10 under its ceiling cannot take a $2 run, but can take a $0.25 call? — no: a call in B does not exist; use A
        card("A", "c02-r1.json", 24.80)
        allowed, why = dispatch_allowed(d, "A", "call")
        (ok if not allowed and "reserves $0.25" in why else bad).append(f"a call that could cross the ceiling is refused before it is made: {why[:70]}")
        allowed, why = dispatch_allowed(d, "A", "call") if False else (None, None)
        # attempts: an open line stops everything; a closed line without a record charges the reserve
        try:
            open_attempt(d, "B-discovery", "run", "M5-b2-inline"); bad.append("an unqualified ref was accepted")
        except BudgetError:
            ok.append("an attempt ref must be stage-qualified")
        aid = open_attempt(d, "B-discovery", "run", "trigger-b/M5-b2-inline", pid=999999)   # a pid that is not alive
        allowed, why = dispatch_allowed(d, "B-discovery")
        (ok if not allowed and "stale attempt" in why else bad).append(f"a stale open attempt (dead pid) refuses every dispatch: {why[:60]}")
        close_attempt(d, aid, None, "failed")
        s = spend(d)
        (ok if s["reserve_charged"] and s["reserve_charged"][0]["usd"] == RESERVE["run"] and not s["open_attempts"] else bad).append(
            "a failed attempt without a record is charged at the run reserve, named")
        # a retry at the same path: the earlier reserve charge stays, the new record counts against its own attempt only
        aid2 = open_attempt(d, "B-discovery", "run", "trigger-b/M5-b2-inline"); close_attempt(d, aid2, 0.7, "ok")
        p = d / "trigger-b" / "runs" / "M5-b2-inline"; p.mkdir(parents=True, exist_ok=True)
        (p / "record.json").write_text(json.dumps({"arm": "inline", "attempt": aid2, "result": {"cost_to_parity": 0.7}}))
        s2 = spend(d)
        (ok if abs(s2["groups"]["B-discovery"] - (s["groups"]["B-discovery"] + 0.7)) < 1e-9 and s2["reserve_charged"] else bad).append(
            "a retry's record counts once against its own attempt; the failed attempt's reserve charge stays")
        # a record that does not name its attempt leaves the closed attempt's charge standing (counted twice, on the side of caution)
        (p / "record.json").write_text(json.dumps({"arm": "inline", "result": {"cost_to_parity": 0.7}}))
        s3 = spend(d)
        (ok if abs(s3["groups"]["B-discovery"] - (s2["groups"]["B-discovery"] + 0.7)) < 1e-9 else bad).append(
            "a record without its attempt id does not cancel the attempt's charge")
        (p / "record.json").write_text(json.dumps({"arm": "inline", "attempt": aid2, "result": {"cost_to_parity": 0.7}}))
        # an in-flight attempt of a live process is reserved, not stale
        aid3 = open_attempt(d, "A", "call", "A/abcd/c01-r1")   # this process's pid: alive
        s4 = spend(d)
        allowed, why = dispatch_allowed(d, "B-discovery")
        (ok if allowed and s4["in_flight"] and abs(s4["groups"]["A"] - (s3["groups"]["A"] + RESERVE["call"])) < 1e-9 else bad).append(
            "a live process's open attempt is reserved into its group and stops nothing")
        close_attempt(d, aid3, 0.05, "ok")
        cap = cap_for(d, "B-discovery", "run")
        (ok if cap == RESERVE["run"] else bad).append(f"the cap is the reserve when the ceilings are far: {cap}")
        f1 = open_attempt(d, "B-sweep", "run", "trigger-b/M1-b1-delegated-sweep"); close_attempt(d, f1, None, "failed: RunError")
        f2 = open_attempt(d, "B-sweep", "run", "trigger-b/M1-b1-delegated-sweep"); close_attempt(d, f2, None, "failed: RunError")
        (ok if trailing_failures(d, "trigger-b/") == 2 else bad).append(f"two trailing failures rebuild a streak of 2 ({trailing_failures(d, 'trigger-b/')})")
        f3 = open_attempt(d, "B-sweep", "run", "trigger-b/M1-b2-delegated-sweep"); close_attempt(d, f3, 0.3, "ok")
        (ok if trailing_failures(d, "trigger-b/") == 0 else bad).append("a success clears the streak")
        (ok if trailing_failures(d, "A/") == 0 else bad).append("another prefix's failures do not count")
        g1 = open_attempt(d, "B-discovery", "run", "trigger-b/M5-b2-inline"); close_attempt(d, g1, None, "failed: RunError")
        g2 = open_attempt(d, "B-discovery", "run", "trigger-b/M5-b2-inline"); close_attempt(d, g2, None, "failed: RunError")
        try:
            ack_streak(d, "trigger-b/", ""); bad.append("an acknowledgement without a reason was written")
        except BudgetError:
            ok.append("an acknowledgement without a reason is refused")
        try:
            ack_streak(d, "A/", "nothing failed here"); bad.append("an acknowledgement of no streak was written")
        except BudgetError:
            ok.append("an acknowledgement is refused where no streak stands")
        before = spend(d)["total"]
        ackd = ack_streak(d, "trigger-b/", "host usage limit restored")
        (ok if trailing_failures(d, "trigger-b/") == 0 and ackd["streak_closed"] == 2 and ackd["group"] == "B-discovery"
         and ackd["status"] == "acknowledged: host usage limit restored" and ackd["cost_usd"] == 0.0 else bad).append(
            f"a person's acknowledgement closes the streak at zero cost with its reason on the row ({ackd})")
        (ok if abs(spend(d)["total"] - before) < 1e-9 else bad).append("an acknowledgement charges nothing")
        # a breaker-ack attempt closed any other way — by hand after a crash, or by a
        # status of its own — neither clears the streak nor counts as a failure (F3)
        h1 = open_attempt(d, "B-discovery", "run", "trigger-b/M5-b3-inline"); close_attempt(d, h1, None, "failed: RunError")
        h2 = open_attempt(d, "B-discovery", "run", "trigger-b/M5-b3-inline"); close_attempt(d, h2, None, "failed: RunError")
        half = open_attempt(d, "B-discovery", "run", f"trigger-b/{ACK_UNIT}"); close_attempt(d, half, None, "closed-by-hand")
        (ok if trailing_failures(d, "trigger-b/") == 2 else bad).append(
            f"a breaker-ack closed by hand clears nothing ({trailing_failures(d, 'trigger-b/')})")
        h3 = open_attempt(d, "B-discovery", "run", f"trigger-b/{ACK_UNIT}"); close_attempt(d, h3, None, "failed: raised")
        (ok if trailing_failures(d, "trigger-b/") == 2 else bad).append("a failed breaker-ack is not another failure")
        rows_before = len(attempts(d))
        ack_streak(d, "trigger-b/", "cause gone")
        (ok if trailing_failures(d, "trigger-b/") == 0 and len(attempts(d)) == rows_before + 2 else bad).append(
            "an acknowledgement is two rows written together and clears the streak")
        # a group's ceiling is the design's until the owner extends it on experiment.json
        (ok if ceilings(d) == CEILINGS else bad).append("without a declaration the ceilings are the design's table")
        (d / ROOT_FILE).write_text(json.dumps({"root_id": "r", "root": str(d.resolve())}))
        for args in (("B-discovery", 75.0, "", "why"), ("B-discovery", 75.0, "D-x", ""), ("B-discovery", 60.0, "D-x", "not a raise"), ("Z", 75.0, "D-x", "why")):
            try:
                extend_ceiling(d, *args); bad.append(f"a ceiling extension was accepted with {args}")
            except BudgetError:
                ok.append("a ceiling extension without decision, reason, a raise, or a table group is refused")
        extend_ceiling(d, "B-discovery", 75.0, "D-20260908-test", "priming was not in the projection")
        (ok if ceilings(d)["B-discovery"] == 75.0 and ceilings(d)["C"] == CEILINGS["C"] else bad).append("an extended group reads its new ceiling, the others the design's")
        (ok if json.loads((d / ROOT_FILE).read_text())["ceiling_decisions"][0]["from"] == 60.0 else bad).append("the extension's row keeps the figure it replaced")
        try:
            extend_ceiling(d, "B-discovery", float("nan"), "D-x", "why"); bad.append("a NaN ceiling was accepted")
        except BudgetError:
            ok.append("a ceiling extension to a non-finite figure is refused")
        idn = json.loads((d / ROOT_FILE).read_text()); idn["ceilings"]["C"] = float("nan"); (d / ROOT_FILE).write_text(json.dumps(idn))
        (ok if ceilings(d)["C"] == CEILINGS["C"] else bad).append("a non-finite figure on experiment.json is not a ceiling")
        # one terminal row per attempt; a correction raises a closed charge with its reason
        c1 = open_attempt(d, "B-discovery", "run", "trigger-b/M1-b6-delegated-workhorse"); close_attempt(d, c1, 0.55, "ok")
        try:
            close_attempt(d, c1, 0.6, "ok"); bad.append("a second terminal row was written")
        except BudgetError:
            ok.append("an attempt closes once")
        for args in ((c1, 0.9, ""), (c1, 0.5, "lower"), ("nope", 0.9, "why"), (c1, float("inf"), "why")):
            try:
                correct_attempt(d, *args); bad.append(f"a correction was accepted with {args}")
            except BudgetError:
                ok.append("a correction without a reason, not a raise, of an unknown attempt, or non-finite is refused")
        before_c = spend(d)["total"]
        correct_attempt(d, c1, 1.42, "the wrapper measured the task the ledger could not close")
        (ok if abs(spend(d)["total"] - before_c - 0.87) < 1e-9 else bad).append("a correction moves the spend by the raise")
        c2 = open_attempt(d, "B-discovery", "run", "trigger-b/M1-b7-inline"); close_attempt(d, c2, None, "failed: RunError")
        c3 = open_attempt(d, "B-discovery", "run", "trigger-b/M1-b7-inline"); close_attempt(d, c3, None, "failed: RunError")
        correct_attempt(d, c3, 2.5, "measured after the fact")
        (ok if trailing_failures(d, "trigger-b/") == 2 else bad).append("a correction is not a success: the streak stands")
        # a run whose ledger could not close is charged what the wrapper measured, plus priming
        rc = run_cost({"result": {"cost_to_parity": None, "ledger": {"usd": None}}, "measured_total_usd": 0.47, "priming": [{"cost_usd": 0.3}]})
        (ok if abs(rc - 0.77) < 1e-9 else bad).append(f"an unpriced run is charged its wrapper figure plus priming ({rc})")
        # --- fix review 4: F5 an unknown task cost is unknown ---------------------------------
        (ok if run_cost({"result": {"cost_to_parity": None}, "priming": [{"cost_usd": 0.3}]}) is None else bad).append(
            "a run with no task figure has an UNKNOWN cost, never zero plus priming (F5)")
        u1 = open_attempt(d, "B-discovery", "run", "trigger-b/M5-b7-inline")
        cl1 = close_run(d, u1, {"result": {"cost_to_parity": None}, "priming": [{"cost_usd": 0.3}]}, "ok")
        (ok if cl1["cost_basis"] == "reserve" and abs(cl1["cost_usd"] - (RESERVE["run"] + 0.3)) < 1e-9 else bad).append(
            f"an unknown task cost closes at the reserve plus the known priming, basis reserve ({cl1['cost_usd']}, {cl1['cost_basis']})")
        run("trigger-b", "M5-b7-inline", "inline", None)
        s5 = spend(d)
        (ok if any("M5-b7-inline" in u for u in s5["uncosted"]) and not dispatch_allowed(d, "B-discovery")[0] else bad).append(
            "a record whose task cost is unknown is uncosted and stops every dispatch (F5)")
        shutil.rmtree(d / "trigger-b" / "runs" / "M5-b7-inline")
        # --- F6: a correction above a record-backed attempt's own figure is charged on top ------
        r6 = open_attempt(d, "B-discovery", "run", "trigger-b/M5-b8-inline"); close_attempt(d, r6, 0.5, "ok")
        p6 = d / "trigger-b" / "runs" / "M5-b8-inline"; p6.mkdir(parents=True, exist_ok=True)
        (p6 / "record.json").write_text(json.dumps({"arm": "inline", "attempt": r6, "result": {"cost_to_parity": 0.5}}))
        t6 = spend(d)["total"]
        correct_attempt(d, r6, 1.2, "the wrapper measured more than the record")
        s6 = spend(d)
        (ok if abs(s6["total"] - t6 - 0.7) < 1e-9 and any(c["attempt"] == r6 for c in s6["corrected"]) else bad).append(
            f"a correction above a record-backed attempt's own figure is charged on top, never dropped (F6): {s6['total'] - t6:.2f}")
        # --- F7: a charge is a finite non-negative figure, written and read ---------------------
        n7 = open_attempt(d, "A", "call", "A/abcd/c02-r1")
        for bad_cost in (float("nan"), -0.1, float("inf")):
            try:
                close_attempt(d, n7, bad_cost, "ok"); bad.append(f"a close at {bad_cost} was written")
            except BudgetError:
                ok.append(f"a close at {bad_cost} is refused (F7)")
        close_attempt(d, n7, 0.01, "ok")
        ledger = d / ATTEMPTS; keep = ledger.read_text()
        ledger.write_text(keep + json.dumps({"attempt": n7, "open": False, "status": "corrected: planted", "cost_usd": float("nan")}) + "\n")
        try:
            spend(d); bad.append("a NaN row on the ledger was read")
        except BudgetError:
            ok.append("a NaN charge on the ledger makes it unreadable, and an unreadable ledger stops every dispatch (F7)")
        # --- F8: one terminal row per attempt, on read -----------------------------------------
        ledger.write_text(keep + json.dumps({"attempt": n7, "open": False, "status": "ok", "cost_usd": 0.02}) + "\n")
        try:
            trailing_failures(d, "A/"); bad.append("a second terminal row was read")
        except BudgetError:
            ok.append("a second terminal row for one attempt makes the ledger unreadable (F8)")
        ledger.write_text(keep)
        # --- F9: the breaker is judged inside the reservation's lock ---------------------------
        f9a = open_attempt(d, "C", "run", "trigger-c/M5-b1-inline"); close_attempt(d, f9a, None, "failed: RunError")
        f9b = open_attempt(d, "C", "run", "trigger-c/M5-b1-inline"); close_attempt(d, f9b, None, "failed: RunError")
        a9, cap9, why9 = reserve(d, "C", "run", "trigger-c/M5-b2-inline", prefix="trigger-c/", max_failures=2)
        (ok if a9 is None and why9.startswith("breaker") else bad).append(f"a reservation under a standing streak is refused inside the lock (F9): {why9[:50]}")
        ack_streak(d, "trigger-c/", "the cause is gone")
        a9b, _, _ = reserve(d, "C", "run", "trigger-c/M5-b2-inline", prefix="trigger-c/", max_failures=2)
        (ok if a9b else bad).append("after the acknowledgement the reservation is taken (F9)")
        close_attempt(d, a9b, 0.1, "ok")
        # --- fix review 5: F5 an unknown priming charge is unknown ------------------------------
        (ok if priming_cost({"priming": [{"cost_usd": 0.3}, {"cost_usd": None}]}) is None
         and run_cost({"result": {"cost_to_parity": 0.5}, "priming": [{"cost_usd": None}]}) is None else bad).append(
            "a priming process with no finite charge makes the run's cost unknown (F5)")
        # --- fix review 6, F5: each source field is a figure before aggregation ------------------
        (ok if run_cost({"result": {"cost_to_parity": -0.5}, "priming": [{"cost_usd": 0.8}]}) is None
         and run_cost({"result": {"cost_to_parity": True}, "priming": []}) is None
         and run_cost({"result": {"cost_to_parity": "0.4"}, "priming": []}) is None
         and run_cost({"result": {"cost_to_parity": 0.5}, "priming": [{"cost_usd": -0.1}]}) is None
         and run_cost({"result": {"cost_to_parity": 0.5}, "priming": [{"cost_usd": 0.2}]}) == 0.7 else bad).append(
            "a negative task cost under a positive priming charge, a boolean, or a numeric string is unknown, never a valid-looking aggregate (fix review 6, F5)")
        u5 = open_attempt(d, "B-discovery", "run", "trigger-b/M5-b9-inline")
        cl5 = close_run(d, u5, {"result": {"cost_to_parity": 0.5}, "priming": [{"cost_usd": None}, {"cost_usd": 0.2}]}, "ok")
        (ok if cl5["cost_basis"] == "reserve" and cl5["cost_usd"] >= RESERVE["run"] + 0.5 else bad).append(
            f"an unknown priming charge closes at the reserve plus the known parts, basis reserve ({cl5['cost_usd']})")
        # --- F6: a NaN or negative figure inside a record is not a spend ---------------------
        for planted in (float("nan"), -0.5):
            run("trigger-b", "M5-b9-inline", "inline", planted)
            s6b = spend(d)
            (ok if any("M5-b9-inline" in u for u in s6b["uncosted"]) and not dispatch_allowed(d, "B-discovery")[0]
             and math.isfinite(s6b["total"]) else bad).append(f"a record charging {planted} is uncosted and stops dispatch, and the total stays a figure (F6)")
        shutil.rmtree(d / "trigger-b" / "runs" / "M5-b9-inline")
        # --- F7: after a failure, dispatches under the prefix are serial ---------------------
        f7 = open_attempt(d, "B-conditional", "run", "trigger-cell3/M3-b1-inline"); close_attempt(d, f7, None, "failed: RunError")
        fly = open_attempt(d, "B-conditional", "run", "trigger-cell3/M3-b1-inline")   # this process's pid: in flight
        a7, _, why7 = reserve(d, "B-conditional", "run", "trigger-cell3/M3-b2-inline", prefix="trigger-cell3/", max_failures=2)
        (ok if a7 is None and "in flight" in why7 else bad).append(f"with a failure standing, a second dispatch waits for the one in flight (F7): {why7[:60]}")
        close_attempt(d, fly, 0.4, "ok")
        a7b, _, _ = reserve(d, "B-conditional", "run", "trigger-cell3/M3-b2-inline", prefix="trigger-cell3/", max_failures=2)
        (ok if a7b else bad).append("once the in-flight dispatch succeeded, the next is taken (F7)")
        close_attempt(d, a7b, 0.4, "ok")
        # --- F9: two closers racing on one attempt write one terminal row (the writer lock) ---
        import threading
        race = open_attempt(d, "A", "call", "A/abcd/c03-r1")
        barrier = threading.Barrier(2)
        real_attempts = globals()["attempts"]
        def slow_attempts(root_):
            rows_ = real_attempts(root_)
            try:
                barrier.wait(timeout=0.5)     # both readers see the attempt open before either writes
            except threading.BrokenBarrierError:
                pass
            return rows_
        outcomes = []
        def closer():
            try:
                close_attempt(d, race, 0.01, "ok"); outcomes.append("wrote")
            except BudgetError:
                outcomes.append("refused")
        globals()["attempts"] = slow_attempts
        try:
            ts = [threading.Thread(target=closer) for _ in range(2)]
            [t_.start() for t_ in ts]; [t_.join() for t_ in ts]
        finally:
            globals()["attempts"] = real_attempts
        (ok if sorted(outcomes) == ["refused", "wrote"] and len([a for a in attempts(d) if a["attempt"] == race and not a.get("open")]) == 1
         else bad).append(f"two closers racing on one attempt: one writes, one is refused, the ledger has one terminal row (F9): {outcomes}")
        sp = spend(d)
        (ok if can_start(d, "B-discovery")[0] or sp["groups"]["B-discovery"] + RESERVE["run"] > 75.0 else bad).append("the extended ceiling gates dispatch")
        aid4, cap4, why4 = reserve(d, "B-discovery", "run", "trigger-b/M5-b9-inline")
        (ok if aid4 and cap4 == RESERVE["run"] else bad).append(f"reserve() opens an attempt under the lock with the cap: {cap4}")
        close_attempt(d, aid4, 0.2, "ok")
        aid5, cap5, why5 = reserve(d, "B-same", "run", "trigger-b/M1-b9-delegated-same")
        (ok if aid5 is None and "ceiling" in why5 else bad).append(f"reserve() refuses at a ceiling without opening anything: {why5[:50]}")
        before = spend(d)["groups"]["B-discovery"]   # carries aid4's closed 0.2
        pr = d / "trigger-b" / "runs" / "M5-b9-inline"; pr.mkdir(parents=True, exist_ok=True)
        (pr / "record.json").write_text(json.dumps({"arm": "inline", "attempt": aid4, "result": {"cost_to_parity": 0.2},
                                                    "priming": [{"cost_usd": 0.03}, {"cost_usd": 0.02}]}))
        sp5 = spend(d)
        # the record replaces its attempt's closing line: 0.2 measured + 0.05 priming, so +0.05 over `before`
        (ok if abs(sp5["groups"]["B-discovery"] - (before + 0.05)) < 1e-9 else bad).append(
            f"a record's priming processes are charged with it ({before:.2f} → {sp5['groups']['B-discovery']:.2f})")
        cap_a = cap_for(d, "A", "call")
        (ok if 0 < cap_a < RESERVE["call"] else bad).append(f"the cap shrinks to the nearer ceiling: A has ${CEILINGS['A'] - s3['groups']['A']:.2f} left → {cap_a}")
        try:
            close_attempt(d, "nope", 1.0, "ok"); bad.append("closing an unopened attempt")
        except BudgetError:
            ok.append("closing an attempt that was never opened is refused")
        allowed, why = dispatch_allowed(d, "B-discovery")
        (ok if allowed else bad).append("another group still dispatches")
        allowed, why = can_start(d, "B-same")
        (ok if not allowed and "nothing left" in why else bad).append("a spent group cannot start")
        # the total: fill C to make the remaining total short of B-conditional's remaining ceiling
        for i in range(30):
            run("trigger-c", f"M5-b{i+1}-inline", "inline", 5.0)   # $150 in C (over its own ceiling: the gate is asked before a dispatch, never enforced after the fact)
        allowed, why = can_start(d, "B-conditional")
        (ok if not allowed and "remaining budget" in why else bad).append(f"a start that the total cannot cover is refused: {why[:70]}")
        allowed, why = dispatch_allowed(d, "B-discovery")
        s = spend(d)
        (ok if (not allowed) == (s["total"] + RESERVE["run"] > TOTAL_CEILING) else bad).append("the total ceiling gates dispatch with the reserve in hand")
        try:
            group_of_run("trigger-b", "fork-same"); bad.append("an arm outside the table got a group")
        except BudgetError:
            ok.append("an arm outside the design's table has no group")
        # an uncosted record is counted at zero and named
        run("trigger-b", "M5-b1-inline", "inline", None)
        s = spend(d)
        (ok if any("M5-b1-inline" in u for u in s["uncosted"]) else bad).append("a record without a cost is listed as uncosted")
        allowed, why = dispatch_allowed(d, "B-sweep")
        (ok if not allowed and "uncosted record" in why else bad).append("an uncosted record refuses every dispatch")
        (pathlib.Path(d) / ATTEMPTS).write_text("{not json\n")
        try:
            spend(d); bad.append("an unreadable ledger was read")
        except BudgetError:
            ok.append("an unreadable attempts ledger stops the read, by line")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for b in bad:
        print("  FAIL", b)
    print(f"budget self-test: {len(ok)} passed, {len(bad)} failed")
    return 0 if not bad else 1


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    if len(sys.argv) >= 6 and sys.argv[1] == "extend":
        # budget.py extend <root> <group> <usd> <decision> <why…> — the owner raises one group's ceiling
        print(json.dumps(extend_ceiling(pathlib.Path(sys.argv[2]), sys.argv[3], float(sys.argv[4]), sys.argv[5], " ".join(sys.argv[6:])), indent=1))
        raise SystemExit(0)
    if len(sys.argv) >= 6 and sys.argv[1] == "correct":
        # budget.py correct <root> <attempt> <cost_usd> <why…> — a person raises a closed attempt's charge
        print(json.dumps(correct_attempt(pathlib.Path(sys.argv[2]), sys.argv[3], float(sys.argv[4]), " ".join(sys.argv[5:])), indent=1))
        raise SystemExit(0)
    if len(sys.argv) >= 4 and sys.argv[1] == "ack":
        # budget.py ack <root> <prefix> <why…> — a person closes the breaker's streak, with the reason on the ledger
        print(json.dumps(ack_streak(pathlib.Path(sys.argv[2]), sys.argv[3], " ".join(sys.argv[4:])), indent=1))
        raise SystemExit(0)
    if len(sys.argv) >= 5 and sys.argv[1] == "close":
        # budget.py close <root> <attempt> <cost_usd|reserve> — a person closes what a crash left open
        cost = None if sys.argv[4] == "reserve" else float(sys.argv[4])
        print(json.dumps(close_attempt(pathlib.Path(sys.argv[2]), sys.argv[3], cost, "closed-by-hand"), indent=1))
        raise SystemExit(0)
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if root is None:
        raise SystemExit("usage: budget.py <tier-root> | close <root> <attempt> <cost_usd|reserve> | ack <root> <prefix> <why…> | extend <root> <group> <usd> <decision> <why…> | correct <root> <attempt> <cost_usd> <why…> | --self-test")
    print(json.dumps(spend(root), indent=1))
