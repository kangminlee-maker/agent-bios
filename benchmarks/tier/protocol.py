#!/usr/bin/env python3
"""Brief protocols, the repair loop, and the run ledger (control 0, and the estimand).

A run is: brief the child, let it work, then bring the result to its visible done-when by
one repair protocol whose every turn is charged to the arm (design, "Parity is enforced").
The run's cost-to-parity is the whole ledger; its level is scored on held-out checks
(level.py). This module owns the control logic and the ledger assembly; the thing that
actually produces a workdir edit — a live child dispatch, or a scripted golden — is a
`solver` injected into the driver, so the loop is provable without a live seat and the
live path is the same driver with a real solver.

Realization selector (mock-realization-boundary): a solver is `live` (a real host
dispatch, its usage read from the child's artifact by usage.py) or `golden` (a scripted
sequence of edits with synthesized usage, for the self-test). The driver, the ledger, and
the level score are shared; only the solver differs, and a golden run is never product
completion evidence.
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass, field

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import level  # noqa: E402
import usage  # noqa: E402

# Repair budget — the same for every arm, set before the data (design, "Variables").
B1_SELF_VERIFY = 2   # child self-verify passes
B2_PARENT_REPAIR = 1  # parent repair passes


class ProtocolError(RuntimeError):
    pass


# --------------------------------------------------------------------------- briefs
STANDARD_BRIEF = """\
Objective: implement every function in pkg/mod.py so the tests under tests_visible pass.
Frozen scope: pkg/mod.py only. Do not edit the tests or add files outside pkg/.
Inputs: the stubbed pkg/mod.py and the visible tests.
Done-when: pytest tests_visible tests_regression is green.
Verification: run that pytest yourself before reporting.
Preserve out-of-scope behaviour: the shared helper _normalize must keep its contract.
Escalate anything the brief does not name instead of guessing.
Items ({m}): {item_ids}.
First line of your report: CANARY=<the CANARY token if it is in your context, else NONE>.
"""

CHEAP_SEAT_BRIEF = STANDARD_BRIEF + """\

Per-item detail (a weaker seat is briefed the way it is briefed in practice):
{item_detail}
Verify each item with: pytest tests_visible/test_{first_item}.py (and its siblings).
Worked example — item {first_item}: read tests_visible/test_{first_item}.py, make that
one assertion pass by editing only its function in pkg/mod.py, then run its test.
Stop-and-report rule: if any item is ambiguous or needs a decision the brief does not
give, stop and report it rather than inventing behaviour.
"""


def render_brief(protocol: str, manifest: dict) -> str:
    ids = ", ".join(manifest["item_ids"])
    if protocol == "standard":
        return STANDARD_BRIEF.format(m=manifest["m"], item_ids=ids)
    if protocol == "cheap-seat":
        # the per-item detail RESTATES the spec every stub's docstring already carries —
        # the same words for every arm, so a weaker seat is briefed the way it is briefed
        # in practice without being better specified than the others (Stage 1 found the
        # cheap-seat brief the only place the transform was named)
        detail = "\n".join(f"  - {it['id']}: {it['name']} — {it.get('spec', 'as its docstring states')}; "
                           f"visible case f{k}({it['visible'][0]!r}) == {it['visible'][1]!r}"
                           for k, it in enumerate(manifest["items"]))
        return CHEAP_SEAT_BRIEF.format(m=manifest["m"], item_ids=ids, item_detail=detail,
                                       first_item=manifest["items"][0]["id"])
    raise ProtocolError(f"unknown brief protocol {protocol!r}")


def write_brief_templates(dest: pathlib.Path) -> dict:
    """Freeze the two templates as files so their hashes enter the experiment pin.
    The templates are the *shape*, not a rendered brief — the hash is stable across
    fixtures, which is what the pin needs."""
    dest.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, tmpl in (("standard", STANDARD_BRIEF), ("cheap-seat", CHEAP_SEAT_BRIEF)):
        p = dest / f"brief-{name}.txt"
        p.write_text(tmpl)
        out[name] = str(p)
    return out


# ------------------------------------------------------------------- pass + run records
@dataclass
class PassRecord:
    """One turn of the protocol: who acted, on what seat, and its usage."""
    participant_id: str
    host: str
    role: str          # child | parent
    seat_model: str
    seat_effort: str
    phase: str         # solve | self_verify | parent_repair
    participant: object = None   # a usage.Participant (live) or a synthetic one (golden)

    def as_participant(self) -> object:
        if self.participant is not None:
            return self.participant
        raise ProtocolError(f"{self.participant_id}: pass has no usage participant")


@dataclass
class RunResult:
    reached: bool
    reached_at: str | None            # the phase that reached done-when, or None
    passes: list = field(default_factory=list)
    ledger: dict = field(default_factory=dict)
    score: dict = field(default_factory=dict)
    cost_to_parity: float | None = None
    problems: list = field(default_factory=list)


def run_ledger(passes: list, declared: list) -> dict:
    """Control 0: every declared participant has a record, each is complete, and cost is
    participant-indexed. `declared` is the set of participant ids the arm's row requires;
    a pass for an undeclared participant, or a declared participant with no pass, fails."""
    seen = {p.participant_id for p in passes}
    problems = []
    for d in declared:
        if d not in seen:
            problems.append(f"declared participant {d} produced no pass — run is incomplete")
    for p in passes:
        if p.participant_id not in declared:
            problems.append(f"pass from undeclared participant {p.participant_id}")
    parts = [p.as_participant() for p in passes]
    lg = usage.ledger(parts)
    problems.extend(lg["problems"])
    priced = None
    if not problems:
        try:
            priced = usage.price_run(parts)["usd"]
        except usage.UsageError as e:
            problems.append(str(e))
    return {"problems": problems, "cost": priced, "participants": lg["participants"],
            "notes": lg.get("notes", [])}


def drive(workdir: pathlib.Path, oracle, manifest: dict,
          solver, declared, b1: int = B1_SELF_VERIFY,
          b2: int = B2_PARENT_REPAIR) -> RunResult:
    """Brief -> child solve -> child self-verify (<=b1) -> parent repair (<=b2), stopping
    at the visible done-when. `solver(phase, failing_items, workdir)` performs one turn
    and returns a PassRecord, or a list of them when one host process produced several
    participants (a live parent that spawned its child); it is the only thing that
    differs between live and golden. `declared` is the participant ids the arm's row
    requires, or a callable over the passes that derives them once the passes' role
    checks have run — a live run cannot know a child's id before it exists, so it
    declares the ROLE before dispatch and the id after. `oracle` is a path, or a callable
    returning one: a live run materialises the answer key only here, after the last
    solver turn, so it is not on disk while any participant runs. done-when is checked by
    the real verifier between turns."""
    passes = []

    def failing():
        dw = level.done_when(workdir)
        return [name for name, o in dw["outcomes"].items() if o == "fail"], dw["reached"]

    def turn(phase, items):
        out = solver(phase, items, workdir)
        passes.extend(out if isinstance(out, list) else [out])

    # initial solve
    turn("solve", manifest["item_ids"])
    fails, reached = failing()
    phase_reached = "solve" if reached else None

    # child self-verify loop
    i = 0
    while not reached and i < b1:
        i += 1
        turn("self_verify", fails)
        fails, reached = failing()
        if reached:
            phase_reached = f"self_verify_{i}"

    # parent repair
    j = 0
    while not reached and j < b2:
        j += 1
        turn("parent_repair", fails)
        fails, reached = failing()
        if reached:
            phase_reached = f"parent_repair_{j}"

    lg = run_ledger(passes, declared(passes) if callable(declared) else declared)
    result = RunResult(reached=reached, reached_at=phase_reached, passes=passes,
                       ledger=lg, cost_to_parity=lg["cost"], problems=list(lg["problems"]))
    # Level is scored only when the ledger is sound; a leak or a missing participant
    # voids the run, not just the level.
    if not lg["problems"]:
        oracle_path = oracle() if callable(oracle) else oracle
        result.score = level.score(workdir, oracle_path, manifest)
        if not result.score.get("scored"):
            result.problems.append("level voided: " + result.score.get("why", "leak"))
    else:
        result.score = {"scored": False, "why": "ledger unsound"}
    return result


if __name__ == "__main__":
    # no default path: a demo fixture written to /tmp is an answer key on disk, and Stage 1's
    # seats found exactly such a leftover there
    if len(sys.argv) < 2:
        raise SystemExit("usage: protocol.py <fixture dir with manifest.json>")
    man = json.loads((pathlib.Path(sys.argv[1]) / "manifest.json").read_text())
    print(render_brief("cheap-seat", man))


# ----------------------------------------------------------------------------- brief receipt
import html  # noqa: E402

FORK_TASK = ("Run {nonce}. Continue in the same working directory: implement every stubbed "
             "function in pkg/mod.py so `python3 -m pytest tests_visible tests_regression -q` "
             "passes; edit only pkg/mod.py; keep _normalize's contract; run that pytest "
             "yourself before reporting. First line of your report: CANARY=<the CANARY "
             "token if it is in your context, else NONE>.\n")
REPAIR_SUFFIX = ("\nRepair pass {i}: the verifier reports these items still failing their "
                 "visible tests: {items}. Fix only those, then run the verification again.\n")


def brief_text(nonce: str, proto: str, manifest: dict, repair: tuple | None = None) -> str:
    """The exact packet the child must receive: nonce first (cache order), then the
    pinned template rendered for this manifest, then a fixed repair suffix on repair
    passes. Equality against this is control 4's brief receipt. A fork gets FORK_TASK."""
    if proto == "none":
        text = FORK_TASK.format(nonce=nonce)
    else:
        text = f"Run {nonce}.\n" + render_brief(proto, manifest)
    if repair:
        text += REPAIR_SUFFIX.format(i=repair[0], items=", ".join(repair[1]))
    return text


def canon_brief(s: str) -> str:
    """A brief up to a relaying seat's escaping: entities unescaped, every backslash
    dropped, a trailing newline ignored. Measured 2026-09-05 over the Stage-1 re-run: the
    Claude helm seat's Agent call carried `<` as `&lt;` in 8 of 12 long standard briefs
    and halved the backslashes of 2 of 6 cheap-seat briefs; under this form the child's
    first message equals the pinned brief in all ten (`D-20260905-fd9177`)."""
    return html.unescape(s).replace("\\", "").rstrip("\n")


def brief_match(pinned: str, received: str) -> str | None:
    """How the child's received text carries the pinned brief: "raw" (the pinned text is
    in it — the Agent tool drops the trailing newline, so equality is on stripped text),
    "escaped" (equal under `canon_brief`: the relaying seat transcribed it), or None."""
    if pinned.strip() in received.strip():
        return "raw"
    if canon_brief(pinned).strip() in canon_brief(received).strip():
        return "escaped"
    return None


def child_first_message(path: pathlib.Path) -> str:
    """A Claude child transcript's first user record — the prompt the Agent tool handed it."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "user":
                continue
            c = (d.get("message") or {}).get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""
