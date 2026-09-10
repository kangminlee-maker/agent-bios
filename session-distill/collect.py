#!/usr/bin/env python3
"""Union the provider screening outputs into candidates-all.json for consolidate.js.

Each candidate gets a stable index `i`, its provider, and the short session tag
(`provider:sid8`) the verifiers cite as supporting evidence. Coverage is
asserted per provider: a screener that returned fewer screened_ids than the
batch held is reported, never silently accepted.

Usage: collect.py [--out DIR]
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=HERE + '/out')
    args = ap.parse_args()
    index = json.load(open(os.path.join(args.out, 'batch_index.json')))
    cands, screened, bad = [], {}, False
    for provider in ('claude', 'codex'):
        path = os.path.join(args.out, f'candidates-{provider}.json')
        if not os.path.exists(path):
            print(f'{provider}: no screening output at {path}', file=sys.stderr)
            bad = True
            continue
        r = json.load(open(path))
        expected = index['sessions'][provider]
        screened[provider] = len(set(r['screened_ids']))
        if screened[provider] != expected:
            print(f'{provider}: screened {screened[provider]} of {expected} sessions', file=sys.stderr)
            bad = True
        for c in r['candidates']:
            cands.append(dict(c, i=len(cands), provider=provider, tag=f"{provider}:{c['session_id'][:8]}"))
    json.dump({'screened': screened, 'candidates': cands},
              open(os.path.join(args.out, 'candidates-all.json'), 'w'), ensure_ascii=False, indent=1)
    print(f"candidates-all.json: {len(cands)} candidates from {sum(screened.values())} screened sessions {screened}")
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
