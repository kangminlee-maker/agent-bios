#!/usr/bin/env python3
"""Assemble the human-reviewable promotion bundle (v1).

Merges Claude + Codex screening candidates, attaches the deterministic session
evidence (goal, signals) from the digests, groups by proposed placement, and
emits a Markdown bundle the user reviews before anything is written to the
canonical instruction corpus. Nothing here edits CLAUDE.md/guides — that is a
separate, explicitly-approved step.

Usage: bundle.py [--claude FILE] [--codex FILE] [--digests FILE] [--out FILE]
"""
import json, os, argparse, collections

HERE = os.path.dirname(os.path.abspath(__file__))

CRIT_LABEL = {
    'high_token': '①high-token', 'rollback': '②rollback', 're_exploration': '③re-exploration',
    'recurrent_error': '④recurrent-error', 'rare_high_cost': '⑤rare-high-cost', 'quality_lever': '⑥quality-lever',
}


def load(path):
    if not path or not os.path.exists(path):
        return {'candidates': [], 'screened_ids': []}
    return json.load(open(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--claude', default=HERE + '/out/candidates-claude.json')
    ap.add_argument('--codex', default=HERE + '/out/candidates-codex.json')
    ap.add_argument('--digests', default=HERE + '/out/digests.json')
    ap.add_argument('--out', default=HERE + '/out/BUNDLE.md')
    args = ap.parse_args()

    cl, cx = load(args.claude), load(args.codex)
    digests = {d['session_id']: d for d in json.load(open(args.digests))}
    cands = [dict(c, _provider='claude') for c in cl['candidates']] + \
            [dict(c, _provider='codex') for c in cx['candidates']]
    screened = set(cl['screened_ids']) | set(cx['screened_ids'])

    # sort by confidence desc within placement groups
    groups = collections.defaultdict(list)
    for c in cands:
        key = c['placement'].strip()
        # normalize common placements
        low = key.lower()
        if 'claude.md' in low or 'global' in low or 'agents.md' in low:
            gk = 'Global CLAUDE.md / AGENTS.md'
        else:
            gk = key
        groups[gk].append(c)

    lines = []
    lines.append('# Session-Distill candidate bundle (v1)\n')
    lines.append(f'Screened **{len(screened)}** directly-handled main-context sessions '
                 f'({len(cl["screened_ids"])} Claude + {len(cx["screened_ids"])} Codex) over the rolling window. '
                 f'**{len(cands)}** candidate learnings survived screening against the current baseline '
                 f'(CLAUDE.md + 12 guides). Nothing below is written to the corpus yet — this is for your review.\n')
    lines.append('Each candidate: the criteria it meets, the general principle proposed for the corpus, '
                 'why it is novel vs the baseline, the session evidence it rests on, and proposed placement. '
                 'Sorted by confidence within each placement group.\n')
    lines.append('---\n')

    n = 0
    for gk in sorted(groups, key=lambda k: -max((c['confidence'] for c in groups[k]), default=0)):
        cs = sorted(groups[gk], key=lambda c: -c['confidence'])
        lines.append(f'## → {gk}  ({len(cs)})\n')
        for c in cs:
            n += 1
            sid = c['session_id']
            dig = digests.get(sid, {})
            sig = dig.get('signals', {})
            crit = ' '.join(CRIT_LABEL.get(x, x) for x in c['criteria'])
            lines.append(f'### {n}. {c["title"]}  \n')
            lines.append(f'`{crit}` · confidence {c["confidence"]} · {c["_provider"]} `{sid[:8]}`\n')
            lines.append(f'**Principle (proposed):** {c["principle"]}\n')
            lines.append(f'**Novelty:** {c["novelty"]}\n')
            lines.append(f'**Evidence:** {c["evidence"]}\n')
            if dig.get('goals'):
                lines.append(f'**Session goal:** {dig["goals"][0][:200]}\n')
            if sig:
                lines.append(f'**Signals:** out-tok {sig.get("total_output_tokens",0):,} · '
                             f'corrections {sig.get("corrections",0)} · errors {sig.get("error_events",0)} · '
                             f'turns {sig.get("user_turns",0)}\n')
            lines.append('')
        lines.append('---\n')

    with open(args.out, 'w') as f:
        f.write('\n'.join(lines))

    # also a compact JSON for programmatic follow-up
    json.dump({'screened': len(screened), 'candidates': cands},
              open(args.out.replace('.md', '.json'), 'w'), ensure_ascii=False, indent=1)
    print(f'bundle: {len(cands)} candidates from {len(screened)} screened sessions -> {args.out}')
    by_crit = collections.Counter(x for c in cands for x in c['criteria'])
    print('by criterion:', {CRIT_LABEL[k]: v for k, v in by_crit.most_common()})


if __name__ == '__main__':
    main()
