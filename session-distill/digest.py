#!/usr/bin/env python3
"""Build one compact, redacted digest per eligible session (v1).

Reads census.json, opens each eligible_main transcript, and emits a small
structured digest: the human goal(s), a deterministic timeline of main-context
decisions/tools/errors, provider-reported token cost, and boolean/scalar
signals for the six value criteria the user cares about:

  1 high_token      final decision reached only after large token spend
  2 rollback        a wrong decision was made then reversed/corrected
  3 re_exploration  repeated setup/discovery that a guide could have shortcut
  4 recurrent_error errors experienced repeatedly
  5 rare_high_cost  a low-frequency but high-consequence event
  6 quality_lever   a criterion/decision that clearly raised speed/cost/quality

Signals are heuristic triage only (they rank, they never decide). The LLM
screen judges materiality and novelty against the baseline.

Secrets are stripped; reasoning is kept. Digests stay local.
"""
import json, os, re, sys, argparse, collections

HERE = os.path.dirname(os.path.abspath(__file__))

# Secret-redaction floor: single-sourced in learn/redact.py (shared with the
# light flow's learn/collect-learning.py) so the floor never drifts per copy.
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "learn"))  # secret floor's owner
from redact import redact, SECRET_RE  # noqa: E402

CORRECTION_RE = re.compile(r'(?i)\b(actually|wait,|revert|roll ?back|undo|my mistake|that was wrong|let me fix|correction|instead of|oops|scratch that|되돌리|잘못|취소|롤백|다시)\b')
ERROR_RE = re.compile(r'(?i)\b(error|exception|traceback|failed|failure|denied|not found|cannot|no such|permission denied|timeout|command not found)\b')


def clip(s, n):
    s = (s or '').strip().replace('\n', ' ')
    return s if len(s) <= n else s[:n] + '…'


# ---------------- Claude transcript ----------------
def digest_claude(path, cap_lines=20000):
    tools = collections.Counter()
    errs = collections.Counter()
    corrections, user_turns, asst_turns = 0, 0, 0
    tok = {'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0}
    timeline = []
    first_ts = last_ts = None
    for i, line in enumerate(open(path, encoding='utf-8', errors='replace')):
        if i > cap_lines:
            break
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = r.get('type')
        ts = r.get('timestamp')
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
        m = r.get('message', {}) if isinstance(r.get('message'), dict) else {}
        if t == 'user' and m.get('role') == 'user':
            content = m.get('content')
            txt = ''
            if isinstance(content, str):
                txt = content
            elif isinstance(content, list):
                # skip tool_result echoes; keep human text
                parts = [c.get('text', '') for c in content if isinstance(c, dict) and c.get('type') == 'text']
                txt = ' '.join(parts)
                for c in content:
                    if isinstance(c, dict) and c.get('type') == 'tool_result':
                        rc = c.get('content')
                        rs = rc if isinstance(rc, str) else json.dumps(rc)[:400]
                        if ERROR_RE.search(rs or ''):
                            for kw in ERROR_RE.findall(rs or ''):
                                errs[kw.lower()] += 1
            if txt.strip():
                user_turns += 1
                if CORRECTION_RE.search(txt):
                    corrections += 1
                if len(timeline) < 60:
                    timeline.append('U: ' + clip(redact(txt), 240))
        elif t == 'assistant':
            asst_turns += 1
            u = m.get('usage', {})
            if isinstance(u, dict):
                tok['input'] += u.get('input_tokens', 0)
                tok['output'] += u.get('output_tokens', 0)
                tok['cache_read'] += u.get('cache_read_input_tokens', 0)
                tok['cache_write'] += u.get('cache_creation_input_tokens', 0)
            content = m.get('content', [])
            if isinstance(content, list):
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if c.get('type') == 'tool_use':
                        tools[c.get('name', '?')] += 1
                    elif c.get('type') == 'text':
                        txt = c.get('text', '')
                        if CORRECTION_RE.search(txt):
                            corrections += 1
                        if len(timeline) < 60 and txt.strip():
                            timeline.append('A: ' + clip(redact(txt), 200))
    return {'tools': dict(tools.most_common(15)), 'errors': dict(errs.most_common(10)),
            'corrections': corrections, 'user_turns': user_turns, 'asst_turns': asst_turns,
            'tokens': tok, 'timeline': timeline, 'first_ts': first_ts, 'last_ts': last_ts}


# ---------------- Codex transcript ----------------
def digest_codex(path, cap_lines=20000):
    tools = collections.Counter()
    errs = collections.Counter()
    corrections, user_turns, asst_turns = 0, 0, 0
    tok = {'input': 0, 'output': 0, 'cache_read': 0}
    timeline = []
    for i, line in enumerate(open(path, encoding='utf-8', errors='replace')):
        if i > cap_lines:
            break
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = r.get('type')
        p = r.get('payload', {}) if isinstance(r.get('payload'), dict) else {}
        if t == 'response_item':
            pt = p.get('type')
            if pt == 'message':
                role = p.get('role')
                txt = ''
                for c in (p.get('content') or []):
                    if isinstance(c, dict) and c.get('type') in ('input_text', 'output_text', 'text'):
                        txt += c.get('text', '')
                if role == 'user' and txt.strip():
                    user_turns += 1
                    if CORRECTION_RE.search(txt):
                        corrections += 1
                    if len(timeline) < 60:
                        timeline.append('U: ' + clip(redact(txt), 240))
                elif role == 'assistant' and txt.strip():
                    asst_turns += 1
                    if CORRECTION_RE.search(txt):
                        corrections += 1
                    if len(timeline) < 60:
                        timeline.append('A: ' + clip(redact(txt), 200))
            elif pt == 'function_call':
                tools[p.get('name', '?')] += 1
            elif pt == 'function_call_output':
                out = p.get('output')
                s = out if isinstance(out, str) else json.dumps(out)[:400]
                if ERROR_RE.search(s or ''):
                    for kw in ERROR_RE.findall(s or ''):
                        errs[kw.lower()] += 1
        elif t == 'event_msg':
            if p.get('type') == 'token_count':
                info = p.get('info') or p
                tu = info.get('total_token_usage') or info.get('last_token_usage') or {}
                if isinstance(tu, dict):
                    tok['input'] = max(tok['input'], tu.get('input_tokens', 0))
                    tok['output'] = max(tok['output'], tu.get('output_tokens', 0))
                    tok['cache_read'] = max(tok['cache_read'], tu.get('cached_input_tokens', 0))
    return {'tools': dict(tools.most_common(15)), 'errors': dict(errs.most_common(10)),
            'corrections': corrections, 'user_turns': user_turns, 'asst_turns': asst_turns,
            'tokens': tok, 'timeline': timeline}


def signals(d):
    tok = d['tokens']
    total_out = tok.get('output', 0)
    total_in = tok.get('input', 0) + tok.get('cache_read', 0)
    err_total = sum(d['errors'].values())
    distinct_err = len(d['errors'])
    return {
        'total_output_tokens': total_out,
        'total_input_tokens': total_in,
        'corrections': d['corrections'],
        'error_events': err_total,
        'distinct_error_kinds': distinct_err,
        'user_turns': d['user_turns'],
        'tool_calls': sum(d['tools'].values()),
        # heuristic triage score (rank only)
        'triage': (min(total_out, 200000) / 20000)
                  + 3 * min(d['corrections'], 5)
                  + 1.5 * min(err_total, 10)
                  + 0.5 * min(d['user_turns'], 20),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--census', default=HERE + '/out/census.json')
    ap.add_argument('--out', default=HERE + '/out')
    ap.add_argument('--limit', type=int, default=0, help='cap sessions (0=all)')
    args = ap.parse_args()

    census = json.load(open(args.census))
    elig = [s for s in census['sessions'] if s['disposition'] == 'eligible_main']
    if args.limit:
        elig = elig[:args.limit]

    digests = []
    for n, s in enumerate(elig):
        path = s['transcript']
        try:
            d = digest_claude(path) if s['provider'] == 'claude' else digest_codex(path)
        except Exception as e:
            d = {'error': str(e), 'tools': {}, 'errors': {}, 'corrections': 0,
                 'user_turns': 0, 'asst_turns': 0, 'tokens': {}, 'timeline': []}
        sig = signals(d)
        digests.append({
            'provider': s['provider'], 'session_id': s['session_id'],
            'transcript': path, 'transcript_bytes': s.get('transcript_bytes', 0),
            'goals': [clip(redact(g), 300) for g in s['goals'][:8]],
            'signals': sig, 'tools': d['tools'], 'errors': d['errors'],
            'timeline': d['timeline'],
        })
        if (n + 1) % 40 == 0:
            print(f'  digested {n+1}/{len(elig)}', file=sys.stderr)

    digests.sort(key=lambda x: x['signals']['triage'], reverse=True)
    with open(os.path.join(args.out, 'digests.json'), 'w') as f:
        json.dump(digests, f, ensure_ascii=False, indent=1)

    # distribution summary
    tri = [x['signals']['triage'] for x in digests]
    import statistics
    print(f"digests: {len(digests)}")
    print(f"triage score  max={max(tri):.1f}  median={statistics.median(tri):.1f}  "
          f"p90={sorted(tri)[int(len(tri)*0.9)]:.1f}")
    for band, lo in [('>=15', 15), ('8-15', 8), ('3-8', 3), ('<3', 0)]:
        c = sum(1 for t in tri if t >= lo) - (sum(1 for t in tri if t >= {'>=15':999,'8-15':15,'3-8':8,'<3':3}[band]) if band!='>=15' else 0)
        pass
    for lab, cond in [('triage>=15', lambda t: t>=15), ('8<=triage<15', lambda t: 8<=t<15),
                      ('3<=triage<8', lambda t: 3<=t<8), ('triage<3', lambda t: t<3)]:
        print(f"  {lab}: {sum(1 for t in tri if cond(t))}")
    print(f"wrote {os.path.join(args.out, 'digests.json')}")


if __name__ == '__main__':
    main()
