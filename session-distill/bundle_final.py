#!/usr/bin/env python3
"""Render the verified, consolidated candidates into a tiered review bundle."""
import json, os, collections

HERE = os.path.dirname(os.path.abspath(__file__))
CRIT = {'high_token': '①hi-tok', 'rollback': '②rollback', 're_exploration': '③re-explore',
        'recurrent_error': '④recur-err', 'rare_high_cost': '⑤rare-hi-cost', 'quality_lever': '⑥quality'}


def norm_place(p):
    low = p.lower()
    if 'claude.md' in low or 'agents.md' in low or 'global' in low:
        return 'Global CLAUDE.md / AGENTS.md'
    for g in ['cli-multi-model-workflow', 'coding-staged-workflow', 'review-request', 'llm-capability-boundary',
              'mock-realization', 'gpt-prompting', 'claude-prompting', 'implementation-map', 'svg-visualization']:
        if g in low:
            return f'guides/{g}.md'
    return p.split('—')[0].strip()[:48]


def main():
    d = json.load(open(HERE + '/out/consolidated.json'))
    idx = json.load(open(HERE + '/out/batch_index.json'))['sessions']
    win = json.load(open(HERE + '/out/census.json'))['window']
    n_raw = len(json.load(open(HERE + '/out/candidates-all.json'))['candidates'])
    surv = [v for v in d['verdicts'] if v['verdict'] in ('novel', 'partial')]
    surv.sort(key=lambda x: (-x['strength'], x['verdict'] != 'novel'))

    L = ['# Session-Distill promotion bundle — verified shortlist\n']
    L.append(f'From **{idx["claude"] + idx["codex"]}** directly-handled main-context sessions '
             f'({idx["claude"]} Claude + {idx["codex"]} Codex, {win["days"]}-day window ending {win["end"][:10]}) → '
             f'{n_raw} raw candidates → **{d["total_clusters"]} consolidated clusters** → '
             f'**{len(surv)} survive** independent novelty verification against the current baseline '
             f'({sum(1 for v in surv if v["verdict"]=="novel")} novel, {sum(1 for v in surv if v["verdict"]=="partial")} extend existing). '
             f'{len(d["verdicts"])-len(surv)} dropped as already-covered/too-specific/weak.\n')
    L.append('`strength` = recurrence (independent sessions) × materiality (1–5). '
             '`novel` = new rule; `partial` = extend an existing rule. '
             'Placement respects the repo rule that **only situation-recognition failures belong in global CLAUDE.md; '
             'procedures/thresholds/examples belong in scoped guides.** Nothing is written to the instructions yet — this is for your selection.\n')
    L.append('---\n')

    for tier in [5, 4, 3, 2, 1]:
        items = [v for v in surv if v['strength'] == tier]
        if not items:
            continue
        L.append(f'## Strength {tier}  ({len(items)})\n')
        for v in items:
            crit = ' '.join(CRIT.get(c, c) for c in v['criteria'])
            n = len(v['supporting'])
            L.append(f'### {v["lesson"]}\n')
            L.append(f'`{v["verdict"]}` · strength {tier} · {n} session{"s" if n>1 else ""} '
                     f'`{" ".join(v["supporting"])}` · {crit}\n')
            L.append(f'**Rule:** {v["principle"]}\n')
            L.append(f'**vs baseline:** {v["baseline_ref"]}\n')
            L.append(f'**Placement:** {v["placement"]}\n')
            L.append(f'**Why (strength):** {v["rationale"]}\n')
            L.append('')
        L.append('---\n')

    # dropped, for transparency
    if d.get('dropped'):
        L.append(f'## Dropped ({len(d["dropped"])})\n')
        for x in d['dropped']:
            L.append(f'- `{x["verdict"]}` {x["lesson"]} — {x["baseline_ref"][:120]}')
        L.append('')

    open(HERE + '/out/BUNDLE.md', 'w').write('\n'.join(L))

    # placement summary
    place = collections.Counter(norm_place(v['placement']) for v in surv)
    print(f'bundle: {len(surv)} survivors → {HERE}/out/BUNDLE.md')
    print('by strength:', dict(collections.Counter(v['strength'] for v in surv)))
    print('by placement:')
    for p, c in place.most_common():
        print(f'  {c:2d}  {p}')


if __name__ == '__main__':
    main()
