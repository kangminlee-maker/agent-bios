export const meta = {
  name: 'session-distill-screen-claude',
  description: 'Screen Claude-session digests for baseline-novel, generalizable learnings',
  phases: [{ title: 'Screen', detail: 'one screener per batch' }],
}

const CRITERIA = `Value criteria (a learning is worth extracting if it fits one or more):
1 high_token — a final decision reached only after large token spend (a rule that would have shortcut it).
2 rollback — a wrong decision made then reversed/corrected (the rule that prevents the wrong turn).
3 re_exploration — repeated setup/discovery the operator redoes from scratch because no guide captures it.
4 recurrent_error — an error experienced repeatedly (the rule/recognition that avoids it).
5 rare_high_cost — a low-frequency but high-consequence event (worth a rule despite rarity).
6 quality_lever — a criterion or decision that clearly raised speed, lowered cost, or raised design quality.`

const SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['candidates', 'screened_ids'],
  properties: {
    screened_ids: { type: 'array', items: { type: 'string' }, description: 'every session_id in the batch you actually screened' },
    candidates: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['session_id', 'title', 'criteria', 'evidence', 'novelty', 'principle', 'placement', 'confidence'],
        properties: {
          session_id: { type: 'string' },
          title: { type: 'string', maxLength: 120 },
          criteria: { type: 'array', items: { enum: ['high_token', 'rollback', 're_exploration', 'recurrent_error', 'rare_high_cost', 'quality_lever'] } },
          evidence: { type: 'string', description: 'what in THIS session shows the learning — reference the goal/timeline/tools/errors in the digest, no invention' },
          novelty: { type: 'string', description: 'why it is NOT already in the baseline; name the closest existing rule/guide and say covered/partial/absent' },
          principle: { type: 'string', description: 'the general, de-anecdotalized rule to add — no names, dates, repo paths, or one-off specifics' },
          placement: { type: 'string', description: 'where it belongs: "global CLAUDE.md" or a specific guide filename, and why' },
          confidence: { type: 'number', minimum: 0, maximum: 1 },
        },
      },
    },
  },
}

// args = the batch index written by batch.py: { baseline, claude_batches, effort? }.
// The model is inherited from the session (WORKHORSE = the session model at
// 'medium'); a batch is one screener, so batch count sets the fan-out.
const baselinePath = args.baseline
const batchPaths = args.claude_batches
if (!baselinePath || !batchPaths || !batchPaths.length) throw new Error('args must carry baseline and a non-empty claude_batches (see batch.py)')
const effort = args.effort || 'medium'

phase('Screen')
const results = await parallel(batchPaths.map((bp, i) => () => agent(
  [`You screen a batch of AI-coding session digests to extract learnings worth adding to the user's global agent instructions (CLAUDE.md / guides). The user's goal: mine directly-handled main-context sessions for generalizable rules that are NOT already in the baseline.`,
   `Read the current canonical baseline at ${baselinePath} (CLAUDE.md + all guides) and this batch of session digests at ${bp}. Each digest has: the human goal(s), a deterministic timeline (U:/A: turns), tools used, error signatures, and token/correction signals — all redacted, own-machine data.`,
   CRITERIA,
   `For EACH session, decide whether it contains one or more learnings that (a) fit a criterion, (b) are generalizable beyond the incident, and (c) are genuinely absent or only partially covered in the baseline. Emit a candidate only when all three hold; a session with nothing worthy contributes zero candidates but its id still goes in screened_ids. Be strict on novelty — if the baseline already states the rule, it is not a candidate (say so by omission). Ground every candidate in the digest's actual content; do not invent decisions the digest does not show. Write each principle as a general rule with no transcript ids, names, dates, or repo-specific paths. One session may yield multiple candidates; many will yield none.`,
   `Set screened_ids to every session_id you examined in the batch (used to prove coverage).`,
  ].join('\n\n'),
  { label: `screen:${i}`, phase: 'Screen', schema: SCHEMA, effort },
)))

const ok = results.filter(Boolean)
const cands = ok.flatMap(r => r.candidates)
const screened = ok.flatMap(r => r.screened_ids)
log(`screened ${screened.length} sessions across ${ok.length}/${batchPaths.length} batches; ${cands.length} raw candidates`)
return { candidates: cands, screened_ids: screened, batches_ok: ok.length, batches_total: batchPaths.length }
