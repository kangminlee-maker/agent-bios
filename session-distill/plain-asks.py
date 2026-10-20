#!/usr/bin/env python3
"""Count user turns asking for a plainer re-explanation, over RAW transcripts.

The field measure for G-12 (decision asks and reports in plain words): how often the
user still has to ask. Reads the census a mining window already produced, keeps only
user turns timestamped inside [--start, --end) KST, and counts the ones that ask for an
easier or newcomer-level explanation. A turn repeated verbatim at the same instant in
two sessions (a forked session carries its parent's history) is counted once.

Usage: plain-asks.py --census out/<window>/census.json --start YYYY-MM-DD --end YYYY-MM-DD
       plain-asks.py --self-test
"""
import argparse, datetime, json, os, re

KST = datetime.timezone(datetime.timedelta(hours=9))
ASK = re.compile(r'쉽게|쉬운 말|이해할 수 있|이해 가능|비유 없이|중학생|10살|초등학생|무슨 말인지|이해가 안|뭔 말|어려워')


def user_text(rec):
    if rec.get('type') != 'user' or rec.get('isSidechain'):
        return None
    c = (rec.get('message') or {}).get('content')
    if isinstance(c, str):
        text = c
    elif isinstance(c, list):
        parts = [x.get('text', '') for x in c if isinstance(x, dict) and x.get('type') == 'text']
        text = ' '.join(parts) if parts else None
    else:
        text = None
    # Harness-injected user records (skill bodies, tags, notifications) are not the user.
    if not text or text.startswith('<') or 'Base directory for this skill' in text:
        return None
    return text


def scan(lines, lo, hi):
    """Yield (instant, text, is_ask) for in-window user turns of one transcript."""
    for i, line in enumerate(lines, 1):
        if '"type":"user"' not in line and '"type": "user"' not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        text, ts = user_text(rec), rec.get('timestamp')
        if not text or not ts:
            continue
        when = datetime.datetime.fromisoformat(ts.replace('Z', '+00:00'))
        if lo <= when < hi:
            # A long pasted document that happens to contain the words is not an ask.
            yield i, when, text, bool(ASK.search(text)) and len(text) < 600


def measure(census, lo, hi):
    sessions = [s for s in census['sessions'] if s['disposition'] == 'eligible_main' and s['provider'] == 'claude']
    if not sessions:
        raise SystemExit('census has no eligible claude sessions: nothing to measure')
    scanned, seen, hits, missing = 0, set(), {}, []
    for s in sessions:
        # A transcript can be deleted after the census (a removed worktree takes its
        # project directory with it). It is reported, never silently dropped from the
        # denominator.
        if not os.path.exists(s['transcript']):
            missing.append(s['session_id'][:8])
            continue
        with open(s['transcript'], encoding='utf-8', errors='replace') as fh:
            for i, when, text, is_ask in scan(fh, lo, hi):
                scanned += 1
                if is_ask and (when, text) not in seen:
                    seen.add((when, text))
                    hits.setdefault(s['session_id'][:8], []).append((i, when, text))
    return len(sessions), scanned, hits, missing


def self_test():
    lo = datetime.datetime(2026, 9, 9, tzinfo=KST)
    hi = datetime.datetime(2026, 9, 22, tzinfo=KST)
    def rec(text, ts, **kw):
        return json.dumps({'type': 'user', 'timestamp': ts, 'message': {'role': 'user', 'content': text}, **kw})
    lines = [
        rec('이 문제에 대해 중학생도 이해 가능한 수준으로 쉽게 설명해줘', '2026-09-10T01:00:00Z'),  # ask
        rec('다음 단계 진행하자', '2026-09-10T01:05:00Z'),                                     # not an ask
        rec('쉽게 설명해줘', '2026-09-08T14:00:00Z'),                                          # before window (KST 23:00 9/8)
        rec('쉽게 설명해줘', '2026-09-10T02:00:00Z', isSidechain=True),                        # a subagent, not the user
        rec('<command-name>쉽게</command-name>', '2026-09-10T03:00:00Z'),                     # harness-injected
        rec('쉽게 ' + 'x' * 700, '2026-09-10T04:00:00Z'),                                      # pasted document
    ]
    got = [(t, a) for _, _, t, a in scan(lines, lo, hi)]
    problems = []
    # Exactly three in-window user turns survive the filters, and only the first is an ask:
    # the pre-window, sidechain and injected records never reach the count at all.
    if [a for _, a in got] != [True, False, False]:
        problems.append(f'expected in-window turns ask/no-ask/pasted, got {[(t[:12], a) for t, a in got]}')
    for p in problems:
        print(f'self-test [FAIL] {p}')
    print('PLAIN-ASKS SELF-TEST ' + ('FAIL' if problems else 'OK: in-window user asks counted; sidechain, '
                                     'injected, pre-window and pasted turns excluded'))
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--census')
    ap.add_argument('--start', help='YYYY-MM-DD, KST, inclusive')
    ap.add_argument('--end', help='YYYY-MM-DD, KST, exclusive')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not (args.census and args.start and args.end):
        ap.error('--census, --start and --end are required')
    lo = datetime.datetime.strptime(args.start, '%Y-%m-%d').replace(tzinfo=KST)
    hi = datetime.datetime.strptime(args.end, '%Y-%m-%d').replace(tzinfo=KST)
    n_sessions, scanned, hits, missing = measure(json.load(open(args.census)), lo, hi)
    if scanned == 0:
        raise SystemExit('no in-window user turns scanned — the census and window do not overlap')
    turns = sum(map(len, hits.values()))
    print(f'window {args.start}..{args.end} KST | claude sessions {n_sessions - len(missing)} read, '
          f'{len(missing)} transcript(s) gone since the census {missing} | user turns {scanned} | '
          f'sessions with plain-explanation asks {len(hits)} | ask turns {turns}')
    for sid, hs in sorted(hits.items()):
        for i, when, text in hs:
            print(f'  {sid}:{i} {when.astimezone(KST):%m-%d %H:%M}  {text[:140]}'.replace('\n', ' '))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
