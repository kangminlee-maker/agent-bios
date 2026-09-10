#!/usr/bin/env python3
"""Aggregate token usage & cost for an agent session (main + subagents).

Usage: session-cost.py <session>.jsonl [...]        per-source cost accounting
       session-cost.py --context <session>.jsonl [...]   context budget
       session-cost.py --context --budget 150000 <session>.jsonl
       session-cost.py --self-test

Cost accounting reads a Claude Code transcript, splitting main-loop from
subagent (sidechain) usage, and also picks up <session-dir>/subagents/
agent-*.jsonl when present. Prints per-source, per-model token sums, modeled
cost, and wall-clock span.

The context budget reads EITHER host's transcript — Claude Code or Codex — and
reports how large the window has grown, how fast it grows per request, and how
many requests remain before a chosen budget. It exists because input dominates
the bill: measured over two real sessions here, cache read + cache write were
92-94% of cost and output 6-8%, so context size is the cost, and the only lever
on it is how long a session is allowed to grow before it is reset.
"""
import json, sys, glob, os, itertools, tempfile, subprocess
from datetime import datetime, timezone

# $/MTok: input, output, cache_read, cache_write_5m, cache_write_1h
PRICES = {
    "claude-fable-5":  (10.0, 50.0, 1.00, 12.50, 20.0),
    # Fable 5.1 model overview, verified 2026-09-08.
    "claude-fable-5-1": (10.0, 50.0, 0.25, 12.50, 20.0),
    "claude-mythos-5": (10.0, 50.0, 1.00, 12.50, 20.0),
    "claude-opus-5":   (5.0, 25.0, 0.50, 6.25, 10.0),
    "claude-opus-4-8": (5.0, 25.0, 0.50, 6.25, 10.0),
    "claude-opus-4-7": (5.0, 25.0, 0.50, 6.25, 10.0),
    "claude-opus-4-6": (5.0, 25.0, 0.50, 6.25, 10.0),
    "claude-sonnet-5": (3.0, 15.0, 0.30, 3.75, 6.0),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30, 3.75, 6.0),
    "claude-haiku-4-5": (1.0, 5.0, 0.10, 1.25, 2.0),
}

def price_for(model):
    # Version-specific rates take precedence over their family prefix.
    for k, v in sorted(PRICES.items(), key=lambda item: len(item[0]), reverse=True):
        if model.startswith(k):
            return v
    return None

def moment(ts):
    """A transcript timestamp as an aware datetime, or None if it is not one.

    Parsed here rather than compared as text: `min`/`max` over ISO STRINGS order by
    code point, which is chronological only while every stamp carries the same zone
    spelling. One `+09:00` stamp beside a `Z` one and the span came out negative —
    printed as a wall-clock figure, with nothing in the output saying it was wrong."""
    if not isinstance(ts, str):
        return None
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def scan(path):
    """-> {(scope, model): {in,out,cr,cw5,cw1,turns}}, (t_min, t_max), {scope: agent_ids}

    A single API response is written to the transcript several times as it
    streams, each line carrying output_tokens *so far* (e.g. 2, 2, 2, 540).
    Keep the record with the LARGEST output_tokens per message id: keeping the
    first one instead under-reports subagent output by ~95%, because sidechain
    messages get snapshotted far more often than main-loop ones do.
    """
    best, tmin, tmax = {}, None, None
    agents = {"main": set(), "sub": set()}
    anonymous = itertools.count()
    try:
        handle = open(path, errors="replace")
    except OSError as exc:
        print(f"session-cost: cannot read {path}: {exc}", file=sys.stderr)
        return {}, (None, None), agents
    with handle:
        for line in handle:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            at = moment(d.get("timestamp"))
            if at is not None:
                tmin = at if tmin is None else min(tmin, at)
                tmax = at if tmax is None else max(tmax, at)
            m = d.get("message") or {}
            u, model = m.get("usage"), m.get("model")
            if not isinstance(u, dict) or not isinstance(model, str) or model == "<synthetic>":
                continue
            scope = "sub" if d.get("isSidechain") else "main"
            if d.get("agentId"):
                agents[scope].add(d["agentId"])
            # De-duplication is what an id BUYS. A record carrying neither id is not a
            # second snapshot of the one before it, so keying them all as (scope, None)
            # kept the largest and discarded the rest — every such response after the
            # first vanished from the totals. Today's transcripts always carry one
            # (0 of 9,749 usage records lacked both), so this is the shape that stops
            # a quiet under-count if that ever stops being true.
            ident = m.get("id") or d.get("requestId")
            key = (scope, ident if ident else f"anonymous-{next(anonymous)}")
            prev = best.get(key)
            if prev is None or u.get("output_tokens", 0) > prev[1].get("output_tokens", 0):
                best[key] = (model, u)

    agg = {}
    for (scope, _), (model, u) in best.items():
        a = agg.setdefault((scope, model), dict(inp=0, out=0, cr=0, cw5=0, cw1=0, turns=0))
        a["inp"] += u.get("input_tokens", 0)
        a["out"] += u.get("output_tokens", 0)
        a["cr"]  += u.get("cache_read_input_tokens", 0)
        cc = u.get("cache_creation") or {}
        if cc:
            a["cw5"] += cc.get("ephemeral_5m_input_tokens", 0)
            a["cw1"] += cc.get("ephemeral_1h_input_tokens", 0)
        else:
            a["cw5"] += u.get("cache_creation_input_tokens", 0)
        a["turns"] += 1
    return agg, (tmin, tmax), agents

def cost(model, a):
    p = price_for(model)
    if not p:
        return None
    i, o, cr, cw5, cw1 = p
    return (a["inp"]*i + a["out"]*o + a["cr"]*cr + a["cw5"]*cw5 + a["cw1"]*cw1) / 1e6

def fmt(n):
    return f"{n/1000:,.0f}k" if n >= 1000 else str(n)

def report(session_path):
    # README names this one of the two things a user runs directly, so a mistyped path is
    # an ordinary event and deserves a sentence rather than a FileNotFoundError traceback.
    if not os.path.isfile(session_path):
        print(f"session-cost: not a readable transcript file: {session_path}", file=sys.stderr)
        return 1
    base = session_path[:-6] if session_path.endswith(".jsonl") else session_path
    sources = [(None, session_path)]
    sources += [(os.path.basename(f)[:-6], f)
                for f in sorted(glob.glob(os.path.join(base, "subagents", "*.jsonl")))]
    print(f"\n=== {os.path.basename(session_path)} ===")
    grand, unpriced = 0.0, []
    hdr = (f"{'source':<38}{'model':<22}{'turns':>6}{'input':>9}{'output':>9}"
           f"{'cache_rd':>10}{'cache_wr':>10}{'cost$':>9}")
    print(hdr); print("-" * len(hdr))
    span_min = span_max = None
    for label, path in sources:
        agg, (tmin, tmax), agents = scan(path)
        if tmin:
            span_min = min(span_min or tmin, tmin); span_max = max(span_max or tmax, tmax)
        for (scope, model), a in sorted(agg.items()):
            if label is not None:
                name = label
            elif scope == "sub":
                n = len(agents["sub"])
                name = f"subagents (n={n})" if n else "subagents"
            else:
                name = "main"
            c = cost(model, a)
            cs = f"{c:9.2f}" if c is not None else "        ?"
            if c is None:
                unpriced.append(model)
            else:
                grand += c
            print(f"{name:<38}{model:<22}{a['turns']:>6}{fmt(a['inp']):>9}{fmt(a['out']):>9}"
                  f"{fmt(a['cr']):>10}{fmt(a['cw5']+a['cw1']):>10}{cs}")
    if span_min:
        mins = (span_max - span_min).total_seconds() / 60
        print(f"\nwall clock: {mins:,.1f} min   |   modeled total cost: ${grand:,.2f}")
    else:
        print(f"\nwall clock: no usable timestamps   |   modeled total cost: ${grand:,.2f}")
    if unpriced:
        print(f"WARN unpriced models: {set(unpriced)}")
    return 0

# ── context budget ────────────────────────────────────────────────────────────
# Both hosts write a transcript that already carries the window size per request,
# so "how full is the context" needs no host API and no hook — only a reader per
# format. That is what keeps this host-agnostic: the hosts differ in how they
# notify, not in what they record.

# Default budget, derived on CLAUDE sessions only: cost per request falls ~4x
# from the 867k auto-compact point to 200k, and the remaining gain to the
# cost-theoretic optimum (~65k) buys a compaction every ~32 requests at 2-3
# minutes each. The measurements behind that, and the rule for choosing a reset
# MECHANISM once a budget is reached, live in guides/cli-multi-model-workflow.md
# ("Context Budget And Reset"); this constant is only its executable default.
#
# The DERIVATION transfers to Codex and the VALUE does not. Growth rate is a
# property of the work, not the host — ~2,400 tok/request over 1,075 sessions of
# 50+ requests, the hosts within 7% (re-measured 2026-08-16; the guide's Evidence
# Base carries the figures) — so the reasoning is shared. But the Codex sessions measured ran a 258,400-token
# window (a later CLI/model pair records 353,400 — the transcript carries it, this
# file never assumes it) and compact at ~95% of it, which puts this default at
# ~77% of that whole context and only just below the point the host would have
# reset anyway: nearly the whole saving Claude gets here is unavailable there. So
# the default is applied to CLAUDE transcripts only; a Codex transcript without an
# explicit --budget gets the window share and no "requests left", because a
# figure against a threshold this file itself calls inapplicable is not a figure.
DEFAULT_BUDGET = 200_000


def detect_host(path):
    """-> 'claude' | 'codex' | None, from the first record that can only be one.

    Sniffed rather than inferred from the path: a transcript copied out of its
    home directory is still readable, and a wrong guess would silently report
    another host's numbers.
    """
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") == "event_msg" or d.get("type") == "session_meta":
                return "codex"
            if "message" in d or d.get("type") in ("user", "assistant", "system"):
                return "claude"
    return None


def context_series(path):
    """-> (host, [ctx per request], [compaction, ...], window or None)

    The two hosts mean different things by `input_tokens`, and conflating them
    understates Claude by the whole cached prefix:
      Claude  — input_tokens is only the UNCACHED remainder, so the request's
                context is input + cache_read + cache_creation.
      Codex   — input_tokens is the whole input and cached_input_tokens is a
                subset of it (verified: total_tokens == input + output), so the
                context is input_tokens alone.

    Claude only: subagents run in their own windows, so sidechain records are
    excluded — including them would report a number no single agent ever held.
    """
    host = detect_host(path)
    series, compactions, window = [], [], None
    if host == "claude":
        best = {}
        order = []
        for line in open(path, errors="replace"):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("subtype") == "compact_boundary":
                cm = d.get("compactMetadata") or {}
                compactions.append({"pre": cm.get("preTokens", 0),
                                    "post": cm.get("postTokens", 0),
                                    "at": len(best)})
                continue
            if d.get("isSidechain"):
                continue
            m = d.get("message") or {}
            u = m.get("usage")
            if not u or m.get("model") in (None, "<synthetic>"):
                continue
            cc = u.get("cache_creation") or {}
            cw = (cc.get("ephemeral_5m_input_tokens", 0) + cc.get("ephemeral_1h_input_tokens", 0)
                  if cc else u.get("cache_creation_input_tokens", 0))
            ctx = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + cw
            # Same streaming-snapshot problem the cost scan documents: one response
            # is written many times. Keep the largest per message id.
            mid = m.get("id") or d.get("requestId")
            if mid not in best:
                order.append(mid)
            best[mid] = max(best.get(mid, 0), ctx)
        series = [best[k] for k in order]
    elif host == "codex":
        for line in open(path, errors="replace"):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            p = d.get("payload") or {}
            if p.get("type") == "context_compacted":
                compactions.append({"pre": 0, "post": 0, "at": len(series)})
                continue
            if p.get("type") != "token_count":
                continue
            info = p.get("info") or {}
            window = info.get("model_context_window") or window
            last = info.get("last_token_usage") or {}
            if last.get("input_tokens"):
                series.append(last["input_tokens"])
    return host, series, compactions, window


def growth_rate(series, compactions):
    """-> (tokens per request, segment count) or (None, 0).

    Measured per compaction segment and reduced by median. A single rate over
    the whole session would be meaningless: each compaction drops the context
    back to near zero, so the raw first-to-last delta describes the reset, not
    the growth. Segments shorter than two requests carry no rate.
    """
    bounds = [c["at"] for c in compactions]
    segments, start = [], 0
    for b in bounds + [len(series)]:
        if b > start:
            segments.append(series[start:b])
        start = b
    # Per INTERVAL, not per sample: n samples span n-1 requests, so [100, 200] is
    # 100 tokens per request, not 50 — the divisor by n under-reported growth by
    # 1/n and over-reported the requests left against a budget.
    rates = [(max(s) - min(s)) / (len(s) - 1) for s in segments if len(s) >= 2]
    if not rates:
        return None, 0
    rates.sort()
    return rates[len(rates) // 2], len(segments)


def context_report(path, budget=None):
    """Print the budget view. Returns False when the transcript yielded nothing.

    `budget=None` means "the default where one applies": DEFAULT_BUDGET on a Claude
    transcript, nothing on a Codex one (see the note above the constant).
    """
    # The same sentence the cost mode gives a mistyped path; without it a missing or
    # directory path reached open() in detect_host and left a traceback.
    if not os.path.isfile(path):
        print(f"session-cost: not a readable transcript file: {path}", file=sys.stderr)
        return False
    try:
        host, series, compactions, window = context_series(path)
    except OSError as exc:
        # isfile() is true of a file this account cannot open (mode 000, another
        # owner); the open() then raised PermissionError past the sentence above.
        print(f"session-cost: not a readable transcript file: {path} ({exc.strerror})",
              file=sys.stderr)
        return False
    print(f"\n=== {os.path.basename(path)} ===  [{host or 'unrecognized'}]")
    if not series:
        # An empty series satisfies every threshold, so it is reported as a
        # failure to read rather than as a session that is comfortably small.
        print("no per-request token records found — nothing measured")
        return False
    now = series[-1]
    peak = max(series)
    rate, nseg = growth_rate(series, compactions)
    print(f"{'requests':<20}{len(series):>12,}")
    print(f"{'context now':<20}{now:>12,} tok")
    print(f"{'peak':<20}{peak:>12,} tok")
    if window:
        print(f"{'window':<20}{window:>12,} tok  ({100*now/window:.0f}% full)")
    else:
        # Claude Code does not record the window; the observed auto-compact point
        # is the honest substitute. Hardcoding a model's window would drift.
        obs = max((c["pre"] for c in compactions), default=0)
        shown = f"{obs:,} tok observed" if obs else "not recorded"
        print(f"{'window':<20}{'—':>12}  (auto-compact: {shown})")
    if compactions:
        pres = [c["pre"] for c in compactions if c["pre"]]
        detail = f"  (pre {fmt(sum(pres)//len(pres))} -> post "\
                 f"{fmt(sum(c['post'] for c in compactions)//len(compactions))})" if pres else ""
        print(f"{'compactions':<20}{len(compactions):>12,}{detail}")
    if rate:
        print(f"{'growth':<20}{rate:>12,.0f} tok/request  (median of {nseg} segment(s))")
    if budget is None and host == "claude":
        budget = DEFAULT_BUDGET
    if budget is None:
        print(f"{'budget':<20}{'—':>12}  (no default transfers to this host; pass --budget N)")
    elif now >= budget:
        print(f"{'budget ' + f'{budget:,}':<20}{'PAST':>12} by {now - budget:,} tok")
    elif rate:
        print(f"{'budget ' + f'{budget:,}':<20}{int((budget - now) / rate):>12,} requests left")
    else:
        print(f"{'budget ' + f'{budget:,}':<20}{budget - now:>12,} tok left")
    return True


# ── self-test ─────────────────────────────────────────────────────────────────

def _self_test():
    """Plant a known transcript of each format and require the derived numbers.

    Every case states the wrong answer it rules out, because a reader that
    silently picks the wrong field still prints a plausible number.
    """
    failures = []

    def check(name, got, want):
        ok = got == want
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f"  got {got!r} want {want!r}"))
        if not ok:
            failures.append(name)

    def write(dirpath, name, records):
        p = os.path.join(dirpath, name)
        with open(p, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
        return p

    with tempfile.TemporaryDirectory() as td:
        # A version-specific cache rate must reach the public report without
        # changing the older model's rate. Run the real CLI/scan/cost path.
        for model, expected in (("claude-fable-5-1", "$0.25"),
                                ("claude-fable-5", "$1.00")):
            transcript = write(td, model + ".jsonl", [
                {"type": "assistant", "message": {
                    "id": "cache-price", "model": model,
                    "usage": {"cache_read_input_tokens": 1_000_000}}},
            ])
            result = subprocess.run(
                [sys.executable, os.path.abspath(__file__), transcript],
                capture_output=True, text=True)
            check(model + " cache price reaches the report",
                  (result.returncode,
                   "modeled total cost: " + expected in result.stdout),
                  (0, True))

        # Claude: two requests. The first is written twice as it streams, the
        # second is a sidechain that must not be counted.
        claude = write(td, "claude.jsonl", [
            {"type": "assistant", "message": {"id": "m1", "model": "claude-opus-5",
             "usage": {"input_tokens": 10, "cache_read_input_tokens": 1000,
                       "cache_creation": {"ephemeral_1h_input_tokens": 90}}}},
            {"type": "assistant", "message": {"id": "m1", "model": "claude-opus-5",
             "usage": {"input_tokens": 10, "cache_read_input_tokens": 4000,
                       "cache_creation": {"ephemeral_1h_input_tokens": 90}}}},
            {"type": "assistant", "isSidechain": True, "message": {"id": "s1",
             "model": "claude-haiku-4-5", "usage": {"input_tokens": 999999,
                                                    "cache_read_input_tokens": 0}}},
            {"type": "assistant", "message": {"id": "m2", "model": "claude-opus-5",
             "usage": {"input_tokens": 10, "cache_read_input_tokens": 6000,
                       "cache_creation": {"ephemeral_1h_input_tokens": 90}}}},
        ])
        host, series, comps, window = context_series(claude)
        check("claude transcript is recognized", host, "claude")
        # 10+4000+90: the largest snapshot, and the cached prefix included. Rules
        # out both reading input_tokens alone (10) and keeping the first snapshot.
        check("claude context sums input + cache_read + cache_creation", series[0], 4100)
        check("claude keeps the largest streaming snapshot", len(series), 2)
        check("claude excludes sidechain requests", max(series), 6100)
        check("claude records no window of its own", window, None)

        # Codex: input_tokens is already the whole input, and cached is a subset.
        codex = write(td, "codex.jsonl", [
            {"type": "session_meta", "payload": {"id": "x"}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "last_token_usage": {"input_tokens": 5000, "cached_input_tokens": 4000,
                                     "output_tokens": 100},
                "model_context_window": 258400}}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "last_token_usage": {"input_tokens": 9000, "cached_input_tokens": 8000,
                                     "output_tokens": 100},
                "model_context_window": 258400}}},
        ])
        host, series, comps, window = context_series(codex)
        check("codex transcript is recognized", host, "codex")
        # Rules out adding cached_input_tokens on top, which would report 9000.
        check("codex context is input_tokens alone", series[0], 5000)
        check("codex window comes from the transcript", window, 258400)
        # The Claude-derived default budget is not applied to a Codex transcript: the
        # report says no default transfers rather than counting requests against a
        # threshold the note above DEFAULT_BUDGET calls inapplicable there.
        import io, contextlib
        def report_text(path, budget=None):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                context_report(path, budget)
            return out.getvalue()
        check("no default budget on a codex transcript",
              "no default transfers to this host" in report_text(codex), True)
        check("the default budget still applies to a claude transcript",
              "budget 200,000" in report_text(claude), True)
        check("an explicit budget applies to codex",
              "budget 150,000" in report_text(codex, 150_000), True)

        # Growth is per segment: a compaction resets the context, so a whole-session
        # delta would report the reset instead of the growth.
        series = [100, 200, 300, 400]
        check("growth over one segment", growth_rate(series, [])[0], 100.0)
        # 100->400 then 100->900. Raw last-minus-first would be (900-100)/7 ≈ 114,
        # which reads the reset as growth; per segment it is median(100, 266.7). An
        # even segment count takes the upper of the two, so this also pins which
        # median an even split returns.
        two = [100, 200, 300, 400, 100, 400, 700, 900]
        check("growth ignores the compaction reset",
              growth_rate(two, [{"at": 4, "pre": 400, "post": 100}])[0], 800 / 3)
        check("a segment shorter than two requests carries no rate",
              growth_rate([500], [])[0], None)

        # A transcript with no usage records must not read as a small context.
        empty = write(td, "empty.jsonl", [{"type": "assistant", "message": {"id": "e"}}])
        check("an unmeasurable transcript reports failure, not zero",
              context_report(empty), False)

    print("\nself-test: " + (f"{len(failures)} FAILED" if failures else "all passed"))
    return 1 if failures else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--self-test" in args:
        sys.exit(_self_test())
    budget = None
    if "--budget" in args:
        i = args.index("--budget")
        # A missing or non-numeric value is an ordinary typo and gets a sentence, not
        # an IndexError or ValueError traceback.
        if i + 1 >= len(args) or not args[i + 1].isdigit() or int(args[i + 1]) <= 0:
            sys.exit("session-cost: --budget takes a positive whole number of tokens, "
                     "e.g. --budget 150000")
        budget = int(args[i + 1])
        del args[i:i + 2]
    if "--context" in args:
        args.remove("--context")
        if not args:
            sys.exit(__doc__)
        ok = [context_report(p, budget) for p in args]
        sys.exit(0 if all(ok) else 1)
    if not args:
        sys.exit(__doc__)
    sys.exit(max(report(p) for p in args))
