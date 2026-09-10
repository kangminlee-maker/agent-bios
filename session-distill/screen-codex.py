#!/usr/bin/env python3
"""Provider-affine screening of the Codex batches: one hermetic `codex exec` per batch.

Mirrors screen-claude.js (same criteria, same output schema) but dispatches
through ~/.codex/bin/codex-run with a self-contained packet on stdin — the
baseline and the batch are inlined, so the reviewer reads nothing from this
checkout and runs read-only. Output: <out>/candidates-codex.json in the shape
collect.py expects ({candidates, screened_ids, batches_ok, batches_total}).

Usage: screen-codex.py [--out DIR] [--model M] [--effort E] [--runner PATH]
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))

CRITERIA = """Value criteria (a learning is worth extracting if it fits one or more):
1 high_token — a final decision reached only after large token spend (a rule that would have shortcut it).
2 rollback — a wrong decision made then reversed/corrected (the rule that prevents the wrong turn).
3 re_exploration — repeated setup/discovery the operator redoes from scratch because no guide captures it.
4 recurrent_error — an error experienced repeatedly (the rule/recognition that avoids it).
5 rare_high_cost — a low-frequency but high-consequence event (worth a rule despite rarity).
6 quality_lever — a criterion or decision that clearly raised speed, lowered cost, or raised design quality."""

SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['candidates', 'screened_ids'],
    'properties': {
        'screened_ids': {'type': 'array', 'items': {'type': 'string'}},
        'candidates': {
            'type': 'array',
            'items': {
                'type': 'object', 'additionalProperties': False,
                'required': ['session_id', 'title', 'criteria', 'evidence', 'novelty', 'principle', 'placement', 'confidence'],
                'properties': {
                    'session_id': {'type': 'string'},
                    'title': {'type': 'string'},
                    'criteria': {'type': 'array', 'items': {'type': 'string', 'enum': ['high_token', 'rollback', 're_exploration', 'recurrent_error', 'rare_high_cost', 'quality_lever']}},
                    'evidence': {'type': 'string'},
                    'novelty': {'type': 'string'},
                    'principle': {'type': 'string'},
                    'placement': {'type': 'string'},
                    'confidence': {'type': 'number'},
                },
            },
        },
    },
}


def packet(baseline, batch):
    return '\n\n'.join([
        "You screen a batch of Codex AI-coding session digests to extract learnings worth adding to the user's global agent instructions (AGENTS.md / CLAUDE.md / guides). Mine directly-handled main-context sessions for generalizable rules NOT already in the baseline.",
        'Each digest has the human goal(s), a deterministic timeline (U:/A: turns), tools, error signatures, and token/correction signals — redacted, own-machine data.',
        CRITERIA,
        'For EACH session, emit a candidate only when the learning (a) fits a criterion, (b) generalizes beyond the incident, and (c) is genuinely absent or only partially covered in the baseline. Be strict on novelty: name the closest existing baseline rule and say covered/partial/absent. Ground every candidate in the digest; do not invent. Write each principle as a general rule with no transcript ids, names, dates, or repo-specific paths. Put every examined session_id in screened_ids even when it yields no candidate. Reply with JSON matching the output schema and nothing else.',
        '===== BASELINE (current canonical corpus) =====\n' + baseline,
        '===== BATCH (session digests, JSON) =====\n' + batch,
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=HERE + '/out')
    ap.add_argument('--model', default='gpt-5.6-sol')
    ap.add_argument('--effort', default='high')
    ap.add_argument('--runner', default=os.path.expanduser('~/.codex/bin/codex-run'))
    args = ap.parse_args()

    index = json.load(open(os.path.join(args.out, 'batch_index.json')))
    baseline = open(index['baseline'], encoding='utf-8').read()
    batches = index['codex_batches']
    schema_path = os.path.join(args.out, 'screen-schema.json')
    json.dump(SCHEMA, open(schema_path, 'w'))
    result = {'candidates': [], 'screened_ids': [], 'batches_ok': 0, 'batches_total': len(batches),
              'seat': {'model': args.model, 'effort': args.effort, 'runner': args.runner, 'profile': 'hermetic'}}
    for bp in batches:
        batch = open(bp, encoding='utf-8').read()
        expected = {d['session_id'] for d in json.loads(batch)}
        proc = subprocess.run(
            [args.runner, '--profile', 'hermetic', '--model', args.model, '--effort', args.effort,
             '--sandbox', 'read-only', '--schema', schema_path],
            input=packet(baseline, batch), text=True, capture_output=True)
        if proc.returncode != 0:
            print(f'FAIL {os.path.basename(bp)}: exit {proc.returncode}\n{proc.stderr[-2000:]}', file=sys.stderr)
            continue
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            print(f'FAIL {os.path.basename(bp)}: non-JSON reply\n{proc.stdout[:500]}', file=sys.stderr)
            continue
        missing = expected - set(out['screened_ids'])
        if missing:
            print(f'WARN {os.path.basename(bp)}: {len(missing)} session(s) not in screened_ids: {sorted(missing)}', file=sys.stderr)
        result['candidates'] += out['candidates']
        result['screened_ids'] += out['screened_ids']
        result['batches_ok'] += 1
        print(f'ok {os.path.basename(bp)}: {len(out["screened_ids"])} screened, {len(out["candidates"])} candidates')
    json.dump(result, open(os.path.join(args.out, 'candidates-codex.json'), 'w'), ensure_ascii=False, indent=1)
    print(f"codex: {result['batches_ok']}/{result['batches_total']} batches, {len(result['screened_ids'])} screened, {len(result['candidates'])} candidates")
    return 0 if result['batches_ok'] == result['batches_total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
