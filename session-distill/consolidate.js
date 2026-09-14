export const meta = {
  name: 'session-distill-consolidate',
  description: 'Cluster, verify novelty, and rank screening candidates into a reviewable shortlist',
  phases: [{ title: 'Cluster' }, { title: 'Verify' }, { title: 'Match' }],
}

// args: { baseline, candidates, n, ledger: [{id, lesson}] } — n is the candidate
// count in candidates-all.json (collect.py), ledger the existing entries a
// survivor may be a recurrence of.
const baselinePath = args.baseline
const candsPath = args.candidates
const N = args.n
const ledger = args.ledger || []
if (!baselinePath || !candsPath || !N) throw new Error('args must carry baseline, candidates, and n (see collect.py)')

const CLUSTER_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['clusters'],
  properties: {
    clusters: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['lesson', 'member_indices'],
        properties: {
          lesson: { type: 'string', description: 'one-line name of the shared underlying lesson' },
          member_indices: { type: 'array', items: { type: 'integer' }, description: 'the `i` indices of candidates that express this same lesson' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['lesson', 'verdict', 'criteria', 'principle', 'baseline_ref', 'placement', 'strength', 'rationale', 'supporting'],
  properties: {
    lesson: { type: 'string' },
    verdict: { enum: ['novel', 'partial', 'already_covered', 'too_specific', 'weak'], description: 'novel/partial = add or extend; already_covered/too_specific/weak = drop with reason' },
    criteria: { type: 'array', items: { enum: ['high_token', 'rollback', 're_exploration', 'recurrent_error', 'rare_high_cost', 'quality_lever'] } },
    principle: { type: 'string', description: 'the final de-anecdotalized rule as it would read in the instructions — invariant trigger + desired behavior + boundary; no names/dates/paths/ids' },
    baseline_ref: { type: 'string', description: 'the closest existing baseline rule/guide and whether it covers/partially-covers/omits this; "none" if truly absent' },
    placement: { type: 'string', description: 'exact target: "global CLAUDE.md §Section" or "guides/<file>.md §Section"' },
    strength: { type: 'integer', minimum: 1, maximum: 5, description: '5=multi-session recurrence + high materiality + clearly general; 1=single weak anecdote' },
    rationale: { type: 'string', description: 'why this verdict/strength — cite recurrence (independent session count) and materiality' },
    supporting: { type: 'array', items: { type: 'string' }, description: 'the provider+sid tags backing this cluster' },
  },
}

phase('Cluster')
const clustered = await agent(
  [`You consolidate ${'session-distill'} screening candidates. Read the current canonical baseline at ${baselinePath} and the ${N} raw candidates at ${candsPath} (each has an index i, provider, sid, title, criteria, proposed principle, novelty claim, evidence, placement, confidence — note confidence is provider-relative and not comparable across providers).`,
   `Group candidates that express the SAME underlying lesson into one cluster (different sessions often surface the same rule). A candidate that stands alone is its own single-member cluster. Every index 0..${N - 1} must appear in exactly one cluster. Return only the clustering.`,
  ].join('\n\n'),
  { label: 'cluster', phase: 'Cluster', schema: CLUSTER_SCHEMA, effort: 'high' },
)
const clusters = clustered.clusters
log(`${clusters.length} clusters from ${N} candidates`)

phase('Verify')
const verdicts = await parallel(clusters.map((cl, i) => () => agent(
  [`You are the verification judge for one consolidated session-distill cluster. Read the current baseline at ${baselinePath} and the full candidate list at ${candsPath}.`,
   `This cluster's shared lesson: "${cl.lesson}". Its member candidate indices: ${JSON.stringify(cl.member_indices)}. Look up those members in the candidate file.`,
   'Judge the cluster strictly and independently — do NOT trust the members\' self-reported novelty or confidence. Verify against the ACTUAL baseline text: is this genuinely absent (novel), partially covered (partial), or already stated (already_covered)? Also judge whether it is too_specific (a one-off with no general form) or weak (thin evidence). Only novel/partial survive. Write the final principle as it would read in the instructions: an invariant trigger, the desired behavior, and its applicability boundary — no transcript ids, names, dates, or repo-specific paths. Set strength from recurrence (how many INDEPENDENT sessions support it) and materiality (criteria ⑤rare-high-cost and repeated ④recurrent-error/②rollback weigh higher). Name the exact placement (global CLAUDE.md section, or a specific guide + section).',
  ].join('\n\n'),
  { label: `verify:${i}`, phase: 'Verify', schema: VERDICT_SCHEMA, effort: 'high' },
)))

const ok = verdicts.filter(Boolean)
const survivors = ok.filter(v => v.verdict === 'novel' || v.verdict === 'partial').sort((a, b) => b.strength - a.strength)
log(`${ok.length} clusters verified; ${survivors.length} survive (novel/partial)`)

// Recurrence accumulates across windows only if a survivor is recognised as
// the lesson an existing ledger entry already carries. Matching is semantic,
// so an agent decides; merge-ledger.py applies the decision.
phase('Match')
const MATCH_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['matches'],
  properties: {
    matches: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false, required: ['survivor', 'ledger_id', 'reason'],
        properties: {
          survivor: { type: 'integer', description: 'index into the survivors list' },
          ledger_id: { type: ['string', 'null'], description: 'the ledger entry expressing the SAME underlying lesson, or null when none does' },
          reason: { type: 'string' },
        },
      },
    },
  },
}
let matches = []
if (survivors.length && ledger.length) {
  const m = await agent(
    ['You match this window\'s surviving session-distill lessons against the existing incubator ledger so recurrence accumulates instead of duplicating.',
     `Survivors (index, lesson, principle):\n${survivors.map((v, j) => `${j}. ${v.lesson} — ${v.principle}`).join('\n')}`,
     `Existing ledger entries (id, lesson):\n${ledger.map(e => `${e.id}: ${e.lesson}`).join('\n')}`,
     'For EVERY survivor index emit one row. ledger_id is set only when the survivor and the entry are the same underlying lesson — the same trigger and the same desired behavior — not merely the same topic; a survivor that refines, narrows, or extends an entry is still that entry. When in doubt, null: a false match hides a new lesson, a missed match only delays recurrence by one window.'].join('\n\n'),
    { label: 'match', phase: 'Match', schema: MATCH_SCHEMA, effort: 'high' },
  )
  matches = m ? m.matches : []
}
log(`${matches.filter(x => x.ledger_id).length} of ${survivors.length} survivors recur in the ledger`)
return {
  total_clusters: clusters.length,
  verdicts: ok,
  survivors,
  matches,
  dropped: ok.filter(v => v.verdict !== 'novel' && v.verdict !== 'partial')
    .map(v => ({ lesson: v.lesson, verdict: v.verdict, baseline_ref: v.baseline_ref })),
}
