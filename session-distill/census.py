#!/usr/bin/env python3
"""Session-Distill census (v1).

Enumerate directly-handled main-context Claude Code / Codex sessions in a
rolling window, exclude dispatched subagents/exec subprocesses, and emit one
compact per-session digest for downstream LLM screening.

Primary enumerator is each provider's history.jsonl (only human-typed
main-context prompts are recorded there). Each history session id is then
confirmed against a retained transcript and classified by transcript-side
provenance. Own data, own machine: this is a deterministic accounting step,
not a privacy boundary — redaction happens in the digest builder.

Usage:
  census.py [--window-days N] [--end YYYY-MM-DD] [--out DIR]
Outputs <out>/census.json (sessions + dispositions) and prints a summary.
"""
import json, os, sys, glob, gzip, argparse, datetime, collections

HOME = os.path.expanduser('~')
CLAUDE_HIST = os.path.join(HOME, '.claude/history.jsonl')
CODEX_HIST = os.path.join(HOME, '.codex/history.jsonl')
CLAUDE_ROOT = os.path.join(HOME, '.claude/projects')
CODEX_ROOT = os.path.join(HOME, '.codex/sessions')


def parse_ts(v):
    """Claude history: epoch-ms string. Codex history: epoch-sec string."""
    if v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        try:
            return datetime.datetime.fromisoformat(str(v).replace('Z', '+00:00')).timestamp()
        except ValueError:
            return None
    # ms vs s heuristic: anything past ~year 2100 in seconds is really ms
    return n / 1000.0 if n > 1e11 else n


def history_sessions(path, tsfield, sidfield, textfield, lo, hi):
    """session_id -> {goals: [text...], first_ts, last_ts, count}."""
    out = collections.defaultdict(lambda: {'goals': [], 'first_ts': None, 'last_ts': None, 'count': 0})
    for line in open(path, encoding='utf-8', errors='replace'):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = parse_ts(r.get(tsfield))
        if ts is None or not (lo <= ts <= hi):
            continue
        sid = r.get(sidfield)
        if not sid:
            continue
        s = out[sid]
        txt = (r.get(textfield) or '').strip()
        if txt and txt not in ('!',) and not txt.startswith('/'):
            s['goals'].append(txt)
        s['count'] += 1
        s['first_ts'] = ts if s['first_ts'] is None else min(s['first_ts'], ts)
        s['last_ts'] = ts if s['last_ts'] is None else max(s['last_ts'], ts)
    return out


def find_claude_transcript(sid):
    hits = glob.glob(os.path.join(CLAUDE_ROOT, '*', sid + '.jsonl'))
    return hits[0] if hits else None


def find_codex_transcript(sid):
    # rollout files embed the session id in the filename
    hits = glob.glob(os.path.join(CODEX_ROOT, '**', '*' + sid + '*.jsonl'), recursive=True)
    return hits[0] if hits else None


def classify_claude(path):
    """Return (disposition, signals) from transcript-side provenance."""
    sig = {'entrypoint': None, 'sidechain_seen': False, 'human_turn': False,
           'agentId_seen': False, 'user_msgs': 0, 'assistant_msgs': 0}
    for line in open(path, encoding='utf-8', errors='replace'):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = r.get('type')
        if r.get('isSidechain'):
            sig['sidechain_seen'] = True
        if r.get('agentId'):
            sig['agentId_seen'] = True
        if r.get('entrypoint') and sig['entrypoint'] is None:
            sig['entrypoint'] = r.get('entrypoint')
        if t == 'user':
            sig['user_msgs'] += 1
            m = r.get('message', {})
            if isinstance(m, dict) and m.get('role') == 'user':
                sig['human_turn'] = True
        elif t == 'assistant':
            sig['assistant_msgs'] += 1
    ep = sig['entrypoint']
    if ep in ('sdk-cli', 'review', 'reconstruct') or sig['agentId_seen']:
        return 'excluded_dispatched', sig
    if ep == 'cli' and not sig['sidechain_seen'] and sig['human_turn']:
        return 'eligible_main', sig
    return 'unknown_quarantine', sig


def classify_codex(path):
    sig = {'originator': None, 'source': None, 'user_turns': 0}
    for i, line in enumerate(open(path, encoding='utf-8', errors='replace')):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get('type') == 'session_meta':
            p = r.get('payload', {})
            sig['originator'] = p.get('originator')
            sig['source'] = p.get('source')
        if r.get('type') == 'response_item':
            p = r.get('payload', {})
            if p.get('type') == 'message' and p.get('role') == 'user':
                sig['user_turns'] += 1
        if i > 4000:
            break
    src, orig = sig['source'], (sig['originator'] or '')
    if src == 'exec' or orig == 'codex_exec':
        return 'excluded_dispatched', sig
    if src in ('cli', 'vscode') and orig in ('codex-tui', 'codex_vscode', 'Codex Desktop', 'codex_work_desktop', 'vscode'):
        return 'eligible_main', sig
    if src in ('cli', 'vscode'):
        return 'eligible_main', sig  # history-confirmed human prompt + interactive source
    return 'unknown_quarantine', sig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--window-days', type=int, default=21)
    ap.add_argument('--end', default=None, help='YYYY-MM-DD; default=now')
    ap.add_argument('--out', default=os.path.dirname(os.path.abspath(__file__)) + '/out')
    args = ap.parse_args()

    end = (datetime.datetime.strptime(args.end, '%Y-%m-%d') if args.end
           else datetime.datetime.now())
    hi = end.timestamp()
    lo = (end - datetime.timedelta(days=args.window_days)).timestamp()
    os.makedirs(args.out, exist_ok=True)

    ch = history_sessions(CLAUDE_HIST, 'timestamp', 'sessionId', 'display', lo, hi)
    xh = history_sessions(CODEX_HIST, 'ts', 'session_id', 'text', lo, hi)

    sessions = []
    disp = collections.Counter()
    for provider, hist, finder, classifier in [
        ('claude', ch, find_claude_transcript, classify_claude),
        ('codex', xh, find_codex_transcript, classify_codex),
    ]:
        for sid, h in hist.items():
            path = finder(sid)
            if not path:
                disp[(provider, 'known_absent_source')] += 1
                sessions.append({'provider': provider, 'session_id': sid, 'disposition': 'known_absent_source',
                                 'transcript': None, 'goals': h['goals'], 'first_ts': h['first_ts'],
                                 'last_ts': h['last_ts'], 'hist_events': h['count']})
                continue
            d, sig = classifier(path)
            disp[(provider, d)] += 1
            sessions.append({'provider': provider, 'session_id': sid, 'disposition': d,
                             'transcript': path, 'goals': h['goals'], 'first_ts': h['first_ts'],
                             'last_ts': h['last_ts'], 'hist_events': h['count'], 'signals': sig,
                             'transcript_bytes': os.path.getsize(path)})

    result = {
        'window': {'start': datetime.datetime.fromtimestamp(lo).isoformat(),
                   'end': datetime.datetime.fromtimestamp(hi).isoformat(),
                   'days': args.window_days},
        'counts': {f'{p}:{d}': n for (p, d), n in sorted(disp.items())},
        'sessions': sessions,
    }
    with open(os.path.join(args.out, 'census.json'), 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    elig = [s for s in sessions if s['disposition'] == 'eligible_main']
    print(f"window: {result['window']['start'][:10]} .. {result['window']['end'][:10]} ({args.window_days}d)")
    for k, n in sorted(result['counts'].items()):
        print(f"  {k}: {n}")
    print(f"eligible_main total: {len(elig)}  "
          f"(claude {sum(1 for s in elig if s['provider']=='claude')}, "
          f"codex {sum(1 for s in elig if s['provider']=='codex')})")
    tb = sum(s.get('transcript_bytes', 0) for s in elig)
    print(f"eligible transcript bytes: {tb/1e6:.1f} MB")
    print(f"wrote {os.path.join(args.out, 'census.json')}")


if __name__ == '__main__':
    main()
