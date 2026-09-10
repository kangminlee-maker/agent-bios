#!/usr/bin/env python3
"""Participants and their usage, read from each host's own artifact.

The unit is a *participant*: a parent, a child, or a fork with an artifact of its own.
A run's cost is the sum over its participants, over their billed requests, over the
token kinds, of usage × the rate of the seat THAT participant ran on — never usage
summed across participants and then priced, because a sol parent and a luna child
differ by 20× on the same kind (design, "The estimator").

Everything here is read from the artifact the host wrote, not from what the runner
requested: the Claude transcript records `message.model` and a record-level `effort` on
every assistant turn; the Codex rollout records `turn_context.model` / `.effort` per
turn and `session_meta.parent_thread_id` on a spawned child. Measured 2026-09-04.

Kinds are a partition — every raw token in exactly one — and the identities that make
it one are checked on every request (`Request.problems`). A request that lacks a field
says so; it is never priced as if the field were zero.
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass, field

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import dispatch  # noqa: E402  (benchmarks/dispatch.py: model_matches)


class UsageError(RuntimeError):
    """An artifact that cannot serve as a participant's evidence."""


# ---------------------------------------------------------------------------
# Rates — the design's table, $/MTok, official 2026-09-03. A seat not here is not
# priced, and pricing it raises rather than guessing.
# ---------------------------------------------------------------------------
RATES = {
    "claude-opus-5":    {"uncached": 5.0, "cache_write_5m": 6.25, "cache_write_1h": 10.0,
                         "cache_read": 0.5, "output": 25.0},
    "claude-sonnet-5":  {"uncached": 2.0, "cache_write_5m": 2.5, "cache_write_1h": 4.0,
                         "cache_read": 0.2, "output": 10.0},
    "claude-haiku-4-5": {"uncached": 1.0, "cache_write_5m": 1.25, "cache_write_1h": 2.0,
                         "cache_read": 0.1, "output": 5.0},
    "gpt-5.6-sol":      {"uncached": 4.0, "cache_write": 5.0, "cache_read": 0.4, "output": 20.0},
    "gpt-5.6-terra":    {"uncached": 2.0, "cache_write": 2.5, "cache_read": 0.2, "output": 12.0},
    "gpt-5.6-luna":     {"uncached": 0.2, "cache_write": 0.25, "cache_read": 0.02, "output": 1.2},
}
# Long-context cliff (Codex): above this many tokens of context in ONE request, input
# kinds bill ×2 and output kinds ×1.5 — applied per request, never per run.
CLIFF_TOKENS = 272_000
CLIFF = {"input": 2.0, "output": 1.5}

KINDS = {
    "claude": ("uncached", "cache_read", "cache_write_5m", "cache_write_1h",
               "visible_output", "thinking"),
    "codex": ("uncached", "cache_read", "cache_write", "visible_output", "thinking"),
}
OUTPUT_KINDS = ("visible_output", "thinking")


def rate_for(model: str) -> dict | None:
    for want, rates in RATES.items():
        if dispatch.model_matches(want, model or ""):
            return rates
    return None


@dataclass
class Request:
    """One billed request of one participant, in kinds."""
    participant: str
    host: str
    model: str
    effort: str | None
    kinds: dict
    context_tokens: int      # what the request carried as context (cliff test)
    present: tuple           # raw fields actually found in the artifact
    ref: str                 # artifact:line, so a number can be traced to its bytes
    identity_problems: list = field(default_factory=list)

    def problems(self) -> list[str]:
        return list(self.identity_problems)


@dataclass
class Participant:
    id: str
    host: str
    role: str                # parent | child
    artifact: str
    requests: list
    terminal: bool           # the artifact carries its terminal record
    completeness: str | None # None when complete, else a blocking problem
    models: list
    efforts: list
    notes: list = field(default_factory=list)  # disclosures, never blocking

    def problems(self) -> list[str]:
        out = []
        if not self.requests:
            out.append(f"{self.id}: no billed request in {self.artifact}")
        if not self.terminal:
            out.append(f"{self.id}: no terminal record — the artifact is cut or still open")
        if self.completeness:
            out.append(f"{self.id}: {self.completeness}")
        for r in self.requests:
            out.extend(f"{self.id} {r.ref}: {p}" for p in r.problems())
        return out


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------
CLAUDE_RAW = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens",
              "cache_creation.ephemeral_5m_input_tokens",
              "cache_creation.ephemeral_1h_input_tokens", "output_tokens",
              "output_tokens_details.thinking_tokens")


def claude_request(usage: dict, model: str, effort: str | None, pid: str, ref: str,
                   snapshot_only: bool = False) -> Request:
    """One request's kinds from a Claude usage object. `snapshot_only` marks a message
    whose transcript carries streaming snapshots and no final record (measured
    2026-09-04: three records with output_tokens 1, no output_tokens_details, no
    stop_reason, followed by the tool's result — the request ran, its final usage was
    never written). Such a request bills from its last snapshot with thinking 0 and is
    disclosed by the participant, not refused: the reconciliation control is what
    measures the under-read, and a final record missing the field stays a problem."""
    cc = usage.get("cache_creation") if isinstance(usage.get("cache_creation"), dict) else {}
    otd = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"),
                                                            dict) else {}
    present = []
    for name in CLAUDE_RAW:
        if "." in name:
            parent, leaf = name.split(".", 1)
            src = cc if parent == "cache_creation" else otd
            if leaf in src:
                present.append(name)
        elif name in usage:
            present.append(name)
    absent = [n for n in CLAUDE_RAW if n not in present]
    if snapshot_only:
        absent = [n for n in absent if n != "output_tokens_details.thinking_tokens"]
    problems = [f"field absent: {n}" for n in absent]
    uncached = int(usage.get("input_tokens") or 0)
    read = int(usage.get("cache_read_input_tokens") or 0)
    w5 = int(cc.get("ephemeral_5m_input_tokens") or 0)
    w1 = int(cc.get("ephemeral_1h_input_tokens") or 0)
    wtot = int(usage.get("cache_creation_input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    think = int(otd.get("thinking_tokens") or 0)
    if "cache_creation_input_tokens" in present and w5 + w1 != wtot:
        problems.append(f"cache_creation {wtot} != 5m {w5} + 1h {w1}")
    if out < think:
        problems.append(f"output {out} < thinking {think}")
    return Request(pid, "claude", model or "", effort,
                   {"uncached": uncached, "cache_read": read, "cache_write_5m": w5,
                    "cache_write_1h": w1, "visible_output": out - think, "thinking": think},
                   uncached + read + w5 + w1, tuple(present), ref, problems)


def _claude_participant(path: pathlib.Path, role: str, pid: str) -> Participant:
    # Per message.id, every usage-bearing record in order: streaming snapshots share
    # the id with output counting up, and the FINAL record — the one carrying
    # output_tokens_details — is the billed one. A message with snapshots and no final
    # record (see claude_request) bills from its last snapshot and is disclosed.
    by_msg: dict = {}
    order: list = []
    last_stop = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "assistant":
                continue
            m = d.get("message") or {}
            u = m.get("usage")
            if not isinstance(u, dict):
                continue
            mid = m.get("id") or f"line{i}"
            if mid not in by_msg:
                order.append(mid)
                by_msg[mid] = []
            by_msg[mid].append((u, m.get("model"), d.get("effort"), f"{path.name}:{i}",
                                bool(m.get("stop_reason"))))
            last_stop = m.get("stop_reason")
    reqs, notes = [], []
    for mid in order:
        recs = by_msg[mid]
        # a final record carries stop_reason; snapshots carry none
        finals = [r for r in recs if r[4]]
        if finals:
            u, model, effort, ref, _ = finals[-1]
            reqs.append(claude_request(u, model, effort, pid, ref))
        else:
            u, model, effort, ref, _ = recs[-1]
            reqs.append(claude_request(u, model, effort, pid, ref, snapshot_only=True))
            notes.append(f"{ref}: message {mid[-8:]} has {len(recs)} streaming snapshot(s) and "
                         f"no final usage record — billed from the last snapshot "
                         f"(output {u.get('output_tokens')}), its true output is under-read")
    return Participant(pid, "claude", role, str(path), reqs, terminal=bool(last_stop),
                       completeness=None,
                       models=sorted({r.model for r in reqs if r.model}),
                       efforts=sorted({r.effort for r in reqs if r.effort}), notes=notes)


def claude_participants(project_dir: pathlib.Path, session_id: str) -> list[Participant]:
    """The parent transcript and every child transcript beside it."""
    parent = project_dir / f"{session_id}.jsonl"
    if not parent.is_file():
        raise UsageError(f"{parent}: parent transcript not found")
    parts = [_claude_participant(parent, "parent", f"claude:{session_id}")]
    for f in sorted((project_dir / session_id / "subagents").glob("agent-*.jsonl")):
        parts.append(_claude_participant(f, "child", f"claude:{f.stem}"))
    return parts


def claude_wrapper(stdout: str) -> dict:
    """The `-p --output-format json` wrapper: measured cost and per-model usage."""
    payload = json.loads(stdout)
    final = (payload if isinstance(payload, list) else [payload])[-1]
    return {"session_id": final.get("session_id"),
            "total_cost_usd": final.get("total_cost_usd"),
            "model_usage": final.get("modelUsage") or {}}


# ---------------------------------------------------------------------------
# Codex
# ---------------------------------------------------------------------------
CODEX_RAW = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
             "output_tokens", "reasoning_output_tokens")


def codex_request(usage: dict, model: str, effort: str | None, pid: str, ref: str) -> Request:
    present = tuple(n for n in CODEX_RAW if n in usage)
    problems = [f"field absent: {n}" for n in CODEX_RAW if n not in present]
    inp = int(usage.get("input_tokens") or 0)
    cached = int(usage.get("cached_input_tokens") or 0)
    write = int(usage.get("cache_write_input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    reasoning = int(usage.get("reasoning_output_tokens") or 0)
    uncached = inp - cached - write
    if uncached < 0:
        problems.append(f"cached {cached} + write {write} exceed input {inp}: the subset "
                        f"relation the partition assumes is false here")
    if out < reasoning:
        problems.append(f"output {out} < reasoning {reasoning}")
    return Request(pid, "codex", model or "", effort,
                   {"uncached": max(uncached, 0), "cache_read": cached, "cache_write": write,
                    "visible_output": out - reasoning, "thinking": reasoning},
                   inp, present, ref, problems)


CODEX_TOTAL_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                      "output_tokens", "reasoning_output_tokens")


def _codex_participant(path: pathlib.Path, role: str) -> Participant:
    """One request per ADVANCE of the cumulative total, not per token_count event.

    Measured 2026-09-04 on a real sol+terra rollout: `total_token_usage` is the
    authoritative running bill, and some token_count events re-report a
    `last_token_usage` while the total does not move — summing every `last` double-counts
    (4.59M vs the true 3.60M input on one 25-event rollout). So a request is taken from
    the DELTA of the cumulative total between the events where it advances; `last` at that
    event carries the request's context size for the cliff test and is checked against the
    delta as the differential probe. Events that do not advance the total are counted as
    duplicates and disclosed, never billed."""
    meta, model, effort = {}, "", None
    reqs: list = []
    prev = {k: 0 for k in CODEX_TOTAL_FIELDS}
    duplicate_events = 0
    last_mismatch = []
    terminal = False
    with open(path, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            t, p = d.get("type"), d.get("payload")
            if not isinstance(p, dict):
                continue
            if t == "session_meta":
                # First wins: a child rollout REPLAYS its parent's session_meta on line 2
                # (measured 2026-09-04), so last-wins collapsed every child onto the parent
                # id and merged their costs — the exact per-participant attribution control 0
                # exists to keep apart.
                if not meta:
                    meta = p
            elif t == "turn_context":
                model = p.get("model") or model
                effort = p.get("effort") or effort
            elif t == "event_msg" and p.get("type") == "token_count":
                info = p.get("info") or {}
                total = info.get("total_token_usage")
                last = info.get("last_token_usage") if isinstance(info.get("last_token_usage"),
                                                                  dict) else {}
                if not isinstance(total, dict):
                    continue
                delta = {k: int(total.get(k) or 0) - prev[k] for k in CODEX_TOTAL_FIELDS}
                if all(v == 0 for v in delta.values()):
                    duplicate_events += 1
                    continue
                if any(v < 0 for v in delta.values()):
                    # A total that went backwards is a reset (compaction or a new
                    # billing window). Re-baseline from it and disclose; the request
                    # is the fresh total itself.
                    delta = {k: int(total.get(k) or 0) for k in CODEX_TOTAL_FIELDS}
                    last_mismatch.append(f"{path.name}:{i} cumulative total went backwards")
                prev = {k: int(total.get(k) or 0) for k in CODEX_TOTAL_FIELDS}
                # The differential probe: last should equal the delta on the raw fields.
                if last and any(int(last.get(k) or 0) != delta[k] for k in CODEX_TOTAL_FIELDS):
                    last_mismatch.append(f"{path.name}:{i} last != total-delta")
                reqs.append(codex_request(delta, model, effort, "", f"{path.name}:{i}"))
            elif t == "event_msg" and p.get("type") == "task_complete":
                terminal = True
    pid = f"codex:{meta.get('id') or path.stem}"
    for r in reqs:
        r.participant = pid
    notes = []
    if duplicate_events:
        notes.append(f"{duplicate_events} token_count event(s) re-reported without advancing "
                     f"the cumulative total; billed from total deltas, not per-turn sums")
    notes.extend(last_mismatch[:3])
    return Participant(pid, "codex", role, str(path), reqs, terminal=terminal,
                       completeness=None,
                       models=sorted({r.model for r in reqs if r.model}),
                       efforts=sorted({r.effort for r in reqs if r.effort}),
                       notes=notes)


def codex_participants(codex_home: pathlib.Path, thread_id: str) -> list[Participant]:
    """The parent rollout and every rollout that names it as parent_thread_id.

    Codex moves finished sessions into `archived_sessions/` while this tree is being read
    (2026-09-06: a scan died on a file archived between the listing and the open), so a
    listed file can be gone by the time it is opened. A vanished candidate is skipped — a
    child this thread spawned is newer than anything Codex archives — and a vanished parent,
    or a vanished child that had already named this thread, is refused by name."""
    root = pathlib.Path(codex_home) / "sessions"
    if not root.is_dir():
        raise UsageError(f"{root}: no sessions directory")
    files = sorted(root.rglob("rollout-*.jsonl"))
    parent = [f for f in files if thread_id in f.name]
    if len(parent) != 1:
        raise UsageError(f"thread {thread_id}: {len(parent)} rollout files match, want 1")
    try:
        parts = [_codex_participant(parent[0], "parent")]
    except FileNotFoundError:
        raise UsageError(f"thread {thread_id}: {parent[0].name} vanished between listing and open "
                         f"(Codex archives sessions) — the read cannot stand") from None
    for f in files:
        if f == parent[0]:
            continue
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                head = fh.readline()
        except FileNotFoundError:
            continue
        if f'"parent_thread_id":"{thread_id}"' in head.replace(" ", ""):
            try:
                parts.append(_codex_participant(f, "child"))
            except FileNotFoundError:
                raise UsageError(f"thread {thread_id}: child {f.name} vanished between listing and open "
                                 f"(Codex archives sessions) — the read cannot stand") from None
    return parts


# ---------------------------------------------------------------------------
# Pricing — participant-indexed, per request
# ---------------------------------------------------------------------------
def price_request(r: Request) -> dict:
    rates = rate_for(r.model)
    if rates is None:
        raise UsageError(f"{r.participant} {r.ref}: unpriced seat {r.model!r}")
    cliff = r.host == "codex" and r.model.startswith("gpt-5.6") and \
        r.context_tokens > CLIFF_TOKENS
    usd, by_kind = 0.0, {}
    for kind, n in r.kinds.items():
        if kind in OUTPUT_KINDS:
            per = rates["output"] * (CLIFF["output"] if cliff else 1.0)
        else:
            if kind not in rates:
                raise UsageError(f"{r.participant} {r.ref}: kind {kind} has no rate for {r.model}")
            per = rates[kind] * (CLIFF["input"] if cliff else 1.0)
        by_kind[kind] = n * per / 1_000_000
        usd += by_kind[kind]
    return {"usd": usd, "by_kind": by_kind, "cliff": cliff}


def price_run(participants: list) -> dict:
    """Σ participant Σ request Σ kind — with the seat of each participant's own request."""
    total, by_p, by_kind, n, cliffs = 0.0, {}, {}, 0, 0
    for p in participants:
        for r in p.requests:
            priced = price_request(r)
            n += 1
            cliffs += int(priced["cliff"])
            total += priced["usd"]
            by_p[p.id] = by_p.get(p.id, 0.0) + priced["usd"]
            for k, v in priced["by_kind"].items():
                by_kind[k] = by_kind.get(k, 0.0) + v
    return {"usd": total, "by_participant": by_p, "by_kind": by_kind,
            "requests": n, "cliff_requests": cliffs}


def output_priced_share(participants: list) -> float | None:
    """(visible + thinking) priced per participant ÷ total, as the design's label."""
    priced = price_run(participants)
    if priced["usd"] <= 0:
        return None
    out = sum(v for k, v in priced["by_kind"].items() if k in OUTPUT_KINDS)
    return out / priced["usd"]


def reconcile(participants: list, measured_usd: float, tolerance: float = 0.03) -> dict:
    """|Σ(kinds×rates) − total_cost_usd| ≤ tolerance × measured — the one place the model
    meets a bill."""
    modelled = price_run(participants)["usd"]
    if not measured_usd:
        return {"modelled": modelled, "measured": measured_usd, "rel_err": None, "ok": False,
                "why": "no measured cost to reconcile against"}
    rel = abs(modelled - measured_usd) / measured_usd
    return {"modelled": modelled, "measured": measured_usd, "rel_err": rel,
            "ok": rel <= tolerance}


def ledger(participants: list) -> dict:
    """A JSON-able account of the run's participants, before any verdict reads it."""
    rows = []
    for p in participants:
        sums = {}
        for r in p.requests:
            for k, v in r.kinds.items():
                sums[k] = sums.get(k, 0) + int(v)
        rows.append({"id": p.id, "host": p.host, "role": p.role, "artifact": p.artifact,
                     "models": p.models, "efforts": p.efforts, "requests": len(p.requests),
                     "kinds": sums, "terminal": p.terminal, "completeness": p.completeness,
                     "notes": p.notes, "problems": p.problems()})
    return {"participants": rows,
            "problems": [pr for row in rows for pr in row["problems"]],
            "notes": [f"{row['id']}: {n}" for row in rows for n in row["notes"]]}


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="read a run's participants from host artifacts")
    ap.add_argument("host", choices=["claude", "codex"])
    ap.add_argument("home", help="claude: the project transcript dir; codex: CODEX_HOME")
    ap.add_argument("id", help="claude session_id / codex thread_id")
    ap.add_argument("--measured-usd", type=float, help="claude: total_cost_usd to reconcile")
    a = ap.parse_args(argv)
    parts = (claude_participants(pathlib.Path(a.home), a.id) if a.host == "claude"
             else codex_participants(pathlib.Path(a.home), a.id))
    out = ledger(parts)
    try:
        out["priced"] = price_run(parts)
        out["output_priced_share"] = output_priced_share(parts)
    except UsageError as exc:
        out["priced"] = {"error": str(exc)}
    if a.measured_usd is not None and "error" not in out["priced"]:
        out["reconciliation"] = reconcile(parts, a.measured_usd)
    print(json.dumps(out, indent=1))
    return 0 if not out["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
