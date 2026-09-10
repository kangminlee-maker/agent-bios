#!/usr/bin/env python3
"""Merge a window's verified survivors into design/session-distill/ledger.json.

consolidate.js decides which survivor is a recurrence of which ledger entry
(its Match phase); this script applies that decision deterministically:

  recurrence  -> the entry gains the window's supporting sessions, keeps the
                 higher strength, and records the recurrence under `recurrence`
                 so the promotion bar (independent recurrence >= 2) can be read
                 off the entry.
  new lesson  -> a new entry, status `candidate`, id continued in the existing
                 S<strength>-<nn> scheme, carrying the verifier's principle,
                 baseline reference, placement proposal and rationale. The
                 user's selection (workflow guide stage 2) moves it to placed
                 or incubating.

Dry-run by default; --apply writes. Refuses to apply twice for one window.

Usage: merge-ledger.py --window-end YYYY-MM-DD [--apply] [--out DIR] [--ledger FILE]
"""
import argparse, collections, datetime, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--window-end', required=True)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--out', default=HERE + '/out')
    ap.add_argument('--ledger', default=os.path.join(REPO, 'design/session-distill/ledger.json'))
    args = ap.parse_args()

    ledger = json.load(open(args.ledger))
    entries = ledger['entries']
    by_id = {e['id']: e for e in entries}
    cons = json.load(open(os.path.join(args.out, 'consolidated.json')))
    survivors = cons['survivors']
    matches = {m['survivor']: m for m in cons.get('matches', [])}
    already = [e['id'] for e in entries if e.get('window') == args.window_end
               or any(r.get('window') == args.window_end for r in e.get('recurrence', []))]
    if already:
        print(f'window {args.window_end} already merged into {len(already)} entries ({already[:5]}...) — refusing', file=sys.stderr)
        return 2

    counters = collections.Counter()
    for e in entries:
        m = re.match(r'^S(\d)-(\d+)$', e['id'])
        if m:
            counters[int(m.group(1))] = max(counters[int(m.group(1))], int(m.group(2)))

    today = datetime.date.today().isoformat()
    added, recurred = [], []
    for j, v in enumerate(survivors):
        m = matches.get(j)
        target = by_id.get(m['ledger_id']) if m and m.get('ledger_id') else None
        if m and m.get('ledger_id') and target is None:
            print(f'survivor {j} matched unknown ledger id {m["ledger_id"]} — treating as new', file=sys.stderr)
        sessions = sorted(set(v['supporting']))
        if target:
            new_sessions = [s for s in sessions if s not in target.get('supporting_sessions', [])]
            target.setdefault('supporting_sessions', []).extend(new_sessions)
            target.setdefault('recurrence', []).append({
                'window': args.window_end, 'sessions': sessions, 'strength': v['strength'],
                'verdict': v['verdict'], 'lesson_as_seen': v['lesson'], 'principle': v['principle'],
                'reason': m['reason']})
            target['strength'] = max(int(target.get('strength') or 0), v['strength'])
            recurred.append((target['id'], target['status'], len(new_sessions), v['lesson']))
        else:
            tier = max(1, min(5, int(v['strength'])))
            counters[tier] += 1
            eid = f'S{tier}-{counters[tier]:02d}'
            entries.append({
                'id': eid, 'lesson': v['lesson'], 'strength': v['strength'], 'verdict': v['verdict'],
                'criteria': v['criteria'], 'supporting_sessions': sessions,
                'principle': v['principle'], 'baseline_ref': v['baseline_ref'],
                'placement_proposed': v['placement'], 'rationale': v['rationale'],
                'classification': None, 'review_note': None, 'status': 'candidate',
                'window': args.window_end, 'surfaced': today,
            })
            added.append((eid, v['strength'], v['lesson']))

    print(f'survivors {len(survivors)}: {len(recurred)} recur, {len(added)} new')
    for eid, status, n, lesson in recurred:
        print(f'  recur {eid} ({status}, +{n} session) {lesson[:90]}')
    for eid, s, lesson in added:
        print(f'  new   {eid} s{s} {lesson[:90]}')
    if not args.apply:
        print('dry run — pass --apply to write')
        return 0
    ledger['window'] = f"census ending {args.window_end} (previous: {ledger.get('window')})"
    json.dump(ledger, open(args.ledger, 'w'), ensure_ascii=False, indent=1)
    open(args.ledger, 'a').write('\n')
    print(f'wrote {args.ledger}: {len(entries)} entries')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
