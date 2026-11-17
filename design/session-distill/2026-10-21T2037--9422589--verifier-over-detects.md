---
created_at: 2026-10-21T20:37:00+09:00
head: 9422589
kind: design
supersedes: 2026-10-21T2009--cae9d22--verifier-independence.md
---

# The verifier over-detects on purpose, because a false positive costs a blank and a false negative is a leak

Lead direction of 2026-10-21, after the eighth review round. The independent verifier stands as the
superseded record states it. What changes is the shape of its detection: it is now a union of four
rules rather than three, and it is deliberately generous.

## Why generous

The two costs are not comparable. A false positive blanks one content block - measured at 2 blocks
in 142,551 on a local sample - and the block can be read again from the immutable copy. A false
negative publishes a credential into a window, an index posting and a quotable evidence record. So
where the two readings disagree, the verifier takes the one that blanks.

## The rules

On EVERY spelling of a block, the union of:

1. **the floor, unchanged** - anything `learn/redact.py` would change is a finding;
2. **an independent text-level keyed rule** - a token the floor treats as a secret's name, a `:` or
   `=` separator within a short span (any quoting, whitespace or escape characters between), then a
   value token: a finding unless that value is exactly the mask. This is what was missing. A fragment
   like `"password":"canary"` standing after a plain structure is a member of no object, carries
   no floor match and holds no home path, so the member rule and the floor both passed it. A value
   that OPENS a structure is left alone: that is the residual structural class awaiting the owner's
   judgement, and this finding's own scope is the readable scalar;
3. **the JSON member rule** - for every member of every decoded object, duplicates kept and any
   whitespace around the colon, a secret-named key's value must be exactly the mask (every leaf, for a
   structure value). Asked first, so a document's finding is named by the reading that found it;
4. **the owner's home path** in every spelling.

**Unfinished decoding is tracked per escape run**, and independently of what else the block holds: an
unrelated plain structure elsewhere used to answer for a run that starts and cannot be read. A
backslash at the end of a string, or a `\u` with too few hex digits, is `verifier-limit`. A Windows
path is not: the lenient reading drops its backslash, so the detectors read its characters.

**The projection is `r12`**, because its output can change, and `r11` is refused by name.

## The closed alternative

**Detecting only what can be located.** Every rule that asks "where does this value begin and end"
is a rule with a blind spot, and the three previous rounds each found one. A rule that asks only
"does this look like a secret standing next to a name that claims it" has no extent to get wrong.

## What it costs

Re-measured on the same local sample of 60 session files and 142,551 projected blocks: **2 blanked
blocks, 0.001%**, both for the floor detector - unchanged from r9, r10 and r11. The text-level keyed
rule and the per-run escape rule cost nothing on real transcripts, because the projection masks those
shapes in place before the verifier sees them. Re-measure before quoting this.
