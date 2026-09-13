#!/usr/bin/env python3
"""Stage between digest.py and the screeners: the baseline blob and the batches.

Writes <out>/baseline.txt — claude/CLAUDE.md plus every claude/guides/*.md,
concatenated with a `===== path =====` header per file so a screener can name
the closest existing rule — and splits <out>/digests.json into per-provider
batch files of at most --batch-size digests. <out>/batch_index.json records the
absolute paths; the screening workflows take that index as their `args`.

The baseline is the repo's canonical instructions, not the deployed copy: promotion
targets the repo, so novelty is judged against what will ship.

Usage: batch.py [--out DIR] [--batch-size N]
"""
import argparse, glob, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=HERE + '/out')
    ap.add_argument('--batch-size', type=int, default=13)
    args = ap.parse_args()

    files = ['claude/CLAUDE.md'] + sorted(
        os.path.relpath(p, REPO) for p in glob.glob(REPO + '/claude/guides/*.md'))
    assert len(files) > 1, 'baseline would hold CLAUDE.md alone — guides missing'
    blob = ''.join(f'===== {f} =====\n' + open(os.path.join(REPO, f), encoding='utf-8').read() + '\n'
                   for f in files)
    baseline = os.path.join(args.out, 'baseline.txt')
    open(baseline, 'w', encoding='utf-8').write(blob)

    digests = json.load(open(os.path.join(args.out, 'digests.json')))
    assert digests, 'digests.json is empty — nothing to batch'
    bdir = os.path.join(args.out, 'batches')
    os.makedirs(bdir, exist_ok=True)
    for old in glob.glob(bdir + '/*.json'):
        os.remove(old)
    index = {'baseline': baseline, 'baseline_files': files, 'claude_batches': [], 'codex_batches': [],
             'sessions': {'claude': 0, 'codex': 0}}
    for provider in ('claude', 'codex'):
        rows = [d for d in digests if d['provider'] == provider]
        index['sessions'][provider] = len(rows)
        for i in range(0, len(rows), args.batch_size):
            path = os.path.join(bdir, f'{provider}-{i // args.batch_size:03d}.json')
            json.dump(rows[i:i + args.batch_size], open(path, 'w'), ensure_ascii=False, indent=1)
            index[f'{provider}_batches'].append(path)
    json.dump(index, open(os.path.join(args.out, 'batch_index.json'), 'w'), indent=1)
    print(f"baseline: {len(files)} files, {len(blob)} bytes -> {baseline}")
    for provider in ('claude', 'codex'):
        print(f"{provider}: {index['sessions'][provider]} sessions -> {len(index[f'{provider}_batches'])} batches")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
