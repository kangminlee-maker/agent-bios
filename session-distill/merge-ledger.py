#!/usr/bin/env python3
"""Merge a window's verified survivors into design/session-distill/ledger.json.

The consolidation step decides which survivor is a recurrence of which ledger
entry (its Match phase; the v1 script that ran it was deleted at the WP-22
cutover, and this file reads the decision rather than making it); this script
applies that decision deterministically:

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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--window-end', required=True)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--out', default=HERE + '/out')
    ap.add_argument('--ledger', default=os.path.join(REPO, 'design/session-distill/ledger.json'))
    args = ap.parse_args(argv)

    ledger = json.load(open(args.ledger))
    # SCHEMA 1 ONLY, and refused before anything is read further. This script writes a top-level
    # `window` and per-entry `strength` / `supporting_sessions`, none of which schema 2 has: run
    # against a migrated ledger it returned 0 and left a document the schema no longer describes
    # (the WP-22a review). The merge belongs to the v1 window flow; a schema-2 merge is a feature
    # the lifecycle intake will carry, not a flag to add here.
    held_schema = ledger.get('schema')
    if held_schema != 1:
        print(f'LEDGER_SCHEMA_UNSUPPORTED {args.ledger}: this merge writes schema 1 fields '
              f'(window, strength, supporting_sessions) and the ledger declares schema '
              f'{held_schema!r}. Nothing was read or written. The window merge is part of the v1 '
              f'flow; after the schema 2 migration a window is folded in by the lifecycle intake.',
              file=sys.stderr)
        return 2
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


def self_test():
    """The schema guard, and that nothing is written when it fires.

    This script has had no suite: it is the v1 window merge, and the cutover left it in place with
    a new way to go wrong — the ledger it writes into is schema 2 now, and it writes schema 1
    fields. One control for the refusal, one for the bytes, one that the refusal comes before any
    read of the consolidation, and a positive control so the guard cannot be passing on nothing.
    """
    import contextlib, io, pathlib, tempfile
    failures = []
    with tempfile.TemporaryDirectory(prefix='merge-ledger-st-') as raw:
        root = pathlib.Path(raw)
        out = root / 'out'
        out.mkdir()
        schema2 = root / 'schema2.json'
        body = {'schema': 2, 'entries': [], 'windows': []}
        schema2.write_text(json.dumps(body), encoding='utf-8')
        before = schema2.read_bytes()
        said = io.StringIO()
        # The call is GUARDED: with the guard reverted the run reaches the consolidation this
        # fixture does not provide and raises, and an unguarded control would die on that instead
        # of saying the guard stopped firing. A traceback is not a control.
        try:
            with contextlib.redirect_stderr(said):
                code = main(['--window-end', '2026-11-12', '--apply', '--ledger', str(schema2),
                             '--out', str(out)])
        except BaseException as exc:  # noqa: BLE001 - not refusing IS the finding
            code = f'raised {type(exc).__name__}: {exc}'
        if code != 2 or 'LEDGER_SCHEMA_UNSUPPORTED' not in said.getvalue():
            failures.append(f'a schema 2 ledger was not refused by name: rc={code} '
                            f'{said.getvalue()!r}')
        if schema2.read_bytes() != before:
            failures.append('the refused run changed the ledger')
        # The refusal comes before the consolidation is read: there is no consolidated.json in
        # `out`, and a run that read it first would have died on that instead.
        if 'consolidated' in said.getvalue():
            failures.append(f'the run reached the consolidation before refusing: '
                            f'{said.getvalue()!r}')
        # Positive control: a schema 1 ledger gets PAST the guard and fails later, on the
        # consolidation this fixture does not provide. Without it the guard could be refusing
        # everything.
        schema1 = root / 'schema1.json'
        schema1.write_text(json.dumps({'schema': 1, 'entries': []}), encoding='utf-8')
        passed_guard = False
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                main(['--window-end', '2026-11-12', '--apply', '--ledger', str(schema1),
                      '--out', str(out)])
        except FileNotFoundError:
            passed_guard = True
        except Exception as exc:  # noqa: BLE001 - any other failure is still past the guard
            passed_guard = 'LEDGER_SCHEMA_UNSUPPORTED' not in str(exc)
        if not passed_guard:
            failures.append('a schema 1 ledger did not get past the guard, so the guard refuses '
                            'every schema rather than the ones this script cannot write')
    for failure in failures:
        print(f'merge-ledger --self-test [FAIL] {failure}', file=sys.stderr)
    if failures:
        return 1
    print('merge-ledger --self-test: OK (3 controls: a schema 2 ledger refused by name before the '
          'consolidation is read and with its bytes unchanged, and a schema 1 ledger past the '
          'guard)')
    return 0


if __name__ == '__main__':
    if '--self-test' in sys.argv[1:]:
        raise SystemExit(self_test())
    raise SystemExit(main())
